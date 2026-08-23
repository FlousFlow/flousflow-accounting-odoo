# -*- coding: utf-8 -*-
from odoo import fields, models


class FlousflowAccountLockDate(models.TransientModel):
    _name = 'flousflow.account.lock.date'
    _description = 'Accounting Lock Dates'

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    fiscalyear_lock_date = fields.Date(string='All Users Lock Date')
    tax_lock_date = fields.Date(string='Tax Return Lock Date')
    sale_lock_date = fields.Date(string='Sales Lock Date')
    purchase_lock_date = fields.Date(string='Purchases Lock Date')
    hard_lock_date = fields.Date(string='Hard Lock Date')

    def action_apply(self):
        self.ensure_one()
        self.company_id.write({
            'fiscalyear_lock_date': self.fiscalyear_lock_date,
            'tax_lock_date': self.tax_lock_date,
            'sale_lock_date': self.sale_lock_date,
            'purchase_lock_date': self.purchase_lock_date,
            'hard_lock_date': self.hard_lock_date,
        })
        return {'type': 'ir.actions.act_window_close'}
