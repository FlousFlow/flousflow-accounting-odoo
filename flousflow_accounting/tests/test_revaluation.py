# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError


class TestRevaluation(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.foreign_currency = cls.env['res.currency'].create({
            'name': 'FXU',
            'symbol': 'FX',
            'rounding': 0.01,
        })
        cls.env['res.currency.rate'].create({
            'name': '2026-08-01',
            'currency_id': cls.foreign_currency.id,
            'company_id': cls.company.id,
            'rate': 2.0,
        })
        cls.exchange_journal = cls.company_data['default_journal_misc']

    def _posted_foreign_receivable(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': fields.Date.from_string('2026-08-01'),
            'currency_id': self.foreign_currency.id,
            'invoice_line_ids': [Command.create({
                'name': 'FX sale',
                'quantity': 1,
                'price_unit': 100,
                'account_id': self.company_data['default_account_revenue'].id,
            })],
        })
        invoice.action_post()
        return invoice

    def test_compute_lines_and_revalue(self):
        self.company.write({
            'income_currency_exchange_account_id': self.company_data['default_account_revenue'].id,
            'expense_currency_exchange_account_id': self.company_data['default_account_expense'].id,
        })
        self._posted_foreign_receivable()
        wizard = self.env['flousflow.account.revaluation.wizard'].create({
            'company_id': self.company.id,
            'currency_ids': [Command.set([self.foreign_currency.id])],
            'date': '2026-08-15',
            'journal_id': self.exchange_journal.id,
            'mode': 'revaluation',
        })
        wizard._onchange_compute_lines()
        self.assertTrue(wizard.line_ids, 'Expected revaluation lines to be computed.')
        action = wizard.action_revaluate()
        moves = self.env['account.move'].search(action['domain'])
        self.assertTrue(moves, 'Expected an exchange difference entry.')
        self.assertTrue(all(m.state == 'posted' for m in moves))

    def test_adjustment_requires_reversal_date(self):
        wizard = self.env['flousflow.account.revaluation.wizard'].create({
            'company_id': self.company.id,
            'currency_ids': [Command.set([self.foreign_currency.id])],
            'date': '2026-08-15',
            'journal_id': self.exchange_journal.id,
            'mode': 'adjustment',
        })
        with self.assertRaises(UserError):
            wizard.action_revaluate()
