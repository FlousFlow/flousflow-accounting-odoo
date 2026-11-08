from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestInternalTransfer(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source_journal = cls.company_data['default_journal_bank']
        cls.destination_journal = cls.source_journal.copy()
        cls.transfer_account = cls.env.company.transfer_account_id

    def _create_transfer(self, payment_type):
        payment_method_line = (
            self.source_journal.inbound_payment_method_line_ids
            if payment_type == 'inbound'
            else self.source_journal.outbound_payment_method_line_ids
        )[:1]
        self.assertTrue(payment_method_line, 'The source journal needs a payment method line.')
        self.assertTrue(self.transfer_account, 'The company needs an internal transfer account.')
        return self.env['account.payment'].create({
            'amount': 125.0,
            'payment_type': payment_type,
            'journal_id': self.source_journal.id,
            'destination_journal_id': self.destination_journal.id,
            'payment_method_line_id': payment_method_line.id,
            'is_internal_transfer': True,
        })

    def _assert_pair_posted(self, payment, expected_pair_type):
        paired = payment.paired_internal_transfer_payment_id
        self.assertTrue(paired, 'Posting an internal transfer must create its paired payment.')
        self.assertEqual(paired.payment_type, expected_pair_type)
        self.assertEqual(paired.journal_id, self.destination_journal)
        self.assertEqual(paired.destination_journal_id, self.source_journal)
        self.assertEqual((payment.state, paired.state), ('posted', 'posted'))
        self.assertEqual((payment.move_id.state, paired.move_id.state), ('posted', 'posted'))
        transfer_lines = (payment.move_id | paired.move_id).line_ids.filtered(
            lambda line: line.account_id == self.transfer_account
        )
        self.assertAlmostEqual(sum(transfer_lines.mapped('balance')), 0.0)
        return paired

    def test_inbound_internal_transfer_posts_and_cancels_both_legs(self):
        payment = self._create_transfer('inbound')

        payment.action_post()
        paired = self._assert_pair_posted(payment, 'outbound')

        payment.action_cancel()
        self.assertEqual((payment.state, paired.state), ('canceled', 'canceled'))

    def test_outbound_transfer_can_be_reset_and_reposted_as_a_pair(self):
        payment = self._create_transfer('outbound')

        payment.action_post()
        paired = self._assert_pair_posted(payment, 'inbound')

        payment.action_cancel()
        self.assertEqual((payment.state, paired.state), ('canceled', 'canceled'))
        payment.action_draft()
        self.assertEqual((payment.state, paired.state), ('draft', 'draft'))

        payment.action_post()
        self.assertEqual(payment.paired_internal_transfer_payment_id, paired)
        self._assert_pair_posted(payment, 'inbound')


@tagged('post_install', '-at_install')
class TestAutomaticPaymentReconciliation(AccountTestInvoicingCommon):
    """Payments created outside an invoice must still clear open documents."""

    def _invoice(self, move_type, amount, partner=None, invoice_date='2026-01-10'):
        return self.init_invoice(
            move_type,
            partner=partner or self.partner_a,
            amounts=[amount],
            taxes=[],
            invoice_date=invoice_date,
            post=True,
        )

    def _payment(self, payment_type, partner_type, partner, amount, date='2026-01-20'):
        payment = self.env['account.payment'].with_context(force_payment_move=True).create({
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': partner.id,
            'amount': amount,
            'date': date,
            'journal_id': self.company_data['default_journal_cash'].id,
        })
        payment.action_post()
        return payment

    def test_customer_payment_allocates_oldest_invoices_and_leaves_credit(self):
        oldest = self._invoice('out_invoice', 100.0, invoice_date='2026-01-01')
        newest = self._invoice('out_invoice', 80.0, invoice_date='2026-01-15')
        payment = self._payment('inbound', 'customer', self.partner_a, 150.0)

        self.assertEqual(oldest.payment_state, 'paid')
        self.assertEqual(newest.payment_state, 'partial')
        self.assertAlmostEqual(newest.amount_residual, 30.0)
        self.assertTrue(payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        ).mapped('reconciled'))

    def test_vendor_payment_allocates_open_bill(self):
        bill = self._invoice('in_invoice', 125.0, invoice_date='2026-01-01')
        payment = self._payment('outbound', 'supplier', self.partner_a, 125.0)

        self.assertEqual(bill.payment_state, 'paid')
        self.assertTrue(payment.move_id.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable'
        ).mapped('reconciled'))
