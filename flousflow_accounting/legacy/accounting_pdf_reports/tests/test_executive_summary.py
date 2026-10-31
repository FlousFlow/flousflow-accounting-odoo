from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestExecutiveSummary(AccountTestInvoicingCommon):

    def test_summary_uses_posted_financial_data_and_handles_zero_denominators(self):
        self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2025-01-10', post=True,
        )
        report = self.env['report.flousflow_accounting.apr__report_financial']
        result = report.get_executive_summary_data('2025-01-01', '2025-12-31')
        groups = {group['key']: group for group in result['groups']}
        items = {
            group_key: {item['key']: item for item in group['items']}
            for group_key, group in groups.items()
        }

        self.assertEqual(items['profitability']['revenue']['value'], 100.0)
        self.assertEqual(items['balance_sheet']['current_assets']['value'], 100.0)
        self.assertEqual(items['performance']['gross_margin']['value'], 100.0)
        self.assertEqual(items['operational']['current_ratio']['value'], 0.0)
        self.assertEqual(result['date_from'], '2025-01-01')
        self.assertEqual(result['date_to'], '2025-12-31')

    def test_summary_rejects_reversed_date_range(self):
        report = self.env['report.flousflow_accounting.apr__report_financial']
        with self.assertRaises(UserError):
            report.get_executive_summary_data('2025-12-31', '2025-01-01')

    def test_debtor_days_matches_enterprise_fixed_365_day_formula(self):
        self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2024-01-10', post=True,
        )
        report = self.env['report.flousflow_accounting.apr__report_financial']
        result = report.get_executive_summary_data('2024-01-01', '2024-12-31')
        debtor_days = next(
            item['value'] for group in result['groups'] if group['key'] == 'operational'
            for item in group['items'] if item['key'] == 'debtor_days'
        )
        self.assertEqual(debtor_days, 365.0)


@tagged('post_install', '-at_install')
class TestExecutiveSummaryTour(HttpCase):

    def test_executive_summary_cards_and_comparison(self):
        action = self.env.ref('flousflow_accounting.apr__action_executive_summary')
        self.start_tour(
            f'/odoo/action-{action.id}',
            'ff_executive_summary',
            login='admin',
        )
