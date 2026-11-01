# -*- coding: utf-8 -*-
import base64
from datetime import timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'loan_parity')
class TestLoanParity(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'general'), ('company_id', '=', cls.company.id)], limit=1)
        cls.long_term = cls.env['account.account'].search([
            ('account_type', '=', 'liability_non_current'), ('company_ids', 'in', cls.company.id)], limit=1)
        cls.short_term = cls.env['account.account'].search([
            ('account_type', '=', 'liability_current'), ('company_ids', 'in', cls.company.id)], limit=1)
        cls.expense = cls.env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation')),
            ('company_ids', 'in', cls.company.id)], limit=1)

    def _loan(self, **extra):
        values = {
            'amount_borrowed': 12000.0,
            'interest': 1200.0,
            'date': '2026-01-31',
            'duration': 12,
            'long_term_account_id': self.long_term.id,
            'short_term_account_id': self.short_term.id,
            'expense_account_id': self.expense.id,
            'journal_id': self.journal.id,
        }
        values.update(extra)
        return self.env['flousflow.account.loan'].create(values)

    def test_compute_monthly_schedule_and_totals(self):
        loan = self._loan()
        loan.action_compute()
        self.assertEqual(len(loan.line_ids), 12)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal_amount')), 12000.0, places=2)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('interest_amount')), 1200.0, places=2)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('payment_amount')), 13200.0, places=2)
        self.assertEqual(loan.line_ids[0].date.isoformat(), '2026-02-28')
        self.assertEqual(loan.line_ids[-1].date.isoformat(), '2027-01-31')
        self.assertEqual(loan.amount_due, 13200.0)
        self.assertEqual(loan.line_ids[-1].amount_due, 0.0)

    def test_confirmation_creates_future_accounting_entries(self):
        loan = self._loan(duration=2, interest=120.0)
        loan.action_compute()
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')
        self.assertEqual(len(loan.line_ids), 2)
        self.assertEqual(len(loan.move_ids), 6)
        for schedule_line in loan.line_ids:
            self.assertEqual(schedule_line.payment_move_id.state, 'draft')
            self.assertEqual(schedule_line.payment_move_id.auto_post, 'at_date')
            self.assertEqual(schedule_line.reclassification_move_id.state, 'draft')
            self.assertEqual(schedule_line.reclassification_reversal_id.state, 'draft')
            self.assertEqual(schedule_line.reclassification_reversal_id.date,
                             schedule_line.date + timedelta(days=1))
            self.assertAlmostEqual(sum(schedule_line.payment_move_id.line_ids.mapped('balance')), 0.0, places=2)
            self.assertEqual(schedule_line.payment_move_id.journal_id, self.journal)
            principal_line = schedule_line.payment_move_id.line_ids.filtered(
                lambda move_line: move_line.debit and move_line.account_id == self.short_term)
            self.assertAlmostEqual(principal_line.debit, schedule_line.principal_amount, places=2)

    def test_close_wizard_closes_loan_and_removes_future_drafts(self):
        loan = self._loan(duration=2)
        loan.action_compute()
        loan.action_confirm()
        wizard = self.env['flousflow.account.loan.close'].create({
            'loan_id': loan.id,
            'close_date': '2026-01-31',
        })
        wizard.action_close()
        self.assertEqual(loan.state, 'closed')
        self.assertFalse(loan.move_ids)
        self.assertEqual(len(loan.line_ids), 2)

    def test_confirmation_rejects_schedule_total_mismatch(self):
        loan = self._loan(duration=1)
        loan.line_ids.create({
            'loan_id': loan.id, 'sequence': 1, 'date': '2026-02-28',
            'principal_amount': 11999.0, 'interest_amount': 1200.0,
        })
        with self.assertRaises(UserError):
            loan.action_confirm()
        self.assertEqual(loan.state, 'draft')
        self.assertFalse(loan.move_ids)

    def test_csv_import_sets_schedule_and_totals(self):
        loan = self._loan(duration=1)
        wizard = self.env['flousflow.account.loan.upload'].create({
            'loan_id': loan.id,
            'file_name': 'schedule.csv',
            'file_data': base64.b64encode(
                b'date,principal,interest\n2026-02-28,6000.00,120.00\n2026-03-31,6000.00,80.00\n').decode(),
        })
        wizard.action_import()
        self.assertEqual(loan.duration, 2)
        self.assertEqual(len(loan.line_ids), 2)
        self.assertAlmostEqual(loan.amount_borrowed, 12000.0, places=2)
        self.assertAlmostEqual(loan.interest, 200.0, places=2)

    def test_csv_import_rejects_duplicate_dates(self):
        loan = self._loan()
        wizard = self.env['flousflow.account.loan.upload'].create({
            'loan_id': loan.id,
            'file_name': 'schedule.csv',
            'file_data': base64.b64encode(
                b'date,principal,interest\n2026-02-28,6000,50\n2026-02-28,6000,50\n').decode(),
        })
        with self.assertRaisesRegex(UserError, 'unique date'):
            wizard.action_import()

    def test_cancellation_removes_only_unposted_generated_entries(self):
        loan = self._loan(duration=2)
        loan.action_compute()
        loan.action_confirm()
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancelled')
        self.assertFalse(loan.move_ids)
        self.assertEqual(len(loan.line_ids), 2)

    def test_invalid_loan_inputs_and_accounts_are_rejected(self):
        with self.assertRaises(ValidationError):
            self._loan(amount_borrowed=0)
        with self.assertRaises(ValidationError):
            self._loan(duration=0)
        with self.assertRaises(ValidationError):
            self._loan(short_term_account_id=self.long_term.id)

    def test_analysis_action_contains_enterprise_views(self):
        action = self.env.ref('flousflow_accounting.loan_analysis_action')
        self.assertEqual(action.res_model, 'flousflow.account.loan.line')
        self.assertEqual(action.view_mode, 'pivot,graph,list')
        self.assertTrue(self.env.ref('flousflow_accounting.loan_analysis_menu').active)

    def test_only_accounting_managers_can_confirm(self):
        accountant = self.env['res.users'].create({
            'name': 'Loan Accountant', 'login': 'loan.accountant@example.com',
            'company_id': self.company.id, 'company_ids': [(6, 0, [self.company.id])],
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('account.group_account_user').id])],
        })
        loan = self._loan()
        loan.action_compute()
        with self.assertRaises(UserError):
            loan.with_user(accountant).action_confirm()
