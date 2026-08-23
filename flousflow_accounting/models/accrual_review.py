# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import ValidationError


class FlousflowAccountAccrualReview(models.TransientModel):
    _name = 'flousflow.account.accrual.review'
    _description = 'Purchase and Sales Accrual Review'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    review_type = fields.Selection(
        [('purchase', 'Goods Received Not Billed'),
         ('sale', 'Goods Delivered Not Invoiced')],
        required=True, default='purchase')
    line_ids = fields.One2many('flousflow.account.accrual.review.line', 'review_id', readonly=True)
    total_amount = fields.Monetary(compute='_compute_total')
    currency_id = fields.Many2one(related='company_id.currency_id')

    def _compute_total(self):
        for review in self:
            review.total_amount = sum(review.line_ids.mapped('amount'))

    def action_generate(self):
        self.ensure_one()
        self.line_ids = [(5, 0, 0)]
        values = self._purchase_values() if self.review_type == 'purchase' else self._sale_values()
        self.line_ids = [(0, 0, value) for value in values]
        return {'type': 'ir.actions.act_window', 'res_model': self._name,
                'res_id': self.id, 'view_mode': 'form', 'target': 'current'}

    def _purchase_values(self):
        moves = self.env['stock.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'),
            ('date', '<=', self.date_to), ('purchase_line_id', '!=', False),
            ('location_dest_id.usage', '=', 'internal'),
        ])
        result = []
        for order_line in moves.mapped('purchase_line_id'):
            received = sum(moves.filtered(lambda move: move.purchase_line_id == order_line).mapped('quantity'))
            billed = sum(order_line.invoice_lines.filtered(
                lambda line: line.parent_state == 'posted'
                and line.move_id.invoice_date <= self.date_to
                and line.move_id.move_type == 'in_invoice').mapped('quantity'))
            pending = received - billed
            if self.company_id.currency_id.is_zero(pending):
                continue
            amount = order_line.currency_id._convert(
                pending * order_line.price_unit, self.company_id.currency_id,
                self.company_id, self.date_to)
            result.append({
                'partner_id': order_line.order_id.partner_id.id,
                'product_id': order_line.product_id.id,
                'purchase_line_id': order_line.id,
                'document_name': order_line.order_id.name,
                'logistics_quantity': received, 'invoiced_quantity': billed,
                'pending_quantity': pending, 'amount': amount,
            })
        return result

    def _sale_values(self):
        moves = self.env['stock.move'].search([
            ('company_id', '=', self.company_id.id), ('state', '=', 'done'),
            ('date', '<=', self.date_to), ('sale_line_id', '!=', False),
            ('location_id.usage', '=', 'internal'),
        ])
        result = []
        for order_line in moves.mapped('sale_line_id'):
            delivered = sum(moves.filtered(lambda move: move.sale_line_id == order_line).mapped('quantity'))
            invoiced = sum(order_line.invoice_lines.filtered(
                lambda line: line.parent_state == 'posted'
                and line.move_id.invoice_date <= self.date_to
                and line.move_id.move_type == 'out_invoice').mapped('quantity'))
            pending = delivered - invoiced
            if self.company_id.currency_id.is_zero(pending):
                continue
            amount = order_line.currency_id._convert(
                pending * order_line.price_unit, self.company_id.currency_id,
                self.company_id, self.date_to)
            result.append({
                'partner_id': order_line.order_id.partner_id.id,
                'product_id': order_line.product_id.id,
                'sale_line_id': order_line.id,
                'document_name': order_line.order_id.name,
                'logistics_quantity': delivered, 'invoiced_quantity': invoiced,
                'pending_quantity': pending, 'amount': amount,
            })
        return result


class FlousflowAccountAccrualReviewLine(models.TransientModel):
    _name = 'flousflow.account.accrual.review.line'
    _description = 'Accounting Accrual Review Line'
    _order = 'document_name, id'

    review_id = fields.Many2one('flousflow.account.accrual.review', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='review_id.company_id')
    currency_id = fields.Many2one(related='review_id.currency_id')
    partner_id = fields.Many2one('res.partner', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    document_name = fields.Char(readonly=True)
    purchase_line_id = fields.Many2one('purchase.order.line', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', readonly=True)
    logistics_quantity = fields.Float(readonly=True)
    invoiced_quantity = fields.Float(readonly=True)
    pending_quantity = fields.Float(readonly=True)
    amount = fields.Monetary(readonly=True)

    def action_open_source(self):
        self.ensure_one()
        source = self.purchase_line_id.order_id or self.sale_line_id.order_id
        if not source:
            raise ValidationError(_('No source order is linked to this line.'))
        return {'type': 'ir.actions.act_window', 'res_model': source._name,
                'res_id': source.id, 'view_mode': 'form', 'target': 'current'}
