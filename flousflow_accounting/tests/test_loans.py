# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestLoans(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.journal = self.env['account.journal'].search([
            ('type', '=', 'general'), ('company_id', '=', self.company.id)], limit=1)
        self.cash = self.env['account.account'].search([
            ('account_type', 'in', ('asset_cash', 'asset_current'))], limit=1)
        self.liability = self.env['account.account'].search([
            ('account_type', 'in', ('liability_current', 'liability_non_current', 'liability_payable'))], limit=1)
        self.interest = self.env['account.account'].search([
            ('account_type', 'in', ('expense', 'expense_direct_cost', 'expense_depreciation'))], limit=1)
        if not all((self.journal, self.cash, self.liability, self.interest)):
            self.skipTest('Required loan accounting configuration is unavailable')
        self.lender = self.env['res.partner'].create({'name': 'Test Lender'})

    def _loan(self, **extra):
        values = {
            'description': 'Equipment finance', 'lender_id': self.lender.id,
            'principal_amount': 12000.0, 'annual_interest_rate': 12.0,
            'installment_count': 12, 'payment_frequency': 'monthly',
            'computation_method': 'annuity', 'start_date': '2026-01-01',
            'first_payment_date': '2026-02-01', 'journal_id': self.journal.id,
            'cash_account_id': self.cash.id, 'liability_account_id': self.liability.id,
            'interest_account_id': self.interest.id,
        }
        values.update(extra)
        return self.env['flousflow.account.loan'].create(values)

    def test_annuity_schedule_reconciles_principal(self):
        loan = self._loan()
        loan.action_generate_schedule()
        self.assertEqual(len(loan.line_ids), 12)
        self.assertAlmostEqual(sum(loan.line_ids.mapped('principal_amount')), 12000.0, places=2)
        self.assertAlmostEqual(loan.line_ids[-1].closing_balance, 0.0, places=2)
        self.assertGreater(loan.total_interest, 0.0)

    def test_fixed_principal_and_interest_only_schedules(self):
        fixed = self._loan(computation_method='fixed_principal', installment_count=4)
        fixed.action_generate_schedule()
        self.assertTrue(all(abs(value - 3000.0) < 0.01 for value in fixed.line_ids.mapped('principal_amount')))
        interest_only = self._loan(computation_method='interest_only', installment_count=4)
        interest_only.action_generate_schedule()
        self.assertEqual(interest_only.line_ids[:-1].mapped('principal_amount'), [0.0, 0.0, 0.0])
        self.assertAlmostEqual(interest_only.line_ids[-1].principal_amount, 12000.0, places=2)

    def test_confirm_and_installment_accounting(self):
        loan = self._loan(installment_count=2)
        loan.action_confirm()
        self.assertEqual(loan.state, 'running')
        self.assertEqual(loan.disbursement_move_id.state, 'posted')
        self.assertAlmostEqual(sum(loan.disbursement_move_id.line_ids.mapped('balance')), 0.0, places=2)
        cash_line = loan.disbursement_move_id.line_ids.filtered(lambda line: line.account_id == self.cash)
        self.assertAlmostEqual(cash_line.debit, 12000.0, places=2)
        first = loan.line_ids[0]
        first.action_post()
        self.assertEqual(first.state, 'posted')
        self.assertAlmostEqual(sum(first.move_id.line_ids.mapped('balance')), 0.0, places=2)
        self.assertAlmostEqual(
            first.move_id.line_ids.filtered(lambda line: line.account_id == self.interest).debit,
            first.interest_amount, places=2)
        with self.assertRaises(UserError):
            first.action_post()

    def test_cancel_reverses_disbursement_but_rejects_paid_loan(self):
        loan = self._loan(installment_count=2)
        loan.action_confirm()
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancelled')
        self.assertTrue(loan.disbursement_move_id.reversal_move_ids)
        paid = self._loan(installment_count=2)
        paid.action_confirm()
        paid.line_ids[0].action_post()
        with self.assertRaises(UserError):
            paid.action_cancel()

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(ValidationError):
            self._loan(principal_amount=0)
        with self.assertRaises(ValidationError):
            self._loan(first_payment_date='2025-12-31')

    def test_loan_analysis_action_has_business_views(self):
        action = self.env.ref('flousflow_accounting.flousflow_loan_action')
        self.assertEqual(action.view_mode, 'list,form,pivot,graph')

    def test_accountant_cannot_confirm_loan_through_rpc(self):
        accountant = self.env['res.users'].create({
            'name': 'Loan Accountant', 'login': 'loan.accountant@example.com',
            'company_id': self.company.id,
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('account.group_account_user').id])],
        })
        loan = self._loan()
        with self.assertRaises(UserError):
            loan.with_user(accountant).action_confirm()
