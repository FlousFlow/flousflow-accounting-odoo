# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('default_internal_transfer_action'):
            values['is_internal_transfer'] = True
            values['partner_id'] = False
            values['partner_bank_id'] = False
            values['salesperson_id'] = False
        return values

    salesperson_id = fields.Many2one(
        'res.users',
        string='Collector',
        tracking=True,
        index=True,
        help='Salesperson responsible for collecting this payment.',
    )

    @api.onchange('partner_id')
    def _onchange_salesperson_from_partner(self):
        for payment in self:
            if payment.partner_type == 'customer' and payment.partner_id and not payment.salesperson_id:
                payment.salesperson_id = payment.partner_id.user_id

    def _autofill_salesperson_from_partner(self):
        """Set the collector from the customer's salesperson when it is blank.

        The onchange below covers the interactive payment form.  This helper is
        also called after ORM creates/updates so payments created by the
        Register Payment wizard, imports, or integrations follow the same rule.
        A manually selected collector always wins.
        """
        for payment in self.filtered(
            lambda pay: (
                pay.partner_type == 'customer'
                and pay.partner_id
                and not pay.salesperson_id
                and pay.partner_id.user_id
            )
        ):
            payment.salesperson_id = payment.partner_id.user_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_internal_transfer'):
                vals.update(partner_id=False, partner_bank_id=False, salesperson_id=False)
        payments = super().create(vals_list)
        payments._autofill_salesperson_from_partner()
        return payments

    def _get_payment_receipt_net_after_payment(self):
        """Return the partner balance as total debit minus total credit."""
        self.ensure_one()
        lines = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('company_id', '=', self.company_id.id),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
        ])
        net_company = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))
        return self.company_id.currency_id._convert(
            net_company,
            self.currency_id,
            self.company_id,
            self.date,
        )

    is_internal_transfer = fields.Boolean(
        string='Internal Transfer', default=False, tracking=True,
    )
    destination_journal_id = fields.Many2one(
        'account.journal', string='Destination Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('id', '!=', journal_id)]",
        check_company=True,
    )
    transfer_fee = fields.Monetary(
        string='Transfer Fee', currency_field='currency_id', default=0.0,
        tracking=True,
        help='Additional bank fee charged on the source journal and posted in the source transfer journal entry.',
    )
    transfer_fee_move_id = fields.Many2one(
        'account.move', string='Transfer Fee Journal Entry', readonly=True,
        copy=False, check_company=True,
    )

    @api.depends(
        'is_internal_transfer', 'destination_journal_id', 'company_id',
    )
    def _compute_destination_account_id(self):
        super()._compute_destination_account_id()
        for payment in self.filtered('is_internal_transfer'):
            payment.destination_account_id = (
                payment.destination_journal_id.default_account_id
            )

    @api.onchange('is_internal_transfer')
    def _onchange_is_internal_transfer(self):
        for payment in self:
            if payment.is_internal_transfer:
                payment.partner_id = False
                payment.partner_bank_id = False
                payment.salesperson_id = False

    def _auto_reconcile_open_invoices(self):
        """Match a posted payment against the partner's open invoices/bills.

        The standard Register Payment wizard already reconciles its active
        invoices. This also covers payments created from the Payments menus,
        using the oldest open receivable/payable items first and preserving any
        overpayment as an unreconciled credit.

        Only the payment's partner control line is considered. Internal
        transfers and non-reconcilable accounts are deliberately excluded.
        """
        move_line = self.env['account.move.line']
        valid_accounts = ('asset_receivable', 'liability_payable')
        for payment in self.filtered(
            lambda pay: pay.partner_id and not pay.is_internal_transfer and pay.move_id
        ):
            payment_lines = payment.move_id.line_ids.filtered(
                lambda line: (
                    line.partner_id == payment.partner_id
                    and line.account_id.account_type in valid_accounts
                    and line.account_id.reconcile
                    and not line.reconciled
                )
            )
            if not payment_lines:
                continue

            invoice_types = (
                ('out_invoice', 'out_refund')
                if payment.partner_type == 'customer'
                else ('in_invoice', 'in_refund')
            )
            for payment_line in payment_lines:
                candidates = move_line.search([
                    ('partner_id', '=', payment.partner_id.id),
                    ('company_id', '=', payment.company_id.id),
                    ('account_id', '=', payment_line.account_id.id),
                    ('account_id.reconcile', '=', True),
                    ('parent_state', '=', 'posted'),
                    ('reconciled', '=', False),
                    ('move_id', '!=', payment.move_id.id),
                    ('move_id.move_type', 'in', invoice_types),
                    ('balance', '>', 0) if payment_line.balance < 0 else ('balance', '<', 0),
                ], order='date_maturity, date, id')
                for candidate in candidates:
                    (payment_line + candidate).reconcile()
                    if payment_line.reconciled:
                        break

    def _check_transfer_fee_configuration(self):
        for payment in self.filtered(lambda pay: pay.is_internal_transfer and pay.transfer_fee > 0):
            account = payment.company_id.transfer_fee_account_id
            if not account:
                raise UserError(_(
                    "Configure the internal transfer fee expense account before posting a transfer with a fee."
                ))
            if account.account_type not in ('expense', 'expense_direct_cost'):
                raise UserError(_("The internal transfer fee account must be an expense account."))

    def _get_internal_transfer_liquidity_account(self, journal):
        self.ensure_one()
        # Internal transfers post directly between the bank/cash control
        # accounts. Payment method accounts are often outstanding accounts,
        # which would recreate the intermediary balance this flow removes.
        return journal.default_account_id

    def _post_internal_transfer_direct(self):
        """Post one balanced move directly between the two journal accounts."""
        self.ensure_one()
        if not self.destination_journal_id or self.journal_id == self.destination_journal_id:
            raise UserError(_(
                "Choose two different bank or cash journals for an internal transfer."
            ))
        if self.paired_internal_transfer_payment_id:
            raise UserError(_(
                "This transfer was created with the previous two-payment workflow. Cancel it and create a new transfer to post directly between journal accounts."
            ))
        if self.amount <= 0 or self.transfer_fee < 0:
            raise UserError(_(
                "The transfer amount must be positive and the transfer fee cannot be negative."
            ))
        if (
            self.journal_id.type not in ('bank', 'cash')
            or self.destination_journal_id.type not in ('bank', 'cash')
            or self.journal_id.company_id != self.company_id
            or self.destination_journal_id.company_id != self.company_id
        ):
            raise UserError(_(
                "Choose two different bank or cash journals for an internal transfer."
            ))
        company_currency = self.company_id.currency_id
        journal_currencies = (
            self.journal_id.currency_id or company_currency,
            self.destination_journal_id.currency_id or company_currency,
        )
        if any(currency != self.currency_id for currency in journal_currencies):
            raise UserError(_(
                "Both journals and the transfer must use the same currency for a direct internal transfer."
            ))

        selected_account = self._get_internal_transfer_liquidity_account(
            self.journal_id,
        )
        other_account = self._get_internal_transfer_liquidity_account(
            self.destination_journal_id,
        )
        expense_account = self.company_id.transfer_fee_account_id
        if not selected_account or not other_account:
            raise UserError(_(
                "Configure a bank or cash account on both journals before posting an internal transfer."
            ))
        if any(
            account.currency_id and account.currency_id != self.currency_id
            for account in (selected_account, other_account)
        ):
            raise UserError(_(
                "Both journal accounts and the transfer must use the same currency for a direct internal transfer."
            ))
        if self.transfer_fee and self.payment_type != 'outbound':
            raise UserError(_(
                "Transfer fees are supported for outbound internal transfers only."
            ))

        line_specs = []
        if self.payment_type == 'outbound':
            line_specs.append((other_account, _('Internal transfer'), self.amount))
            if self.transfer_fee:
                line_specs.append((expense_account, _('Internal transfer fee'), self.transfer_fee))
            line_specs.append((
                selected_account,
                _('Internal transfer'),
                -(self.amount + self.transfer_fee),
            ))
        else:
            line_specs.extend((
                (selected_account, _('Internal transfer'), self.amount),
                (other_account, _('Internal transfer'), -self.amount),
            ))

        line_commands = []
        for account, label, amount_currency in line_specs:
            balance = self.currency_id._convert(
                amount_currency, company_currency, self.company_id, self.date,
            )
            line_commands.append((0, 0, {
                'name': label,
                'account_id': account.id,
                'currency_id': self.currency_id.id,
                'balance': balance,
                'amount_currency': amount_currency,
            }))

        move_vals = {
            'ref': self.memo or _('Internal transfer'),
            'date': self.date,
            'currency_id': self.currency_id.id,
            'line_ids': [(5, 0, 0), *line_commands],
        }
        move = self.move_id
        if move:
            if move.state != 'draft':
                raise UserError(_(
                    "Reset the transfer to draft before posting it again."
                ))
            move.write(move_vals)
        else:
            move = self.env['account.move'].create({
                **move_vals,
                'move_type': 'entry',
                'journal_id': self.journal_id.id,
                'company_id': self.company_id.id,
                'origin_payment_id': self.id,
            })
        move.action_post()
        self.write({'move_id': move.id, 'state': 'paid'})

    def action_post(self):
        for payment in self:
            if payment.is_internal_transfer:
                payment._check_transfer_fee_configuration()
                payment._post_internal_transfer_direct()
            else:
                super(AccountPayment, payment).action_post()
                payment._auto_reconcile_open_invoices()
        return True

    def action_cancel(self):
        result = super().action_cancel()
        for payment in self:
            paired = payment.paired_internal_transfer_payment_id
            if paired and paired.state != 'canceled':
                paired.action_cancel()
            if payment.transfer_fee_move_id and payment.transfer_fee_move_id.state == 'posted':
                payment.transfer_fee_move_id.button_cancel()
        return result

    def action_draft(self):
        result = super().action_draft()
        for payment in self:
            paired = payment.paired_internal_transfer_payment_id
            if paired and paired.state != 'draft':
                paired.action_draft()
        return result

    def unlink(self):
        paired_payments = self.mapped('paired_internal_transfer_payment_id')
        result = super().unlink()
        if paired_payments:
            paired_payments.with_context(skip_pairing_sync=True).unlink()
        return result

    def write(self, vals):
        if 'amount' in vals and not self.env.context.get('skip_pairing_sync'):
            paired_transfers = self.filtered(
                lambda payment: payment.is_internal_transfer
                and payment.paired_internal_transfer_payment_id
                and payment.amount != vals['amount']
            )
            if paired_transfers:
                raise UserError(_(
                    'You cannot change the amount of an internal transfer after its paired payment has been created. Cancel and recreate the transfer instead.'
                ))
        if 'transfer_fee' in vals:
            changed_fee = self.filtered(
                lambda payment: payment.is_internal_transfer
                and payment.transfer_fee_move_id
                and payment.transfer_fee != vals['transfer_fee']
            )
            if changed_fee:
                raise UserError(_(
                    'You cannot change the transfer fee after its journal entry has been created. Cancel and recreate the transfer instead.'
                ))
        result = super().write(vals)
        if {'partner_id', 'partner_type'} & set(vals):
            self._autofill_salesperson_from_partner()
        if not self.env.context.get('skip_pairing_sync'):
            for payment in self.with_context(skip_pairing_sync=True):
                paired = payment.paired_internal_transfer_payment_id
                if not payment.is_internal_transfer or not paired:
                    continue
                sync_vals = {}
                for field_name in ('amount', 'date', 'memo'):
                    if field_name in vals:
                        sync_vals[field_name] = vals[field_name]
                if 'destination_journal_id' in vals:
                    sync_vals['journal_id'] = vals['destination_journal_id']
                if sync_vals:
                    paired.write(sync_vals)
        return result


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _select_action_to_open(self):
        self.ensure_one()
        if self.type == 'cash':
            # The standard cash-journal Transactions button opens statement
            # headers, which cannot list account.payment internal transfers.
            # Open the journal's posted entries instead; Statements stays
            # available from the dashboard menu.
            return 'action_move_journal_line'
        return super()._select_action_to_open()

    def _get_dashboard_liquidity_account_ids(self):
        """Return the ledger accounts that define this journal's balance."""
        self.ensure_one()
        accounts = self.default_account_id
        accounts |= self.inbound_payment_method_line_ids.payment_account_id
        accounts |= self.outbound_payment_method_line_ids.payment_account_id
        # Odoo may resolve the outstanding account from the company chart
        # rather than storing it on the journal payment method line. Include
        # the accounts actually used by this journal's posted payments.
        accounts |= self.env['account.payment'].search([
            ('journal_id', '=', self.id),
            ('company_id', '=', self.company_id.id),
            ('outstanding_account_id', '!=', False),
        ]).mapped('outstanding_account_id')
        return accounts

    def _get_net_dashboard_balance(self):
        self.ensure_one()
        accounts = self._get_dashboard_liquidity_account_ids()
        if not accounts:
            return 0.0
        lines = self.env['account.move.line'].search([
            ('account_id', 'in', accounts.ids),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ])
        return sum(lines.mapped('balance'))

    def _get_journal_dashboard_data_batched(self):
        data = super()._get_journal_dashboard_data_batched()
        for journal in self:
            if journal.type in ('bank', 'cash') and journal.id in data:
                data[journal.id]['account_balance'] = journal._get_net_dashboard_balance()
        return data

    def create_internal_transfer(self):
        return self.open_payments_action('transfer', mode='form')


