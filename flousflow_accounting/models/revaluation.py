# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FlousflowAccountRevaluationWizard(models.TransientModel):
    """Revalue foreign-currency balances at a given date.

    Community reimplementation of the standard Enterprise
    ``account.multicurrency.revaluation.wizard``. Two modes:

    * ``revaluation`` — post a realized exchange gain/loss that adjusts the
      residual of each open line to the new rate (irreversible).
    * ``adjustment`` — post an unrealized provision entry that is auto-reversed
      on ``reversal_date`` (standard Odoo provision pattern).
    """
    _name = 'flousflow.account.revaluation.wizard'
    _description = 'FlousFlow Multicurrency Revaluation'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    currency_ids = fields.Many2many(
        'res.currency', string='Currencies',
        help='Foreign currencies to revalue. The company currency is excluded.')
    date = fields.Date(
        string='Revaluation Date', required=True,
        default=fields.Date.context_today)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        check_company=True, domain=[('type', '=', 'general')],
        default=lambda self: self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.env.company.id)],
            limit=1))
    mode = fields.Selection(
        [('revaluation', 'Revaluation'), ('adjustment', 'Adjustment')],
        string='Mode', required=True, default='revaluation',
        help='Revaluation posts a realized entry; Adjustment posts a provision '
             'that is automatically reversed.')
    reversal_date = fields.Date(
        string='Reversal Date',
        help='Required when the mode is Adjustment.')
    line_ids = fields.One2many(
        'flousflow.account.revaluation.line', 'wizard_id', string='Lines')

    @api.onchange('company_id', 'currency_ids', 'date', 'journal_id', 'mode')
    def _onchange_compute_lines(self):
        self.line_ids = self._compute_lines()

    def _available_account_types(self):
        return ('asset_receivable', 'asset_cash', 'asset_current',
                'liability_payable', 'liability_current')

    def _compute_lines(self):
        """Return command list for the wizard lines."""
        self.ensure_one()
        if not (self.company_id and self.currency_ids and self.date
                and self.journal_id):
            return [(5, 0, 0)]
        company_currency = self.company_id.currency_id
        currencies = self.currency_ids.filtered(
            lambda c: c != company_currency and c.active)
        if not currencies:
            return [(5, 0, 0)]

        domain = [
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('full_reconcile_id', '=', False),
            ('account_id.account_type', 'in', self._available_account_types()),
            ('currency_id', 'in', currencies.ids),
            ('amount_residual_currency', '!=', 0.0),
        ]
        lines = self.env['account.move.line'].search(domain)
        if not lines:
            return [(5, 0, 0)]

        commands = [(5, 0, 0)]
        for currency in currencies:
            rates = currency._get_rates(self.company_id, self.date)
            rate = rates.get(currency.id)
            if not rate:
                raise UserError(_(
                    'No rate found for currency %(currency)s on %(date)s.',
                    currency=currency.name, date=self.date))
            for line in lines.filtered(lambda l: l.currency_id == currency):
                residual_currency = line.amount_residual_currency
                residual_company = line.amount_residual
                new_balance = company_currency.round(residual_currency * rate)
                adjustment = new_balance - residual_company
                if company_currency.is_zero(adjustment):
                    continue
                commands.append((0, 0, {
                    'account_id': line.account_id.id,
                    'partner_id': line.partner_id.id,
                    'currency_id': currency.id,
                    'amount_residual_currency': residual_currency,
                    'amount_residual': residual_company,
                    'currency_rate': rate,
                    'adjustment_amount': adjustment,
                }))
        return commands

    def action_revaluate(self):
        self.ensure_one()
        if self.mode == 'adjustment' and not self.reversal_date:
            raise UserError(_(
                'Please set a reversal date when using the Adjustment mode.'))
        if self.reversal_date and self.reversal_date < self.date:
            raise UserError(_(
                'The reversal date must not be before the revaluation date.'))
        if not self.line_ids:
            raise UserError(_(
                'No open foreign-currency lines to revalue for the selected '
                'currencies and date.'))

        company = self.company_id
        income_account = company.income_currency_exchange_account_id
        expense_account = company.expense_currency_exchange_account_id
        if not (income_account or expense_account):
            raise UserError(_(
                'Configure the currency exchange gain/loss accounts in '
                'Accounting Settings before revaluing.'))

        moves = self.env['account.move']
        grouped = {}
        for line in self.line_ids:
            grouped.setdefault(
                line.currency_id, self.env['flousflow.account.revaluation.line'])
            grouped[line.currency_id] |= line

        for currency, lines in grouped.items():
            if self.mode == 'revaluation':
                moves |= self._create_revaluation_move(
                    currency, lines, income_account, expense_account)
            else:
                moves |= self._create_adjustment_move(
                    currency, lines, income_account, expense_account)
        moves.filtered(lambda m: m.state == 'draft').action_post()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Exchange Difference Entries'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', moves.ids)],
        }

    def _build_line_values(self, lines):
        """Build revaluation legs (one per account) and the balancing exchange leg.

        Returns the complete ``line_ids`` command list for a balanced move. The
        exchange leg lands on the income (gain) account when the net revaluation
        increases assets and on the expense (loss) account otherwise.
        """
        move_lines = []
        total_debit = 0.0
        total_credit = 0.0
        for line in lines:
            adjustment = line.adjustment_amount
            account_type = line.account_id.account_type
            if account_type.startswith('asset'):
                debit = adjustment if adjustment > 0 else 0.0
                credit = -adjustment if adjustment < 0 else 0.0
            else:
                credit = adjustment if adjustment > 0 else 0.0
                debit = -adjustment if adjustment < 0 else 0.0
            total_debit += debit
            total_credit += credit
            move_lines.append((0, 0, {
                'account_id': line.account_id.id,
                'partner_id': line.partner_id.id,
                'debit': debit,
                'credit': credit,
                'amount_currency': 0.0,
                'currency_id': line.currency_id.id,
            }))
        return move_lines, total_debit, total_credit

    def _append_exchange_leg(self, move_lines, total_debit, total_credit,
                             income_account, expense_account):
        if total_debit > total_credit:
            # Net gain: credit the income account.
            move_lines.append((0, 0, {
                'account_id': income_account.id,
                'debit': 0.0,
                'credit': total_debit - total_credit,
            }))
        elif total_credit > total_debit:
            # Net loss: debit the expense account.
            move_lines.append((0, 0, {
                'account_id': expense_account.id,
                'debit': total_credit - total_debit,
                'credit': 0.0,
            }))

    def _create_revaluation_move(self, currency, lines,
                                 income_account, expense_account):
        self.ensure_one()
        company = self.company_id
        move_lines, total_debit, total_credit = self._build_line_values(lines)
        self._append_exchange_leg(
            move_lines, total_debit, total_credit, income_account, expense_account)
        return self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.date,
            'journal_id': self.journal_id.id,
            'company_id': company.id,
            'ref': _('Currency revaluation %s') % currency.name,
            'line_ids': move_lines,
        })

    def _create_adjustment_move(self, currency, lines,
                                income_account, expense_account):
        self.ensure_one()
        company = self.company_id
        move_lines, total_debit, total_credit = self._build_line_values(lines)
        self._append_exchange_leg(
            move_lines, total_debit, total_credit, income_account, expense_account)
        provision = self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.date,
            'journal_id': self.journal_id.id,
            'company_id': company.id,
            'ref': _('Currency revaluation (provision) %s') % currency.name,
            'line_ids': move_lines,
        })
        reversal = provision._reverse_moves(
            default_values_list=[{
                'date': self.reversal_date,
                'ref': _('Reversal of: %s', provision.name),
            }],
            cancel=False)
        return provision | reversal


class FlousflowAccountRevaluationLine(models.TransientModel):
    _name = 'flousflow.account.revaluation.line'
    _description = 'FlousFlow Multicurrency Revaluation Line'

    wizard_id = fields.Many2one(
        'flousflow.account.revaluation.wizard', ondelete='cascade', required=True)
    account_id = fields.Many2one('account.account', string='Account', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    company_currency_id = fields.Many2one(
        related='wizard_id.company_id.currency_id', string='Company Currency')
    amount_residual_currency = fields.Monetary(
        string='Residual (Currency)', currency_field='currency_id')
    amount_residual = fields.Monetary(
        string='Residual (Company)', currency_field='company_currency_id')
    currency_rate = fields.Float(string='New Rate', digits=(12, 6))
    adjustment_amount = fields.Monetary(
        string='Adjustment', currency_field='company_currency_id')
