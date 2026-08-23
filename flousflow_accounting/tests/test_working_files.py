# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestWorkingFiles(TransactionCase):

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
