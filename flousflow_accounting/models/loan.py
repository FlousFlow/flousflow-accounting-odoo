# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FlousflowAccountLoan(models.Model):
    _name = 'flousflow.account.loan'
    _description = 'FlousFlow Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    description = fields.Char(required=True, tracking=True)
    lender_id = fields.Many2one('res.partner', required=True, check_company=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id, tracking=True)
    asset_group_id = fields.Many2one(
        'flousflow.account.asset.group', string='Asset Group',
        check_company=True, tracking=True,
        help='Optional reporting classification for loan analysis.')
    principal_amount = fields.Monetary(required=True, tracking=True)
    annual_interest_rate = fields.Float(string='Annual Interest Rate (%)', required=True, tracking=True)
    installment_count = fields.Integer(required=True, default=12, tracking=True)
    payment_frequency = fields.Selection(
        [('monthly', 'Monthly'), ('quarterly', 'Quarterly'),
         ('semiannual', 'Semi-Annual'), ('annual', 'Annual')],
        required=True, default='monthly', tracking=True)
    computation_method = fields.Selection(
        [('annuity', 'Annuity'), ('fixed_principal', 'Fixed Principal'),
         ('interest_only', 'Interest Only')],
        required=True, default='annuity', tracking=True)
    start_date = fields.Date(required=True, default=fields.Date.context_today)
    first_payment_date = fields.Date(required=True)
    end_date = fields.Date(
        string='End Date', compute='_compute_end_date', store=True, readonly=True)
    journal_id = fields.Many2one('account.journal', required=True, check_company=True, domain="[('type', '=', 'general')]", string='Loan Journal')
    cash_account_id = fields.Many2one('account.account', required=True, check_company=True, domain="[('account_type', 'in', ('asset_cash', 'asset_current'))]", string='Cash / Settlement Account')
    liability_account_id = fields.Many2one('account.account', required=True, check_company=True, domain="[('account_type', 'in', ('liability_current', 'liability_non_current', 'liability_payable'))]", string='Loan Liability Account')
    interest_account_id = fields.Many2one('account.account', required=True, check_company=True, domain="[('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))]", string='Interest Expense Account')
    analytic_distribution = fields.Json(string='Analytic Distribution')
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('running', 'Running'), ('closed', 'Closed'),
         ('cancelled', 'Cancelled')], default='draft', required=True,
        tracking=True, copy=False)
    line_ids = fields.One2many('flousflow.account.loan.line', 'loan_id', copy=True, string='Amortization Schedule')
    disbursement_move_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)
    total_interest = fields.Monetary(compute='_compute_totals', store=True)
    total_payable = fields.Monetary(compute='_compute_totals', store=True)
    outstanding_principal = fields.Monetary(compute='_compute_totals', store=True)
    paid_installments = fields.Integer(compute='_compute_totals', store=True)

    @api.depends('first_payment_date', 'installment_count', 'payment_frequency')
    def _compute_end_date(self):
        months_by_frequency = {
            'monthly': 1, 'quarterly': 3, 'semiannual': 6, 'annual': 12,
        }
        for loan in self:
            months = months_by_frequency.get(loan.payment_frequency)
            if not loan.first_payment_date or not months or loan.installment_count < 1:
                loan.end_date = False
                continue
            loan.end_date = loan.first_payment_date + relativedelta(
                months=months * (loan.installment_count - 1))

    @api.depends('principal_amount', 'line_ids.interest_amount', 'line_ids.principal_amount', 'line_ids.state')
    def _compute_totals(self):
        for loan in self:
            loan.total_interest = sum(loan.line_ids.mapped('interest_amount'))
            loan.total_payable = loan.principal_amount + loan.total_interest
            paid = loan.line_ids.filtered(lambda line: line.state == 'posted')
            loan.outstanding_principal = max(loan.principal_amount - sum(paid.mapped('principal_amount')), 0.0)
            loan.paid_installments = len(paid)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('flousflow.account.loan') or _('New')
        return super().create(vals_list)

    @api.constrains('principal_amount', 'annual_interest_rate', 'installment_count')
    def _check_amounts(self):
        for loan in self:
            if loan.principal_amount <= 0:
                raise ValidationError(_('Principal amount must be greater than zero.'))
            if loan.annual_interest_rate < 0:
                raise ValidationError(_('Interest rate cannot be negative.'))
            if loan.installment_count <= 0:
                raise ValidationError(_('Installment count must be greater than zero.'))

    @api.constrains('start_date', 'first_payment_date')
    def _check_dates(self):
        for loan in self:
            if loan.first_payment_date <= loan.start_date:
                raise ValidationError(_('First payment date must be after the start date.'))

    def _period_months(self):
        self.ensure_one()
        return {'monthly': 1, 'quarterly': 3, 'semiannual': 6, 'annual': 12}[self.payment_frequency]

    def _schedule_values(self):
        self.ensure_one()
        currency = self.currency_id
        periods = self.installment_count
        period_rate = (self.annual_interest_rate / 100.0) * self._period_months() / 12.0
        balance = self.principal_amount
        if self.computation_method == 'annuity' and period_rate:
            payment = balance * period_rate / (1 - (1 + period_rate) ** -periods)
        elif self.computation_method == 'annuity':
            payment = balance / periods
        else:
            payment = 0.0
        values = []
        for number in range(1, periods + 1):
            interest = currency.round(balance * period_rate)
            if self.computation_method == 'annuity':
                principal = currency.round(payment - interest)
            elif self.computation_method == 'fixed_principal':
                principal = currency.round(self.principal_amount / periods)
            else:
                principal = self.principal_amount if number == periods else 0.0
            if number == periods:
                principal = currency.round(balance)
            principal = min(principal, balance)
            opening = balance
            balance = currency.round(balance - principal)
            values.append({
                'sequence': number,
                'date': self.first_payment_date + relativedelta(months=self._period_months() * (number - 1)),
                'opening_balance': opening,
                'principal_amount': principal,
                'interest_amount': interest,
                'payment_amount': currency.round(principal + interest),
                'closing_balance': balance,
            })
        return values

    def action_generate_schedule(self):
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_('Only draft loans can regenerate their schedule.'))
            loan.line_ids.unlink()
            loan.line_ids = [(0, 0, vals) for vals in loan._schedule_values()]
        return True

    def action_confirm(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can confirm loans.'))
        for loan in self:
            if loan.state != 'draft':
                raise UserError(_('Only draft loans can be confirmed.'))
            if not loan.line_ids:
                loan.action_generate_schedule()
            amount = loan.currency_id._convert(loan.principal_amount, loan.company_id.currency_id, loan.company_id, loan.start_date)
            foreign = loan.currency_id != loan.company_id.currency_id
            move = self.env['account.move'].with_company(loan.company_id).create({
                'move_type': 'entry', 'date': loan.start_date,
                'journal_id': loan.journal_id.id, 'company_id': loan.company_id.id,
                'ref': loan.name,
                'line_ids': [(0, 0, {
                    'name': loan.description, 'account_id': loan.cash_account_id.id,
                    'partner_id': loan.lender_id.id, 'debit': amount,
                    **({'currency_id': loan.currency_id.id, 'amount_currency': loan.principal_amount} if foreign else {}),
                }), (0, 0, {
                    'name': loan.description, 'account_id': loan.liability_account_id.id,
                    'partner_id': loan.lender_id.id, 'credit': amount,
                    **({'currency_id': loan.currency_id.id, 'amount_currency': -loan.principal_amount} if foreign else {}),
                })],
            })
            move.action_post()
            loan.write({'disbursement_move_id': move.id, 'state': 'running'})
        return True

    def action_cancel(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can cancel loans.'))
        for loan in self:
            if loan.line_ids.filtered(lambda line: line.state == 'posted'):
                raise UserError(_('A loan with posted installments cannot be cancelled.'))
            if loan.disbursement_move_id and loan.disbursement_move_id.state == 'posted':
                loan.disbursement_move_id._reverse_moves(
                    default_values_list=[{'date': fields.Date.context_today(loan), 'ref': _('Reversal of %s', loan.name)}], cancel=True)
            loan.state = 'cancelled'
        return True

    def action_close(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can close loans.'))
        for loan in self:
            if loan.line_ids.filtered(lambda line: line.state != 'posted'):
                raise UserError(_('All installments must be posted before closing the loan.'))
            loan.state = 'closed'
        return True

    def unlink(self):
        if self.filtered(lambda loan: loan.state != 'draft'):
            raise UserError(_('Only draft loans can be deleted.'))
        return super().unlink()


class FlousflowAccountLoanLine(models.Model):
    _name = 'flousflow.account.loan.line'
    _description = 'FlousFlow Loan Installment'
    _order = 'date, sequence, id'
    _check_company_auto = True

    loan_id = fields.Many2one('flousflow.account.loan', required=True, ondelete='cascade', index=True)
    loan_name = fields.Char(related='loan_id.name', store=True, index=True)
    loan_state = fields.Selection(related='loan_id.state', store=True, index=True)
    loan_date = fields.Date(related='loan_id.start_date', store=True, index=True)
    active = fields.Boolean(related='loan_id.active', store=True, index=True)
    loan_asset_group_id = fields.Many2one(
        related='loan_id.asset_group_id', store=True, index=True)
    sequence = fields.Integer(required=True)
    date = fields.Date(required=True)
    company_id = fields.Many2one(related='loan_id.company_id', store=True)
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True)
    opening_balance = fields.Monetary(required=True)
    principal_amount = fields.Monetary(required=True)
    interest_amount = fields.Monetary(required=True)
    payment_amount = fields.Monetary(required=True)
    closing_balance = fields.Monetary(required=True)
    long_term_theoretical_balance = fields.Monetary(
        compute='_compute_theoretical_balances', store=True)
    short_term_theoretical_balance = fields.Monetary(
        compute='_compute_theoretical_balances', store=True)
    move_id = fields.Many2one('account.move', readonly=True, copy=False, check_company=True)
    state = fields.Selection([('draft', 'Scheduled'), ('posted', 'Posted'), ('reversed', 'Reversed')], compute='_compute_state', store=True)

    @api.depends('closing_balance', 'date', 'loan_id.start_date',
                 'loan_id.installment_count', 'loan_id.payment_frequency',
                 'loan_id.company_id.fiscalyear_last_day',
                 'loan_id.company_id.fiscalyear_last_month')
    def _compute_theoretical_balances(self):
        for line in self:
            if not line.date or not line.loan_id.company_id:
                line.long_term_theoretical_balance = 0.0
                line.short_term_theoretical_balance = 0.0
                continue
            loan = line.loan_id
            remaining_lines = loan.line_ids.filtered(lambda installment: installment.date > line.date)
            current_fiscal_year_end = loan.company_id.compute_fiscalyear_dates(
                line.date)['date_to']
            next_fiscal_year_end = loan.company_id.compute_fiscalyear_dates(
                current_fiscal_year_end + relativedelta(days=1))['date_to']
            short_term = sum(
                installment.principal_amount for installment in remaining_lines
                if installment.date <= next_fiscal_year_end)
            line.short_term_theoretical_balance = short_term
            line.long_term_theoretical_balance = max(
                line.closing_balance - short_term, 0.0)

    @api.depends('move_id.state', 'move_id.reversal_move_ids')
    def _compute_state(self):
        for line in self:
            if line.move_id and line.move_id.reversal_move_ids:
                line.state = 'reversed'
            elif line.move_id and line.move_id.state == 'posted':
                line.state = 'posted'
            else:
                line.state = 'draft'

    def action_post(self):
        for line in self:
            if line.loan_id.state != 'running':
                raise UserError(_('Installments can only be posted for running loans.'))
            if line.move_id:
                raise UserError(_('This installment already has an accounting entry.'))
            loan = line.loan_id
            company_currency = loan.company_id.currency_id
            principal = loan.currency_id._convert(line.principal_amount, company_currency, loan.company_id, line.date)
            interest = loan.currency_id._convert(line.interest_amount, company_currency, loan.company_id, line.date)
            foreign = loan.currency_id != company_currency
            lines = [(0, 0, {
                'name': _('%s - Principal', loan.name), 'account_id': loan.liability_account_id.id,
                'partner_id': loan.lender_id.id, 'debit': principal,
                **({'currency_id': loan.currency_id.id, 'amount_currency': line.principal_amount} if foreign else {}),
            })]
            if interest:
                lines.append((0, 0, {
                    'name': _('%s - Interest', loan.name), 'account_id': loan.interest_account_id.id,
                    'partner_id': loan.lender_id.id, 'debit': interest,
                    'analytic_distribution': loan.analytic_distribution,
                    **({'currency_id': loan.currency_id.id, 'amount_currency': line.interest_amount} if foreign else {}),
                }))
            lines.append((0, 0, {
                'name': _('%s - Payment', loan.name), 'account_id': loan.cash_account_id.id,
                'partner_id': loan.lender_id.id, 'credit': principal + interest,
                **({'currency_id': loan.currency_id.id, 'amount_currency': -line.payment_amount} if foreign else {}),
            }))
            move = self.env['account.move'].with_company(loan.company_id).create({
                'move_type': 'entry', 'date': line.date, 'journal_id': loan.journal_id.id,
                'company_id': loan.company_id.id, 'ref': _('%s installment %s', loan.name, line.sequence),
                'line_ids': lines,
            })
            move.action_post()
            line.move_id = move.id
        return True

    def action_reverse(self):
        for line in self:
            if not line.move_id or line.move_id.state != 'posted':
                raise UserError(_('Only posted installments can be reversed.'))
            line.move_id._reverse_moves(default_values_list=[{
                'date': fields.Date.context_today(line), 'ref': _('Reversal of loan installment')}], cancel=True)
        return True

    def unlink(self):
        if self.filtered('move_id'):
            raise UserError(_('Installments linked to journal entries cannot be deleted.'))
        return super().unlink()
