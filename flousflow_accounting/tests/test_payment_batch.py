# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestPaymentBatch(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.journal = self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', 'in', ('bank', 'cash')),
        ], limit=1)
        if not self.journal:
            self.skipTest('A bank or cash journal is required')
        method_line = self.journal.outbound_payment_method_line_ids[:1]
        if not method_line:
            self.skipTest('An outbound payment method is required')
        self.partner = self.env['res.partner'].create({'name': 'Batch Vendor'})
        self.payment = self.env['account.payment'].create({
            'date': '2026-08-22',
            'amount': 125.0,
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'payment_method_line_id': method_line.id,
        })

    def _batch(self):
        return self.env['flousflow.account.payment.batch'].create({
            'date': '2026-08-22',
            'journal_id': self.journal.id,
            'payment_type': 'outbound',
            'payment_ids': [(6, 0, self.payment.ids)],
        })

    def test_batch_approval_posts_standard_payment(self):
        batch = self._batch()
        self.assertNotEqual(batch.name, 'New')
        self.assertEqual(batch.payment_count, 1)
        self.assertAlmostEqual(batch.amount_total, 125.0, places=2)

        batch.action_submit()
        self.assertEqual(batch.state, 'submitted')
        batch.action_approve()
        self.assertEqual(batch.state, 'approved')
        batch.action_post()

        self.assertEqual(batch.state, 'posted')
        self.assertNotEqual(self.payment.state, 'draft')
        with self.assertRaises(UserError):
            batch.action_cancel()

    def test_batch_rejects_empty_or_mismatched_payments(self):
        empty = self.env['flousflow.account.payment.batch'].create({
            'journal_id': self.journal.id,
            'payment_type': 'outbound',
        })
        with self.assertRaises(ValidationError):
            empty.action_submit()

        batch = self._batch()
        self.payment.payment_type = 'inbound'
        with self.assertRaises(ValidationError):
            batch.action_submit()

    def test_accountant_cannot_approve_or_post_batch(self):
        accountant = self.env['res.users'].create({
            'name': 'Batch Accountant',
            'login': 'batch.accountant@example.com',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
            'company_id': self.company.id,
            'company_ids': [(6, 0, self.company.ids)],
        })
        batch = self._batch()
        batch.action_submit()
        with self.assertRaises(AccessError):
            batch.with_user(accountant).action_approve()
