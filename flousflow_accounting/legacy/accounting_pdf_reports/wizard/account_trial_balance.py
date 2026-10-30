from odoo import fields, models, api


class AccountBalanceReport(models.TransientModel):
    _name = 'account.balance.report'
    _inherit = "account.common.account.report"
    _description = 'Trial Balance Report'

    cash_basis = fields.Boolean(string='Cash Basis Method')

    journal_ids = fields.Many2many(
        'account.journal', 'account_balance_report_journal_rel',
        'account_id', 'journal_id',
        string='Journals', required=True, default=[]
    )
    analytic_account_ids = fields.Many2many(
        'account.analytic.account',
        'account_trial_balance_analytic_rel', string='Analytic Accounts'
    )

    def _build_contexts(self, data):
        result = super()._build_contexts(data)
        result['tax_exigible'] = bool(self.cash_basis)
        return result

    def _get_report_data(self, data):
        data = self.pre_print_report(data)
        records = self.env[data['model']].browse(data.get('ids', []))
        return records, data

    def _print_report(self, data):
        records, data = self._get_report_data(data)
        return self.env.ref('flousflow_accounting.apr__action_report_trial_balance').report_action(records, data=data)
