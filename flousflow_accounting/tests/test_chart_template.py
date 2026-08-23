# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo.tests import TransactionCase


class TestFlousChartTemplate(TransactionCase):
    """Verify the FlousFlow generic chart template is registered and complete."""

    def _chart_template(self):
        return self.env['account.chart.template']

    def test_template_registered(self):
        mapping = self._chart_template()._get_chart_template_mapping()
        self.assertIn('flous_generic_coa', mapping)
        info = mapping['flous_generic_coa']
        self.assertEqual(info['module'], 'flousflow_accounting')
        self.assertIsNone(info.get('country_id'))

    def test_template_data_complete(self):
        data = self._chart_template()._get_chart_template_data('flous_generic_coa')
        # Accounts
        accounts = data['account.account']
        for xmlid in ('flous_receivable', 'flous_payable', 'flous_income',
                      'flous_expense', 'flous_pos_receivable',
                      'flous_stock_valuation', 'flous_tax_received',
                      'flous_tax_paid'):
            self.assertIn(xmlid, accounts, f'Account {xmlid} missing')
        # Tax groups
        tax_groups = data['account.tax.group']
        self.assertIn('flous_tax_group_15', tax_groups)
        self.assertIn('flous_tax_group_0', tax_groups)
        # Taxes
        taxes = data['account.tax']
        self.assertIn('flous_sale_tax_template', taxes)
        self.assertIn('flous_purchase_tax_template', taxes)
        self.assertIn('flous_sale_export_tax_template', taxes)
        self.assertIn('flous_purchase_import_tax_template', taxes)
        # Fiscal positions
        fps = data['account.fiscal.position']
        self.assertIn('flous_template_domestic_fiscal_position', fps)
        self.assertIn('flous_template_export_fiscal_position', fps)

    def test_template_guessable(self):
        # The template must be selectable through the standard mechanism.
        mapping = self._chart_template()._get_chart_template_mapping()
        self.assertIn('flous_generic_coa', mapping)
        # A company without a country-specific localization should be able to
        # pick the FlousFlow generic chart from the standard selection.
        selection = self._chart_template()._select_chart_template()
        codes = [code for code, _name in selection]
        self.assertIn('flous_generic_coa', codes)

    def test_company_defaults_in_template(self):
        data = self._chart_template()._get_chart_template_data('flous_generic_coa')
        company_vals = data['res.company']
        self.assertTrue(company_vals)
        for field in ('income_account_id', 'expense_account_id',
                      'default_cash_difference_income_account_id',
                      'default_cash_difference_expense_account_id',
                      'bank_account_code_prefix'):
            self.assertIn(field, list(company_vals.values())[0],
                          f'Company field {field} missing from template')

    def test_country_template_is_preferred_when_available(self):
        egypt = self.env.ref('base.eg')
        company = self.env['res.company'].new({'country_id': egypt.id})
        template_code = self._chart_template()._flousflow_template_for_company(
            company)
        mapping = self._chart_template()._get_chart_template_mapping()

        self.assertEqual(mapping[template_code]['country_id'], egypt.id)
        self.assertEqual(mapping[template_code]['module'], 'l10n_eg')

    def test_generic_fallback_for_country_without_localization(self):
        mapping = self._chart_template()._get_chart_template_mapping()
        localized_country_ids = {
            template['country_id']
            for template in mapping.values()
            if template.get('country_id')
        }
        country = self.env['res.country'].search([
            ('id', 'not in', list(localized_country_ids)),
        ], limit=1)
        if not country:
            self.skipTest('Every installed country has a localization template')
        company = self.env['res.company'].new({'country_id': country.id})

        self.assertEqual(
            self._chart_template()._flousflow_template_for_company(company),
            'flous_generic_coa')

    def test_branch_keeps_parent_chart(self):
        parent = self.env.company
        self.assertTrue(parent.chart_template)
        branch = self.env['res.company'].new({
            'country_id': self.env.ref('base.eg').id,
            'parent_id': parent.id,
        })

        self.assertEqual(
            self._chart_template()._flousflow_template_for_company(branch),
            parent.chart_template)
