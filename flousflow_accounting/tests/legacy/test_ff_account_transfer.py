from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestInternalTransfer(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source_journal = cls.company_data['default_journal_bank']
        cls.source_account = cls.source_journal.default_account_id
        cls.destination_account = cls.env['account.account'].create({
            'name': 'Direct Transfer Destination Test',
            'code': 'TSTTRFROOT',
            'account_type': 'asset_cash',
        })
        cls.destination_journal = cls.source_journal.copy({
            'default_account_id': cls.destination_account.id,
        })
        cls.transfer_account = cls.env.company.transfer_account_id

    def _create_transfer(self, payment_type):
        payment_method_line = (
            self.source_journal.inbound_payment_method_line_ids
            if payment_type == 'inbound'
            else self.source_journal.outbound_payment_method_line_ids
        )[:1]
        self.assertTrue(payment_method_line, 'The source journal needs a payment method line.')
        return self.env['account.payment'].create({
            'amount': 125.0,
            'payment_type': payment_type,
            'journal_id': self.source_journal.id,
            'destination_journal_id': self.destination_journal.id,
            'payment_method_line_id': payment_method_line.id,
            'is_internal_transfer': True,
        })

    def _assert_direct_move(self, payment, payment_type):
        self.assertFalse(payment.paired_internal_transfer_payment_id)
        self.assertEqual(payment.state, 'paid')
        move = payment.move_id
        self.assertEqual(move.journal_id, self.source_journal)
        self.assertEqual(move.state, 'posted')
        self.assertEqual(len(move.line_ids), 2)
        source_line = move.line_ids.filtered(
            lambda line: line.account_id == self.source_account
        )
        destination_line = move.line_ids.filtered(
            lambda line: line.account_id == self.destination_account
        )
        self.assertEqual(len(source_line), 1)
        self.assertEqual(len(destination_line), 1)
        self.assertFalse(move.line_ids.filtered(
            lambda line: line.account_id == self.transfer_account
        ))
        if payment_type == 'outbound':
            self.assertAlmostEqual(destination_line.debit, 125.0)
            self.assertAlmostEqual(source_line.credit, 125.0)
        else:
            self.assertAlmostEqual(source_line.debit, 125.0)
            self.assertAlmostEqual(destination_line.credit, 125.0)
        return move

    def test_inbound_internal_transfer_posts_one_direct_move(self):
        payment = self._create_transfer('inbound')

        payment.action_post()
        move = self._assert_direct_move(payment, 'inbound')

        payment.action_cancel()
        self.assertEqual(payment.state, 'canceled')
        self.assertEqual(move.state, 'cancel')

    def test_outbound_transfer_can_be_reset_and_reposted_with_same_direct_move(self):
        payment = self._create_transfer('outbound')

        payment.action_post()
        move = self._assert_direct_move(payment, 'outbound')

        payment.action_cancel()
        self.assertEqual(payment.state, 'canceled')
        self.assertEqual(move.state, 'cancel')
        payment.action_draft()
        self.assertEqual(payment.state, 'draft')

        payment.action_post()
        self.assertEqual(payment.move_id, move)
        self._assert_direct_move(payment, 'outbound')
