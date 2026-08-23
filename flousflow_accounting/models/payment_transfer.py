# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
# Internal paired transfers between bank and cash journals.
# (Merged from the former standalone ff_account_transfer module.)

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
            if (
                payment.is_internal_transfer
                and not payment.paired_internal_transfer_payment_id
                and payment.payment_type == 'outbound'
            ):
                paired_payment = self.with_context(
                    skip_pairing_sync=True
                ).create(payment._prepare_paired_transfer_vals())
                payment.paired_internal_transfer_payment_id = paired_payment
                paired_payment.paired_internal_transfer_payment_id = payment
                super(AccountPayment, payment).action_post()
                paired_payment.action_post()
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

    def create_internal_transfer(self):
        return self.open_payments_action('transfer', mode='form')
