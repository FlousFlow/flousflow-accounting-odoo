from datetime import date

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from psycopg2.errors import UniqueViolation

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTaxReturn(AccountTestInvoicingCommon):

    def _new_return(self, **values):
        vals = {
            'return_type': 'annual_corporate_tax',
            'date_from': '2025-01-01',
            'date_to': '2025-12-31',
            'company_id': self.company_data['company'].id,
        }
        vals.update(values)
        return self.env['account.tax.return'].create(vals)

    def test_return_workflow_and_history(self):
        record = self._new_return()
        self.assertTrue(record.name.startswith('TR/'))
        self.assertEqual(record.state, 'to_review')
        record.action_mark_reviewed()
        self.assertEqual(record.state, 'to_submit')
        self.assertEqual(record.reviewed_by, self.env.user)
        self.assertTrue(record.reviewed_on)
        record.action_mark_submitted()
        self.assertEqual(record.state, 'submitted')
        self.assertEqual(record.submitted_by, self.env.user)
        record.action_mark_paid()
        self.assertEqual(record.state, 'paid')
        self.assertEqual(record.paid_by, self.env.user)

    def test_return_requires_ordered_dates(self):
        with self.assertRaises(ValidationError):
            self._new_return(date_from='2025-12-31', date_to='2025-01-01')

    def test_duplicate_period_is_rejected(self):
        self._new_return()
        with self.cr.savepoint():
            with self.assertRaises(UniqueViolation):
                self._new_return()

    def test_workflow_cannot_skip_steps(self):
        record = self._new_return()
        with self.assertRaises(UserError):
            record.action_mark_submitted()
        with self.assertRaises(UserError):
            record.action_mark_paid()

    def test_tax_report_action_uses_return_period_and_company(self):
        record = self._new_return()
        action = record.action_open_tax_report()
        self.assertEqual(action['res_model'], 'accounting.report')
        self.assertEqual(action['context']['default_date_from'], date(2025, 1, 1))
        self.assertEqual(action['context']['default_date_to'], date(2025, 12, 31))
        self.assertEqual(action['context']['default_company_id'], record.company_id.id)

    def test_periodic_return_opens_tax_report(self):
        record = self._new_return(
            return_type='tax', date_from='2025-04-01', date_to='2025-04-30')
        action = record.action_open_tax_report()
        self.assertEqual(action['res_model'], 'account.tax.report.wizard')
        self.assertEqual(action['context']['default_period'], 'custom')
        self.assertEqual(action['context']['default_date_from'], date(2025, 4, 1))

    def test_tax_closing_not_offered_for_corporate_tax(self):
        record = self._new_return()
        record.action_mark_reviewed()
        with self.assertRaises(UserError):
            record.action_open_tax_closing()
