# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from lxml import etree

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestFinancialReports(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        # Ensure a receivable/payable account and income/expense exist
        # (available in both the generic and country chart of accounts).
        self.receivable = self.env['account.account'].search(
            [('account_type', '=', 'asset_receivable')], limit=1)
        self.payable = self.env['account.account'].search(
            [('account_type', '=', 'liability_payable')], limit=1)
        self.income = self.env['account.account'].search(
            [('account_type', '=', 'income')], limit=1)
        self.expense = self.env['account.account'].search(
            [('account_type', '=', 'expense')], limit=1)
        if not all([self.receivable, self.payable, self.income, self.expense]):
            self.skipTest('Required accounts not available')

    def _post_move(
            self, debit_acc, credit_acc, amount, partner=None,
            posting_date='2026-01-15'):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': posting_date,
            'line_ids': [
                (0, 0, {
                    'account_id': debit_acc.id,
                    'debit': amount,
                    'credit': 0.0,
                    'name': 'Test debit',
                    'partner_id': partner.id if partner else False,
                }),
                (0, 0, {
                    'account_id': credit_acc.id,
                    'debit': 0.0,
                    'credit': amount,
                    'name': 'Test credit',
                    'partner_id': partner.id if partner else False,
                }),
            ],
        })
        move.action_post()
        return move

    def test_report_wizard_defaults(self):
        wizard = self.env['flousflow.account.report'].create({})
        self.assertEqual(wizard.report_type, 'profit_loss')
        self.assertEqual(wizard.date_filter, 'current_year')
        self.assertTrue(wizard.date_from)
        self.assertTrue(wizard.date_to)

    def test_standard_date_filter_presets(self):
        today = fields.Date.today()
        wizard = self.env['flousflow.account.report'].new({})

        wizard.date_filter = 'current_month'
        wizard._onchange_date_filter()
        self.assertEqual(wizard.date_from, today.replace(day=1))
        self.assertEqual(wizard.date_to, today)

        wizard.date_filter = 'current_quarter'
        wizard._onchange_date_filter()
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        self.assertEqual(
            wizard.date_from, today.replace(month=quarter_month, day=1))

        wizard.date_filter = 'current_year'
        wizard._onchange_date_filter()
        self.assertEqual(wizard.date_from, today.replace(month=1, day=1))

    def test_previous_year_comparison(self):
        self._post_move(
            self.receivable, self.income, 80.0,
            posting_date='2025-03-15')
        self._post_move(
            self.receivable, self.income, 100.0,
            posting_date='2026-03-15')
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'comparison_mode': 'previous_year',
            'account_ids': self.receivable.ids,
        })

        wizard.action_generate()

        total = wizard.line_ids.filtered('is_total')
        self.assertAlmostEqual(total.balance, 100.0, places=2)
        self.assertAlmostEqual(total.comparison_balance, 80.0, places=2)
        self.assertAlmostEqual(total.variance, 20.0, places=2)
        self.assertAlmostEqual(total.variance_percent, 25.0, places=2)

    def test_fold_unfold_and_report_notes_are_preserved(self):
        self._post_move(self.receivable, self.income, 125.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'account_ids': self.receivable.ids,
            'report_note': 'Reviewed against the receivable control account.',
        })
        wizard.action_generate()

        wizard.action_fold_all()
        self.assertEqual(wizard.display_mode, 'collapsed')
        self.assertFalse(wizard.visible_line_ids.filtered('move_id'))
        wizard.action_unfold_all()
        self.assertEqual(wizard.display_mode, 'expanded')
        self.assertTrue(wizard.visible_line_ids.filtered('move_id'))
        self.assertEqual(
            wizard.report_note,
            'Reviewed against the receivable control account.')

    def test_collapsed_mode_keeps_totals_and_hides_journal_details(self):
        self._post_move(self.receivable, self.income, 125.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'display_mode': 'collapsed',
            'account_ids': self.receivable.ids,
        })

        wizard.action_generate()

        self.assertTrue(wizard.line_ids.filtered('move_id'))
        self.assertFalse(wizard.visible_line_ids.filtered('move_id'))
        self.assertTrue(wizard.visible_line_ids.filtered('is_total'))

    def test_saved_filter_round_trip_and_same_name_update(self):
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_filter': 'custom',
            'date_from': '2026-02-01',
            'date_to': '2026-02-28',
            'comparison_mode': 'previous_year',
            'display_mode': 'collapsed',
            'account_ids': self.receivable.ids,
            'preset_name': 'Monthly review',
        })

        wizard.action_save_preset()

        preset = wizard.preset_id
        self.assertEqual(preset.user_id, self.env.user)
        self.assertEqual(preset.company_id, self.company)
        self.assertEqual(preset.account_ids, self.receivable)
        wizard.preset_name = 'Monthly review'
        wizard.target_move = 'all'
        wizard.action_save_preset()
        self.assertEqual(self.env['flousflow.account.report.preset'].search_count([
            ('name', '=', 'Monthly review'),
            ('user_id', '=', self.env.user.id),
        ]), 1)
        self.assertEqual(preset.target_move, 'all')

        restored = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'preset_id': preset.id,
        })
        restored.action_apply_preset()
        self.assertEqual(restored.date_filter, 'custom')
        self.assertEqual(restored.date_from, fields.Date.from_string('2026-02-01'))
        self.assertEqual(restored.comparison_mode, 'previous_year')
        self.assertEqual(restored.display_mode, 'collapsed')
        self.assertEqual(restored.target_move, 'all')
        self.assertEqual(restored.account_ids, self.receivable)

    def test_saved_filter_buttons_require_their_inputs(self):
        wizard = self.env['flousflow.account.report'].create({})
        with self.assertRaises(UserError):
            wizard.action_save_preset()
        with self.assertRaises(UserError):
            wizard.action_apply_preset()

    def test_report_rejects_inverted_date_range(self):
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.report'].create({
                'date_from': '2026-12-31',
                'date_to': '2026-01-01',
            })

    def test_report_print_requires_generated_lines(self):
        wizard = self.env['flousflow.account.report'].create({
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        with self.assertRaises(UserError):
            wizard.action_print()
        self._post_move(self.receivable, self.income, 50.0)
        wizard.action_generate()
        action = wizard.action_print()
        if action['type'] == 'ir.actions.act_window':
            # Odoo opens the standard document-layout configurator on first print.
            action = action['context']['report_action']
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(
            action['report_name'],
            'flousflow_accounting.report_financial_statement')

    def test_general_ledger(self):
        partner = self.env['res.partner'].create({'name': 'Report Partner'})
        self._post_move(self.receivable, self.income, 100.0, partner)
        self._post_move(self.expense, self.payable, 40.0, partner)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        self.assertTrue(wizard.line_ids)
        # Every GL line must have an account
        self.assertTrue(all(l.account_id for l in wizard.line_ids))
        receivable_total = wizard.line_ids.filtered(
            lambda line: line.account_id == self.receivable and line.is_total)
        self.assertEqual(len(receivable_total), 1)
        self.assertTrue(wizard.line_ids.filtered(
            lambda line: line.account_id == self.receivable and line.move_id))
        action = receivable_total.action_open_entries()
        self.assertEqual(action['res_model'], 'account.move.line')
        self.assertIn(('account_id', '=', self.receivable.id), action['domain'])

    def test_previous_period_comparison(self):
        self._post_move(
            self.receivable, self.income, 80.0,
            posting_date='2025-01-15')
        self._post_move(self.receivable, self.income, 100.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'comparison_mode': 'previous_period',
        })
        wizard.action_generate()
        line = wizard.line_ids.filtered(
            lambda row: row.account_id == self.receivable and row.is_total)
        self.assertAlmostEqual(line.balance, 100.0, places=2)
        self.assertAlmostEqual(line.comparison_balance, 80.0, places=2)
        self.assertAlmostEqual(line.variance, 20.0, places=2)

    def test_report_filters_by_journal_account_and_partner(self):
        selected_partner = self.env['res.partner'].create({'name': 'Selected Partner'})
        other_partner = self.env['res.partner'].create({'name': 'Other Partner'})
        selected_move = self._post_move(
            self.receivable, self.income, 70.0, selected_partner)
        self._post_move(self.receivable, self.income, 30.0, other_partner)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
            'journal_ids': selected_move.journal_id.ids,
            'account_ids': self.receivable.ids,
            'partner_ids': selected_partner.ids,
        })

        wizard.action_generate()

        self.assertEqual(wizard.line_ids.account_id, self.receivable)
        total = wizard.line_ids.filtered('is_total')
        self.assertAlmostEqual(total.debit, 70.0, places=2)
        action = wizard.action_open_all_entries()
        self.assertIn(('journal_id', 'in', selected_move.journal_id.ids), action['domain'])
        self.assertIn(('account_id', 'in', self.receivable.ids), action['domain'])
        self.assertIn(('partner_id', 'in', selected_partner.ids), action['domain'])

    def test_report_can_optionally_include_draft_entries(self):
        draft = self.env['account.move'].create({
            'move_type': 'entry', 'date': '2026-01-15',
            'line_ids': [
                (0, 0, {'account_id': self.receivable.id, 'debit': 25.0, 'name': 'Draft'}),
                (0, 0, {'account_id': self.income.id, 'credit': 25.0, 'name': 'Draft'}),
            ],
        })
        posted_only = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
            'account_ids': self.receivable.ids,
        })
        posted_only.action_generate()
        self.assertFalse(posted_only.line_ids)
        with_drafts = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
            'account_ids': self.receivable.ids,
            'target_move': 'all',
        })

        with_drafts.action_generate()

        self.assertAlmostEqual(
            with_drafts.line_ids.filtered('is_total').debit, 25.0, places=2)
        self.assertEqual(draft.state, 'draft')

    def test_xlsx_export_creates_downloadable_attachment(self):
        self._post_move(self.receivable, self.income, 50.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'general_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()

        action = wizard.action_export_xlsx()

        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', wizard._name), ('res_id', '=', wizard.id),
            ('mimetype', '=', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
        ], limit=1)
        self.assertTrue(attachment)
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn(str(attachment.id), action['url'])

    def test_profit_loss(self):
        self._post_move(self.receivable, self.income, 100.0)
        self._post_move(self.expense, self.payable, 40.0)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'profit_loss',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        self.assertTrue(wizard.line_ids)
        # A net profit total line must exist
        self.assertTrue(wizard.line_ids.filtered(lambda l: l.is_total))

    def test_balance_sheet(self):
        self._post_move(self.receivable, self.income, 100.0)
        self._post_move(self.expense, self.payable, 40.0)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'balance_sheet',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        self.assertTrue(wizard.line_ids)
        self.assertTrue(wizard.line_ids.filtered(lambda l: l.is_total))

    def test_balance_sheet_is_cumulative_before_date_from(self):
        self._post_move(
            self.receivable, self.income, 125.0,
            posting_date='2025-12-15')
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'balance_sheet',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        receivables = wizard.line_ids.filtered(lambda line: line.code == 'receivables')
        self.assertAlmostEqual(receivables.balance, 125.0, places=2)

    def test_aged_receivable(self):
        partner = self.env['res.partner'].create({'name': 'Aged Partner'})
        self._post_move(self.receivable, self.income, 150.0, partner)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'aged_receivable',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        lines = wizard.line_ids.filtered(lambda l: l.partner_id)
        self.assertTrue(lines)
        total = sum(l.balance for l in lines)
        self.assertGreater(total, 0.0)

    def test_aged_receivable_includes_open_items_before_date_from(self):
        partner = self.env['res.partner'].create({'name': 'Old Open Item'})
        self._post_move(
            self.receivable, self.income, 90.0, partner,
            posting_date='2025-12-15')
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'aged_receivable',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        line = wizard.line_ids.filtered(lambda row: row.partner_id == partner)
        self.assertAlmostEqual(line.balance, 90.0, places=2)
        action = line.action_open_entries()
        self.assertNotIn(('date', '>=', wizard.date_from), action['domain'])
        self.assertIn(('date', '<=', wizard.date_to), action['domain'])

    def test_aged_receivable_reconstructs_reconciliation_after_report_date(self):
        partner = self.env['res.partner'].create({'name': 'Historical Aging'})
        invoice_move = self._post_move(
            self.receivable, self.income, 100.0, partner,
            posting_date='2026-01-15')
        settlement_move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-03-15',
            'line_ids': [
                (0, 0, {
                    'account_id': self.expense.id,
                    'debit': 100.0,
                    'name': 'Settlement counterpart',
                }),
                (0, 0, {
                    'account_id': self.receivable.id,
                    'credit': 100.0,
                    'partner_id': partner.id,
                    'name': 'Settlement',
                }),
            ],
        })
        settlement_move.action_post()
        invoice_line = invoice_move.line_ids.filtered(
            lambda line: line.account_id == self.receivable)
        settlement_line = settlement_move.line_ids.filtered(
            lambda line: line.account_id == self.receivable)
        (invoice_line + settlement_line).reconcile()
        self.assertTrue(invoice_line.reconciled)

        before_payment = self.env['flousflow.account.report'].create({
            'report_type': 'aged_receivable',
            'date_from': '2026-01-01',
            'date_to': '2026-02-28',
        })
        before_payment.action_generate()
        historical_line = before_payment.line_ids.filtered(
            lambda line: line.partner_id == partner)
        self.assertAlmostEqual(historical_line.balance, 100.0, places=2)

        after_payment = self.env['flousflow.account.report'].create({
            'report_type': 'aged_receivable',
            'date_from': '2026-01-01',
            'date_to': '2026-03-31',
        })
        after_payment.action_generate()
        self.assertFalse(after_payment.line_ids.filtered(
            lambda line: line.partner_id == partner))

    def test_partner_ledger(self):
        partner = self.env['res.partner'].create({'name': 'Ledger Partner'})
        self._post_move(
            self.receivable, self.income, 50.0, partner,
            posting_date='2025-12-20')
        self._post_move(self.receivable, self.income, 300.0, partner)
        self._post_move(self.expense, self.payable, 100.0, partner)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'partner_ledger',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        partner_lines = wizard.line_ids.filtered(
            lambda line: line.partner_id == partner)
        opening = partner_lines.filtered('is_section')
        details = partner_lines.filtered('move_id')
        total = partner_lines.filtered('is_total')
        self.assertEqual(len(opening), 1)
        self.assertEqual(len(details), 2)
        self.assertEqual(len(total), 1)
        self.assertAlmostEqual(opening.running_balance, 50.0, places=2)
        self.assertAlmostEqual(total.debit, 300.0, places=2)
        self.assertAlmostEqual(total.credit, 100.0, places=2)
        self.assertAlmostEqual(total.balance, 250.0, places=2)
        self.assertAlmostEqual(total.running_balance, 250.0, places=2)
        self.assertEqual(details.sorted('sequence')[-1].running_balance, 250.0)

    def test_customer_statement_has_opening_details_and_running_balance(self):
        partner = self.env['res.partner'].create({'name': 'Statement Customer'})
        self._post_move(
            self.receivable, self.income, 40.0, partner,
            posting_date='2025-12-20')
        current_move = self._post_move(
            self.receivable, self.income, 125.0, partner)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'customer_statement',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'partner_ids': partner.ids,
        })

        wizard.action_generate()

        self.assertEqual(len(wizard.line_ids), 3)
        opening = wizard.line_ids.filtered('is_section')
        detail = wizard.line_ids.filtered('move_id')
        total = wizard.line_ids.filtered('is_total')
        self.assertTrue(opening.is_section)
        self.assertAlmostEqual(opening.running_balance, 40.0, places=2)
        self.assertEqual(detail.move_id, current_move)
        self.assertEqual(detail.partner_id, partner)
        self.assertAlmostEqual(detail.debit, 125.0, places=2)
        self.assertAlmostEqual(detail.running_balance, 165.0, places=2)
        self.assertAlmostEqual(total.running_balance, 165.0, places=2)

    def test_vendor_statement_and_required_partner(self):
        partner = self.env['res.partner'].create({'name': 'Statement Vendor'})
        current_move = self._post_move(
            self.expense, self.payable, 75.0, partner)
        missing_partner = self.env['flousflow.account.report'].create({
            'report_type': 'vendor_statement',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        with self.assertRaises(UserError):
            missing_partner.action_generate()
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'vendor_statement',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
            'partner_ids': partner.ids,
        })

        wizard.action_generate()

        detail = wizard.line_ids.filtered('move_id')
        self.assertEqual(detail.move_id, current_move)
        self.assertAlmostEqual(detail.credit, 75.0, places=2)
        self.assertAlmostEqual(detail.running_balance, -75.0, places=2)

    def test_account_statement_has_opening_details_and_requires_account(self):
        partner = self.env['res.partner'].create({'name': 'Account Statement Partner'})
        self._post_move(
            self.receivable, self.income, 30.0, partner,
            posting_date='2025-12-20')
        current_move = self._post_move(
            self.receivable, self.income, 90.0, partner)
        missing_account = self.env['flousflow.account.report'].create({
            'report_type': 'account_statement',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })
        with self.assertRaises(UserError):
            missing_account.action_generate()
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'account_statement',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
            'account_ids': self.receivable.ids,
            'partner_ids': partner.ids,
        })

        wizard.action_generate()

        opening = wizard.line_ids.filtered('is_section')
        detail = wizard.line_ids.filtered('move_id')
        self.assertAlmostEqual(opening.running_balance, 30.0, places=2)
        self.assertEqual(detail.move_id, current_move)
        self.assertEqual(detail.partner_id, partner)
        self.assertAlmostEqual(detail.running_balance, 120.0, places=2)
        self.assertAlmostEqual(
            wizard.line_ids.filtered('is_total').running_balance, 120.0, places=2)

    def test_executive_summary(self):
        self._post_move(self.receivable, self.income, 100.0)
        self._post_move(self.expense, self.payable, 40.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'executive_summary',
            'date_from': '2026-01-01', 'date_to': '2026-12-31',
        })

        wizard.action_generate()

        amounts = {line.code: line.balance for line in wizard.line_ids}
        self.assertEqual(
            set(amounts),
            {'cash', 'receivables', 'payables', 'revenue', 'expenses', 'net_profit'})
        self.assertAlmostEqual(amounts['receivables'], 100.0, places=2)
        self.assertAlmostEqual(amounts['payables'], 40.0, places=2)
        self.assertAlmostEqual(amounts['revenue'], 100.0, places=2)
        self.assertAlmostEqual(amounts['expenses'], 40.0, places=2)
        self.assertAlmostEqual(amounts['net_profit'], 60.0, places=2)

    def test_statement_actions_are_full_page(self):
        for xml_id in (
                'flousflow_account_report_customer_statement_action',
                'flousflow_account_report_vendor_statement_action',
                'flousflow_account_report_account_statement_action',
                'flousflow_account_report_executive_action'):
            self.assertEqual(self.env.ref(
                'flousflow_accounting.%s' % xml_id).target, 'current')

    def test_report_actions_use_the_correct_form_view(self):
        generic_view = self.env.ref(
            'flousflow_accounting.flousflow_account_report_view_form')
        statement_view = self.env.ref(
            'flousflow_accounting.flousflow_partner_statement_view_form')
        generic_actions = (
            'flousflow_account_report_action',
            'flousflow_account_report_pnl_action',
            'flousflow_account_report_balance_action',
            'flousflow_account_report_gl_action',
            'flousflow_account_report_aged_rec_action',
            'flousflow_account_report_aged_pay_action',
            'flousflow_account_report_partner_ledger_action',
            'flousflow_account_report_cash_flow_action',
            'flousflow_account_report_trial_balance_action',
            'flousflow_account_report_journal_audit_action',
            'flousflow_account_report_tax_action',
            'flousflow_account_report_executive_action',
            'flousflow_account_report_account_statement_action',
        )
        for xml_id in generic_actions:
            self.assertEqual(
                self.env.ref('flousflow_accounting.%s' % xml_id).view_id,
                generic_view)
        for xml_id in (
                'flousflow_account_report_customer_statement_action',
                'flousflow_account_report_vendor_statement_action'):
            self.assertEqual(
                self.env.ref('flousflow_accounting.%s' % xml_id).view_id,
                statement_view)

    def test_refresh_keeps_the_correct_report_view(self):
        customer = self.env['res.partner'].create({
            'name': 'Refresh View Customer', 'customer_rank': 1})
        statement = self.env['flousflow.account.report'].create({
            'report_type': 'customer_statement',
            'partner_ids': [(6, 0, customer.ids)],
        })
        statement_action = statement.action_generate()
        self.assertEqual(
            statement_action['view_id'],
            self.env.ref(
                'flousflow_accounting.flousflow_partner_statement_view_form').id)
        trial_balance = self.env['flousflow.account.report'].create({
            'report_type': 'trial_balance',
        })
        generic_action = trial_balance.action_generate()
        self.assertEqual(
            generic_action['view_id'],
            self.env.ref(
                'flousflow_accounting.flousflow_account_report_view_form').id)

    def test_accounting_uses_single_standard_application_root(self):
        standard_root = self.env.ref('account.menu_finance')
        legacy_root = self.env.ref(
            'flousflow_accounting.menu_flousflow_accounting_root')
        self.assertEqual(standard_root.name, 'Accounting')
        self.assertEqual(
            standard_root.web_icon,
            'flousflow_accounting,static/description/accounting_icon_v2.png')
        module = self.env['ir.module.module'].search([
            ('name', '=', 'flousflow_accounting'),
        ], limit=1)
        self.assertEqual(
            module.icon,
            '/flousflow_accounting/static/description/accounting_icon_v2.png')
        self.assertFalse(legacy_root.active)
        self.assertEqual(
            self.env.ref(
                'flousflow_accounting.menu_flousflow_accounting_budgets'
            ).parent_id,
            self.env.ref('account.account_account_menu'))

    def test_accounting_settings_uses_the_accounting_application_icon(self):
        arch = etree.fromstring(self.env.ref(
            'account.res_config_settings_view_form').get_combined_arch())
        accounting_apps = arch.xpath("//app[@name='account']")
        self.assertEqual(len(accounting_apps), 1)
        self.assertEqual(
            accounting_apps[0].get('logo'),
            '/flousflow_accounting/static/description/accounting_icon_v2.png')

    def test_accounting_root_has_only_standard_primary_sections(self):
        standard_root = self.env.ref('account.menu_finance')
        visible_children = self.env['ir.ui.menu'].search([
            ('parent_id', '=', standard_root.id),
        ])
        expected = self.env['ir.ui.menu'].browse([
            self.env.ref(xml_id).id for xml_id in (
                'account.menu_board_journal_1',
                'account.menu_finance_receivables',
                'account.menu_finance_payables',
                'account.menu_finance_entries',
                'account.account_audit_menu',
                'account.menu_finance_reports',
                'account.menu_finance_configuration',
            )
        ])
        self.assertEqual(set(visible_children.ids), set(expected.ids))

    def test_standard_accounting_navigation_hierarchy_is_preserved(self):
        expected = {
            'account.menu_action_move_journal_line_form': (
                'account.account_transactions_menu', 'account.move'),
            'account.menu_action_account_moves_all': (
                'account.account_audit_control_menu', 'account.move.line'),
            'account.menu_action_account_form': (
                'account.account_account_menu', 'account.account'),
        }
        for xml_id, (parent_xml_id, model) in expected.items():
            menu = self.env.ref(xml_id)
            self.assertEqual(menu.parent_id, self.env.ref(parent_xml_id))
            self.assertEqual(menu.action.res_model, model)
        bank_statements = self.env.ref(
            'flousflow_accounting.menu_flousflow_accounting_bank_statements')
        self.assertEqual(
            bank_statements.parent_id,
            self.env.ref('account.account_transactions_menu'))
        self.assertEqual(
            bank_statements.action,
            self.env.ref('account.action_bank_statement_tree'))

    def test_saved_filter_management_action_and_menu(self):
        action = self.env.ref(
            'flousflow_accounting.flousflow_account_report_preset_action')
        menu = self.env.ref(
            'flousflow_accounting.menu_flousflow_accounting_saved_report_filters')
        report_menu = self.env.ref('account.menu_finance_reports')

        self.assertEqual(action.res_model, 'flousflow.account.report.preset')
        self.assertEqual(action.view_mode, 'list,form')
        self.assertEqual(menu.parent_id, report_menu)
        self.assertEqual(menu.action, action)
        self.assertTrue(action.view_ids.filtered(
            lambda item: item.view_mode == 'list').view_id)
        self.assertTrue(action.view_ids.filtered(
            lambda item: item.view_mode == 'form').view_id)

    def test_report_breadcrumb_uses_business_name(self):
        report = self.env['flousflow.account.report'].create({
            'report_type': 'customer_statement',
        })
        self.assertEqual(report.display_name, 'Customer Statement')
        self.assertNotIn('flousflow.account.report', report.display_name)

    def test_partner_statement_buttons_prepare_standard_report_filters(self):
        customer = self.env['res.partner'].create({
            'name': 'Statement Button Customer', 'customer_rank': 1})
        vendor = self.env['res.partner'].create({
            'name': 'Statement Button Vendor', 'supplier_rank': 1})

        customer_action = customer.action_open_customer_statement()
        vendor_action = vendor.action_open_vendor_statement()

        customer_report = self.env['flousflow.account.report'].browse(
            customer_action['res_id'])
        vendor_report = self.env['flousflow.account.report'].browse(
            vendor_action['res_id'])
        self.assertEqual(customer_report.report_type, 'customer_statement')
        self.assertEqual(customer_report.partner_ids, customer)
        self.assertEqual(vendor_report.report_type, 'vendor_statement')
        self.assertEqual(vendor_report.partner_ids, vendor)
        self.assertEqual(customer_action['target'], 'current')
        self.assertEqual(vendor_action['target'], 'current')
        statement_view = self.env.ref(
            'flousflow_accounting.flousflow_partner_statement_view_form')
        self.assertEqual(customer_action['view_id'], statement_view.id)
        self.assertEqual(vendor_action['view_id'], statement_view.id)
        self.assertTrue(customer_report.line_ids)
        self.assertTrue(vendor_report.line_ids)

    def test_trial_balance(self):
        self._post_move(
            self.receivable, self.income, 100.0,
            posting_date='2025-12-15')
        self._post_move(self.receivable, self.income, 250.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'trial_balance',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        self.assertTrue(wizard.line_ids)
        self.assertAlmostEqual(sum(wizard.line_ids.mapped('debit')), 250.0, places=2)
        self.assertAlmostEqual(sum(wizard.line_ids.mapped('credit')), 250.0, places=2)
        self.assertAlmostEqual(sum(wizard.line_ids.mapped('balance')), 0.0, places=2)
        receivable = wizard.line_ids.filtered(
            lambda line: line.account_id == self.receivable)
        self.assertAlmostEqual(receivable.opening_balance, 100.0, places=2)
        self.assertAlmostEqual(receivable.closing_balance, 350.0, places=2)

    def test_journal_audit(self):
        move = self._post_move(self.receivable, self.income, 175.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'journal_audit',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        line = wizard.line_ids.filtered(lambda row: row.journal_id == move.journal_id)
        self.assertTrue(line)
        self.assertAlmostEqual(line.debit, 175.0, places=2)
        self.assertAlmostEqual(line.credit, 175.0, places=2)

    def test_cash_flow(self):
        cash = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1)
        fixed_asset = self.env['account.account'].search(
            [('account_type', '=', 'asset_fixed')], limit=1)
        long_term_liability = self.env['account.account'].search(
            [('account_type', '=', 'liability_non_current')], limit=1)
        if not all((cash, fixed_asset, long_term_liability)):
            self.skipTest('Cash-flow classification accounts are required')
        self._post_move(
            cash, self.income, 200.0, posting_date='2025-12-20')
        self._post_move(cash, self.income, 50.0)
        self._post_move(fixed_asset, cash, 30.0)
        self._post_move(cash, long_term_liability, 40.0)
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'cash_flow',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        by_code = {line.code: line.balance for line in wizard.line_ids}
        self.assertEqual(set(by_code), {
            'opening_cash', 'operating', 'investing', 'financing',
            'net_cash_flow', 'closing_cash',
        })
        self.assertAlmostEqual(by_code['opening_cash'], 200.0, places=2)
        self.assertAlmostEqual(by_code['operating'], 50.0, places=2)
        self.assertAlmostEqual(by_code['investing'], -30.0, places=2)
        self.assertAlmostEqual(by_code['financing'], 40.0, places=2)
        self.assertAlmostEqual(by_code['net_cash_flow'], 60.0, places=2)
        self.assertAlmostEqual(by_code['closing_cash'], 260.0, places=2)

    def test_cash_flow_prefers_standard_account_tags_to_account_type(self):
        cash = self.env['account.account'].search(
            [('account_type', '=', 'asset_cash')], limit=1)
        ordinary_expense = self.env['account.account'].search(
            [('account_type', '=', 'expense')], limit=1)
        financing_tag = self.env.ref('account.account_tag_financing')
        if not cash or not ordinary_expense:
            self.skipTest('Cash-flow classification accounts are required')
        ordinary_expense.tag_ids = financing_tag
        self._post_move(ordinary_expense, cash, 75.0)

        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'cash_flow',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
            'account_ids': cash.ids,
        })
        wizard.action_generate()

        by_code = {line.code: line.balance for line in wizard.line_ids}
        self.assertAlmostEqual(by_code['operating'], 0.0, places=2)
        self.assertAlmostEqual(by_code['financing'], -75.0, places=2)

    def test_tax_report(self):
        tax = self.env['account.tax'].search([('type_tax_use', '=', 'sale')], limit=1)
        if not tax:
            self.skipTest('A sales tax is required')
        partner = self.env['res.partner'].create({'name': 'Tax Report Customer'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'date': '2026-01-15',
            'invoice_date': '2026-01-15',
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Taxable service',
                    'account_id': self.income.id,
                    'quantity': 1.0,
                    'price_unit': 100.0,
                    'tax_ids': [(6, 0, tax.ids)],
                }),
            ],
        })
        move.action_post()
        wizard = self.env['flousflow.account.report'].create({
            'report_type': 'tax_report',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        wizard.action_generate()
        line = wizard.line_ids.filtered(lambda row: row.tax_id == tax)
        self.assertTrue(line)
        self.assertAlmostEqual(line.tax_base_amount, 100.0, places=2)
        self.assertAlmostEqual(line.balance, abs(move.amount_tax), places=2)
