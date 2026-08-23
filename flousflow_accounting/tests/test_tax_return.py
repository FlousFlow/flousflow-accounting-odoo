# -*- coding: utf-8 -*-
from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError


class TestTaxReturnReview(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_tag = cls.env['account.account.tag'].create({
            'name': '+FF TAX REVIEW', 'applicability': 'taxes',
            'country_id': cls.env.company.account_fiscal_country_id.id,
        })

    def _tax_move(self, state='posted'):
        move = self.env['account.move'].create({
            'move_type': 'entry', 'date': fields.Date.from_string('2026-07-15'),
            'line_ids': [
                Command.create({
                    'name': 'Tax grid amount',
                    'account_id': self.company_data['default_account_expense'].id,
                    'debit': 140, 'tax_tag_ids': [Command.set(self.tax_tag.ids)],
                }),
                Command.create({
                    'name': 'Counterpart',
                    'account_id': self.company_data['default_account_revenue'].id,
                    'credit': 140,
                }),
            ],
        })
        if state == 'posted':
            move.action_post()
        return move

    def _return(self):
        return self.env['flousflow.account.tax.return'].create({
            'date_from': '2026-07-01', 'date_to': '2026-07-31',
            'reviewer_id': self.env.user.id,
        })

    def test_prepare_uses_posted_localization_tax_tags(self):
        move = self._tax_move()
        record = self._return()
        move_count = self.env['account.move'].search_count([])

        record.action_prepare()

        self.assertEqual(record.line_ids.tag_id, self.tax_tag)
        self.assertAlmostEqual(record.total_amount, 140)
        self.assertEqual(self.env['account.move'].search_count([]), move_count)
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), sum(move.line_ids.mapped('credit')))

    def test_submit_rejects_draft_tax_entries(self):
        self._tax_move()
        record = self._return()
        record.action_prepare()
        self._tax_move(state='draft')

        with self.assertRaises(UserError):
            record.action_submit()

    def test_approval_and_close_apply_tax_lock_without_entry(self):
        self._tax_move()
        record = self._return()
        record.action_prepare()
        record.action_submit()
        record.action_approve()
        move_count = self.env['account.move'].search_count([])

        record.action_close()

        self.assertEqual(record.state, 'closed')
        self.assertEqual(record.company_id.tax_lock_date, record.date_to)
        self.assertEqual(self.env['account.move'].search_count([]), move_count)

    def test_closed_return_is_immutable(self):
        self._tax_move()
        record = self._return()
        record.action_prepare(); record.action_submit(); record.action_approve(); record.action_close()
        with self.assertRaises(UserError):
            record.write({'date_to': '2026-08-31'})
