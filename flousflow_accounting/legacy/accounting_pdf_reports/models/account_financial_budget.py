from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AccountFinancialBudget(models.Model):
    _name = 'account.financial.budget'
    _description = 'Financial Report Budget'
    _order = 'date_from desc, name'
    _check_company_auto = True

    name = fields.Char(required=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    line_ids = fields.One2many('account.financial.budget.line', 'budget_id', copy=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_from > budget.date_to:
                raise ValidationError(_('The budget start date must be on or before its end date.'))


class AccountFinancialBudgetLine(models.Model):
    _name = 'account.financial.budget.line'
    _description = 'Financial Report Budget Line'
    _check_company_auto = True
    _order = 'account_id'

    budget_id = fields.Many2one('account.financial.budget', required=True, ondelete='cascade', index=True,
                                 check_company=True)
    account_id = fields.Many2one('account.account', required=True, check_company=True, index=True)
    company_id = fields.Many2one(related='budget_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='budget_id.currency_id', readonly=True)
    planned_amount = fields.Monetary(required=True, default=0.0, currency_field='currency_id')

    _budget_account_unique = models.Constraint(
        'UNIQUE(budget_id, account_id)', 'A budget can only have one line per account.'
    )

    @api.constrains('account_id', 'budget_id')
    def _check_account_company(self):
        for line in self:
            if line.account_id.company_ids and line.budget_id.company_id not in line.account_id.company_ids:
                raise ValidationError(_('The account must belong to the budget company.'))
