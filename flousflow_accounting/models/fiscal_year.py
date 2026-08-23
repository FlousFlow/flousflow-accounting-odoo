# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FlousflowFiscalYear(models.Model):
    _name = 'flousflow.account.fiscal.year'
    _description = 'FlousFlow Fiscal Year'
    _order = 'date_from desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Name', required=True)
    date_from = fields.Date(
        string='Start Date', required=True,
        help='Start date, included in the fiscal year.')
    date_to = fields.Date(
        string='End Date', required=True,
        help='End date, included in the fiscal year.')
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)

    @api.constrains('date_from', 'date_to', 'company_id')
    def _check_dates(self):
        for fy in self:
            if fy.date_to < fy.date_from:
                raise ValidationError(
                    _('The ending date must not be prior to the starting date.'))
            domain = [
                ('id', '!=', fy.id),
                ('company_id', '=', fy.company_id.id),
                '|', '|',
                '&', ('date_from', '<=', fy.date_from), ('date_to', '>=', fy.date_from),
                '&', ('date_from', '<=', fy.date_to), ('date_to', '>=', fy.date_to),
                '&', ('date_from', '<=', fy.date_from), ('date_to', '>=', fy.date_to),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _('Fiscal years cannot overlap. Please correct the start '
                      'and/or end dates.'))
