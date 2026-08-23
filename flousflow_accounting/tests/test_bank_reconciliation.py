# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError, ValidationError


class TestBankReconciliation(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.partner_a
        cls.bank_journal = cls.company_data['default_journal_bank']

    def _invoice(self, amount, ref):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.from_string('2026-08-01'),
            'payment_reference': ref,
            'invoice_line_ids': [Command.create({
                'name': ref,
                'quantity': 1,
                'price_unit': amount,
                'account_id': self.company_data['default_account_revenue'].id,
            })],
        })
        invoice.action_post()
        return invoice

    def _bank_line(self, amount, ref, partner=None):
        return self.env['account.bank.statement.line'].create({
            'journal_id': self.bank_journal.id,
            'date': fields.Date.from_string('2026-08-03'),
            'payment_ref': ref,
            'partner_id': (partner or self.partner).id,
            'amount': amount,
        })

    def _wizard(self, bank_line):
        wizard = self.env['flousflow.account.bank.reconcile.session'].create({
            'statement_line_id': bank_line.id,
            'company_id': bank_line.company_id.id,
        })
        wizard._refresh_candidates()
        return wizard

    def test_exact_match_is_ranked_and_reconciled(self):
        invoice = self._invoice(100, 'INV-EXACT-100')
        bank_line = self._bank_line(100, 'INV-EXACT-100')
        wizard = self._wizard(bank_line)
        receivable = invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable')
        candidate = wizard.candidate_ids.filtered(lambda item: item.move_line_id == receivable)

        self.assertTrue(candidate)
        self.assertGreaterEqual(candidate.score, 90)
        candidate.selected = True
        wizard.action_reconcile()

        self.assertTrue(bank_line.is_reconciled)
        self.assertTrue(invoice.payment_state in ('paid', 'in_payment'))

    def test_partial_payment_preserves_invoice_residual(self):
        invoice = self._invoice(150, 'INV-PARTIAL-150')
        bank_line = self._bank_line(60, 'INV-PARTIAL-150')
        wizard = self._wizard(bank_line)
        receivable = invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable')
        candidate = wizard.candidate_ids.filtered(lambda item: item.move_line_id == receivable)
        candidate.selected = True

        wizard.action_reconcile()

        self.assertTrue(bank_line.is_reconciled)
        self.assertAlmostEqual(receivable.amount_residual, 90.0)
        self.assertEqual(invoice.payment_state, 'partial')

    def test_undo_restores_open_invoice_and_bank_transaction(self):
        invoice = self._invoice(80, 'INV-UNDO-80')
        bank_line = self._bank_line(80, 'INV-UNDO-80')
        wizard = self._wizard(bank_line)
        wizard.candidate_ids.filtered(
            lambda item: item.move_line_id.move_id == invoice
        ).selected = True
        wizard.action_reconcile()

        bank_line.action_flousflow_undo_reconciliation()

        self.assertFalse(bank_line.is_reconciled)
        self.assertEqual(invoice.payment_state, 'not_paid')
        self.assertAlmostEqual(invoice.amount_residual, 80.0)

    def test_one_bank_transaction_reconciles_multiple_invoices(self):
        invoice_a = self._invoice(40, 'BATCH-A')
        invoice_b = self._invoice(60, 'BATCH-B')
        bank_line = self._bank_line(100, 'BATCH')
        wizard = self._wizard(bank_line)
        move_lines = (invoice_a | invoice_b).line_ids.filtered(
            lambda line: line.account_type == 'asset_receivable'
        )
        wizard.candidate_ids.filtered(
            lambda item: item.move_line_id in move_lines
        ).selected = True

        wizard.action_reconcile()

        self.assertTrue(bank_line.is_reconciled)
        self.assertTrue(all(move.payment_state in ('paid', 'in_payment') for move in invoice_a | invoice_b))

    def test_vendor_bill_outgoing_transaction(self):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.from_string('2026-08-01'),
            'payment_reference': 'BILL-OUT-70',
            'invoice_line_ids': [Command.create({
                'name': 'BILL-OUT-70',
                'quantity': 1,
                'price_unit': 70,
                'account_id': self.company_data['default_account_expense'].id,
            })],
        })
        bill.action_post()
        bank_line = self._bank_line(-70, 'BILL-OUT-70')
        wizard = self._wizard(bank_line)
        payable = bill.line_ids.filtered(lambda line: line.account_type == 'liability_payable')
        wizard.candidate_ids.filtered(lambda item: item.move_line_id == payable).selected = True

        wizard.action_reconcile()

        self.assertTrue(bank_line.is_reconciled)
        self.assertTrue(bill.payment_state in ('paid', 'in_payment'))

    def test_stale_candidate_is_rejected(self):
        invoice = self._invoice(50, 'STALE-50')
        bank_line = self._bank_line(50, 'STALE-50')
        wizard = self._wizard(bank_line)
        receivable = invoice.line_ids.filtered(lambda line: line.account_type == 'asset_receivable')
        candidate = wizard.candidate_ids.filtered(lambda item: item.move_line_id == receivable)
        candidate.selected = True
        counterpart = self.env['account.move'].create({
            'move_type': 'entry',
            'date': fields.Date.from_string('2026-08-03'),
            'line_ids': [
                Command.create({'account_id': receivable.account_id.id, 'credit': 50, 'partner_id': self.partner.id}),
                Command.create({'account_id': self.company_data['default_account_revenue'].id, 'debit': 50}),
            ],
        })
        counterpart.action_post()
        (receivable + counterpart.line_ids.filtered(lambda line: line.account_id == receivable.account_id)).reconcile()

        with self.assertRaises(UserError):
            wizard.action_reconcile()

    def test_only_manager_can_undo(self):
        invoice = self._invoice(50, 'UNDO-RIGHTS-50')
        bank_line = self._bank_line(50, 'UNDO-RIGHTS-50')
        wizard = self._wizard(bank_line)
        wizard.candidate_ids.filtered(lambda item: item.move_line_id.move_id == invoice).selected = True
        wizard.action_reconcile()
        accountant = self.env['res.users'].create({
            'name': 'Bank Reconciliation Accountant',
            'login': 'bank.reconciliation.accountant@example.com',
            'company_id': self.env.company.id,
            'company_ids': [Command.set(self.env.company.ids)],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
        })
        with self.assertRaises(AccessError):
            bank_line.with_user(accountant).action_flousflow_undo_reconciliation()

    def test_workbench_action_menu_and_acl_exist(self):
        action = self.env.ref('flousflow_accounting.action_flousflow_manual_bank_reconciliation')
        menu = self.env.ref('flousflow_accounting.menu_flousflow_accounting_manual_bank_reconciliation')
        self.assertEqual(action.res_model, 'flousflow.account.bank.reconcile.session')
        self.assertEqual(action.target, 'new')
        self.assertEqual(
            menu.parent_id, self.env.ref('account.account_transactions_menu'))
        for model_name in (
            'flousflow.account.bank.reconcile.session',
            'flousflow.account.bank.reconcile.candidate',
        ):
            model = self.env['ir.model']._get(model_name)
            self.assertTrue(self.env['ir.model.access'].search_count([
                ('model_id', '=', model.id),
                ('group_id', '=', self.env.ref('account.group_account_user').id),
                ('perm_read', '=', True),
                ('perm_write', '=', True),
                ('perm_create', '=', True),
            ]))

    def test_cross_company_candidate_is_rejected(self):
        other_company = self.env['res.company'].create({'name': 'Other Reconciliation Company'})
        self.env.user.company_ids |= other_company
        self.env['account.chart.template'].try_loading(
            'flous_generic_coa', company=other_company, install_demo=False,
        )
        other_env = self.env(context={**self.env.context, 'allowed_company_ids': [other_company.id]})
        receivable = other_env['account.account'].search([
            ('company_ids', 'in', other_company.id),
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)
        income = other_env['account.account'].search([
            ('company_ids', 'in', other_company.id),
            ('account_type', '=', 'income'),
        ], limit=1)
        foreign_move = other_env['account.move'].with_company(other_company).create({
            'move_type': 'entry',
            'date': fields.Date.from_string('2026-08-01'),
            'company_id': other_company.id,
            'line_ids': [
                Command.create({'account_id': receivable.id, 'debit': 50, 'partner_id': self.partner.id}),
                Command.create({'account_id': income.id, 'credit': 50}),
            ],
        })
        foreign_move.action_post()
        foreign_line = foreign_move.line_ids.filtered(lambda line: line.account_id == receivable)
        bank_line = self._bank_line(50, 'COMPANY-GUARD')
        wizard = self._wizard(bank_line)
        candidate = self.env['flousflow.account.bank.reconcile.candidate'].create({
            'session_id': wizard.id,
            'move_line_id': foreign_line.id,
            'match_amount': 50,
            'selected': True,
        })
        self.assertTrue(candidate)
        with self.assertRaises(ValidationError):
            wizard.action_reconcile()
