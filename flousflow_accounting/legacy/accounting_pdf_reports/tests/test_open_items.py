from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.flousflow_accounting.legacy.accounting_pdf_reports.controllers.open_items import build_open_items_xlsx


@tagged('post_install', '-at_install')
class TestOpenItems(AccountTestInvoicingCommon):

    def setUp(self):
        super().setUp()
        self.report = self.env['report.flousflow_accounting.apr__report_agedpartnerbalance']

    def _pay(self, invoice, amount, date):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'payment_date': date,
            'amount': amount,
            'payment_difference_handling': 'open',
        })._create_payments()

    def test_open_items_use_native_residual_as_of_date(self):
        invoice = self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[1000.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        self._pay(invoice, 400.0, '2025-07-01')
        self._pay(invoice, 600.0, '2026-01-15')
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )

        early = self.report.get_open_items_data(
            date_from='2025-06-15', result_selection='customer', partner_ids=[self.partner_a.id],
        )
        later = self.report.get_open_items_data(
            date_from='2025-12-31', result_selection='customer', partner_ids=[self.partner_a.id],
        )
        settled = self.report.get_open_items_data(
            date_from='2026-02-01', result_selection='customer', partner_ids=[self.partner_a.id],
        )

        early_line = next(line for row in early['rows'] for line in row['lines'] if line['id'] == receivable.id)
        later_line = next(line for row in later['rows'] for line in row['lines'] if line['id'] == receivable.id)
        self.assertEqual(early_line['residual'], 1000.0)
        self.assertEqual(later_line['residual'], 600.0)
        self.assertFalse(any(line['id'] == receivable.id for row in settled['rows'] for line in row['lines']))

    def test_open_items_filters_account_type_and_move_state(self):
        customer_invoice = self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        vendor_bill = self.init_invoice(
            'in_invoice', partner=self.partner_b, amounts=[200.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        draft_invoice = self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[300.0], taxes=[],
            invoice_date='2025-06-01', post=False,
        )
        date_from = '2025-12-31'

        customer = self.report.get_open_items_data(date_from=date_from, result_selection='customer')
        payable = self.report.get_open_items_data(date_from=date_from, result_selection='supplier')
        posted = self.report.get_open_items_data(date_from=date_from, result_selection='trade', target_move='posted')
        all_entries = self.report.get_open_items_data(date_from=date_from, result_selection='trade', target_move='all')
        line_ids = lambda data: {line['id'] for row in data['rows'] for line in row['lines']}

        self.assertTrue(line_ids(customer) & set(customer_invoice.line_ids.ids))
        self.assertTrue(line_ids(payable) & set(vendor_bill.line_ids.ids))
        self.assertFalse(line_ids(posted) & set(draft_invoice.line_ids.ids))
        self.assertTrue(line_ids(all_entries) & set(draft_invoice.line_ids.ids))
        self.assertGreater(posted['unposted_count'], 0)

    def test_open_items_action_opens_interactive_report_for_partner(self):
        action = self.report.get_open_items_action(self.partner_a.id)
        self.assertEqual(action['type'], 'ir.actions.client')
        self.assertEqual(action['tag'], 'flousflow_accounting.apr__open_items')
        self.assertEqual(action['context']['default_partner_ids'], [self.partner_a.id])

    def test_open_items_send_reminder_opens_the_existing_followup_wizard(self):
        action = self.report.get_open_items_reminder_action(self.partner_a.id)

        self.assertEqual(action['res_model'], 'followup.send')
        self.assertEqual(action['target'], 'new')
        self.assertEqual(action['context']['active_model'], 'res.partner')
        self.assertEqual(action['context']['active_ids'], [self.partner_a.id])

    def test_open_items_can_exclude_an_invoice_from_reminders(self):
        invoice = self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )[:1]

        self.report.set_open_items_no_reminder(receivable.ids, True)

        self.assertTrue(receivable.no_followup)

    def test_open_items_print_uses_the_pdf_action_and_current_filters(self):
        invoice = self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )

        action = self.report.print_open_items(
            date_from='2025-12-31', result_selection='customer',
            partner_ids=[self.partner_a.id],
        )

        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'flousflow_accounting.apr__open_items_document')
        self.assertEqual(action['report_type'], 'qweb-pdf')
        self.assertTrue(invoice)
        html, _report_type = self.env['ir.actions.report']._render_qweb_html(
            action['report_name'], [], data=action['data'],
        )
        self.assertIn(invoice.name.encode(), html)
        self.assertIn(b'100.00', html)

    def test_open_items_xlsx_contains_a_workbook(self):
        self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        data = self.report.get_open_items_data(
            date_from='2025-12-31', result_selection='customer',
            partner_ids=[self.partner_a.id],
        )
        company_currency = self.env.company.currency_id
        currencies = {company_currency.id: company_currency}

        workbook = build_open_items_xlsx(data, 'unit', company_currency, currencies)

        self.assertTrue(workbook.startswith(b'PK'))
