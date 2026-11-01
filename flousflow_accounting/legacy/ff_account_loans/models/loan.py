# -*- coding: utf-8 -*-
import calendar
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError, ValidationError


class FlousflowAccountLoan(models.Model):
    _name = 'flousflow.account.loan'
    _description = 'Accounting Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, default=lambda self: _('New'), tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company,
                                 index=True, tracking=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    asset_group_id = fields.Many2one(
        'account.asset.category', string='Asset Group', check_company=True,
        help='Optional asset group used to classify the financed asset.')
    amount_borrowed = fields.Monetary(required=True, tracking=True)
    interest = fields.Monetary(required=True, default=0.0, tracking=True,
                               help='Total interest across the amortization schedule.')
    amount_due = fields.Monetary(compute='_compute_amounts', store=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    duration = fields.Integer(required=True, default=12, tracking=True,
                              help='Number of monthly amortization installments.')
    end_date = fields.Date(compute='_compute_end_date', store=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('running', 'Running'), ('closed', 'Closed'), ('cancelled', 'Cancelled')
    ], default='draft', required=True, copy=False, tracking=True, index=True)
    line_ids = fields.One2many('flousflow.account.loan.line', 'loan_id', string='Amortization Schedule',
                               copy=True)
    long_term_account_id = fields.Many2one(
        'account.account', string='Long Term Account', required=True, check_company=True,
        domain="[('account_type', 'in', ('liability_non_current', 'liability_current'))]")
    short_term_account_id = fields.Many2one(
        'account.account', string='Short Term Account', required=True, check_company=True,
        domain="[('account_type', 'in', ('liability_current', 'liability_non_current'))]")
    expense_account_id = fields.Many2one(
        'account.account', string='Expense Account', required=True, check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))]")
    journal_id = fields.Many2one('account.journal', string='Journal', required=True,
                                 check_company=True, domain="[('type', '=', 'general')]")
    skip_until_date = fields.Date(string='Transfer to First Amortization Schedule')
    move_ids = fields.One2many('account.move', 'flousflow_loan_id', string='Accounting Entries', readonly=True)
    line_count = fields.Integer(compute='_compute_line_count')

    @api.depends('amount_borrowed', 'interest')
    def _compute_amounts(self):
        for loan in self:
            loan.amount_due = loan.amount_borrowed + loan.interest

    @api.depends('line_ids')
    def _compute_line_count(self):
        for loan in self:
            loan.line_count = len(loan.line_ids)

    @api.depends('date', 'duration')
    def _compute_end_date(self):
        for loan in self:
            loan.end_date = loan.date + relativedelta(months=loan.duration) if loan.date and loan.duration else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'flousflow.account.loan') or _('New')
        return super().create(vals_list)

    @api.constrains('amount_borrowed', 'duration')
    def _check_amounts(self):
        for loan in self:
            if loan.amount_borrowed <= 0:
                raise ValidationError(_('The borrowed amount must be greater than zero.'))
            if loan.duration <= 0:
                raise ValidationError(_('The duration must be at least one month.'))

    @api.constrains('date', 'skip_until_date')
    def _check_dates(self):
        for loan in self:
            if loan.skip_until_date and loan.skip_until_date < loan.date:
                raise ValidationError(_('The transfer date cannot be earlier than the loan date.'))

    @api.constrains('long_term_account_id', 'short_term_account_id', 'expense_account_id')
    def _check_accounts(self):
        for loan in self:
            accounts = [loan.long_term_account_id, loan.short_term_account_id, loan.expense_account_id]
            if len(set(accounts)) != len(accounts):
                raise ValidationError(_('Long-term, short-term, and expense accounts must be different.'))

    def _month_end(self, value):
        last_day = calendar.monthrange(value.year, value.month)[1]
        return value.replace(day=min(value.day, last_day))

    def _schedule_values(self):
        self.ensure_one()
        principal_piece = self.amount_borrowed / self.duration
        interest_piece = self.interest / self.duration
        principal_left = self.amount_borrowed
        principal_sum = interest_sum = 0.0
        values = []
        start_date = self.skip_until_date or self.date
        for number in range(1, self.duration + 1):
            principal = principal_left if number == self.duration else self.currency_id.round(principal_piece)
            interest = self.currency_id.round(interest_piece)
            principal = min(principal, principal_left)
            principal_left = self.currency_id.round(principal_left - principal)
            principal_sum += principal
            interest_sum += interest
            values.append({
                'sequence': number,
                'date': self._month_end(start_date + relativedelta(months=number)),
                'principal_amount': principal,
                'interest_amount': interest,
            })
        # Put currency rounding residue on the last line so the schedule always reconciles.
        if values:
            values[-1]['principal_amount'] += self.currency_id.round(self.amount_borrowed - principal_sum)
            values[-1]['interest_amount'] += self.currency_id.round(self.interest - interest_sum)
        return values

    def action_compute(self):
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_('Only draft loans can compute a schedule.'))
            loan.line_ids.unlink()
            loan.line_ids = [Command.create(vals) for vals in loan._schedule_values()]
        return True

    def _check_schedule(self):
        self.ensure_one()
        if len(self.line_ids) != self.duration:
            raise UserError(_('The number of schedule lines must match the loan duration.'))
        principal_total = sum(self.line_ids.mapped('principal_amount'))
        interest_total = sum(self.line_ids.mapped('interest_amount'))
        if not self.currency_id.is_zero(principal_total - self.amount_borrowed):
            raise UserError(_('The schedule principal total must equal the borrowed amount.'))
        if not self.currency_id.is_zero(interest_total - self.interest):
            raise UserError(_('The schedule interest total must equal the loan interest.'))
        if any(line.principal_amount < 0 or line.interest_amount < 0 for line in self.line_ids):
            raise UserError(_('Schedule principal and interest amounts cannot be negative.'))
        if self.line_ids.sorted('date') != self.line_ids:
            raise UserError(_('Schedule dates must be in chronological order.'))
        if len(self.line_ids.mapped('date')) != len(self.line_ids):
            raise UserError(_('Schedule dates must be unique.'))

    def _prepare_move(self, line, move_date, ref, move_lines):
        return {
            'move_type': 'entry', 'date': move_date, 'journal_id': self.journal_id.id,
            'company_id': self.company_id.id, 'ref': ref, 'auto_post': 'at_date',
            'flousflow_loan_id': self.id, 'flousflow_loan_line_id': line.id,
            'line_ids': [Command.create(vals) for vals in move_lines],
        }

    def action_confirm(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can confirm loans.'))
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_('Only draft loans can be confirmed.'))
            loan._check_schedule()
            for line in loan.line_ids.sorted('date'):
                # Reclassify the next 12 months of principal from long-term to short-term.
                next_year = loan.line_ids.filtered(
                    lambda item: line.date <= item.date < line.date + relativedelta(months=12))
                reclass_amount = sum(next_year.mapped('principal_amount'))
                reclass_vals = loan._prepare_move(line, line.date,
                    _('%s - Current portion reclassification', loan.name), [
                        {'name': loan.name, 'account_id': loan.long_term_account_id.id,
                         'debit': reclass_amount, 'analytic_distribution': loan.analytic_distribution},
                        {'name': loan.name, 'account_id': loan.short_term_account_id.id,
                         'credit': reclass_amount, 'analytic_distribution': loan.analytic_distribution},
                    ])
                reclass_move = self.env['account.move'].with_company(loan.company_id).create(reclass_vals)
                reverse_vals = reclass_move._reverse_moves(default_values_list=[{
                    'date': line.date + timedelta(days=1),
                    'ref': _('%s - Reverse current portion reclassification', loan.name),
                    'auto_post': 'at_date',
                    'flousflow_loan_id': loan.id,
                    'flousflow_loan_line_id': line.id,
                }], cancel=False)
                line.write({'reclassification_move_id': reclass_move.id,
                            'reclassification_reversal_id': reverse_vals.id})

                payment_vals = loan._prepare_move(line, line.date,
                    _('%s - Installment %s', loan.name, line.sequence), [
                        {'name': _('%s - Principal', loan.name),
                         # The current portion was reclassified immediately before
                         # payment, so amortization must reduce the short-term liability.
                         'account_id': loan.short_term_account_id.id, 'debit': line.principal_amount,
                         'analytic_distribution': loan.analytic_distribution},
                        *([{'name': _('%s - Interest', loan.name),
                            'account_id': loan.expense_account_id.id, 'debit': line.interest_amount,
                            'analytic_distribution': loan.analytic_distribution}]
                          if not loan.currency_id.is_zero(line.interest_amount) else []),
                        {'name': _('%s - Payment due', loan.name),
                         'account_id': loan.short_term_account_id.id, 'credit': line.payment_amount,
                         'analytic_distribution': loan.analytic_distribution},
                    ])
                payment_move = self.env['account.move'].with_company(loan.company_id).create(payment_vals)
                line.payment_move_id = payment_move.id
            loan.state = 'running'
        return True

    def action_close(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Close Loan'),
            'res_model': 'flousflow.account.loan.close', 'view_mode': 'form',
            'target': 'new', 'context': {'default_loan_id': self.id},
        }

    def action_open_upload(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('A schedule can only be imported for a draft loan.'))
        return {
            'type': 'ir.actions.act_window', 'name': _('Upload Amortization Schedule'),
            'res_model': 'flousflow.account.loan.upload', 'view_mode': 'form',
            'target': 'new', 'context': {'default_loan_id': self.id},
        }

    def action_cancel(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can cancel loans.'))
        for loan in self:
            if loan.state not in ('draft', 'running'):
                raise UserError(_('Only draft or running loans can be cancelled.'))
            posted_moves = loan.move_ids.filtered(lambda move: move.state == 'posted')
            draft_moves = loan.move_ids.filtered(lambda move: move.state == 'draft')
            if posted_moves:
                posted_moves._reverse_moves(default_values_list=[{
                    'date': fields.Date.context_today(loan), 'ref': _('Reversal of %s', loan.name),
                    'flousflow_loan_id': loan.id,
                } for _move in posted_moves], cancel=True)
            draft_moves.button_cancel()
            draft_moves.unlink()
            loan.state = 'cancelled'
        return True

    def unlink(self):
        if self.filtered(lambda loan: loan.state != 'draft' or loan.move_ids):
            raise UserError(_('Only draft loans without accounting entries can be deleted.'))
        return super().unlink()


class FlousflowAccountLoanLine(models.Model):
    _name = 'flousflow.account.loan.line'
    _description = 'Loan Amortization Schedule Line'
    _order = 'date, sequence, id'
    _check_company_auto = True

    loan_id = fields.Many2one('flousflow.account.loan', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(required=True, default=1)
    date = fields.Date(required=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True)
    principal_amount = fields.Monetary(required=True, default=0.0)
    interest_amount = fields.Monetary(required=True, default=0.0)
    payment_amount = fields.Monetary(compute='_compute_payment_amount', store=True)
    opening_balance = fields.Monetary(compute='_compute_balances', store=True)
    amount_due = fields.Monetary(compute='_compute_balances', store=True, string='Amount Due')
    payment_move_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)
    reclassification_move_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)
    reclassification_reversal_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)
    state = fields.Selection([
        ('draft', 'Scheduled'), ('posted', 'Posted'), ('reversed', 'Reversed')
    ], compute='_compute_state', store=True)

    @api.depends('principal_amount', 'interest_amount')
    def _compute_payment_amount(self):
        for line in self:
            line.payment_amount = line.principal_amount + line.interest_amount

    @api.depends('loan_id.amount_borrowed', 'loan_id.line_ids.date', 'loan_id.line_ids.sequence',
                 'loan_id.line_ids.principal_amount')
    def _compute_balances(self):
        for loan in self.mapped('loan_id'):
            balance = loan.amount_borrowed
            for line in loan.line_ids.sorted(lambda item: (item.date or fields.Date.today(), item.sequence, item.id or 0)):
                line.opening_balance = max(balance, 0.0)
                balance -= line.principal_amount
                line.amount_due = max(balance, 0.0)

    @api.depends('payment_move_id.state', 'payment_move_id.reversal_move_ids')
    def _compute_state(self):
        for line in self:
            if line.payment_move_id and line.payment_move_id.reversal_move_ids:
                line.state = 'reversed'
            elif line.payment_move_id and line.payment_move_id.state == 'posted':
                line.state = 'posted'
            else:
                line.state = 'draft'

    @api.constrains('principal_amount', 'interest_amount', 'date')
    def _check_values(self):
        for line in self:
            if line.principal_amount < 0 or line.interest_amount < 0:
                raise ValidationError(_('Principal and interest amounts cannot be negative.'))
            if line.loan_id.state != 'draft' and (line.principal_amount or line.interest_amount or line.date):
                raise ValidationError(_('A confirmed loan schedule cannot be edited.'))

    def unlink(self):
        if self.filtered(lambda line: line.payment_move_id or line.reclassification_move_id):
            raise UserError(_('Schedule lines linked to accounting entries cannot be deleted.'))
        return super().unlink()


class AccountMove(models.Model):
    _inherit = 'account.move'

    flousflow_loan_id = fields.Many2one('flousflow.account.loan', index=True, copy=False, readonly=True,
                                        check_company=True)
    flousflow_loan_line_id = fields.Many2one('flousflow.account.loan.line', index=True, copy=False,
                                             readonly=True, check_company=True)
