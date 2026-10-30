import base64
from io import BytesIO
from zipfile import ZipFile, is_zipfile

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestFinancialReportCashBasis(AccountTestInvoicingCommon):

    def setUp(self):
        super().setUp()
        self.env.company.tax_exigibility = True
        self.env.company.tax_cash_basis_journal_id = self.company_data['default_journal_misc']
        self.transition_account = self.env['account.account'].create({
            'code': 'CBTR%03d' % self.env.company.id,
            'name': 'Cash basis tax transition',
            'account_type': 'liability_current',
            'reconcile': True,
        })
        self.cash_basis_tax = self.tax_sale_a.copy({
            'name': 'Cash Basis 15%',
            'tax_exigibility': 'on_payment',
            'cash_basis_transition_account_id': self.transition_account.id,
        })

    def _financial_report(self, cash_basis):
        return self.env['report.flousflow_accounting.apr__report_financial'].get_interactive_data(
            self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0').id,
            '2025-01-01', '2025-12-31', cash_basis=cash_basis,
        )

    def _revenue_amount(self, data, account):
        row_key = 'pnl-revenue-%s' % self.env.ref(
            'flousflow_accounting.apr__account_financial_report_profitandloss0').id
        revenue_line = next(line for line in data['lines'] if line.get('row_key') == row_key)
        self.assertIn(account.id, revenue_line.get('account_ids', []))
        return revenue_line.get('balance', 0.0)

    def test_cash_basis_filter_follows_invoice_payment_in_report_and_exports(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-15',
            'date': '2025-01-15',
            'invoice_line_ids': [Command.create({
                'name': 'Cash-basis taxable sale',
                'price_unit': 1000.0,
                'tax_ids': [Command.set(self.cash_basis_tax.ids)],
            })],
        })
        invoice.action_post()
        revenue_account = invoice.invoice_line_ids.account_id

        accrual_data = self._financial_report(cash_basis=False)
        unpaid_cash_data = self._financial_report(cash_basis=True)
        self.assertFalse(accrual_data['cash_basis'])
        self.assertTrue(unpaid_cash_data['cash_basis'])
        self.assertAlmostEqual(abs(self._revenue_amount(accrual_data, revenue_account)), 1000.0)
        self.assertAlmostEqual(self._revenue_amount(unpaid_cash_data, revenue_account), 0.0)

        bank = self.company_data['default_journal_bank']
        outstanding = self.env['account.account'].create({
            'code': 'CBOUT%03d' % self.env.company.id,
            'name': 'Cash-basis test outstanding',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        (bank.inbound_payment_method_line_ids | bank.outbound_payment_method_line_ids).payment_account_id = outstanding
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'payment_date': '2025-02-10',
            'journal_id': bank.id,
        })._create_payments()

        paid_cash_data = self._financial_report(cash_basis=True)
        self.assertTrue(paid_cash_data['cash_basis_domain'])

        partials = invoice.mapped('line_ids.matched_credit_ids')
        cash_basis_moves = self.env['account.move'].search([
            ('tax_cash_basis_rec_id', 'in', partials.ids),
        ])
        self.assertTrue(cash_basis_moves, 'The payment must create a cash-basis journal entry.')
        report_context = {
            'date_from': '2025-01-01',
            'date_to': '2025-12-31',
            'strict_range': True,
            'state': 'posted',
            'company_id': self.env.company.id,
            'journal_ids': paid_cash_data['journal_ids'],
            'tax_exigible': True,
        }
        eligible_cash_basis_lines = self.env['account.move.line'].with_context(
            **report_context,
        ).search([
            ('move_id', 'in', cash_basis_moves.ids),
            ('date', '>=', '2025-01-01'),
            ('date', '<=', '2025-12-31'),
            ('company_id', '=', self.env.company.id),
            ('journal_id', 'in', paid_cash_data['journal_ids']),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('parent_state', '=', 'posted'),
        ] + paid_cash_data['cash_basis_domain'])
        self.assertTrue(eligible_cash_basis_lines, 'Cash-basis entries must pass Odoo\'s native filter.')

        report_revenue = self._revenue_amount(paid_cash_data, revenue_account)
        eligible_revenue = self.env['account.move.line'].with_context(
            **report_context,
        ).search([
            ('account_id', '=', revenue_account.id),
            ('date', '>=', '2025-01-01'),
            ('date', '<=', '2025-12-31'),
            ('company_id', '=', self.env.company.id),
            ('journal_id', 'in', paid_cash_data['journal_ids']),
            ('display_type', 'not in', ('line_section', 'line_note')),
            ('parent_state', '=', 'posted'),
        ] + paid_cash_data['cash_basis_domain'])
        self.assertAlmostEqual(report_revenue, sum(eligible_revenue.mapped('balance')))

        wizard = self.env['accounting.report'].create({
            'account_report_id': self.env.ref(
                'flousflow_accounting.apr__account_financial_report_profitandloss0'
            ).id,
            'company_id': self.env.company.id,
            'date_from': '2025-01-01',
            'date_to': '2025-12-31',
            'journal_ids': [Command.set(self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
            'target_move': 'posted',
            'filter_cmp': 'filter_no',
            'cash_basis': True,
        })
        form = wizard.read([
            'date_from', 'date_to', 'journal_ids', 'target_move', 'company_id',
            'account_report_id', 'filter_cmp', 'enable_filter', 'debit_credit',
            'cash_basis', 'financial_budget_id',
        ])[0]
        exported_data = wizard._get_interactive_report_data(form)
        self.assertTrue(exported_data['cash_basis'])
        self.assertAlmostEqual(self._revenue_amount(exported_data, revenue_account), report_revenue)

        pdf_values = self.env['report.flousflow_accounting.apr__report_financial'].with_context(
            active_model='accounting.report', active_id=wizard.id,
        )._get_report_values(wizard.ids, {'form': form})
        self.assertTrue(pdf_values['data']['cash_basis'])
        pdf_revenue = sum(line.get('balance', 0.0) for line in pdf_values['report_lines']
                          if line.get('account_id') == revenue_account.id)
        self.assertAlmostEqual(pdf_revenue, report_revenue)

        wizard.action_export_xlsx()
        self.assertTrue(wizard.xlsx_file)
        xlsx_content = bytes(wizard.xlsx_file)
        if not is_zipfile(BytesIO(xlsx_content)):
            xlsx_content = base64.b64decode(xlsx_content)
        with ZipFile(BytesIO(xlsx_content)) as xlsx:
            self.assertIn(b'Cash Basis', xlsx.read('xl/sharedStrings.xml'))
