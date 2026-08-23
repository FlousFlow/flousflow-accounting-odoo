# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo.tests.common import TransactionCase


class TestFinancialReportEngine(TransactionCase):

    def setUp(self):
        super().setUp()
        self.receivable = self.env['account.account'].search(
            [('account_type', '=', 'asset_receivable')], limit=1)
        self.payable = self.env['account.account'].search(
            [('account_type', '=', 'liability_payable')], limit=1)
        self.income = self.env['account.account'].search(
            [('account_type', '=', 'income')], limit=1)
        self.expense = self.env['account.account'].search(
            [('account_type', '=', 'expense')], limit=1)
        if not all([self.receivable, self.payable, self.income, self.expense]):
            self.skipTest('Required accounts not available')

    def _post(self, debit_acc, credit_acc, amount, posting_date='2026-03-15'):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': posting_date,
            'line_ids': [
                (0, 0, {'account_id': debit_acc.id, 'debit': amount,
                        'credit': 0.0, 'name': 'D'}),
                (0, 0, {'account_id': credit_acc.id, 'debit': 0.0,
                        'credit': amount, 'name': 'C'}),
            ],
        })
        move.action_post()

    def test_templates_exist(self):
        pl = self.env['flousflow.account.report.template'].search(
            [('code', '=', 'profit_loss')], limit=1)
        bs = self.env['flousflow.account.report.template'].search(
            [('code', '=', 'balance_sheet')], limit=1)
        self.assertTrue(pl)
        self.assertTrue(bs)

    def test_profit_loss_engine(self):
        self._post(self.receivable, self.income, 1000.0)
        self._post(self.expense, self.payable, 300.0)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'profit_loss',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        net = wizard.line_ids.filtered(lambda l: l.code == 'net_profit')
        self.assertEqual(len(net), 1)
        self.assertAlmostEqual(net.balance, 700.0, places=2)
        # hierarchy rendered with levels
        self.assertTrue(any(l.level > 0 for l in wizard.line_ids))

    def test_balance_sheet_engine(self):
        self._post(self.receivable, self.income, 1000.0)
        self._post(self.expense, self.payable, 300.0)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'balance_sheet',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        by_code = {l.code: l.balance for l in wizard.line_ids}
        self.assertAlmostEqual(by_code.get('total_assets', 0.0), 1000.0, places=2)
        self.assertAlmostEqual(by_code.get('total_liabilities', 0.0), 300.0, places=2)
        self.assertAlmostEqual(by_code.get('current_year_earnings', 0.0), 700.0, places=2)
        self.assertAlmostEqual(
            by_code.get('unallocated_profit_loss', 0.0), 0.0, places=2)

    def test_balance_sheet_current_earnings_respect_company_fiscal_year(self):
        self.company = self.env.company
        self.company.write({
            'fiscalyear_last_day': 30,
            'fiscalyear_last_month': '6',
        })
        self._post(
            self.receivable, self.income, 400.0,
            posting_date='2025-06-15')
        self._post(
            self.receivable, self.income, 1000.0,
            posting_date='2025-07-15')
        self._post(
            self.expense, self.payable, 300.0,
            posting_date='2026-03-15')

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'balance_sheet',
            'date_from': '2026-01-01',
            'date_to': '2026-03-31',
        })
        wizard.action_generate()
        current = wizard.line_ids.filtered(
            lambda line: line.code == 'current_year_earnings')
        self.assertAlmostEqual(current.balance, 700.0, places=2)
        self.assertFalse(wizard.line_ids.filtered(
            lambda line: line.code in ('current_year_income', 'current_year_expenses')))
