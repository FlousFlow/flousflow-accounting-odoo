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
        for direction in ('inbound', 'outbound'):
            source_lines = getattr(cls.source_journal, f'{direction}_payment_method_line_ids')
            destination_lines = getattr(cls.destination_journal, f'{direction}_payment_method_line_ids')
            for source_line, destination_line in zip(source_lines, destination_lines):
                destination_line.payment_account_id = source_line.payment_account_id

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
        self.assertIn(payment.state, ('posted', 'paid'))
        self.assertIn(paired.state, ('posted', 'paid'))
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
