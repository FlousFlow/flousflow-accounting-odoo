from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestSalespersonCreditLimit(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.salesperson_credit_limit_block = True
        cls.salesperson = new_test_user(
            cls.env,
            login="salesperson_credit_limit_user",
            groups="base.group_user,sales_team.group_sale_salesman",
            company_id=cls.company.id,
        )
        cls.product = cls.env["product.product"].create({
            "name": "Salesperson credit limit product",
            "type": "service",
            "list_price": 100.0,
            "taxes_id": [Command.clear()],
        })
        cls.limit = cls.env["salesperson.credit.limit"].create({
            "salesperson_id": cls.salesperson.id,
            "company_id": cls.company.id,
            "credit_limit": 1000.0,
        })

    def _order(self, amount):
        return self.env["sale.order"].sudo().create({
            "partner_id": self.partner_a.id,
            "user_id": self.salesperson.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": amount / 100.0,
                "price_unit": 100.0,
                "tax_ids": [Command.clear()],
            })],
        })

    def test_order_over_salesperson_limit_is_refused(self):
        order = self._order(1200.0)
        with self.assertRaisesRegex(UserError, "credit limit"):
            order.with_user(self.salesperson).action_confirm()
        self.assertEqual(order.state, "draft")

    def test_confirmed_uninvoiced_order_reserves_limit(self):
        order = self._order(600.0)
        order.with_user(self.salesperson).action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertAlmostEqual(self.limit.used_credit, 600.0, places=2)
        self.assertAlmostEqual(self.limit.available_credit, 400.0, places=2)

    def test_zero_limit_means_unlimited(self):
        self.limit.credit_limit = 0.0
        order = self._order(5000.0)
        order.with_user(self.salesperson).action_confirm()
        self.assertEqual(order.state, "sale")
