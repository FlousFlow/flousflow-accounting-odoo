# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class FlousflowAccountBankReconcileSession(models.TransientModel):
    _name = 'flousflow.account.bank.reconcile.session'
    _description = 'Manual Bank Reconciliation Session'

    statement_line_id = fields.Many2one(
        'account.bank.statement.line', required=True, string='Bank Transaction',
        domain="[('company_id', '=', company_id), ('is_reconciled', '=', False)]",
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(related='statement_line_id.journal_id', readonly=True)
    partner_id = fields.Many2one(related='statement_line_id.partner_id', readonly=True)
    payment_ref = fields.Char(related='statement_line_id.payment_ref', readonly=True)
    date = fields.Date(related='statement_line_id.date', readonly=True)
    amount = fields.Monetary(related='statement_line_id.amount', readonly=True)
    currency_id = fields.Many2one(related='statement_line_id.currency_id', readonly=True)
    candidate_ids = fields.One2many(
        'flousflow.account.bank.reconcile.candidate', 'session_id', string='Matching Entries',
    )
    selected_amount = fields.Monetary(compute='_compute_selected_amount', currency_field='currency_id')
    remaining_amount = fields.Monetary(compute='_compute_selected_amount', currency_field='currency_id')

    @api.depends('candidate_ids.selected', 'candidate_ids.match_amount', 'amount')
    def _compute_selected_amount(self):
        for wizard in self:
            wizard.selected_amount = sum(wizard.candidate_ids.filtered('selected').mapped('match_amount'))
            wizard.remaining_amount = abs(wizard.amount) - wizard.selected_amount

    @api.onchange('statement_line_id')
    def _onchange_statement_line_id(self):
        if self.statement_line_id:
            self.company_id = self.statement_line_id.company_id
            self._refresh_candidates()

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        if self.env.context.get('active_model') == 'account.bank.statement.line' and self.env.context.get('active_id'):
            line = self.env['account.bank.statement.line'].browse(self.env.context['active_id']).exists()
            if line:
                values.update(statement_line_id=line.id, company_id=line.company_id.id)
        return values

    @staticmethod
    def _normalize_reference(value):
        return re.sub(r'[^a-z0-9]+', '', (value or '').lower())

    def _candidate_score(self, line):
        self.ensure_one()
        score = 0
        reasons = []
        bank_line = self.statement_line_id
        if bank_line.partner_id and line.partner_id == bank_line.partner_id:
            score += 40
            reasons.append(_('Same partner'))
        bank_ref = self._normalize_reference(bank_line.payment_ref)
        line_ref = self._normalize_reference(' '.join(filter(None, [line.move_name, line.ref, line.name])))
        if bank_ref and (bank_ref in line_ref or line_ref in bank_ref):
            score += 30
            reasons.append(_('Reference match'))
        residual = abs(line.amount_residual_currency if line.currency_id else line.amount_residual)
        if bank_line.currency_id.compare_amounts(residual, abs(bank_line.amount_residual or bank_line.amount)) == 0:
            score += 20
            reasons.append(_('Exact amount'))
        day_gap = abs((bank_line.date - line.date).days)
        if day_gap <= 7:
            score += 10
            reasons.append(_('Close date'))
        elif day_gap <= 30:
            score += 5
        return score, ', '.join(reasons)

    def _refresh_candidates(self):
        self.ensure_one()
        self.candidate_ids = [(5, 0, 0)]
        bank_line = self.statement_line_id
        if not bank_line or bank_line.is_reconciled:
            return
        domain = bank_line._get_default_amls_matching_domain()
        domain += [('company_id', '=', bank_line.company_id.id)]
        lines = self.env['account.move.line'].search(domain, limit=200)
        candidates = []
        for line in lines:
            residual = abs(line.amount_residual_currency if line.currency_id else line.amount_residual)
            if bank_line.amount * line.balance <= 0 or bank_line.currency_id.is_zero(residual):
                continue
            score, reason = self._candidate_score(line)
            candidates.append((score, line, residual, reason))
        candidates.sort(key=lambda item: (-item[0], abs(item[2] - abs(bank_line.amount)), item[1].date, item[1].id))
        self.candidate_ids = [(0, 0, {
            'move_line_id': line.id,
            'score': score,
            'match_reason': reason or _('Open reconcilable entry'),
            'match_amount': min(residual, abs(bank_line.amount)),
        }) for score, line, residual, reason in candidates[:80]]

    def action_refresh_candidates(self):
        self._refresh_candidates()
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manual Bank Reconciliation'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reconcile(self):
        self.ensure_one()
        bank_line = self.statement_line_id.exists()
        if not bank_line or bank_line.is_reconciled:
            raise UserError(_('The bank transaction is already reconciled or no longer exists.'))
        selected = self.candidate_ids.filtered('selected')
        if not selected:
            raise UserError(_('Select at least one journal item to reconcile.'))
        move_lines = selected.move_line_id
        if any(line.parent_state != 'posted' or line.reconciled for line in move_lines):
            raise UserError(_('One of the selected entries changed. Refresh the suggestions and try again.'))
        if any(line.company_id != bank_line.company_id for line in move_lines):
            raise ValidationError(_('All entries must belong to the bank transaction company.'))
        if len(move_lines.account_id) != 1 or not move_lines.account_id.reconcile:
            raise ValidationError(_('Selected entries must use one reconcilable account.'))
        if any(bank_line.amount * line.balance <= 0 for line in move_lines):
            raise ValidationError(_('Selected entries must have the same payment direction as the bank transaction.'))
        if bank_line.currency_id.compare_amounts(sum(selected.mapped('match_amount')), abs(bank_line.amount_residual or bank_line.amount)) > 0:
            raise ValidationError(_('The selected amount exceeds the remaining bank transaction amount.'))
        _liquidity, suspense_lines, _other = bank_line.with_context(
            skip_account_move_synchronization=True,
        )._seek_for_lines()
        if len(suspense_lines) != 1:
            raise UserError(_('The bank transaction must contain one suspense line before reconciliation.'))
        suspense_lines.with_context(skip_account_move_synchronization=True).write({
            'account_id': move_lines.account_id.id,
            'partner_id': move_lines.partner_id[:1].id or bank_line.partner_id.id,
            'name': bank_line.payment_ref or _('Bank reconciliation'),
        })
        (suspense_lines + move_lines).reconcile()
        bank_line.checked = True
        return {'type': 'ir.actions.act_window_close'}


class FlousflowAccountBankReconcileCandidate(models.TransientModel):
    _name = 'flousflow.account.bank.reconcile.candidate'
    _description = 'Bank Reconciliation Candidate'
    _order = 'score desc, id'

    session_id = fields.Many2one(
        'flousflow.account.bank.reconcile.session', required=True, ondelete='cascade',
    )
    selected = fields.Boolean()
    move_line_id = fields.Many2one('account.move.line', required=True, readonly=True)
    move_id = fields.Many2one(related='move_line_id.move_id', readonly=True)
    partner_id = fields.Many2one(related='move_line_id.partner_id', readonly=True)
    account_id = fields.Many2one(related='move_line_id.account_id', readonly=True)
    date = fields.Date(related='move_line_id.date', readonly=True)
    maturity_date = fields.Date(related='move_line_id.date_maturity', readonly=True)
    currency_id = fields.Many2one(related='move_line_id.currency_id', readonly=True)
    residual = fields.Monetary(related='move_line_id.amount_residual', currency_field='company_currency_id', readonly=True)
    company_currency_id = fields.Many2one(related='move_line_id.company_currency_id', readonly=True)
    match_amount = fields.Monetary(required=True, currency_field='session_currency_id')
    session_currency_id = fields.Many2one(related='session_id.currency_id', readonly=True)
    score = fields.Integer(readonly=True)
    match_reason = fields.Char(readonly=True)

    @api.constrains('match_amount')
    def _check_match_amount(self):
        for candidate in self:
            if candidate.match_amount <= 0:
                raise ValidationError(_('The matching amount must be positive.'))


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    def action_open_flousflow_reconciliation(self):
        self.ensure_one()
        wizard = self.env['flousflow.account.bank.reconcile.session'].create({
            'statement_line_id': self.id,
            'company_id': self.company_id.id,
        })
        wizard._refresh_candidates()
        return wizard._reopen()

    def action_flousflow_undo_reconciliation(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only an Accounting Manager can undo a bank reconciliation.'))
        self.filtered('is_reconciled').action_undo_reconciliation()
        return True
