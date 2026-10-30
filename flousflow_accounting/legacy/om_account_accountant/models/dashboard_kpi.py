import json

from odoo import api, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def get_account_dashboard_kpis(self):
        cards = super().get_account_dashboard_kpis()
        # Keep each Community tile pointed at the same report destination as Enterprise.
        # The Enterprise account_reports action IDs are not installed on Community.
        report_actions = {
            'invoices': 'account.action_account_invoice_report_all',
            'expenses': 'flousflow_accounting.apr__action_interactive_profit_and_loss',
            'receivable': 'flousflow_accounting.apr__action_interactive_aged_receivable',
            'payable': 'flousflow_accounting.apr__action_interactive_aged_payable',
        }
        for card in cards:
            action_xmlid = report_actions.get(card['id'])
            if action_xmlid:
                action = self.env.ref(action_xmlid, raise_if_not_found=False)
                if action:
                    card['action_id'] = action.id
        return cards


class ResUsers(models.Model):
    _inherit = 'res.users'

    account_dashboard_kpi_order = fields.Char(default='[]', copy=False)

    @api.model
    def get_account_dashboard_kpi_order(self):
        try:
            order = json.loads(self.env.user.sudo().account_dashboard_kpi_order or '[]')
        except (TypeError, ValueError):
            return []
        allowed = {'invoices', 'expenses', 'cash', 'receivable', 'payable', 'invoice_layout'}
        return [item for item in order if item in allowed]

    @api.model
    def save_account_dashboard_kpi_order(self, order):
        allowed = {'invoices', 'expenses', 'cash', 'receivable', 'payable', 'invoice_layout'}
        if not isinstance(order, list):
            return False
        cleaned = list(dict.fromkeys(item for item in order if isinstance(item, str) and item in allowed))
        self.env.user.sudo().write({'account_dashboard_kpi_order': json.dumps(cleaned)})
        return True
