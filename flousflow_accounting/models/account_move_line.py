# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    invoice_origin = fields.Char(
        related='move_id.invoice_origin', string='Origin', readonly=True)
    move_attachment_ids = fields.One2many(
        related='move_id.attachment_ids', string='Move Attachments', readonly=True)
    asset_ids = fields.One2many(
        'flousflow.account.asset', 'source_move_line_id',
        string='Related Assets', readonly=True)
