from odoo.tests import tagged
from odoo.exceptions import UserError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAgedPartnerBalance(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_data_2 = cls.setup_other_company()

    def _aged_lines(self, env, date='2025-12-31'):
        wizard = env['account.aged.trial.balance'].create({'date_from': date})
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        values = env['report.flousflow_accounting.apr__report_agedpartnerbalance'].with_context(
            active_model=wizard._name, active_id=wizard.id)._get_report_values(None, data)
        return {line['partner_id']: line for line in values['get_partner_lines']}

    def _aged_balance(self, env, date='2025-12-31'):
        return {partner_id: line['total'] for partner_id, line in self._aged_lines(env, date).items()}

    def _pay(self, invoice, amount, date):
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({'payment_date': date, 'amount': amount, 'payment_difference_handling': 'open'})._create_payments()

    def test_aged_balance_of_the_active_company(self):
        company_2 = self.company_data_2['company']
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-06-01', post=True)
        self.init_invoice('out_invoice', partner=self.partner_b, amounts=[250.0], taxes=[],
                          invoice_date='2025-06-01', post=True, company=company_2)
        user = self.env.user
        user.company_ids |= company_2
        self.assertNotEqual(user.company_id, company_2)

        # the report of the company selected in the switcher, not the default company of the user
        env_company_2 = self.env(context=dict(self.env.context, allowed_company_ids=[company_2.id, user.company_id.id]))
        self.assertEqual(self._aged_balance(env_company_2), {self.partner_b.id: 250.0})
        self.assertEqual(self._aged_balance(self.env), {self.partner_a.id: 100.0})

    def test_aged_balance_as_of_a_date(self):
        """ An item counts with what was paid until the date of the report, not after it """
        invoice = self.init_invoice('out_invoice', partner=self.partner_a, amounts=[1000.0], taxes=[],
                                    invoice_date='2025-06-01', post=True)
        self._pay(invoice, 400.0, '2025-07-01')
        self._pay(invoice, 600.0, '2026-01-15')
        self.assertTrue(invoice.line_ids.filtered(lambda line: line.account_id.account_type == 'asset_receivable').reconciled)

        self.assertEqual(self._aged_balance(self.env, '2025-06-15'), {self.partner_a.id: 1000.0})
        self.assertEqual(self._aged_balance(self.env, '2025-12-31'), {self.partner_a.id: 600.0})
        self.assertEqual(self._aged_balance(self.env, '2026-02-01'), {})

    def test_aged_balance_periods(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-12-20', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[200.0], taxes=[],
                          invoice_date='2025-11-15', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[300.0], taxes=[],
                          invoice_date='2025-01-10', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[50.0], taxes=[],
                          invoice_date='2025-12-31', post=True)

        line = self._aged_lines(self.env)[self.partner_a.id]
        self.assertEqual(line['direction'], 50.0)  # not due
        self.assertEqual(line['4'], 100.0)  # 1-30 days
        self.assertEqual(line['3'], 200.0)  # 31-60 days
        self.assertEqual(line['0'], 300.0)  # more than 120 days
        self.assertEqual(line['total'], 650.0)

    def test_interactive_report_custom_periods_for_customers_and_suppliers(self):
        """Custom period lengths classify customer and vendor balances consistently."""
        date_from = '2025-12-31'
        amounts_by_date = [
            ('2025-12-20', 100.0),  # 1-15 days
            ('2025-12-15', 200.0),  # 16-30 days
            ('2025-12-01', 50.0),   # 16-30 days, lower boundary
            ('2025-11-30', 300.0),  # 31-45 days
            ('2025-11-01', 400.0),  # 46-60 days
            ('2025-10-31', 500.0),  # older than 60 days
            (date_from, 25.0),      # not due as of the report date
        ]
        customer = self.partner_a
        supplier = self.partner_b

        for move_type, partner in (('out_invoice', customer), ('in_invoice', supplier)):
            for invoice_date, amount in amounts_by_date:
                self.init_invoice(
                    move_type,
                    partner=partner,
                    amounts=[amount],
                    taxes=[],
                    invoice_date=invoice_date,
                    post=True,
                )

        report = self.env['report.flousflow_accounting.apr__report_agedpartnerbalance']
        customer_data = report.get_interactive_data(
            result_selection='customer',
            date_from=date_from,
            period_length=15,
            date_basis='due_date',
        )
        customer_row = next(row for row in customer_data['rows'] if row['partner_id'] == customer.id)
        self.assertEqual(customer_data['period_length'], 15)
        self.assertEqual(customer_row['buckets'], [100.0, 250.0, 300.0, 400.0, 500.0])
        self.assertEqual(customer_row['not_due'], 25.0)
        self.assertEqual(customer_row['total'], 1575.0)
        self.assertEqual(
            customer_row['total'],
            customer_row['not_due'] + sum(customer_row['buckets']),
        )

        supplier_data = report.get_interactive_data(
            result_selection='supplier',
            date_from=date_from,
            period_length=15,
            date_basis='due_date',
        )
        supplier_row = next(row for row in supplier_data['rows'] if row['partner_id'] == supplier.id)
        self.assertEqual(supplier_data['period_length'], 15)
        # partner_b uses 30% due immediately and 70% due at the end of the
        # following month, so supplier installments fall into different buckets.
        self.assertEqual(supplier_row['buckets'], [-30.0, -75.0, -440.0, -120.0, -150.0])
        self.assertEqual(supplier_row['not_due'], -760.0)
        self.assertEqual(supplier_row['total'], -1575.0)
        self.assertEqual(
            supplier_row['total'],
            supplier_row['not_due'] + sum(supplier_row['buckets']),
        )

    def test_interactive_report_uses_individually_configured_bucket_ends(self):
        date_from = '2025-12-31'
        for invoice_date, amount in (
            ('2025-12-26', 10.0),  # 1-10
            ('2025-12-16', 20.0),  # 11-20
            ('2025-12-01', 30.0),  # 21-40
            ('2025-11-11', 40.0),  # 41-60
            ('2025-10-01', 50.0),  # older than 60
        ):
            self.init_invoice(
                'out_invoice', partner=self.partner_a, amounts=[amount], taxes=[],
                invoice_date=invoice_date, post=True,
            )

        report = self.env['report.flousflow_accounting.apr__report_agedpartnerbalance']
        data = report.get_interactive_data(
            result_selection='customer', date_from=date_from, date_basis='invoice_date',
            bucket_ends=[10, 20, 40, 60],
        )
        row = next(item for item in data['rows'] if item['partner_id'] == self.partner_a.id)

        self.assertEqual(data['bucket_ends'], [10, 20, 40, 60])
        self.assertEqual(row['buckets'], [10.0, 20.0, 30.0, 40.0, 50.0])
        self.assertEqual(row['total'], row['not_due'] + sum(row['buckets']))

    def test_interactive_report_rejects_invalid_bucket_ends(self):
        report = self.env['report.flousflow_accounting.apr__report_agedpartnerbalance']
        for bucket_ends in ([30, 20, 90, 120], [30, 30, 90, 120], [30, 60, 90], [30, 60, 90, 16000]):
            with self.subTest(bucket_ends=bucket_ends), self.assertRaises(UserError):
                report.get_interactive_data(bucket_ends=bucket_ends)
