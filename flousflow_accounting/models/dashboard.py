# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models


class FlousflowDashboard(models.TransientModel):
    _name = 'flousflow.account.dashboard'
    _description = 'FlousFlow Accounting Dashboard'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')

    total_bank = fields.Monetary(string='Bank & Cash', currency_field='currency_id')
    total_receivable = fields.Monetary(string='Receivable', currency_field='currency_id')
    total_payable = fields.Monetary(string='Payable', currency_field='currency_id')
    total_income = fields.Monetary(string='Income (YTD)', currency_field='currency_id')
    total_expense = fields.Monetary(string='Expenses (YTD)', currency_field='currency_id')
    net_profit = fields.Monetary(string='Net Profit (YTD)', currency_field='currency_id')

    open_invoices_count = fields.Integer(string='Open Invoices')
    open_bills_count = fields.Integer(string='Open Bills')
    overdue_invoices_count = fields.Integer(string='Overdue Invoices')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company = self.env.company
        res.update(self._compute_metrics(company))
        res['company_id'] = company.id
        return res

    def _read_group_sum(self, domain, aggregate):
        groups = self.env['account.move.line']._read_group(
            domain, aggregates=[aggregate])
        if groups and groups[0]:
            return groups[0][0] or 0.0
        return 0.0

    def _compute_metrics(self, company):
        aml = self.env['account.move.line']
        today = fields.Date.today()
        year_start = today.replace(month=1, day=1)
        base = [('company_id', '=', company.id), ('parent_state', '=', 'posted')]
        open_domain = base + [('full_reconcile_id', '=', False)]

        total_bank = self._read_group_sum(
            open_domain + [('account_id.account_type', '=', 'asset_cash')],
            'amount_residual:sum')
        total_receivable = self._read_group_sum(
            open_domain + [('account_id.account_type', '=', 'asset_receivable')],
            'amount_residual:sum')
        total_payable = -self._read_group_sum(
            open_domain + [('account_id.account_type', '=', 'liability_payable')],
            'amount_residual:sum')

        def period_balance(types):
            groups = aml._read_group(
                base + [
                    ('account_id.account_type', 'in', types),
                    ('date', '>=', year_start),
                    ('date', '<=', today),
                ],
                aggregates=['debit:sum', 'credit:sum'])
            if groups and groups[0]:
                debit, credit = groups[0]
                return (credit or 0.0) - (debit or 0.0)
            return 0.0

        total_income = period_balance(['income', 'income_other'])
        total_expense = -period_balance(
            ['expense', 'expense_depreciation', 'expense_direct_cost'])
        net_profit = total_income - total_expense

        move = self.env['account.move']
        open_invoices_count = move.search_count(
            [('company_id', '=', company.id),
             ('move_type', 'in', ('out_invoice', 'out_refund')),
             ('state', '=', 'posted'),
             ('payment_state', 'in', ('not_paid', 'partial'))])
        open_bills_count = move.search_count(
            [('company_id', '=', company.id),
             ('move_type', 'in', ('in_invoice', 'in_refund')),
             ('state', '=', 'posted'),
             ('payment_state', 'in', ('not_paid', 'partial'))])
        overdue_invoices_count = move.search_count(
            [('company_id', '=', company.id),
             ('move_type', 'in', ('out_invoice', 'out_refund')),
             ('state', '=', 'posted'),
             ('payment_state', 'in', ('not_paid', 'partial')),
             ('invoice_date_due', '<', today)])

        return {
            'total_bank': total_bank,
            'total_receivable': total_receivable,
            'total_payable': total_payable,
            'total_income': total_income,
            'total_expense': total_expense,
            'net_profit': net_profit,
            'open_invoices_count': open_invoices_count,
            'open_bills_count': open_bills_count,
            'overdue_invoices_count': overdue_invoices_count,
        }

    def action_refresh(self):
        self.ensure_one()
        self.write(self._compute_metrics(self.company_id))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
