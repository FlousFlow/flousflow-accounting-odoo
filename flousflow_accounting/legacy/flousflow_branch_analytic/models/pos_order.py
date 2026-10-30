from odoo import models


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _prepare_account_move_line_data(self, aggregate=True):
        """Tag POS revenue lines for invoices and session-closing moves."""
        lines = super()._prepare_account_move_line_data(aggregate=aggregate)
        session_account = self[:1].config_id.analytic_account_id
        for line_data in lines:
            vals = line_data.get('account.move.line', {})
            if vals.get('display_type') != 'product':
                continue
            if session_account:
                vals['analytic_distribution'] = {str(session_account.id): 100.0}
        return lines

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        account = self.config_id.analytic_account_id
        if account:
            vals['analytic_account_id'] = account.id
        return vals
