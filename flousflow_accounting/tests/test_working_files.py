# -*- coding: utf-8 -*-
import ast

from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestWorkingFiles(TransactionCase):

    def test_working_files_action_defaults_to_todo_and_paused(self):
        action = self.env.ref(
            'flousflow_accounting.flousflow_working_file_action')
        self.assertEqual(action.view_mode, 'kanban,list,form')
        self.assertEqual(action.search_view_id,
                         self.env.ref('flousflow_accounting.flousflow_working_file_search_view'))
        context = ast.literal_eval(action.context or '{}')
        self.assertEqual(context.get('search_default_todo_returns'), 1)
        self.assertEqual(context.get('search_default_paused_returns'), 1)
        self.assertIn("('state', 'in', ('draft', 'in_review'))",
                      action.search_view_id.arch)
        self.assertIn("('state', '=', 'paused')", action.search_view_id.arch)

    def _file(self, **extra):
        values = {
            'title': 'Receivables review', 'period_start': '2026-01-01',
            'period_end': '2026-01-31', 'objective': 'Validate receivables.',
            'reviewer_id': self.env.user.id,
        }
        values.update(extra)
        return self.env['flousflow.account.working.file'].create(values)

    def test_review_and_approval_trail(self):
        working_file = self._file()
        working_file.action_submit()
        self.assertEqual(working_file.state, 'in_review')
        working_file.action_approve()
        self.assertEqual(working_file.state, 'approved')
        self.assertEqual(working_file.approved_by_id, self.env.user)
        self.assertTrue(working_file.approved_date)
        with self.assertRaises(UserError):
            working_file.write({'objective': 'Changed after approval'})
        with self.assertRaises(UserError):
            working_file.action_cancel()

    def test_pause_and_resume_restore_the_previous_workflow_stage(self):
        working_file = self._file()
        working_file.action_pause()
        self.assertEqual(working_file.state, 'paused')
        self.assertEqual(working_file.paused_from_state, 'draft')
        working_file.action_resume()
        self.assertEqual(working_file.state, 'draft')
        self.assertFalse(working_file.paused_from_state)

        working_file.action_submit()
        working_file.action_pause()
        self.assertEqual(working_file.paused_from_state, 'in_review')
        working_file.action_resume()
        self.assertEqual(working_file.state, 'in_review')

    def test_only_active_working_files_can_be_paused(self):
        working_file = self._file()
        working_file.action_submit()
        working_file.action_approve()
        with self.assertRaises(UserError):
            working_file.action_pause()

    def test_workflow_state_cannot_be_changed_directly(self):
        working_file = self._file()
        with self.assertRaises(UserError):
            working_file.write({'state': 'paused'})
        with self.assertRaises(UserError):
            working_file.write({'paused_from_state': 'draft'})
        with self.assertRaises(UserError):
            self._file(state='paused', paused_from_state='draft')

    def test_reviewer_and_period_are_required_by_business_flow(self):
        with self.assertRaises(ValidationError):
            self._file(period_start='2026-02-01', period_end='2026-01-01')
        working_file = self._file(reviewer_id=False)
        with self.assertRaises(UserError):
            working_file.action_submit()

    def test_only_draft_can_be_deleted(self):
        working_file = self._file()
        working_file.action_submit()
        with self.assertRaises(UserError):
            working_file.unlink()
