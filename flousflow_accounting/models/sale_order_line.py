# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    unit_cost = fields.Float(
        string='Cost by Unit', compute='_compute_enterprise_cost_fields', store=True,
        groups='base.group_user')
    total_cost = fields.Float(
        string='Total Cost', compute='_compute_enterprise_cost_fields', store=True,
        groups='base.group_user')

    @api.depends('purchase_price', 'product_uom_qty', 'qty_delivered')
    def _compute_enterprise_cost_fields(self):
        for line in self:
            line.unit_cost = line.purchase_price
            line.total_cost = line.purchase_price * line._get_product_qty()
