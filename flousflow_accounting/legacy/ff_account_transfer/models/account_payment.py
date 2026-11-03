# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_internal_transfer = fields.Boolean(
        string='Internal Transfer', default=False, tracking=True,
    )
    destination_journal_id = fields.Many2one(
        'account.journal', string='Destination Journal',
        domain="[('type', 'in', ('bank', 'cash')), ('id', '!=', journal_id)]",
        check_company=True,
    )

    @api.depends('is_internal_transfer', 'destination_journal_id', 'company_id')
    def _compute_destination_account_id(self):
        super()._compute_destination_account_id()
        for payment in self.filtered('is_internal_transfer'):
            if not payment.company_id.transfer_account_id:
                raise UserError(_(
                    "There is no default Internal Transfer Account configured for company '%s'.",
                    payment.company_id.name,
                ))
            payment.destination_account_id = payment.company_id.transfer_account_id

    def _prepare_paired_transfer_vals(self):
        self.ensure_one()
        paired_payment_type = (
            'inbound' if self.payment_type == 'outbound' else 'outbound'
        )
        lines = (
            self.destination_journal_id.inbound_payment_method_line_ids
            if paired_payment_type == 'inbound'
            else self.destination_journal_id.outbound_payment_method_line_ids
        )
        if not lines:
            raise UserError(_(
                "The destination journal '%(journal)s' must have at least one %(payment_type)s payment method configured.",
                journal=self.destination_journal_id.name,
                payment_type=paired_payment_type,
            ))
        return {
            'amount': self.amount,
            'payment_type': paired_payment_type,
            'journal_id': self.destination_journal_id.id,
            'destination_journal_id': self.journal_id.id,
            'is_internal_transfer': True,
            'date': self.date,
            'memo': self.memo,
            'paired_internal_transfer_payment_id': self.id,
            'payment_method_line_id': lines[0].id,
            'currency_id': self.currency_id.id,
        }

    def action_post(self):
        for payment in self:
            if payment.is_internal_transfer:
                paired_payment = payment.paired_internal_transfer_payment_id
                if not paired_payment:
                    paired_payment = self.with_context(
                        skip_pairing_sync=True
                    ).create(payment._prepare_paired_transfer_vals())
                    payment.paired_internal_transfer_payment_id = paired_payment
                    paired_payment.paired_internal_transfer_payment_id = payment

                # Posting one leg must always post its counterpart too. This
                # also keeps both entries in sync when a canceled transfer is
                # reset to draft and posted again.
                for transfer_payment in payment | paired_payment:
                    if transfer_payment.state == 'draft':
                        super(AccountPayment, transfer_payment).action_post()
            else:
                super(AccountPayment, payment).action_post()
        return True

    def action_cancel(self):
        result = super().action_cancel()
        for payment in self:
            paired = payment.paired_internal_transfer_payment_id
            if paired and paired.state != 'canceled':
                paired.action_cancel()
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
        result = super().write(vals)
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
