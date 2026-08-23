# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


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
        move = self.env['stock.move'].create({
            'product_id': self.product.id,
            'product_uom_qty': 5.0, 'product_uom': self.product.uom_id.id,
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

    def test_review_action_is_accounting_only_and_self_contained(self):
        action = self.env.ref('flousflow_accounting.flousflow_accrual_review_action')
        self.assertEqual(action.res_model, 'flousflow.account.accrual.review')
        self.assertEqual(action.target, 'new')
