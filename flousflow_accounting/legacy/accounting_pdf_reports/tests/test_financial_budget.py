from io import BytesIO
from zipfile import ZipFile

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestInteractiveFinancialBudget(AccountTestInvoicingCommon):

    def _create_budget_export_fixture(self):
        invoice = self.init_invoice(
            'out_invoice', amounts=[1000.0], invoice_date='2026-03-15', taxes=[], post=True,
        )
        account = invoice.invoice_line_ids.account_id
        budget = self.env['account.financial.budget'].create({
            'name': 'FY 2026 export budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'company_id': self.env.company.id,
            'line_ids': [(0, 0, {'account_id': account.id, 'planned_amount': 12000.0})],
        })
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')
        wizard = self.env['accounting.report'].create({
            'account_report_id': report.id,
            'company_id': self.env.company.id,
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'journal_ids': [(6, 0, self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
            'target_move': 'posted',
            'filter_cmp': 'filter_no',
            'financial_budget_id': budget.id,
        })
        return account, budget, wizard

    def test_profit_and_loss_displays_account_budget_amounts(self):
        invoice = self.init_invoice(
            'out_invoice', amounts=[1000.0], invoice_date='2026-03-15', taxes=[], post=True,
        )
        account = invoice.invoice_line_ids.account_id
        budget = self.env['account.financial.budget'].create({
            'name': 'FY 2026 test budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'company_id': self.env.company.id,
            'line_ids': [(0, 0, {'account_id': account.id, 'planned_amount': 12000.0})],
        })
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')

        data = self.env['report.flousflow_accounting.apr__report_financial'].get_interactive_data(
            report.id, '2026-01-01', '2026-12-31', financial_budget_id=budget.id,
        )

        account_line = next(line for line in data['lines'] if line.get('account_id') == account.id)
        self.assertEqual(account_line['budget_amount'], 12000.0)
        self.assertTrue(account_line['budget_line_id'])
        self.assertEqual(data['financial_budget']['id'], budget.id)

    def test_profit_and_loss_prorates_budget_for_selected_date_range(self):
        invoice = self.init_invoice(
            'out_invoice', amounts=[1000.0], invoice_date='2026-03-15', taxes=[], post=True,
        )
        account = invoice.invoice_line_ids.account_id
        budget = self.env['account.financial.budget'].create({
            'name': 'FY 2026 prorated budget',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'company_id': self.env.company.id,
            'line_ids': [(0, 0, {'account_id': account.id, 'planned_amount': 12000.0})],
        })
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')

        data = self.env['report.flousflow_accounting.apr__report_financial'].get_interactive_data(
            report.id, '2026-01-01', '2026-03-31', financial_budget_id=budget.id,
        )

        account_line = next(line for line in data['lines'] if line.get('account_id') == account.id)
        self.assertAlmostEqual(account_line['budget_amount'], 12000.0 * 90 / 365)

    def test_print_and_xlsx_exports_include_selected_budget(self):
        account, budget, wizard = self._create_budget_export_fixture()
        form = wizard.read([
            'date_from', 'date_to', 'journal_ids', 'target_move', 'company_id',
            'account_report_id', 'date_from_cmp', 'date_to_cmp', 'filter_cmp',
            'enable_filter', 'label_filter', 'debit_credit', 'comparison_period_ranges',
            'comparison_sort', 'comparison_display', 'comparison_mode',
            'percentage_of_row_key', 'financial_budget_id',
        ])[0]
        report_data = wizard._prepare_export_data(form, wizard._get_interactive_report_data(form))
        account_line = next(line for line in report_data['lines'] if line.get('account_id') == account.id)
        self.assertTrue(report_data['show_budget'])
        self.assertEqual(report_data['budget_label'], budget.name)
        self.assertEqual(account_line['budget_amount'], 12000.0)

        pdf_values = self.env['report.flousflow_accounting.apr__report_financial'].with_context(
            active_model='accounting.report', active_id=wizard.id,
        )._get_report_values(wizard.ids, {'form': form})
        self.assertTrue(pdf_values['show_budget'])
        self.assertEqual(pdf_values['budget_label'], budget.name)

        wizard.action_export_xlsx()
        workbook = ZipFile(BytesIO(bytes(wizard.xlsx_file)))
        shared_strings = workbook.read('xl/sharedStrings.xml')
        worksheet = workbook.read('xl/worksheets/sheet1.xml')
        self.assertIn(b'FY 2026 export budget', shared_strings)
        self.assertIn(b'<v>12000</v>', worksheet)
