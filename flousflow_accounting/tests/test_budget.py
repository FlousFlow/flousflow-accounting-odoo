# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestBudget(TransactionCase):

    def setUp(self):
        super().setUp()
        self.income = self.env['account.account'].search(
            [('account_type', '=', 'income')], limit=1)
        self.expense = self.env['account.account'].search(
            [('account_type', '=', 'expense')], limit=1)
        self.receivable = self.env['account.account'].search(
            [('account_type', '=', 'asset_receivable')], limit=1)
        self.payable = self.env['account.account'].search(
            [('account_type', '=', 'liability_payable')], limit=1)
        if not all([self.income, self.expense, self.receivable, self.payable]):
            self.skipTest('Required accounts not available')

    def _post(self, debit_acc, credit_acc, amount, day):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-01-%02d' % day,
            'line_ids': [
                (0, 0, {'account_id': debit_acc.id, 'debit': amount,
                        'credit': 0.0, 'name': 'D'}),
                (0, 0, {'account_id': credit_acc.id, 'debit': 0.0,
                        'credit': amount, 'name': 'C'}),
            ],
        })
        move.action_post()

    def test_budget_actuals(self):
        self._post(self.receivable, self.income, 600.0, 10)
        self._post(self.expense, self.payable, 200.0, 15)

        budget = self.env['flousflow.account.budget'].create({
            'name': '2026 Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'line_ids': [
                (0, 0, {
                    'account_ids': [(6, 0, [self.income.id])],
                    'date_from': '2026-01-01',
                    'date_to': '2026-12-31',
                    'planned_amount': 1000.0,
                }),
                (0, 0, {
                    'account_ids': [(6, 0, [self.expense.id])],
                    'date_from': '2026-01-01',
                    'date_to': '2026-12-31',
                    'planned_amount': -500.0,
                }),
            ],
        })
        rev = budget.line_ids.filtered(lambda l: self.income in l.account_ids)
        cost = budget.line_ids.filtered(lambda l: self.expense in l.account_ids)
        self.assertAlmostEqual(rev.practical_amount, 600.0, places=2)
        self.assertAlmostEqual(cost.practical_amount, -200.0, places=2)

    def test_budget_state_flow(self):
        budget = self.env['flousflow.account.budget'].create({
            'name': 'Flow Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        self.assertEqual(budget.state, 'draft')
        budget.action_confirm()
        self.assertEqual(budget.state, 'confirm')
        budget.action_validate()
        self.assertEqual(budget.state, 'validate')
        budget.action_done()
        self.assertEqual(budget.state, 'done')

    def test_budget_rejects_invalid_state_transition(self):
        budget = self.env['flousflow.account.budget'].create({
            'name': 'Controlled Flow',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        with self.assertRaises(UserError):
            budget.action_validate()
        budget.action_confirm()
        budget.action_cancel()
        budget.action_draft()
        self.assertEqual(budget.state, 'draft')

    def test_budget_line_requires_account(self):
        budget = self.env['flousflow.account.budget'].create({
            'name': 'No Account',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        line = self.env['flousflow.account.budget.line'].create({
            'budget_id': budget.id,
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'planned_amount': 100.0,
        })
        # No accounts: practical amount must stay 0 without error
        self.assertEqual(line.practical_amount, 0.0)

    def test_expense_overrun_is_flagged(self):
        self._post(self.expense, self.payable, 1200.0, 15)
        budget = self.env['flousflow.account.budget'].create({
            'name': 'Expense Control',
            'date_from': '2026-01-01',
            'date_to': '2026-06-30',
            'line_ids': [(0, 0, {
                'account_ids': [(6, 0, [self.expense.id])],
                'date_from': '2026-01-01',
                'date_to': '2026-06-30',
                'planned_amount': -1000.0,
            })],
        })
        line = budget.line_ids
        self.assertAlmostEqual(line.practical_amount, -1200.0, places=2)
        self.assertTrue(line.is_above_budget)

    def test_budget_line_must_stay_inside_budget_period(self):
        budget = self.env['flousflow.account.budget'].create({
            'name': 'Annual Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.budget.line'].create({
                'budget_id': budget.id,
                'account_ids': [(6, 0, [self.expense.id])],
                'date_from': '2025-12-01',
                'date_to': '2026-12-31',
                'planned_amount': -1000.0,
            })

    def test_budget_actuals_can_be_filtered_by_analytic_account(self):
        plan = self.env['account.analytic.plan'].create({'name': 'Budget Plan'})
        analytic = self.env['account.analytic.account'].create({
            'name': 'Project Alpha',
            'plan_id': plan.id,
        })
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-01-20',
            'line_ids': [
                (0, 0, {
                    'account_id': self.expense.id,
                    'debit': 200.0,
                    'name': 'Analytic expense',
                    'analytic_distribution': {str(analytic.id): 100},
                }),
                (0, 0, {
                    'account_id': self.payable.id,
                    'credit': 200.0,
                    'name': 'Payable',
                }),
            ],
        })
        move.action_post()
        self._post(self.expense, self.payable, 100.0, 21)
        budget = self.env['flousflow.account.budget'].create({
            'name': 'Analytic Budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'line_ids': [(0, 0, {
                'account_ids': [(6, 0, self.expense.ids)],
                'analytic_account_ids': [(6, 0, analytic.ids)],
                'date_from': '2026-01-01',
                'date_to': '2026-12-31',
                'planned_amount': -500.0,
            })],
        })
        self.assertAlmostEqual(budget.line_ids.practical_amount, -200.0, places=2)
