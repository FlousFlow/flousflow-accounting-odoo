# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class LoanCloseWizard(models.TransientModel):
    _name = 'flousflow.account.loan.close'
    _description = 'Close Loan'

    loan_id = fields.Many2one('flousflow.account.loan', required=True, readonly=True)
    close_date = fields.Date(required=True, default=fields.Date.context_today)

    def action_close(self):
        self.ensure_one()
        loan = self.loan_id
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can close loans.'))
        if loan.state != 'running':
            raise UserError(_('Only running loans can be closed.'))
        future_moves = loan.move_ids.filtered(lambda move: move.date > self.close_date)
        posted_moves = future_moves.filtered(lambda move: move.state == 'posted')
        if posted_moves:
            posted_moves._reverse_moves(default_values_list=[{
                'date': self.close_date,
                'ref': _('Reversal of future loan entry %s', move.name),
                'flousflow_loan_id': loan.id,
            } for move in posted_moves], cancel=True)
        draft_moves = future_moves.filtered(lambda move: move.state == 'draft')
        draft_moves.button_cancel()
        draft_moves.unlink()
        loan.state = 'closed'
        return {'type': 'ir.actions.act_window', 'res_model': loan._name, 'res_id': loan.id,
                'view_mode': 'form', 'target': 'current'}
