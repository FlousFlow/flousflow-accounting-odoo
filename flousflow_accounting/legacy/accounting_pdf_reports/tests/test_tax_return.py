from datetime import date

from lxml import etree
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

    def test_create_wizard_creates_return_for_selected_period(self):
        wizard = self.env['account.tax.return.create.wizard'].create({
            'return_type': 'tax',
            'date_from': '2034-04-01',
            'date_to': '2034-06-30',
        })

        action = wizard.action_create_return()
        record = self.env['account.tax.return'].search([
            ('company_id', '=', self.env.company.id),
            ('return_type', '=', 'tax'),
            ('date_from', '=', '2034-04-01'),
            ('date_to', '=', '2034-06-30'),
        ])
        self.assertEqual(len(record), 1)
        self.assertEqual(action, {'type': 'ir.actions.client', 'tag': 'reload'})

    def test_create_entrypoints_open_the_enterprise_style_wizard(self):
        create_action = self.env.ref(
            'flousflow_accounting.apr__action_account_tax_return_create')
        self.assertEqual(create_action.res_model, 'account.tax.return.create.wizard')
        self.assertEqual(create_action.target, 'new')

        kanban_arch = etree.fromstring(self.env.ref(
            'flousflow_accounting.apr__account_tax_return_view_kanban').arch_db.encode())
        self.assertEqual(kanban_arch.get('on_create'), str(create_action.id))

        list_arch = etree.fromstring(self.env.ref(
            'flousflow_accounting.apr__account_tax_return_view_list').arch_db.encode())
        self.assertEqual(list_arch.get('create'), 'false')
        create_buttons = list_arch.xpath("./header/button[@type='action']")
        self.assertEqual(len(create_buttons), 1)
        self.assertEqual(create_buttons[0].get('name'), str(create_action.id))

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
