# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
import ast
from pathlib import Path

from lxml import etree
from odoo import Command
from odoo.tests.common import TransactionCase


class TestCommunityIndependence(TransactionCase):
    """Prevent accidental coupling to proprietary accounting clients."""

    REPORT_MENU_XMLIDS = (
        'menu_flousflow_accounting_executive_summary',
        'menu_flousflow_accounting_pnl',
        'menu_flousflow_accounting_balance_sheet',
        'menu_flousflow_accounting_cash_flow',
        'menu_flousflow_accounting_trial_balance',
        'menu_flousflow_accounting_general_ledger',
        'menu_flousflow_accounting_account_statement',
        'menu_flousflow_accounting_partner_ledger',
        'menu_flousflow_accounting_customer_statement',
        'menu_flousflow_accounting_vendor_statement',
        'menu_flousflow_accounting_aged_receivable',
        'menu_flousflow_accounting_aged_payable',
        'menu_flousflow_accounting_tax_report',
    )

    @classmethod
    def _module_path(cls):
        return Path(__file__).resolve().parents[1]

    def test_manifest_has_no_proprietary_dependency(self):
        manifest = ast.literal_eval(
            (self._module_path() / '__manifest__.py').read_text(encoding='utf-8'))
        forbidden = {'account_reports', 'account_accountant', 'web_enterprise'}

        self.assertFalse(
            forbidden.intersection(manifest.get('depends', [])),
            'FlousFlow Accounting must remain installable without proprietary addons.')
        self.assertEqual(manifest.get('license'), 'LGPL-3')

    def test_executable_sources_do_not_import_proprietary_clients(self):
        forbidden_imports = (
            'odoo.addons.' + 'account_reports',
            'odoo.addons.' + 'account_accountant',
            'odoo.addons.' + 'web_enterprise',
            '@' + 'account_reports/',
            '@' + 'web_enterprise/',
        )
        source_files = (
            path for path in self._module_path().rglob('*')
            if path.suffix in {'.py', '.js', '.xml', '.scss'}
            and path.name != Path(__file__).name
        )

        violations = []
        for path in source_files:
            source = path.read_text(encoding='utf-8')
            for forbidden in forbidden_imports:
                if forbidden in source:
                    violations.append(f'{path.relative_to(self._module_path())}: {forbidden}')
        self.assertFalse(violations, '\n'.join(violations))

    def test_report_menus_use_original_flousflow_actions(self):
        interactive_report_menus = {
            'menu_flousflow_accounting_pnl',
            'menu_flousflow_accounting_balance_sheet',
            'menu_flousflow_accounting_cash_flow',
            'menu_flousflow_accounting_trial_balance',
            'menu_flousflow_accounting_general_ledger',
        }
        for menu_xmlid in self.REPORT_MENU_XMLIDS:
            menu = self.env.ref(f'flousflow_accounting.{menu_xmlid}')
            self.assertTrue(menu.action, menu_xmlid)
            expected_model = (
                'ir.actions.client' if menu_xmlid in interactive_report_menus
                else 'ir.actions.act_window')
            self.assertEqual(menu.action._name, expected_model, menu_xmlid)
            action_xmlids = menu.action.get_external_id()
            self.assertTrue(
                action_xmlids[menu.action.id].startswith('flousflow_accounting.'),
                menu_xmlid)

    def test_community_account_report_configuration_destination(self):
        menu = self.env.ref(
            'flousflow_accounting.menu_flousflow_accounting_report_configuration')
        action = self.env.ref(
            'flousflow_accounting.action_account_report_configuration')
        self.assertEqual(menu.action, action)
        self.assertEqual(action.res_model, 'account.report')
        self.assertEqual(action.view_mode, 'list,form')
        self.assertEqual(ast.literal_eval(action.context or '{}'), {})
        self.assertEqual(
            action.view_ids.sorted('sequence').mapped('view_mode'),
            ['list', 'form'])
        self.assertEqual(
            action.views,
            [[self.env.ref(
                'flousflow_accounting.view_account_report_configuration_list').id,
              'list'],
             [self.env.ref(
                'flousflow_accounting.view_account_report_configuration_form').id,
              'form']])
        report_list = self.env.ref(
            'flousflow_accounting.view_account_report_configuration_list')
        self.assertEqual(
            set(etree.fromstring(report_list.arch_db.encode()).xpath('.//field/@name')),
            {'sequence', 'name', 'root_report_id', 'country_id'})
        self.assertEqual(menu.parent_id, self.env.ref('account.account_account_menu'))
        self.assertTrue(menu.group_ids & self.env.ref('account.group_account_readonly'))
        self.assertTrue(action.search_view_id)

        report_form = self.env.ref(
            'flousflow_accounting.view_account_report_configuration_form')
        for field_name in ('line_ids', 'expression_ids', 'engine', 'formula',
                           'subformula', 'date_scope', 'figure_type',
                           'filter_multi_company', 'filter_date_range',
                           'filter_show_draft', 'filter_unreconciled',
                           'only_tax_exigible', 'filter_period_comparison',
                           'filter_growth_comparison', 'filter_hierarchy',
                           'filter_hide_0_lines', 'filter_budgets',
                           'default_opening_date_filter', 'use_fiscal_periods',
                           'currency_translation', 'enable_snapshots',
                           'groupby', 'user_groupby', 'section_report_ids',
                           'section_main_report_ids'):
            self.assertIn(f'name="{field_name}"', report_form.arch)
        options_page = report_form.arch.split('<page string="Options"', 1)[1]
        self.assertIn('groups="account.group_account_manager"', options_page)
        expressions_page = report_form.arch.split('<page string="Lines"', 1)[1]
        self.assertIn('groups="account.group_account_manager"', expressions_page)

        report = self.env['account.report'].create({
            'name': 'FlousFlow Expression Configuration Check',
        })
        line = self.env['account.report.line'].create({
            'report_id': report.id,
            'name': 'Operating Result',
            'code': 'FF_OPERATING_RESULT',
        })
        expression = self.env['account.report.expression'].create({
            'report_line_id': line.id,
            'label': 'balance',
            'engine': 'domain',
            'formula': '[]',
            'subformula': 'sum',
            'date_scope': 'strict_range',
        })
        self.assertEqual(line.expression_ids, expression)

        section = self.env['account.report'].create({
            'name': 'FlousFlow Composite Report Section Check',
        })
        report.write({'section_report_ids': [Command.set([section.id])]})
        self.assertEqual(report.section_report_ids, section)
        self.assertTrue(report.use_sections)
