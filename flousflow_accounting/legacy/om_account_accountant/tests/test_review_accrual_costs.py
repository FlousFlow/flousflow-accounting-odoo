from datetime import timedelta

from lxml import etree
from odoo import Command, fields
from odoo.tools.safe_eval import safe_eval
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestReviewAccrualCosts(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.uom = cls.env.ref("uom.product_uom_unit")
        cls.product = cls.env["product.product"].with_company(cls.env.company).create({
            "name": "Review accrual cost test product",
            "type": "service",
            "invoice_policy": "delivery",
            "uom_id": cls.uom.id,
            "standard_price": 125.0,
            "list_price": 400.0,
            "taxes_id": [Command.clear()],
        })

    def _create_order_line(self, invoice_policy="delivery", quantity=5.0):
        self.product.invoice_policy = invoice_policy
        order = self.env["sale.order"].sudo().create({
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": quantity,
                "price_unit": 400.0,
                "tax_ids": [Command.clear()],
            })],
        })
        order.action_confirm()
        return order, order.order_line

    def test_invoice_to_be_issued_cost_uses_delivered_quantity(self):
        _order, line = self._create_order_line()
        line.qty_delivered = 3.0

        report_line = line.with_context(
            accrual_entry_date=fields.Date.to_string(fields.Date.today()),
        )

        self.assertEqual(report_line.qty_delivered_at_date, 3.0)
        self.assertAlmostEqual(report_line.review_accrual_unit_cost, 125.0)
        self.assertAlmostEqual(report_line.review_accrual_delivered_total_cost, 375.0)

        grouped_rows = self.env["sale.order.line"].sudo().with_context(
            accrual_entry_date=fields.Date.to_string(fields.Date.today()),
        ).formatted_read_group(
            [("id", "=", line.id)],
            ["order_partner_id"],
            ["review_accrual_delivered_total_cost:sum"],
        )
        self.assertEqual(grouped_rows[0]["review_accrual_delivered_total_cost:sum"], 375.0)

    def test_invoiced_not_delivered_cost_uses_invoiced_quantity(self):
        _order, line = self._create_order_line(invoice_policy="order", quantity=2.0)
        invoice = line.order_id._create_invoices()
        invoice.action_post()

        report_line = line.with_context(
            accrual_entry_date=fields.Date.to_string(fields.Date.today()),
        )

        self.assertEqual(report_line.qty_invoiced_at_date, 2.0)
        self.assertAlmostEqual(report_line.review_accrual_unit_cost, 125.0)
        self.assertAlmostEqual(report_line.review_accrual_invoiced_total_cost, 250.0)

        yesterday = fields.Date.to_string(fields.Date.today() - timedelta(days=1))
        historical_line = line.with_context(accrual_entry_date=yesterday)
        self.assertEqual(historical_line.qty_invoiced_at_date, 0.0)
        self.assertAlmostEqual(historical_line.review_accrual_invoiced_total_cost, 0.0)
        self.assertFalse(
            self.env["sale.order.line"].with_context(accrual_entry_date=yesterday).search(
                [("id", "=", line.id), ("deferred_revenue", "in", [True])]
            )
        )

    def test_review_unit_cost_uses_the_order_line_company(self):
        company_data = self.setup_other_company(name="review_cost_company")
        company = company_data["company"]
        product = self.env["product.product"].sudo().create({
            "name": "Company-specific review cost product",
            "type": "service",
            "invoice_policy": "delivery",
            "uom_id": self.uom.id,
            "standard_price": 125.0,
            "list_price": 400.0,
            "taxes_id": [Command.clear()],
        })
        product.with_company(company).standard_price = 225.0
        pricelist = self.env["product.pricelist"].with_company(company).search([
            ("currency_id", "=", company.currency_id.id),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ], limit=1)
        order = self.env["sale.order"].sudo().create({
            "company_id": company.id,
            "partner_id": self.partner_a.id,
            "pricelist_id": pricelist.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 2.0,
                "price_unit": 400.0,
                "tax_ids": [Command.clear()],
            })],
        })
        order.with_company(company).action_confirm()

        line = order.order_line
        self.assertEqual(line.company_id, company)
        self.assertAlmostEqual(line.review_accrual_unit_cost, 225.0)

    def test_purchase_review_search_and_group_sums_use_as_of_context(self):
        product = self.env["product.product"].sudo().with_company(self.env.company).create({
            "name": "Purchase review accrual test product",
            "type": "service",
            "uom_id": self.uom.id,
            "standard_price": 100.0,
            "list_price": 150.0,
            "taxes_id": [Command.clear()],
            "supplier_taxes_id": [Command.clear()],
        })
        order = self.env["purchase.order"].sudo().create({
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_qty": 5.0,
                "price_unit": 100.0,
                "tax_ids": [Command.clear()],
            })],
        })
        order.button_confirm()
        line = order.order_line
        line.qty_received_manual = 5.0
        order.action_create_invoice()
        invoice = order.invoice_ids
        invoice.invoice_date = fields.Date.today()
        invoice.action_post()
        self.assertEqual(line.qty_invoiced, 5.0, invoice.invoice_line_ids.mapped("quantity"))

        today = fields.Date.to_string(fields.Date.today())
        yesterday = fields.Date.to_string(fields.Date.today() - timedelta(days=1))
        purchase_lines = self.env["purchase.order.line"]
        self.assertIn(
            line,
            purchase_lines.with_context(accrual_entry_date=yesterday)._get_accrual_line_ids(
                "bill_to_receive"
            ),
        )
        self.assertNotIn(
            line,
            purchase_lines.with_context(accrual_entry_date=today)._get_accrual_line_ids(
                "bill_to_receive"
            ),
        )

        historical_line = line.with_context(accrual_entry_date=yesterday)
        self.assertEqual(historical_line.qty_received_at_date, 5.0)
        self.assertEqual(historical_line.qty_invoiced_at_date, 0.0)
        grouped_rows = purchase_lines.with_context(
            accrual_entry_date=yesterday,
        ).formatted_read_group(
            [("id", "=", line.id)],
            ["partner_id"],
            ["qty_received_at_date:sum", "qty_invoiced_at_date:sum"],
        )
        self.assertEqual(grouped_rows[0]["qty_received_at_date:sum"], 5.0)
        self.assertEqual(grouped_rows[0]["qty_invoiced_at_date:sum"], 0.0)

    def test_purchase_unit_price_group_uses_average(self):
        product = self.env["product.product"].sudo().with_company(self.env.company).create({
            "name": "Purchase review average price test product",
            "type": "service",
            "uom_id": self.uom.id,
            "standard_price": 50.0,
            "list_price": 150.0,
            "taxes_id": [Command.clear()],
            "supplier_taxes_id": [Command.clear()],
        })
        lines = self.env["purchase.order.line"]
        for unit_price, quantity in ((132.50, 20.0), (89.0, 5.0)):
            order = self.env["purchase.order"].sudo().create({
                "partner_id": self.partner_a.id,
                "order_line": [Command.create({
                    "product_id": product.id,
                    "product_qty": quantity,
                    "price_unit": unit_price,
                    "tax_ids": [Command.clear()],
                })],
            })
            order.button_confirm()
            lines |= order.order_line

        grouped_rows = lines.formatted_read_group(
            [("id", "in", lines.ids)],
            ["partner_id"],
            ["price_unit:avg"],
        )
        self.assertAlmostEqual(grouped_rows[0]["price_unit:avg"], 110.75)

    def test_sale_unit_price_group_uses_sum(self):
        order = self.env["sale.order"].sudo().create({
            "partner_id": self.partner_a.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "price_unit": unit_price,
                "tax_ids": [Command.clear()],
            }) for unit_price in (14920.0, 5222.0, 3730.0)],
        })
        order.action_confirm()

        grouped_rows = order.order_line.formatted_read_group(
            [("id", "in", order.order_line.ids)],
            ["order_partner_id"],
            ["price_unit:sum"],
        )
        self.assertAlmostEqual(grouped_rows[0]["price_unit:sum"], 23872.0)

    def test_sales_review_cost_columns_match_enterprise_grouping(self):
        delivered_view = self.env.ref(
            "flousflow_accounting.acc__view_sale_invoice_to_be_issued_list"
        )
        delivered_arch = etree.fromstring(delivered_view.arch_db)
        unit_cost = delivered_arch.xpath(
            "//field[@name='review_accrual_unit_cost']"
        )[0]
        total_cost = delivered_arch.xpath(
            "//field[@name='review_accrual_delivered_total_cost']"
        )[0]
        self.assertEqual(unit_cost.get("sum"), "Unit Cost")
        self.assertIsNone(total_cost.get("sum"))

        invoiced_view = self.env.ref(
            "flousflow_accounting.acc__view_sale_invoiced_not_delivered_list"
        )
        invoiced_arch = etree.fromstring(invoiced_view.arch_db)
        invoiced_total_cost = invoiced_arch.xpath(
            "//field[@name='review_accrual_invoiced_total_cost']"
        )[0]
        self.assertIsNone(invoiced_total_cost.get("sum"))

    def test_review_accrual_actions_default_to_enterprise_grouping_and_period(self):
        purchase_action = self.env.ref(
            "flousflow_accounting.acc__action_purchase_bill_to_receive"
        )
        purchase_context = safe_eval(purchase_action.context)
        self.assertEqual(purchase_context["search_default_order_date_last_year"], 1)
        self.assertEqual(purchase_context["search_default_groupby_supplier"], 1)

        sale_action = self.env.ref("flousflow_accounting.acc__action_sale_invoice_to_be_issued")
        sale_context = safe_eval(sale_action.context)
        self.assertEqual(sale_context["search_default_review_order_date_last_year"], 1)
        self.assertEqual(sale_context["search_default_review_groupby_customer"], 1)

    def test_review_accrual_reports_use_their_own_list_views(self):
        report_mappings = (
            (
                "acc__action_purchase_bill_to_receive_list",
                "acc__action_purchase_bill_to_receive",
                "acc__view_purchase_bill_to_receive_list",
                "avg",
            ),
            (
                "acc__action_purchase_billed_not_received_list",
                "acc__action_purchase_billed_not_received",
                "acc__view_purchase_billed_not_received_list",
                "avg",
            ),
            (
                "acc__action_sale_invoice_to_be_issued_list",
                "acc__action_sale_invoice_to_be_issued",
                "acc__view_sale_invoice_to_be_issued_list",
                "sum",
            ),
            (
                "acc__action_sale_invoiced_not_delivered_list",
                "acc__action_sale_invoiced_not_delivered",
                "acc__view_sale_invoiced_not_delivered_list",
                "sum",
            ),
        )
        for mapping_xmlid, action_xmlid, view_xmlid, unit_price_aggregator in report_mappings:
            with self.subTest(mapping=mapping_xmlid):
                mapping = self.env.ref(f"flousflow_accounting.{mapping_xmlid}")
                self.assertEqual(
                    mapping.act_window_id,
                    self.env.ref(f"flousflow_accounting.{action_xmlid}"),
                )
                self.assertEqual(
                    mapping.view_id,
                    self.env.ref(f"flousflow_accounting.{view_xmlid}"),
                )
                combined_arch = etree.fromstring(mapping.view_id.get_combined_arch().encode())
                unit_price = combined_arch.xpath(".//field[@name='price_unit']")
                self.assertEqual(len(unit_price), 1)
                self.assertEqual(
                    unit_price[0].get(unit_price_aggregator),
                    "Average Unit Price" if unit_price_aggregator == "avg" else "Total Unit Price",
                )


@tagged("post_install", "-at_install")
class TestReviewAccrualDatePicker(HttpCase):

    def test_review_accrual_date_picker(self):
        action = self.env.ref("flousflow_accounting.acc__action_purchase_bill_to_receive")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_review_accrual_date_picker",
            login="admin",
        )
