# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFiscalYear(TransactionCase):

    def test_fiscal_year_create(self):
        fy = self.env['flousflow.account.fiscal.year'].create({
            'name': 'FY 2026',
            'date_from': '2026-07-01',
            'date_to': '2027-06-30',
        })
        self.assertTrue(fy)

    def test_fiscal_year_overlap(self):
        self.env['flousflow.account.fiscal.year'].create({
            'name': 'FY 2026',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.fiscal.year'].create({
                'name': 'FY Overlap',
                'date_from': '2026-06-01',
                'date_to': '2027-05-31',
            })


class TestRecurring(TransactionCase):

    def setUp(self):
        super().setUp()
        self.journal = self.env['account.journal'].search(
            [('type', 'in', ('bank', 'cash')),
             ('company_id', '=', self.env.company.id)], limit=1)
        if not self.journal:
            self.skipTest('No bank/cash journal available')
        outstanding_account = (
            self.journal.suspense_account_id or self.journal.default_account_id)
        if not outstanding_account:
            self.skipTest('A payment outstanding account is required')
        self.journal.inbound_payment_method_line_ids.payment_account_id = outstanding_account
        self.journal.outbound_payment_method_line_ids.payment_account_id = outstanding_account
        # Odoo 20 requires a receivable/payable destination account when a
        # payment move is generated.  The minimal test chart does not assign
        # those company defaults, so configure the standard chart accounts in
        # the fixture instead of weakening the ORM constraint.
        receivable = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id),
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)
        payable = self.env['account.account'].search([
            ('company_ids', 'in', self.env.company.id),
            ('account_type', '=', 'liability_payable'),
        ], limit=1)
        if not receivable or not payable:
            self.skipTest('Receivable and payable accounts are required')
        company_partner = self.env.company.partner_id
        company_partner.property_account_receivable_id = receivable
        company_partner.property_account_payable_id = payable
        self.receivable_account = receivable
        self.payable_account = payable

    def _partner(self, name):
        return self.env['res.partner'].create({
            'name': name,
            'property_account_receivable_id': self.receivable_account.id,
            'property_account_payable_id': self.payable_account.id,
        })

    def test_recurring_schedule(self):
        partner = self._partner('Recurring Partner')
        rec = self.env['flousflow.account.recurring'].create({
            'partner_id': partner.id,
            'amount': 100.0,
            'journal_id': self.journal.id,
            'payment_type': 'outbound',
            'recurring_period': 'months',
            'recurring_interval': 1,
            'date_begin': '2026-01-01',
            'date_end': '2026-06-01',
        })
        rec.action_generate_schedule()
        self.assertEqual(rec.state, 'done')
        self.assertEqual(len(rec.line_ids), 6)

    def test_recurring_generate_payments(self):
        partner = self._partner('Recurring Partner 2')
        rec = self.env['flousflow.account.recurring'].create({
            'partner_id': partner.id,
            'amount': 50.0,
            'journal_id': self.journal.id,
            'payment_type': 'inbound',
            'recurring_period': 'days',
            'recurring_interval': 1,
            'date_begin': '2026-01-01',
            'date_end': '2026-01-03',
        })
        rec.action_generate_schedule()
        rec.action_generate_payments()
        self.assertTrue(all(l.state in ('in_process', 'paid') for l in rec.line_ids))
        self.assertTrue(all(l.payment_id for l in rec.line_ids))
        self.assertTrue(all(l.payment_id.state != 'draft' for l in rec.line_ids))

        payment_ids = rec.line_ids.payment_id.ids
        rec.action_generate_payments()
        self.assertEqual(rec.line_ids.payment_id.ids, payment_ids)

    def test_recurring_interval_must_be_positive(self):
        partner = self._partner('Invalid Interval')
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.recurring'].create({
                'partner_id': partner.id,
                'amount': 50.0,
                'journal_id': self.journal.id,
                'payment_type': 'outbound',
                'recurring_period': 'months',
                'recurring_interval': 0,
                'date_begin': date.today(),
                'date_end': date.today() + timedelta(days=30),
            })

    def test_generate_payments_only_processes_selected_schedule(self):
        partner = self._partner('Scoped Schedule')
        values = {
            'partner_id': partner.id,
            'amount': 25.0,
            'journal_id': self.journal.id,
            'payment_type': 'outbound',
            'recurring_period': 'days',
            'recurring_interval': 1,
            'date_begin': date.today(),
            'date_end': date.today(),
        }
        selected = self.env['flousflow.account.recurring'].create(values)
        other = self.env['flousflow.account.recurring'].create(values)
        (selected | other).action_generate_schedule()

        selected.action_generate_payments()

        self.assertTrue(selected.line_ids.payment_id)
        self.assertFalse(other.line_ids.payment_id)

    def test_recurring_cron_processes_due_lines_only(self):
        partner = self._partner('Cron Schedule')
        recurring = self.env['flousflow.account.recurring'].create({
            'partner_id': partner.id,
            'amount': 75.0,
            'journal_id': self.journal.id,
            'payment_type': 'outbound',
            'recurring_period': 'days',
            'recurring_interval': 1,
            'date_begin': date.today(),
            'date_end': date.today() + timedelta(days=1),
        })
        recurring.action_generate_schedule()

        self.env['flousflow.account.recurring.line']._cron_generate_due_payments()

        due = recurring.line_ids.filtered(lambda line: line.date == date.today())
        future = recurring.line_ids - due
        self.assertTrue(due.payment_id)
        self.assertFalse(future.payment_id)
        cron = self.env.ref('flousflow_accounting.ir_cron_recurring_payments')
        self.assertTrue(cron.active)

    def test_recurring_amount_validation(self):
        partner = self._partner('Bad Amount')
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.recurring'].create({
                'partner_id': partner.id,
                'amount': 0.0,
                'journal_id': self.journal.id,
                'payment_type': 'inbound',
                'recurring_period': 'months',
                'recurring_interval': 1,
                'date_begin': '2026-01-01',
                'date_end': '2026-06-01',
            })
