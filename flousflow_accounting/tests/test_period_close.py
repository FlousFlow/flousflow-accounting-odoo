# -*- coding: utf-8 -*-
from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase


class TestPeriodClose(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.manager = cls.env['res.users'].create({
            'name': 'Close Manager',
            'login': 'close_manager',
            'email': 'close.manager@example.com',
            'company_id': cls.company.id,
            'company_ids': [Command.set([cls.company.id])],
            'group_ids': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('account.group_account_manager').id,
            ])],
        })
        cls.accountant = cls.env['res.users'].create({
            'name': 'Close Accountant',
            'login': 'close_accountant',
            'email': 'close.accountant@example.com',
            'company_id': cls.company.id,
            'company_ids': [Command.set([cls.company.id])],
            'group_ids': [Command.set([
                cls.env.ref('base.group_user').id,
                cls.env.ref('account.group_account_user').id,
            ])],
        })

    def _create_close(self, **extra):
        values = {
            'date_start': '2024-01-01',
            'date_end': '2024-01-31',
            'company_id': self.company.id,
            'reviewer_id': self.manager.id,
        }
        values.update(extra)
        return self.env['flousflow.account.period.close'].create(values)

    def _complete(self, close):
        close.task_ids.write({'done': True})

    def test_complete_close_applies_standard_soft_locks(self):
        close = self._create_close()
        self.assertEqual(len(close.task_ids), 6)
        self._complete(close)
        close.action_submit()
        close.with_user(self.manager).action_approve()
        close.with_user(self.manager).action_close()
        self.assertEqual(close.state, 'closed')
        self.assertEqual(self.company.fiscalyear_lock_date.isoformat(), '2024-01-31')
        self.assertEqual(self.company.tax_lock_date.isoformat(), '2024-01-31')
        self.assertEqual(self.company.sale_lock_date.isoformat(), '2024-01-31')
        self.assertEqual(self.company.purchase_lock_date.isoformat(), '2024-01-31')
        self.assertFalse(self.company.hard_lock_date)

    def test_incomplete_checklist_blocks_submission(self):
        close = self._create_close()
        with self.assertRaises(UserError):
            close.action_submit()

    def test_draft_entry_blocks_submission(self):
        close = self._create_close(date_start='2024-02-01', date_end='2024-02-29')
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id), ('type', '=', 'general')], limit=1)
        self.env['account.move'].create({
            'move_type': 'entry', 'date': '2024-02-15',
            'journal_id': journal.id,
        })
        self._complete(close)
        with self.assertRaises(UserError):
            close.action_submit()

    def test_accountant_cannot_approve_or_close_over_rpc(self):
        close = self._create_close(date_start='2024-03-01', date_end='2024-03-31')
        self._complete(close)
        close.action_submit()
        with self.assertRaises(AccessError):
            close.with_user(self.accountant).action_approve()

    def test_manager_cannot_approve_a_period_outside_allowed_companies(self):
        other_company = self.env['res.company'].create({'name': 'Other Close Co'})
        close = self.env['flousflow.account.period.close'].create({
            'date_start': '2024-05-01',
            'date_end': '2024-05-31',
            'company_id': other_company.id,
            'reviewer_id': self.manager.id,
        })
        close.task_ids.write({'done': True})
        close.action_submit()

        with self.assertRaises(AccessError):
            close.with_user(self.manager).action_approve()

    def test_overlap_and_approved_immutability(self):
        close = self._create_close(date_start='2024-04-01', date_end='2024-04-30')
        with self.assertRaises(ValidationError):
            self._create_close(date_start='2024-04-15', date_end='2024-05-15')
        self._complete(close)
        close.action_submit()
        close.with_user(self.manager).action_approve()
        with self.assertRaises(UserError):
            close.write({'date_end': '2024-04-29'})
        with self.assertRaises(UserError):
            close.unlink()
