# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestFollowup(TransactionCase):

    def setUp(self):
        super().setUp()
        self.receivable = self.env['account.account'].search(
            [('account_type', '=', 'asset_receivable')], limit=1)
        self.income = self.env['account.account'].search(
            [('account_type', '=', 'income')], limit=1)
        if not self.receivable or not self.income:
            self.skipTest('Required accounts not available')

    def test_followup_config_constraint(self):
        config = self.env['flousflow.account.followup'].create({
            'followup_line_ids': [
                (0, 0, {'name': 'Level 1', 'delay': 0}),
                (0, 0, {'name': 'Level 2', 'delay': 30}),
            ],
        })
        self.assertEqual(len(config.followup_line_ids), 2)

    def test_followup_process(self):
        config = self.env['flousflow.account.followup'].create({
            'followup_line_ids': [
                (0, 0, {'name': 'Level 1', 'delay': 0,
                        'send_email': False, 'send_letter': False}),
                (0, 0, {'name': 'Level 2', 'delay': 30,
                        'send_email': False, 'send_letter': False}),
            ],
        })
        partner = self.env['res.partner'].create({'name': 'Overdue Partner'})
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-01-10',
            'line_ids': [
                (0, 0, {
                    'account_id': self.receivable.id,
                    'debit': 500.0, 'credit': 0.0,
                    'partner_id': partner.id,
                    'date_maturity': '2026-02-10',
                    'name': 'Sale',
                }),
                (0, 0, {
                    'account_id': self.income.id,
                    'debit': 0.0, 'credit': 500.0,
                    'name': 'Sale',
                }),
            ],
        })
        move.action_post()

        wizard = self.env['flousflow.account.followup.wizard'].create({
            'company_id': self.env.company.id,
            'date': '2026-08-15',
        })
        wizard.action_process()

        line = move.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable')
        self.assertTrue(line.followup_line_id)
        # 186 days overdue -> highest level reached
        self.assertEqual(line.followup_line_id.delay, 30)
        self.assertEqual(line.followup_date, date(2026, 8, 15))
        with self.assertRaises(UserError):
            wizard.action_print_letters()
        line.followup_line_id.send_letter = True
        action = wizard.action_print_letters()
        if action['type'] == 'ir.actions.act_window':
            action = action['context']['report_action']
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(
            action['report_name'],
            'flousflow_accounting.report_followup_letters')

    def test_total_overdue_excludes_not_yet_due_receivables(self):
        partner = self.env['res.partner'].create({'name': 'Aging Partner'})
        for amount, maturity in ((500.0, '2026-01-01'), (300.0, '2027-01-01')):
            move = self.env['account.move'].create({
                'move_type': 'entry',
                'date': '2026-01-01',
                'line_ids': [
                    (0, 0, {
                        'account_id': self.receivable.id,
                        'debit': amount,
                        'partner_id': partner.id,
                        'date_maturity': maturity,
                        'name': 'Receivable',
                    }),
                    (0, 0, {
                        'account_id': self.income.id,
                        'credit': amount,
                        'name': 'Revenue',
                    }),
                ],
            })
            move.action_post()

        self.assertAlmostEqual(partner.total_overdue, 500.0, places=2)

    def test_manual_followup_creates_history_and_activity(self):
        responsible = self.env.user
        self.env['flousflow.account.followup'].create({
            'followup_line_ids': [(0, 0, {
                'name': 'Call Customer', 'delay': 0,
                'send_email': False, 'send_letter': False,
                'manual_action': True,
                'manual_action_note': 'Call about overdue invoice',
                'manual_action_responsible_id': responsible.id,
            })],
        })
        partner = self.env['res.partner'].create({'name': 'Activity Customer'})
        move = self.env['account.move'].create({
            'move_type': 'entry', 'date': '2026-01-01',
            'line_ids': [
                (0, 0, {
                    'account_id': self.receivable.id, 'debit': 250.0,
                    'partner_id': partner.id, 'date_maturity': '2026-01-05',
                    'name': 'Receivable',
                }),
                (0, 0, {
                    'account_id': self.income.id, 'credit': 250.0,
                    'name': 'Revenue',
                }),
            ],
        })
        move.action_post()
        self.env['flousflow.account.followup.wizard'].create({
            'date': '2026-02-01', 'partner_ids': partner.ids,
        }).action_process()

        history = self.env['flousflow.account.followup.history'].search([
            ('partner_id', '=', partner.id),
        ])
        self.assertEqual(len(history), 1)
        self.assertEqual(history.level_id.name, 'Call Customer')
        activity = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'), ('res_id', '=', partner.id),
            ('user_id', '=', responsible.id),
        ])
        self.assertTrue(activity)
        self.assertEqual(activity.summary, 'Call Customer')

    def test_automatic_followup_is_opt_in_and_idempotent_per_level(self):
        config = self.env['flousflow.account.followup'].create({
            'automatic': True,
            'followup_line_ids': [(0, 0, {
                'name': 'Automatic Reminder', 'delay': 0,
                'send_email': False, 'send_letter': False,
                'repeat_every_days': 0,
            })],
        })
        partner = self.env['res.partner'].create({'name': 'Automatic Customer'})
        move = self.env['account.move'].create({
            'move_type': 'entry', 'date': '2026-01-01',
            'line_ids': [
                (0, 0, {
                    'account_id': self.receivable.id, 'debit': 100.0,
                    'partner_id': partner.id, 'date_maturity': '2026-01-05',
                    'name': 'Automatic receivable',
                }),
                (0, 0, {
                    'account_id': self.income.id, 'credit': 100.0,
                    'name': 'Revenue',
                }),
            ],
        })
        move.action_post()

        config.with_context(followup_date=date(2026, 2, 1))._cron_process_automatic_followup()
        config.with_context(followup_date=date(2026, 2, 2))._cron_process_automatic_followup()

        history = self.env['flousflow.account.followup.history'].search([
            ('partner_id', '=', partner.id),
        ])
        self.assertEqual(len(history), 1)
        self.assertEqual(history.level_id.name, 'Automatic Reminder')

    def test_payment_promise_lifecycle_has_no_accounting_entry(self):
        partner = self.env['res.partner'].create({'name': 'Promise Customer', 'customer_rank': 1})
        move_count = self.env['account.move'].search_count([])
        promise = self.env['flousflow.account.payment.promise'].create({
            'partner_id': partner.id, 'amount': 500,
            'promise_date': '2026-09-01',
        })
        promise.action_mark_kept()
        self.assertEqual(promise.state, 'kept')
        self.assertTrue(promise.resolved_date)
        self.assertEqual(self.env['account.move'].search_count([]), move_count)
        with self.assertRaises(UserError):
            promise.action_mark_broken()

    def test_payment_promise_requires_positive_amount(self):
        partner = self.env['res.partner'].create({'name': 'Invalid Promise Customer', 'customer_rank': 1})
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.payment.promise'].create({
                'partner_id': partner.id, 'amount': 0,
                'promise_date': '2026-09-01',
            })
