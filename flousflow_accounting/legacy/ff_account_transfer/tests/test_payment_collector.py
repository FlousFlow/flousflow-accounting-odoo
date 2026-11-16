from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPaymentCollector(AccountTestInvoicingCommon):
    """Customer payments inherit the partner salesperson as collector."""

    @classmethod
    def setup_independent_company(cls, **kwargs):
        return cls.env.company

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.salesperson = new_test_user(
            cls.env,
            login='payment_collector_salesperson',
            groups='sales_team.group_sale_salesman',
        )
        cls.partner_a.user_id = cls.salesperson
        cls.manual_collector = new_test_user(
            cls.env,
            login='payment_manual_collector',
            groups='sales_team.group_sale_salesman',
        )

    def _payment(self, partner_type='customer', salesperson_id=False):
        vals = {
            'payment_type': 'inbound' if partner_type == 'customer' else 'outbound',
            'partner_type': partner_type,
            'partner_id': self.partner_a.id,
            'amount': 10.0,
            'date': '2026-01-20',
            'journal_id': self.company_data['default_journal_cash'].id,
        }
        if salesperson_id:
            vals['salesperson_id'] = salesperson_id
        return self.env['account.payment'].with_context(force_payment_move=True).create(vals)

    def test_customer_payment_defaults_to_partner_salesperson(self):
        payment = self._payment()
        self.assertEqual(payment.salesperson_id, self.salesperson)

    def test_manual_collector_is_preserved(self):
        payment = self._payment(salesperson_id=self.manual_collector.id)
        self.assertEqual(payment.salesperson_id, self.manual_collector)

    def test_vendor_payment_does_not_get_customer_salesperson(self):
        payment = self._payment(partner_type='supplier')
        self.assertFalse(payment.salesperson_id)

    def test_server_side_partner_change_fills_blank_collector(self):
        original_partner = self.env['res.partner'].create({
            'name': 'Collector Original Partner',
        })
        other_partner = self.env['res.partner'].create({
            'name': 'Collector Change Partner',
            'user_id': self.manual_collector.id,
        })
        payment = self.env['account.payment'].with_context(force_payment_move=True).create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': original_partner.id,
            'amount': 10.0,
            'date': '2026-01-20',
            'journal_id': self.company_data['default_journal_cash'].id,
        })
        self.assertFalse(payment.salesperson_id)
        payment.write({'partner_id': other_partner.id})
        self.assertEqual(payment.salesperson_id, self.manual_collector)

    def test_register_payment_values_include_collector(self):
        invoice = self.init_invoice(
            'out_invoice',
            partner=self.partner_a,
            amounts=[25.0],
            taxes=[],
            invoice_date='2026-01-10',
            post=True,
        )
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move',
            active_ids=invoice.ids,
        ).create({})
        batch = wizard._get_batches()[0]
        vals = wizard._create_payment_vals_from_wizard(batch)
        self.assertEqual(vals['salesperson_id'], self.salesperson.id)
