# -*- coding: utf-8 -*-
from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError


class TestAnnualReportManagement(AccountTestInvoicingCommon):

    def _template(self, **values):
        vals = {
            'name': 'Annual Review Template',
            'company_id': self.company.id,
            'content': '<h2>Management review</h2><p>Annual summary</p>',
        }
        vals.update(values)
        return self.env['flousflow.account.annual.report.template'].create(vals)

    def _report(self, **values):
        vals = {
            'title': 'FY Annual Review',
            'company_id': self.company.id,
            'start_date': '2026-01-01',
            'end_date': '2026-12-31',
            'responsible_user_ids': [(6, 0, [self.env.user.id])],
        }
        vals.update(values)
        return self.env['flousflow.account.annual.report'].create(vals)

    def test_annual_report_destination_has_enterprise_style_views_and_fields(self):
        action = self.env.ref('flousflow_accounting.flousflow_annual_report_action')
        self.assertEqual(action.res_model, 'flousflow.account.annual.report')
        self.assertEqual(action.view_mode, 'kanban,list')
        self.assertTrue(action.search_view_id)

        list_view = self.env.ref('flousflow_accounting.flousflow_annual_report_list')
        kanban_view = self.env.ref('flousflow_accounting.flousflow_annual_report_kanban')
        form_view = self.env.ref('flousflow_accounting.flousflow_annual_report_form')
        for field_name in (
                'title', 'status', 'start_date', 'end_date', 'company_id',
                'responsible_user_ids', 'template_id'):
            self.assertIn(f'name="{field_name}"', list_view.arch)
        for field_name in (
                'title', 'status', 'start_date', 'end_date', 'company_id',
                'responsible_user_ids', 'template_id'):
            self.assertIn(f'name="{field_name}"', kanban_view.arch)
        for button_name in (
                'action_start', 'action_complete',
                'action_generate_financial_statements', 'action_print_report'):
            self.assertIn(f'name="{button_name}"', form_view.arch)

    def test_template_content_is_copied_and_financial_report_uses_record_period(self):
        template = self._template()
        report = self._report(template_id=template.id)
        self.assertEqual(report.content, template.content)

        action = report.action_generate_financial_statements()
        self.assertEqual(action['res_model'], 'flousflow.account.report')
        self.assertEqual(action['context']['default_report_type'], 'annual_report')
        self.assertEqual(action['context']['default_company_id'], self.company.id)
        self.assertEqual(action['context']['default_date_from'], report.start_date)
        self.assertEqual(action['context']['default_date_to'], report.end_date)
        self.assertEqual(action['context']['default_comparison_mode'], 'previous_year')

        print_action = report.action_print_report()
        if print_action['type'] == 'ir.actions.act_window':
            print_action = print_action['context']['report_action']
        self.assertEqual(print_action['type'], 'ir.actions.report')
        self.assertEqual(
            print_action['report_name'],
            'flousflow_accounting.report_annual_report_record')
        html, _content_type = self.env['ir.actions.report']._render_qweb_html(
            'flousflow_accounting.report_annual_report_record', [report.id])
        self.assertIn(b'FY Annual Review', html)
        self.assertIn(b'Management review', html)
        self.assertIn(self.env.user.name.encode(), html)

    def test_report_workflow_protects_status_and_completed_content(self):
        report = self._report()
        with self.assertRaises(UserError):
            report.write({'status': 'done'})

        report.action_start()
        self.assertEqual(report.status, 'in_progress')
        report.action_complete()
        self.assertEqual(report.status, 'done')
        with self.assertRaises(UserError):
            report.write({'content': '<p>Changed after completion</p>'})
        with self.assertRaises(UserError):
            report.unlink()

    def test_dates_and_manager_reopen_are_validated(self):
        with self.assertRaises(ValidationError):
            self._report(start_date='2026-12-31', end_date='2026-01-01')

        report = self._report()
        report.action_start()
        report.action_complete()
        report.action_reset_to_draft()
        self.assertEqual(report.status, 'draft')

    def test_annual_reports_and_templates_obey_company_rules(self):
        other_company = self.env['res.company'].create({
            'name': 'Annual Report Other Company',
            'currency_id': self.company.currency_id.id,
        })
        foreign_report = self.env['flousflow.account.annual.report'].sudo().create({
            'title': 'Other Company Report',
            'company_id': other_company.id,
            'start_date': '2026-01-01',
            'end_date': '2026-12-31',
        })
        foreign_template = self._template(
            name='Other Company Template', company_id=other_company.id)
        shared_template = self._template(
            name='Shared Template', company_id=False)
        accountant = self.env['res.users'].create({
            'name': 'Annual Report Accountant',
            'login': 'annual.report.accountant@example.com',
            'company_id': self.company.id,
            'company_ids': [Command.set([self.company.id])],
            'group_ids': [Command.set([
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
        })
        visible_reports = self.env['flousflow.account.annual.report'].with_user(
            accountant).search([])
        visible_templates = self.env[
            'flousflow.account.annual.report.template'].with_user(accountant).search([])
        self.assertNotIn(foreign_report, visible_reports)
        self.assertNotIn(foreign_template, visible_templates)
        self.assertIn(shared_template, visible_templates)
