from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAutomaticPaymentReconciliation(AccountTestInvoicingCommon):
    """Payments created outside an invoice must still clear open documents."""

    def _invoice(self, move_type, amount, invoice_date='2026-01-10'):
        return self.init_invoice(
            move_type,
            partner=self.partner_a,
            amounts=[amount],
            taxes=[],
            invoice_date=invoice_date,
            post=True,
        )

    def _payment(self, payment_type, partner_type, amount, date='2026-01-20'):
        payment = self.env['account.payment'].with_context(force_payment_move=True).create({
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': self.partner_a.id,
            'amount': amount,
            'date': date,
            'journal_id': self.company_data['default_journal_cash'].id,
        })
        payment.action_post()
        return payment

    def test_customer_payment_allocates_oldest_invoices_and_leaves_credit(self):
        oldest = self._invoice('out_invoice', 100.0, invoice_date='2026-01-01')
        newest = self._invoice('out_invoice', 80.0, invoice_date='2026-01-15')
        payment = self._payment('inbound', 'customer', 150.0)

        self.assertEqual(oldest.payment_state, 'paid')
        self.assertEqual(newest.payment_state, 'partial')
        self.assertAlmostEqual(newest.amount_residual, 30.0)
        self.assertTrue(payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        ).mapped('reconciled'))

    def test_vendor_payment_allocates_open_bill(self):
        bill = self._invoice('in_invoice', 125.0, invoice_date='2026-01-01')
        payment = self._payment('outbound', 'supplier', 125.0)

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable'
        ).mapped('reconciled'))