class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _get_opening_balance(self):
        self.ensure_one()
        balance = super()._get_opening_balance()
        cash_method = self.sudo()._get_cash_payment_method()
        if not cash_method:
            return balance

        journal = cash_method.journal_id
        company = journal.company_id
        balance_currency = journal.currency_id or company.currency_id
        liquidity_accounts = (
            journal.default_account_id
            | journal.inbound_payment_method_line_ids.payment_account_id
            | journal.outbound_payment_method_line_ids.payment_account_id
        )

        # Use the same effective statement checkpoint as Odoo's running-balance
        # computation. Open POS sessions are not checkpoints: their opening
        # balance may be stale until the session is closed.
        last_statement = self.env['account.bank.statement'].sudo().search([
            ('journal_id', '=', journal.id),
            ('company_id', '=', company.id),
            ('first_line_index', '!=', False),
            '|',
            ('pos_session_id', '=', False),
            ('pos_session_id.state', '=', 'closed'),
        ], order='date desc, id desc', limit=1)
        payment_domain = [
            ('journal_id', '=', journal.id),
            ('company_id', '=', company.id),
            ('is_internal_transfer', '=', True),
            ('move_id.state', '=', 'posted'),
        ]
        if last_statement:
            checkpoint_datetime = (
                last_statement.pos_session_id.write_date
                if last_statement.pos_session_id
                else last_statement.write_date
            )
            payment_domain.append(('create_date', '>', checkpoint_datetime))

        pending_transfers = self.env['account.payment'].sudo().search(payment_domain)
        for payment in pending_transfers:
            cash_lines = payment.move_id.line_ids.filtered(
                lambda line: line.account_id in liquidity_accounts
            )
            if cash_lines.filtered('reconciled'):
                continue

            signed_amount = payment.amount_company_currency_signed
            if balance_currency != company.currency_id:
                signed_amount = company.currency_id._convert(
                    signed_amount,
                    balance_currency,
                    company,
                    payment.date,
                )
            balance += signed_amount

        return balance


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    salesperson_id = fields.Many2one(
        'res.users',
        string='Collector',
        compute='_compute_salesperson_id',
        store=True,
        readonly=False,
        help='Salesperson responsible for collecting this payment.',
    )

    @api.depends('partner_id', 'partner_type')
    def _compute_salesperson_id(self):
        for wizard in self:
            if wizard.partner_type == 'customer' and wizard.partner_id:
                wizard.salesperson_id = wizard.partner_id.user_id
            else:
                wizard.salesperson_id = False

    def _get_collector_for_partner(self, partner):
        self.ensure_one()
        if partner and partner.id == self.partner_id.id and self.salesperson_id:
            return self.salesperson_id
        return partner.user_id if partner and self.partner_type == 'customer' else self.env['res.users']

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super()._create_payment_vals_from_wizard(batch_result)
        partner = self.env['res.partner'].browse(payment_vals.get('partner_id'))
        collector = self._get_collector_for_partner(partner)
        if collector:
            payment_vals['salesperson_id'] = collector.id
        return payment_vals

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super()._create_payment_vals_from_batch(batch_result)
        partner = self.env['res.partner'].browse(payment_vals.get('partner_id'))
        collector = self._get_collector_for_partner(partner)
        if collector:
            payment_vals['salesperson_id'] = collector.id
        return payment_vals
