from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.addons.flousflow_accounting.legacy.accounting_pdf_reports.controllers.tax_report import build_tax_report_xlsx

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestTaxReport(AccountTestInvoicingCommon):

    def _post(self, move_type, tax, amount, date='2025-03-10'):
        # the accounting date set as well: the test helpers leave the date of a refund to the form
        move = self.env['account.move'].create({
            'move_type': move_type, 'partner_id': self.partner_a.id,
            'invoice_date': date, 'date': date,
            'invoice_line_ids': [Command.create({'name': 'test line', 'price_unit': amount,
                                                 'tax_ids': [Command.set(tax.ids)]})],
        })
        move.action_post()
        return move

    def _tax_lines(self, date_from='2025-01-01', date_to='2025-12-31'):
        # read with SQL, like the report: it flushes in _get_report_values
        self.env.flush_all()
        lines = self.env['report.flousflow_accounting.apr__report_tax'].get_lines({
            'date_from': date_from, 'date_to': date_to, 'target_move': 'posted',
            'used_context': {'company_id': self.env.company.id},
        })
        return {
            group: {line['name']: (line['net'], line['tax']) for line in group_lines}
            for group, group_lines in lines.items()
        }

    def test_refunds_are_deducted_and_both_sides_are_positive(self):
        sale_tax, purchase_tax = self.tax_sale_a, self.tax_purchase_a
        for move_type, tax, amount in (
            ('out_invoice', sale_tax, 1000.0),
            ('out_refund', sale_tax, 100.0),
            ('in_invoice', purchase_tax, 400.0),
            ('in_refund', purchase_tax, 40.0),
        ):
            self._post(move_type, tax, amount)

        lines = self._tax_lines()
        # the sales are credits and the purchases debits: both print as positive figures,
        # a refund is deducted from its side
        self.assertEqual(lines['sale'][sale_tax.name], (900.0, 135.0))
        self.assertEqual(lines['purchase'][purchase_tax.name], (360.0, 54.0))

    def test_a_period_of_refunds_stays_negative(self):
        self._post('out_refund', self.tax_sale_a, 100.0)
        self.assertEqual(self._tax_lines()['sale'][self.tax_sale_a.name], (-100.0, -15.0))

    def test_interactive_report_uses_the_same_tax_engine_as_print(self):
        self._post('out_invoice', self.tax_sale_a, 1000.0)
        report = self.env['report.flousflow_accounting.apr__report_tax']
        interactive = report.get_interactive_data('2025-03-01', '2025-03-31', 'posted')
        printed = report.get_lines({
            'date_from': '2025-03-01',
            'date_to': '2025-03-31',
            'target_move': 'posted',
            'used_context': {
                'company_id': self.env.company.id,
                'allowed_company_ids': self.env.companies.ids,
            },
        })

        self.assertEqual(interactive['groups'], printed)
        self.assertEqual(interactive['groups']['sale'][0]['tax_id'], self.tax_sale_a.id)
        self.assertEqual(interactive['totals']['sale']['net'], 1000.0)
        self.assertEqual(interactive['totals']['sale']['tax'], 150.0)
        self.assertEqual(interactive['target_move'], 'posted')

    def test_tax_report_groupings_preserve_general_report_totals(self):
        self._post('out_invoice', self.tax_sale_a, 1000.0)
        report = self.env['report.flousflow_accounting.apr__report_tax']
        account_tax = report.get_interactive_data(
            '2025-03-01', '2025-03-31', 'posted', report_view='account_tax'
        )
        tax_account = report.get_interactive_data(
            '2025-03-01', '2025-03-31', 'posted', report_view='tax_account'
        )

        account_tax_rows = [
            line
            for account in account_tax['periods'][0]['grouped_lines']['account_tax']['sale']
            for line in account['lines']
        ]
        tax_account_rows = [
            account
            for tax in tax_account['periods'][0]['grouped_lines']['tax_account']['sale']
            for account in tax['accounts']
        ]
        self.assertEqual(sum(line['net'] for line in account_tax_rows), 1000.0)
        self.assertEqual(sum(line['tax'] for line in account_tax_rows), 150.0)
        self.assertEqual(sum(line['net'] for line in tax_account_rows), 1000.0)
        self.assertEqual(sum(line['tax'] for line in tax_account_rows), 150.0)
        self.assertTrue(all(account['account_label'] for account in account_tax['periods'][0]['grouped_lines']['account_tax']['sale']))

    def test_interactive_report_rejects_unknown_report_grouping(self):
        with self.assertRaises(ValidationError):
            self.env['report.flousflow_accounting.apr__report_tax'].get_interactive_data(
                '2025-03-01', '2025-03-31', 'posted', report_view='unknown'
            )

    def test_interactive_report_rejects_invalid_periods(self):
        with self.assertRaises(ValidationError):
            self.env['report.flousflow_accounting.apr__report_tax'].get_interactive_data(
                '2025-04-01', '2025-03-01', 'posted'
            )

    def test_interactive_report_compares_previous_periods_and_orders_columns(self):
        self._post('out_invoice', self.tax_sale_a, 1000.0, '2025-03-10')
        self._post('out_invoice', self.tax_sale_a, 500.0, '2025-02-10')
        self._post('out_invoice', self.tax_sale_a, 250.0, '2025-01-10')
        data = self.env['report.flousflow_accounting.apr__report_tax'].get_interactive_data(
            '2025-03-01', '2025-03-31', 'posted',
            comparison_mode='previous_period', comparison_periods=2,
            comparison_sort='ascending',
        )

        self.assertEqual(
            [(period['date_from'], period['date_to']) for period in data['periods']],
            [('2025-01-01', '2025-01-31'), ('2025-02-01', '2025-02-28'),
             ('2025-03-01', '2025-03-31')],
        )
        self.assertEqual([period['totals']['sale']['net'] for period in data['periods']], [250.0, 500.0, 1000.0])

    def test_interactive_report_compares_same_period_last_year_and_custom_dates(self):
        self._post('out_invoice', self.tax_sale_a, 1000.0, '2025-03-10')
        self._post('out_invoice', self.tax_sale_a, 400.0, '2024-03-10')
        self._post('out_invoice', self.tax_sale_a, 200.0, '2024-02-10')
        report = self.env['report.flousflow_accounting.apr__report_tax']
        yearly = report.get_interactive_data(
            '2025-03-01', '2025-03-31', 'posted', comparison_mode='same_period_last_year'
        )
        custom = report.get_interactive_data(
            '2025-03-01', '2025-03-31', 'posted', comparison_mode='custom',
            comparison_date_from='2024-02-01', comparison_date_to='2024-02-29',
        )

        self.assertEqual(yearly['periods'][0]['totals']['sale']['net'], 1000.0)
        self.assertEqual(yearly['periods'][1]['totals']['sale']['net'], 400.0)
        self.assertEqual(custom['periods'][1]['totals']['sale']['net'], 200.0)

    def test_tax_report_xlsx_uses_report_totals_and_scale(self):
        data = {
            'company_name': 'Test Company',
            'date_from': '2025-03-01',
            'date_to': '2025-03-31',
            'target_move': 'posted',
            'groups': {
                'sale': [{'tax_id': 1, 'name': 'Sales 15%', 'net': 1000.0, 'tax': 150.0}],
                'purchase': [],
                'withholding': [],
            },
            'totals': {'sale': {'net': 1000.0, 'tax': 150.0}},
        }

        workbook = build_tax_report_xlsx(data, 'thousand', 'USD')
        self.assertTrue(ZipFile(BytesIO(workbook)).testzip() is None)
        with ZipFile(BytesIO(workbook)) as archive:
            shared_strings = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = ' '.join(node.text or '' for node in shared_strings.iter())
            sheet = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        self.assertIn('Sales 15%', strings)
        self.assertIn('Total Sales', strings)
        numeric_values = [float(node.text) for node in sheet.findall('.//{*}v') if node.text]
        self.assertIn(1.0, numeric_values)
        self.assertIn(0.15, numeric_values)

    def test_tax_report_xlsx_includes_comparison_period_columns(self):
        current = {
            'date_from': '2025-03-01', 'date_to': '2025-03-31', 'current': True,
            'groups': {'sale': [{'tax_id': 1, 'name': 'Sales 15%', 'net': 1000.0, 'tax': 150.0}]},
            'totals': {'sale': {'net': 1000.0, 'tax': 150.0}},
        }
        previous = {
            'date_from': '2025-02-01', 'date_to': '2025-02-28', 'current': False,
            'groups': {'sale': [{'tax_id': 1, 'name': 'Sales 15%', 'net': 500.0, 'tax': 75.0}]},
            'totals': {'sale': {'net': 500.0, 'tax': 75.0}},
        }
        data = {
            'company_name': 'Test Company', 'date_from': current['date_from'], 'date_to': current['date_to'],
            'target_move': 'posted', 'groups': current['groups'], 'totals': current['totals'],
            'periods': [previous, current],
        }
        workbook = build_tax_report_xlsx(data, 'unit', 'USD')
        with ZipFile(BytesIO(workbook)) as archive:
            sheet = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            strings = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))

        text_values = ' '.join(node.text or '' for node in strings.iter())
        numeric_values = [float(node.text) for node in sheet.findall('.//{*}v') if node.text]
        self.assertIn('2025-02-01 – 2025-02-28', text_values)
        self.assertIn('2025-03-01 – 2025-03-31', text_values)
        self.assertIn(500.0, numeric_values)
        self.assertIn(75.0, numeric_values)

    def test_tax_report_xlsx_exports_account_tax_grouping(self):
        period = {
            'date_from': '2025-03-01', 'date_to': '2025-03-31', 'current': True,
            'groups': {'sale': [], 'purchase': [], 'withholding': []},
            'totals': {'sale': {'net': 1000.0, 'tax': 150.0}},
            'grouped_lines': {
                'account_tax': {
                    'sale': [{
                        'account_id': 101, 'account_label': '400000 Product Sales',
                        'lines': [{'tax_id': 7, 'name': 'Sales 15%', 'net': 1000.0, 'tax': 150.0}],
                    }],
                    'purchase': [], 'withholding': [],
                },
            },
        }
        data = {
            'company_name': 'Test Company', 'date_from': period['date_from'], 'date_to': period['date_to'],
            'target_move': 'posted', 'groups': period['groups'], 'totals': period['totals'],
            'periods': [period], 'report_view': 'account_tax',
        }
        workbook = build_tax_report_xlsx(data, 'unit', 'USD')
        with ZipFile(BytesIO(workbook)) as archive:
            strings = ElementTree.fromstring(archive.read('xl/sharedStrings.xml'))
            sheet = ElementTree.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        text_values = ' '.join(node.text or '' for node in strings.iter())
        numeric_values = [float(node.text) for node in sheet.findall('.//{*}v') if node.text]
        self.assertIn('400000 Product Sales', text_values)
        self.assertIn('Sales 15%', text_values)
        self.assertIn(1000.0, numeric_values)
        self.assertIn(150.0, numeric_values)

    def _pay(self, move, payment_date, **values):
        """ Pay `move` from a bank journal whose payments are entries reconciled with it """
        bank = self.company_data['default_journal_bank']
        outstanding = self.env['account.account'].create({
            'code': 'OUTST%d' % move.id, 'name': 'Outstanding', 'account_type': 'asset_current', 'reconcile': True})
        (bank.inbound_payment_method_line_ids | bank.outbound_payment_method_line_ids).payment_account_id = outstanding
        return self.env['account.payment.register'].with_context(active_model='account.move', active_ids=move.ids)\
            .create({'payment_date': payment_date, 'journal_id': bank.id, **values})._create_payments()

    def test_a_cash_basis_tax_is_due_on_its_payment(self):
        """ Invoiced in January and paid in February: the cash basis tax is in the report of February only. """
        self.env.company.tax_exigibility = True
        self.env.company.tax_cash_basis_journal_id = self.company_data['default_journal_misc']
        transition = self.env['account.account'].create({
            'code': 'CABATR', 'name': 'Tax to collect', 'account_type': 'liability_current', 'reconcile': True})
        tax = self.tax_sale_a.copy({'name': 'Cash Basis 15%', 'tax_exigibility': 'on_payment',
                                    'cash_basis_transition_account_id': transition.id})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': self.partner_a.id, 'invoice_date': '2025-01-15',
            'date': '2025-01-15',
            'invoice_line_ids': [Command.create({'name': 'line', 'price_unit': 1000.0, 'tax_ids': [Command.set(tax.ids)]})],
        })
        invoice.action_post()
        self._pay(invoice, '2025-02-10')
        self.assertNotIn('Cash Basis 15%', self._tax_lines('2025-01-01', '2025-01-31')['sale'])
        self.assertEqual(self._tax_lines('2025-02-01', '2025-02-28')['sale']['Cash Basis 15%'], (1000.0, 150.0))

    def test_a_withholding_tax_is_counted_once_and_apart(self):
        """ With l10n_account_withholding_tax: the tax withheld on a payment is in a section of its own, its
        base counted once, on the payment, not on the bill too. """
        if 'is_withholding_tax' not in self.env['account.tax']._fields:
            self.skipTest('l10n_account_withholding_tax is not installed')
        self.env.company.withholding_tax_base_account_id = self.env['account.account'].create({
            'code': 'WITHB', 'name': 'Withholding Tax Base', 'account_type': 'asset_current'})
        sequence = self.env['ir.sequence'].create({'implementation': 'no_gap', 'name': 'Withholding', 'padding': 4})
        withholding = self.tax_purchase_a.copy({
            'name': 'Withholding 5%', 'amount': -5, 'is_withholding_tax': True, 'withholding_sequence_id': sequence.id})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice', 'partner_id': self.partner_a.id, 'invoice_date': '2025-06-01',
            'date': '2025-06-01',
            'invoice_line_ids': [Command.create({'name': 'line', 'price_unit': 1000.0,
                                                 'tax_ids': [Command.set((self.tax_purchase_a | withholding).ids)]})],
        })
        bill.action_post()
        self._pay(bill, '2025-06-20')
        lines = self._tax_lines('2025-06-01', '2025-06-30')
        self.assertEqual(lines['withholding']['Withholding 5%'], (1000.0, 50.0))
        self.assertEqual(lines['purchase'][self.tax_purchase_a.name], (1000.0, 150.0))
        self.assertNotIn('Withholding 5%', lines['purchase'])
