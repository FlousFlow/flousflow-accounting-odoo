# -*- coding: utf-8 -*-
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestStandardAppIntegrations(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.close = cls.env['flousflow.account.period.close'].create({
            'date_start': '2026-07-01',
            'date_end': '2026-07-31',
            'company_id': cls.env.company.id,
            'reviewer_id': cls.env.user.id,
        })
        cls.close.task_ids.write({'done': True})

    def test_standard_accounting_link_fields_are_available(self):
        expected_fields = {
            'hr.expense': 'account_move_id',
            'mrp.production': 'wip_move_ids',
            'pos.session': 'move_id',
            'project.project': 'account_id',
            'stock.move': 'account_move_id',
        }
        for model_name, field_name in expected_fields.items():
            self.assertIn(field_name, self.env[model_name]._fields)
        self.assertIn(
            'analytic_distribution', self.env['account.move.line']._fields)

    def test_open_pos_session_blocks_period_submission(self):
        Session = type(self.env['pos.session'])
        original = Session.search_count

        def search_count(recordset, domain, *args, **kwargs):
            if ('state', '!=', 'closed') in domain:
                return 1
            return original(recordset, domain, *args, **kwargs)

        with patch.object(Session, 'search_count', search_count):
            with self.assertRaisesRegex(UserError, 'not closed and posted'):
                self.close.action_submit()

    def test_pos_menu_is_single_and_uses_standard_action(self):
        menu = self.env.ref(
            'flousflow_accounting.menu_flousflow_accounting_pos_sessions')
        self.assertEqual(
            menu.parent_id, self.env.ref('account.account_transactions_menu'))
        self.assertEqual(menu.action.res_model, 'pos.session')
        matching = self.env['ir.ui.menu'].search([
            ('parent_id', '=', self.env.ref(
                'account.account_transactions_menu').id),
            ('action', '=', f'ir.actions.act_window,{menu.action.id}'),
            ('active', '=', True),
        ])
        self.assertEqual(matching, menu)

    def test_posted_operational_entry_is_read_once_by_general_ledger(self):
        debit_account = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id),
            ('account_type', '=', 'asset_cash'),
        ], limit=1)
        credit_account = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id),
            ('account_type', '=', 'income'),
        ], limit=1)
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id),
            ('type', '=', 'general'),
        ], limit=1)
        if not debit_account or not credit_account or not journal:
            self.skipTest('A configured accounting chart is required')
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': '2026-07-15',
            'ref': 'STANDARD APP INTEGRATION PROOF',
            'line_ids': [
                Command.create({
                    'name': 'Operational debit',
                    'account_id': debit_account.id,
                    'debit': 125.0,
                }),
                Command.create({
                    'name': 'Operational credit',
                    'account_id': credit_account.id,
                    'credit': 125.0,
                }),
            ],
        })
        move.action_post()
        report = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-07-01',
            'date_to': '2026-07-31',
            'account_ids': [Command.set(debit_account.ids)],
        })
        report.action_generate()
        report_lines = report.line_ids.filtered(
            lambda line: line.move_id == move)
        self.assertEqual(len(report_lines), 1)
        self.assertAlmostEqual(report_lines.balance, 125.0, places=2)
