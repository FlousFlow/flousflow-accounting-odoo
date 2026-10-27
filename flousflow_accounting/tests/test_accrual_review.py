# -*- coding: utf-8 -*-
from lxml import etree
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


class TestAccrualReview(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({'name': 'Accrual Vendor'})
        self.product = self.env['product.product'].create({
            'name': 'Accrual Product', 'is_storable': True,
        })
        self.vendor_location = self.env.ref('stock.stock_location_suppliers')
        self.stock_location = self.env.ref('stock.stock_location_stock')

    def test_received_not_billed_is_reported(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_qty': 5.0,
                'price_unit': 100.0,
            })],
        })
        self.assertEqual(order.order_line.product_categ_id, self.product.categ_id)
        move = self.env['stock.move'].create({
            'product_id': self.product.id,
            'product_uom_qty': 5.0, 'uom_id': self.product.uom_id.id,
            'location_id': self.vendor_location.id,
            'location_dest_id': self.stock_location.id,
            'purchase_line_id': order.order_line.id,
        })
        move._action_confirm()
        move.quantity = 5.0
        move.picked = True
        move._action_done()
        review = self.env['flousflow.account.accrual.review'].create({
            'review_type': 'purchase', 'date_to': '2026-12-31',
        })
        review.action_generate()
        line = review.line_ids.filtered(lambda item: item.purchase_line_id == order.order_line)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.logistics_quantity, 5.0, places=2)
        self.assertAlmostEqual(line.invoiced_quantity, 0.0, places=2)
        self.assertAlmostEqual(line.amount, 500.0, places=2)

    def test_purchase_order_line_exposes_enterprise_product_category(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_qty': 2.0,
                'price_unit': 25.0,
            })],
        })
        line = order.order_line
        self.assertEqual(line.product_categ_id, self.product.categ_id)
        self.assertEqual(
            self.env['purchase.order.line']._fields['product_categ_id'].related,
            'product_id.categ_id')

    def test_billed_not_received_includes_unreceived_purchase_lines(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_qty': 5.0,
                'price_unit': 100.0,
            })],
        })
        order.button_confirm()
        order.action_create_invoice()
        bill = order.invoice_ids
        bill.invoice_date = '2026-12-15'
        bill.invoice_line_ids.quantity = 5.0
        bill.action_post()
        review = self.env['flousflow.account.accrual.review'].create({
            'review_type': 'purchase_not_received', 'date_to': '2026-12-31',
        })

        review.action_generate()

        line = review.line_ids.filtered(
            lambda item: item.purchase_line_id == order.order_line)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.logistics_quantity, 0.0, places=2)
        self.assertAlmostEqual(line.invoiced_quantity, 5.0, places=2)
        self.assertAlmostEqual(line.pending_quantity, 5.0, places=2)
        self.assertAlmostEqual(line.amount, 500.0, places=2)

    def test_invoiced_not_delivered_includes_undelivered_sales_lines(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 5.0,
                'price_unit': 100.0,
            })],
        })
        order.action_confirm()
        invoice = order._create_invoices()
        invoice.invoice_date = '2026-12-15'
        invoice.action_post()
        review = self.env['flousflow.account.accrual.review'].create({
            'review_type': 'sale_not_delivered', 'date_to': '2026-12-31',
        })

        review.action_generate()

        line = review.line_ids.filtered(
            lambda item: item.sale_line_id == order.order_line)
        self.assertEqual(len(line), 1)
        self.assertAlmostEqual(line.logistics_quantity, 0.0, places=2)
        self.assertAlmostEqual(line.invoiced_quantity, 5.0, places=2)
        self.assertAlmostEqual(line.pending_quantity, 5.0, places=2)
        self.assertAlmostEqual(line.amount, 500.0, places=2)

    def test_sales_accrual_cost_fields_match_community_margin_basis(self):
        self.product.standard_price = 30.0
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_qty': 5.0,
                'price_unit': 100.0,
            })],
        })
        line = order.order_line
        self.assertAlmostEqual(line.purchase_price, 30.0, places=2)
        self.assertAlmostEqual(line.unit_cost, 30.0, places=2)
        self.assertAlmostEqual(line.total_cost, 150.0, places=2)

    def test_review_action_is_accounting_only_and_self_contained(self):
        action = self.env.ref('flousflow_accounting.flousflow_accrual_review_action')
        self.assertEqual(action.res_model, 'flousflow.account.accrual.review')
        self.assertEqual(action.target, 'new')

    def test_four_enterprise_accrual_menus_use_native_order_line_queues(self):
        expected = {
            'menu_flousflow_accounting_bills_to_receive': (
                'purchase.order.line', "[('bill_to_receive', '=', True)]", 'bill_to_receive',
                'menu_flousflow_accounting_review_purchases',
                {'currency_id', 'order_id', 'partner_id', 'product_id', 'product_qty',
                 'qty_received_at_date', 'qty_invoiced_at_date', 'uom_id', 'price_unit',
                 'amount_to_invoice_at_date'},
                'purchase.action_accrued_expense_entry_purchase_order_line'),
            'menu_flousflow_accounting_billed_not_received': (
                'purchase.order.line', "[('prepaid_expense', '=', True)]", 'billed_not_received',
                'menu_flousflow_accounting_review_purchases',
                {'currency_id', 'order_id', 'partner_id', 'product_id', 'product_qty',
                 'qty_received_at_date', 'qty_invoiced_at_date', 'uom_id', 'price_unit',
                 'amount_to_invoice_at_date'},
                'purchase.action_accrued_expense_entry_purchase_order_line'),
            'menu_flousflow_accounting_invoices_to_be_issued': (
                'sale.order.line', "[('invoice_to_be_issued', '=', True)]", 'invoice_to_be_issued',
                'menu_flousflow_accounting_review_sales',
                {'currency_id', 'order_id', 'order_partner_id', 'name', 'salesman_id',
                 'product_uom_qty', 'qty_delivered_at_date', 'qty_invoiced_at_date',
                 'product_uom_id', 'price_unit', 'amount_to_invoice_at_date',
                 'unit_cost', 'total_cost'},
                'sale.action_accrued_revenue_entry_sale_order_line'),
            'menu_flousflow_accounting_invoiced_not_delivered': (
                'sale.order.line', "[('deferred_revenue', '=', True)]", 'invoiced_not_delivered',
                'menu_flousflow_accounting_review_sales',
                {'currency_id', 'order_id', 'order_partner_id', 'name', 'salesman_id',
                 'product_uom_qty', 'qty_delivered_at_date', 'qty_invoiced_at_date',
                 'product_uom_id', 'price_unit', 'amount_to_invoice_at_date',
                 'unit_cost', 'total_cost'},
                'sale.action_accrued_revenue_entry_sale_order_line'),
        }
        for menu_xmlid, (model, domain, accrual_type, parent_xmlid,
                         expected_fields, server_action_xmlid) in expected.items():
            menu = self.env.ref('flousflow_accounting.%s' % menu_xmlid)
            self.assertEqual(
                menu.parent_id,
                self.env.ref('flousflow_accounting.%s' % parent_xmlid))
            action = menu.action
            self.assertEqual(action.res_model, model)
            self.assertEqual(action.view_mode, 'list')
            self.assertEqual(action.domain, domain)
            self.assertEqual(action.view_id.model, model)
            arch = etree.fromstring(action.view_id.arch_db.encode())
            self.assertEqual(set(arch.xpath('.//field/@name')), expected_fields)
            button = arch.xpath('.//header/button')
            self.assertEqual(len(button), 1)
            self.assertEqual(
                button[0].get('name'),
                str(self.env.ref(server_action_xmlid).id))
            context = safe_eval(menu.action.context or '{}')
            self.assertEqual(context['accrual_type'], accrual_type)
            self.assertEqual(context.get('search_default_last_365_days'), 1)
