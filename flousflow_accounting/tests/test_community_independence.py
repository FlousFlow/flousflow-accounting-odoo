# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
import ast
from pathlib import Path

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

    def test_report_menus_use_original_flousflow_window_actions(self):
        for menu_xmlid in self.REPORT_MENU_XMLIDS:
            menu = self.env.ref(f'flousflow_accounting.{menu_xmlid}')
            self.assertTrue(menu.action, menu_xmlid)
            self.assertEqual(menu.action._name, 'ir.actions.act_window', menu_xmlid)
            action_xmlids = menu.action.get_external_id()
            self.assertTrue(
                action_xmlids[menu.action.id].startswith('flousflow_accounting.'),
                menu_xmlid)
