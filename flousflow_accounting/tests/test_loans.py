# -*- coding: utf-8 -*-
import ast
from datetime import timedelta

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
        self.assertEqual(action.view_mode, 'list,form,kanban,pivot,graph')
        kanban = self.env.ref('flousflow_accounting.flousflow_loan_kanban_view')
        self.assertEqual(kanban.model, action.res_model)
        self.assertIn('<kanban', kanban.arch)
        self.assertIn('outstanding_principal', kanban.arch)
        loan_list = self.env.ref('flousflow_accounting.flousflow_loan_list_view')
        for field_name in (
                'principal_amount', 'currency_id', 'start_date', 'end_date',
                'interest_account_id', 'outstanding_principal', 'state'):
            self.assertIn(f'name="{field_name}"', loan_list.arch)
        self.assertIn('string="Amount Borrowed"', loan_list.arch)
        self.assertIn('string="Outstanding Balance"', loan_list.arch)

        analysis_action = self.env.ref(
            'flousflow_accounting.flousflow_loan_analysis_action')
        self.assertEqual(analysis_action.res_model, 'flousflow.account.loan.line')
        self.assertEqual(analysis_action.view_mode, 'list,form')
        context = ast.literal_eval(analysis_action.context or '{}')
        self.assertEqual(context.get('search_default_current'), 1)
        self.assertNotIn('search_default_group_by_loan', context)
        ordered_views = analysis_action.view_ids.sorted('sequence').mapped(
            lambda action_view: action_view.view_mode)
        self.assertEqual(ordered_views, ['pivot', 'list', 'form'])
        search = self.env.ref(
            'flousflow_accounting.flousflow_loan_line_search_view')
        self.assertIn('name="current"', search.arch)
        self.assertIn('loan_name', search.arch)
        self.assertIn('name="loan_line_date"', search.arch)
        self.assertIn('date="date"', search.arch)
        self.assertIn('name="group_by_asset_group"', search.arch)
        analysis_list = self.env.ref(
            'flousflow_accounting.flousflow_loan_line_list_view')
        for field_name in (
                'loan_date', 'loan_asset_group_id', 'principal_amount',
                'interest_amount', 'payment_amount',
                'long_term_theoretical_balance',
                'short_term_theoretical_balance'):
            self.assertIn(f'name="{field_name}"', analysis_list.arch)
        analysis_pivot = self.env.ref(
            'flousflow_accounting.flousflow_loan_line_pivot_view')
        self.assertLess(
            analysis_pivot.arch.index('name="date"'),
            analysis_pivot.arch.index('name="loan_id"'))
        self.assertIn('interval="year"', analysis_pivot.arch)
        for field_name, label in (
                ('principal_amount', 'Principal'),
                ('interest_amount', 'Interest'),
                ('payment_amount', 'Payment')):
            self.assertIn(
                f'name="{field_name}" type="measure" string="{label}"',
                analysis_pivot.arch)
        self.assertNotIn('closing_balance', analysis_pivot.arch)

        loan = self._loan()
        loan.action_generate_schedule()
        self.assertEqual(loan.end_date, loan.line_ids[-1].date)
        installment = loan.line_ids[0]
        self.assertEqual(installment.loan_name, loan.name)
        self.assertEqual(installment.loan_state, 'draft')
        self.assertEqual(installment.loan_date, loan.start_date)
        self.assertEqual(installment.active, loan.active)
        self.assertEqual(installment.long_term_theoretical_balance, 0.0)
        self.assertGreater(installment.short_term_theoretical_balance, 0.0)
        self.assertEqual(
            loan.line_ids.filtered_domain([
                ('loan_state', 'in', ('draft', 'running'))]), loan.line_ids)

        extended_loan = self._loan(
            installment_count=36, start_date='2026-01-01',
            first_payment_date='2026-02-01')
        extended_loan.action_generate_schedule()
        first_installment = extended_loan.line_ids[0]
        expected_year_end = self.company.compute_fiscalyear_dates(
            first_installment.date)['date_to']
        next_year_end = self.company.compute_fiscalyear_dates(
            expected_year_end + timedelta(days=1))['date_to']
        remaining = extended_loan.line_ids.filtered(
            lambda installment: installment.date > first_installment.date)
        expected_short_term = sum(
            installment.principal_amount for installment in remaining
            if installment.date <= next_year_end)
        self.assertAlmostEqual(
            first_installment.short_term_theoretical_balance,
            expected_short_term, places=2)
        self.assertGreater(first_installment.long_term_theoretical_balance, 0.0)

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
