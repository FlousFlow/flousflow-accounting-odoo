# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_categ_id = fields.Many2one(
        related='product_id.categ_id', string='Product Category',
        store=True, readonly=True)
