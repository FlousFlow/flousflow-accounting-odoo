# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class TestOpenItemReconciliation(AccountTestInvoicingCommon):

    def _invoice(self, partner, amount, move_type='out_invoice', ref='OPEN-ITEM'):
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': partner.id,
            'invoice_date': fields.Date.from_string('2026-08-01'),
            'ref': ref,
            'invoice_line_ids': [Command.create({
                'name': ref,
                'quantity': 1,
                'price_unit': amount,
                'account_id': self.company_data['default_account_revenue'].id,
            })],
        })
        move.action_post()
        return move

    def _receivable(self, moves):
        return moves.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable')

    def test_partial_match_uses_standard_reconciliation_without_new_move(self):
        invoice = self._invoice(self.partner_a, 100, ref='OPEN-100')
        credit_note = self._invoice(
            self.partner_a, 40, move_type='out_refund', ref='CREDIT-40')
        lines = self._receivable(invoice | credit_note)
        move_count = self.env['account.move'].search_count([
            ('company_id', '=', self.company.id)])

        action = lines.action_flousflow_reconcile_open_items()

        invoice_line = self._receivable(invoice)
        credit_line = self._receivable(credit_note)
        self.assertAlmostEqual(invoice_line.amount_residual, 60.0, places=2)
        self.assertAlmostEqual(credit_line.amount_residual, 0.0, places=2)
        self.assertTrue(invoice_line.matched_credit_ids)
        self.assertEqual(self.env['account.move'].search_count([
            ('company_id', '=', self.company.id)]), move_count)
        self.assertEqual(action['tag'], 'display_notification')

    def test_selection_cannot_cross_partners(self):
        invoice_a = self._invoice(self.partner_a, 100, ref='PARTNER-A')
        invoice_b = self._invoice(self.partner_b, 100, ref='PARTNER-B')
        lines = self._receivable(invoice_a | invoice_b)

        with self.assertRaisesRegex(
                UserError, 'at least two different journal entries for the same'):
            lines.action_flousflow_reconcile_open_items()

        self.assertAlmostEqual(
            sum(self._receivable(invoice_a).mapped('amount_residual')), 100.0, places=2)
        self.assertAlmostEqual(
            sum(self._receivable(invoice_b).mapped('amount_residual')), 100.0, places=2)

    def test_non_receivable_item_is_rejected_before_reconciliation(self):
        invoice = self._invoice(self.partner_a, 100, ref='INVALID-ACCOUNT')
        receivable = self._receivable(invoice)
        revenue = invoice.line_ids.filtered(
            lambda line: line.account_id == self.company_data['default_account_revenue'])

        with self.assertRaisesRegex(UserError, 'Only posted, open items on reconcilable accounts'):
            (receivable | revenue).action_flousflow_reconcile_open_items()

        self.assertFalse(receivable.reconciled)

    def test_reconcilable_general_account_items_are_supported(self):
        account = self.company_data['default_account_expense']
        account.reconcile = True
        offset = self.company_data['default_account_revenue']

        def entry(ref, debit, credit):
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'date': fields.Date.from_string('2026-08-10'),
                'journal_id': self.company_data['default_journal_misc'].id,
                'ref': ref,
                'line_ids': [
                    Command.create({
                        'name': ref, 'account_id': account.id,
                        'partner_id': self.partner_a.id,
                        'debit': debit, 'credit': credit,
                    }),
                    Command.create({
                        'name': ref, 'account_id': offset.id,
                        'debit': credit, 'credit': debit,
                    }),
                ],
            })
            move.action_post()
            return move

        debit_move = entry('GENERAL-DEBIT', 100.0, 0.0)
        credit_move = entry('GENERAL-CREDIT', 0.0, 40.0)
        lines = (debit_move | credit_move).line_ids.filtered(
            lambda line: line.account_id == account)

        lines.action_flousflow_reconcile_open_items()

        self.assertTrue(lines.mapped('matched_debit_ids') or lines.mapped('matched_credit_ids'))
        self.assertAlmostEqual(sum(lines.mapped('amount_residual')), 60.0, places=2)

    def test_reconciliation_menu_uses_enterprise_open_item_scope_and_filters(self):
        action = self.env.ref(
            'flousflow_accounting.flousflow_open_item_reconciliation_action')
        self.assertEqual(safe_eval(action.domain), [
            ('display_type', 'not in', ('line_section', 'line_subsection', 'line_note')),
            ('account_id.reconcile', '=', True),
            ('full_reconcile_id', '=', False),
            ('parent_state', '!=', 'cancel'),
        ])
        context = safe_eval(action.context)
        self.assertEqual(context['journal_type'], 'general')
        self.assertEqual(context['search_default_posted'], 1)
        self.assertEqual(context['search_default_unreconciled'], 1)
        self.assertNotIn('search_default_reconcilable_account', context)
        self.assertEqual(context['search_default_group_by_account'], 1)
        self.assertEqual(context['search_default_group_by_partner'], 1)
