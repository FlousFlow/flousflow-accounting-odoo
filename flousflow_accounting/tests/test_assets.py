# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAssets(TransactionCase):

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        fixed = self.env['account.account'].search(
            [('account_type', '=', 'asset_fixed')], limit=1)
        expense = self.env['account.account'].search(
            [('account_type', 'in', ['expense', 'expense_depreciation'])], limit=1)
        journal = self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.company.id)], limit=1)
        if not fixed or not expense or not journal:
            self.skipTest('Required accounts/journal not available')

        self.category = self.env['flousflow.account.asset.category'].create({
            'name': 'Computers',
            'asset_account_id': fixed.id,
            'depreciation_account_id': fixed.id,
            'expense_account_id': expense.id,
            'journal_id': journal.id,
            'method': 'linear',
            'method_number': 5,
            'method_period': 12,
            'prorata': False,
        })

    def test_asset_board_linear(self):
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Laptop',
            'value': 1000.0,
            'salvage_value': 0.0,
            'category_id': self.category.id,
        })
        asset.action_confirm()
        self.assertEqual(asset.state, 'open')
        self.assertEqual(len(asset.depreciation_line_ids), 5)
        total = sum(l.amount for l in asset.depreciation_line_ids)
        self.assertAlmostEqual(total, 1000.0, places=2)

    def test_asset_board_with_salvage(self):
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Machine',
            'value': 1000.0,
            'salvage_value': 100.0,
            'category_id': self.category.id,
        })
        asset.action_confirm()
        total = sum(l.amount for l in asset.depreciation_line_ids)
        self.assertAlmostEqual(total, 900.0, places=2)

    def test_post_depreciation_creates_move(self):
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Truck',
            'value': 1200.0,
            'salvage_value': 0.0,
            'category_id': self.category.id,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        # All lines due if date in the past
        asset.post_depreciation_lines()
        self.assertTrue(all(l.move_id for l in asset.depreciation_line_ids))
        self.assertEqual(asset.state, 'close')

    def test_cannot_delete_running_asset(self):
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Forklift',
            'value': 5000.0,
            'category_id': self.category.id,
        })
        asset.action_confirm()
        with self.assertRaises(Exception):
            asset.unlink()

    def test_degressive_board(self):
        self.category.write({'method': 'degressive', 'method_progress_factor': 0.3})
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Car',
            'value': 1000.0,
            'category_id': self.category.id,
        })
        asset.action_confirm()
        total = sum(l.amount for l in asset.depreciation_line_ids)
        self.assertAlmostEqual(total, 1000.0, places=2)

    def test_degressive_then_linear_switches_to_straight_line(self):
        self.category.write({
            'method': 'degressive_then_linear',
            'method_progress_factor': 0.3,
            'method_number': 4,
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Hybrid Asset',
            'value': 1000.0,
            'category_id': self.category.id,
        })

        asset.action_confirm()

        amounts = asset.depreciation_line_ids.sorted('sequence').mapped('amount')
        self.assertEqual(len(amounts), 4)
        self.assertAlmostEqual(amounts[0], 300.0, places=2)
        self.assertAlmostEqual(sum(amounts), 1000.0, places=2)
        self.assertGreater(amounts[1], 1000.0 * 0.7 * 0.3)

    def test_hybrid_method_honors_daily_prorata(self):
        self.category.write({
            'method': 'degressive_then_linear',
            'method_progress_factor': 0.3,
            'method_number': 4,
            'prorata_computation_type': 'daily_computation',
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Hybrid Prorata Asset',
            'value': 1000.0,
            'date': '2026-07-01',
            'category_id': self.category.id,
        })

        asset.action_confirm()

        amounts = asset.depreciation_line_ids.sorted('sequence').mapped('amount')
        self.assertEqual(len(amounts), 5)
        self.assertLess(amounts[0], 300.0)
        self.assertAlmostEqual(sum(amounts), 1000.0, places=2)

    def test_daily_prorata_adds_balancing_period(self):
        self.category.write({
            'method_number': 5,
            'method_period': 12,
            'prorata_computation_type': 'daily_computation',
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Prorated Asset',
            'value': 1000.0,
            'date': '2026-07-01',
            'category_id': self.category.id,
        })

        asset.action_confirm()

        lines = asset.depreciation_line_ids.sorted('sequence')
        self.assertEqual(len(lines), 6)
        self.assertLess(lines[0].amount, 200.0)
        self.assertAlmostEqual(sum(lines.mapped('amount')), 1000.0, places=2)

    def test_asset_model_applies_group_and_computation_defaults(self):
        group = self.env['flousflow.account.asset.group'].create({
            'name': 'Vehicles',
        })
        self.category.write({
            'group_id': group.id,
            'method': 'degressive_then_linear',
            'method_number': 4,
            'prorata_computation_type': 'constant_periods',
        })

        asset = self.env['flousflow.account.asset'].create({
            'name': 'Model Defaults',
            'value': 1000.0,
            'category_id': self.category.id,
        })

        self.assertEqual(asset.group_id, group)
        self.assertEqual(asset.method, 'degressive_then_linear')
        self.assertEqual(asset.method_number, 4)
        self.assertEqual(asset.prorata_computation_type, 'constant_periods')

    def test_depreciation_schedule_action_has_analysis_views(self):
        action = self.env.ref(
            'flousflow_accounting.flousflow_asset_dep_line_action')
        self.assertEqual(
            action.res_model, 'flousflow.account.asset.depreciation.line')
        self.assertIn('pivot', action.view_mode)
        self.assertIn('graph', action.view_mode)

    def test_depreciation_expense_keeps_analytic_distribution(self):
        plan = self.env['account.analytic.plan'].create({
            'name': 'Asset Cost Centers',
        })
        analytic = self.env['account.analytic.account'].create({
            'name': 'Factory',
            'plan_id': plan.id,
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Analytic Machine',
            'value': 1000.0,
            'date': '2019-01-01',
            'category_id': self.category.id,
            'analytic_distribution': {str(analytic.id): 100.0},
        })
        asset.action_confirm()
        line = asset.depreciation_line_ids.sorted('date')[0]

        move = asset._create_depreciation_move(line)

        expense_line = move.line_ids.filtered(
            lambda item: item.account_id == self.category.expense_account_id)
        self.assertEqual(
            expense_line.analytic_distribution, {str(analytic.id): 100.0})

    def test_deferred_expense_posts_expense_against_prepayment(self):
        prepayment = self.env['account.account'].search(
            [('account_type', '=', 'asset_prepayments')], limit=1)
        if not prepayment:
            self.skipTest('Prepayment account not available')
        self.category.write({
            'recognition_type': 'expense',
            'asset_account_id': prepayment.id,
            'method_number': 1,
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Annual Insurance',
            'value': 1200.0,
            'category_id': self.category.id,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        asset.post_depreciation_lines()
        move = asset.depreciation_line_ids.move_id
        self.assertEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == self.category.expense_account_id
            ).mapped('debit')),
            1200.0,
        )
        self.assertEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == prepayment
            ).mapped('credit')),
            1200.0,
        )

    def test_deferred_revenue_posts_liability_against_income(self):
        liability = self.env['account.account'].search(
            [('account_type', '=', 'liability_current')], limit=1)
        income = self.env['account.account'].search(
            [('account_type', 'in', ['income', 'income_other'])], limit=1)
        if not liability or not income:
            self.skipTest('Deferred revenue accounts not available')
        self.category.write({
            'recognition_type': 'revenue',
            'deferred_revenue_account_id': liability.id,
            'revenue_account_id': income.id,
            'method_number': 1,
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Annual Support Contract',
            'value': 2400.0,
            'category_id': self.category.id,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        asset.post_depreciation_lines()
        move = asset.depreciation_line_ids.move_id
        self.assertEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == liability
            ).mapped('debit')),
            2400.0,
        )
        self.assertEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == income
            ).mapped('credit')),
            2400.0,
        )

    def test_deferred_revenue_category_requires_only_relevant_accounts(self):
        liability = self.env['account.account'].search(
            [('account_type', '=', 'liability_current')], limit=1)
        income = self.env['account.account'].search(
            [('account_type', 'in', ['income', 'income_other'])], limit=1)
        if not liability or not income:
            self.skipTest('Deferred revenue accounts not available')
        category = self.env['flousflow.account.asset.category'].create({
            'name': 'Revenue Only Configuration',
            'recognition_type': 'revenue',
            'deferred_revenue_account_id': liability.id,
            'revenue_account_id': income.id,
            'journal_id': self.category.journal_id.id,
        })
        self.assertEqual(category.recognition_type, 'revenue')

    def test_cancel_reverses_posted_recognition_and_preserves_audit_trail(self):
        self.category.method_number = 1
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Cancelled Laptop',
            'value': 1200.0,
            'category_id': self.category.id,
            'method_number': 1,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        asset.post_depreciation_lines()
        original_move = asset.depreciation_line_ids.move_id

        asset.action_cancel()

        reversal_move = asset.depreciation_line_ids.reversal_move_id
        self.assertEqual(asset.state, 'cancelled')
        self.assertEqual(original_move.state, 'posted')
        self.assertEqual(reversal_move.state, 'posted')
        self.assertEqual(reversal_move.reversed_entry_id, original_move)
        for account in (original_move + reversal_move).line_ids.account_id:
            self.assertAlmostEqual(
                sum((original_move + reversal_move).line_ids.filtered(
                    lambda line: line.account_id == account
                ).mapped('balance')),
                0.0,
                places=2,
            )
        self.assertAlmostEqual(asset.value_residual, asset.value, places=2)

    def test_foreign_currency_recognition_uses_company_amount_and_amount_currency(self):
        foreign_currency = self.env['res.currency'].with_context(active_test=False).search([
            ('id', '!=', self.company.currency_id.id),
        ], limit=1)
        if not foreign_currency:
            self.skipTest('No foreign currency available')
        foreign_currency.active = True
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Foreign Currency Asset',
            'value': 100.0,
            'currency_id': foreign_currency.id,
            'category_id': self.category.id,
            'method_number': 1,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        asset.post_depreciation_lines()
        move = asset.depreciation_line_ids.move_id
        expected_company_amount = foreign_currency._convert(
            100.0, self.company.currency_id, self.company, move.date)

        self.assertTrue(all(line.currency_id == foreign_currency for line in move.line_ids))
        self.assertEqual(set(move.line_ids.mapped('amount_currency')), {100.0, -100.0})
        self.assertAlmostEqual(sum(move.line_ids.mapped('debit')), expected_company_amount, places=2)
        self.assertAlmostEqual(sum(move.line_ids.mapped('credit')), expected_company_amount, places=2)

    def test_asset_can_be_created_from_posted_vendor_bill_line(self):
        payable = self.env['account.account'].search(
            [('account_type', '=', 'liability_payable')], limit=1)
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', self.company.id),
        ], limit=1)
        if not payable or not purchase_journal:
            self.skipTest('Vendor bill prerequisites are unavailable')
        vendor = self.env['res.partner'].create({'name': 'Asset Vendor'})
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': vendor.id,
            'journal_id': purchase_journal.id,
            'invoice_date': '2026-01-15',
            'invoice_line_ids': [(0, 0, {
                'name': 'Production Machine',
                'account_id': self.category.asset_account_id.id,
                'quantity': 1,
                'price_unit': 5000.0,
            })],
        })
        bill.action_post()
        source_line = bill.invoice_line_ids

        asset = self.env['flousflow.account.asset'].create({
            'category_id': self.category.id,
            'source_move_line_id': source_line.id,
        })

        self.assertEqual(asset.name, 'Production Machine')
        self.assertEqual(asset.source_move_id, bill)
        self.assertEqual(asset.partner_id, vendor)
        self.assertEqual(asset.date.isoformat(), '2026-01-15')
        self.assertEqual(asset.value, 5000.0)

    def test_asset_source_rejects_draft_vendor_bill_and_duplicate_line(self):
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', self.company.id),
        ], limit=1)
        if not purchase_journal:
            self.skipTest('Purchase journal is unavailable')
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.env['res.partner'].create({'name': 'Draft Vendor'}).id,
            'journal_id': purchase_journal.id,
            'invoice_date': '2026-01-15',
            'invoice_line_ids': [(0, 0, {
                'name': 'Server',
                'account_id': self.category.asset_account_id.id,
                'quantity': 1,
                'price_unit': 1000.0,
            })],
        })
        line = bill.invoice_line_ids
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.asset'].create({
                'category_id': self.category.id,
                'source_move_line_id': line.id,
            })
        bill.action_post()
        self.env['flousflow.account.asset'].create({
            'category_id': self.category.id,
            'source_move_line_id': line.id,
        })
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.asset'].create({
                'category_id': self.category.id,
                'source_move_line_id': line.id,
            })

    def test_vendor_bill_asset_wizard_creates_selected_assets(self):
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', self.company.id),
        ], limit=1)
        if not purchase_journal:
            self.skipTest('Purchase journal is unavailable')
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.env['res.partner'].create({'name': 'Wizard Vendor'}).id,
            'journal_id': purchase_journal.id,
            'invoice_date': '2026-02-01',
            'invoice_line_ids': [(0, 0, {
                'name': name,
                'account_id': self.category.asset_account_id.id,
                'quantity': 1,
                'price_unit': amount,
            }) for name, amount in [('Laptop', 2000.0), ('Printer', 800.0)]],
        })
        bill.action_post()
        wizard = self.env['flousflow.account.asset.create.wizard'].with_context(
            active_model='account.move', active_id=bill.id,
        ).create({'category_id': self.category.id})
        wizard.line_ids = bill.invoice_line_ids

        action = wizard.action_create_assets()

        assets = self.env['flousflow.account.asset'].browse(action['res_ids'])
        self.assertEqual(len(assets), 2)
        self.assertEqual(set(assets.mapped('value')), {2000.0, 800.0})
        self.assertEqual(assets.mapped('source_move_id'), bill)

    def test_scrap_asset_removes_cost_and_books_residual_loss(self):
        loss_account = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'expense_depreciation']),
        ], limit=1)
        self.category.write({'disposal_loss_account_id': loss_account.id})
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Scrapped Machine',
            'value': 1000.0,
            'category_id': self.category.id,
            'method_number': 2,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        first_line = asset.depreciation_line_ids.sorted('date')[0]
        first_line.move_id = asset._create_depreciation_move(first_line)

        wizard = self.env['flousflow.account.asset.disposal.wizard'].create({
            'asset_id': asset.id,
            'date': '2026-02-28',
        })
        wizard.action_dispose()

        move = asset.disposal_move_id
        self.assertEqual(asset.state, 'close')
        self.assertEqual(move.state, 'posted')
        self.assertAlmostEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == self.category.asset_account_id
            ).mapped('credit')), 1000.0, places=2)
        self.assertAlmostEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == self.category.depreciation_account_id
            ).mapped('debit')), 500.0, places=2)
        self.assertAlmostEqual(
            sum(move.line_ids.filtered(
                lambda line: line.account_id == loss_account
            ).mapped('debit')), 500.0, places=2)

    def test_disposal_reversal_preserves_original_entry(self):
        loss_account = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'expense_depreciation']),
        ], limit=1)
        self.category.write({'disposal_loss_account_id': loss_account.id})
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Reversible Scrap', 'value': 1000.0,
            'category_id': self.category.id, 'date': '2019-01-01',
        })
        asset.action_confirm()
        self.env['flousflow.account.asset.disposal.wizard'].create({
            'asset_id': asset.id, 'date': '2026-03-01',
        }).action_dispose()
        original = asset.disposal_move_id

        asset.action_reverse_disposal()

        self.assertEqual(original.state, 'posted')
        self.assertEqual(asset.disposal_reversal_move_id.state, 'posted')
        self.assertEqual(asset.disposal_reversal_move_id.reversed_entry_id, original)
        self.assertEqual(asset.state, 'open')

    def test_asset_sale_uses_customer_invoice_and_books_gain(self):
        clearing = self.env['account.account'].search([
            ('account_type', '=', 'asset_current'),
        ], limit=1)
        gain = self.env['account.account'].search([
            ('account_type', 'in', ['income', 'income_other']),
        ], limit=1)
        sale_journal = self.env['account.journal'].search([
            ('type', '=', 'sale'), ('company_id', '=', self.company.id),
        ], limit=1)
        if not clearing or not gain or not sale_journal:
            self.skipTest('Asset sale prerequisites are unavailable')
        self.category.write({
            'disposal_clearing_account_id': clearing.id,
            'disposal_gain_account_id': gain.id,
        })
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Sold Vehicle', 'value': 1000.0,
            'category_id': self.category.id, 'date': '2019-01-01',
        })
        asset.action_confirm()
        customer = self.env['res.partner'].create({'name': 'Asset Buyer'})
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice', 'partner_id': customer.id,
            'journal_id': sale_journal.id, 'invoice_date': '2026-03-01',
            'invoice_line_ids': [(0, 0, {
                'name': 'Vehicle sale', 'account_id': clearing.id,
                'quantity': 1, 'price_unit': 1200.0,
            })],
        })
        invoice.action_post()

        self.env['flousflow.account.asset.disposal.wizard'].create({
            'asset_id': asset.id, 'date': '2026-03-01',
            'disposal_type': 'sale',
            'sale_move_line_id': invoice.invoice_line_ids.id,
        }).action_dispose()

        move = asset.disposal_move_id
        self.assertEqual(asset.disposal_source_move_id, invoice)
        self.assertAlmostEqual(sum(move.line_ids.filtered(
            lambda line: line.account_id == clearing).mapped('debit')), 1200.0)
        self.assertAlmostEqual(sum(move.line_ids.filtered(
            lambda line: line.account_id == gain).mapped('credit')), 200.0)
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.asset.disposal.wizard'].create({
                'asset_id': self.env['flousflow.account.asset'].create({
                    'name': 'Other Asset', 'value': 500.0,
                    'category_id': self.category.id,
                }).id,
                'date': '2026-03-01', 'disposal_type': 'sale',
                'sale_move_line_id': invoice.invoice_line_ids.id,
            }).action_dispose()

    def test_foreign_currency_scrap_uses_historical_company_value(self):
        foreign = self.env['res.currency'].with_context(active_test=False).search([
            ('id', '!=', self.company.currency_id.id),
        ], limit=1)
        if not foreign:
            self.skipTest('No foreign currency is available')
        foreign.active = True
        loss = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'expense_depreciation']),
        ], limit=1)
        self.category.disposal_loss_account_id = loss
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Foreign Scrap', 'value': 100.0,
            'currency_id': foreign.id, 'category_id': self.category.id,
            'date': '2020-01-01',
        })
        expected = foreign._convert(
            100.0, self.company.currency_id, self.company, asset.date)
        asset.action_confirm()

        self.env['flousflow.account.asset.disposal.wizard'].create({
            'asset_id': asset.id, 'date': '2026-03-01',
        }).action_dispose()

        self.assertAlmostEqual(asset.company_value, expected, places=2)
        self.assertAlmostEqual(sum(asset.disposal_move_id.line_ids.filtered(
            lambda line: line.account_id == self.category.asset_account_id
        ).mapped('credit')), expected, places=2)

    def test_posted_vendor_bill_can_auto_create_and_confirm_asset(self):
        purchase_journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'), ('company_id', '=', self.company.id),
        ], limit=1)
        if not purchase_journal:
            self.skipTest('Purchase journal is unavailable')
        self.category.auto_create_asset = 'validate'
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.env['res.partner'].create({'name': 'Auto Asset Vendor'}).id,
            'journal_id': purchase_journal.id,
            'invoice_date': '2026-04-01',
            'invoice_line_ids': [(0, 0, {
                'name': 'Automatic Machine',
                'account_id': self.category.asset_account_id.id,
                'quantity': 1, 'price_unit': 3000.0,
            })],
        })

        bill.action_post()

        asset = self.env['flousflow.account.asset'].search([
            ('source_move_line_id', '=', bill.invoice_line_ids.id),
        ])
        self.assertEqual(len(asset), 1)
        self.assertEqual(asset.state, 'open')
        self.assertTrue(asset.depreciation_line_ids)

    def test_auto_asset_account_must_be_unambiguous_per_company(self):
        self.category.auto_create_asset = 'draft'
        with self.assertRaises(ValidationError):
            self.env['flousflow.account.asset.category'].create({
                'name': 'Duplicate Automatic Category',
                'asset_account_id': self.category.asset_account_id.id,
                'depreciation_account_id': self.category.depreciation_account_id.id,
                'expense_account_id': self.category.expense_account_id.id,
                'journal_id': self.category.journal_id.id,
                'auto_create_asset': 'validate',
            })

    def test_asset_schedule_modification_preserves_posted_lines(self):
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Modified Machine', 'value': 1200.0,
            'category_id': self.category.id, 'method_number': 4,
            'date': '2019-01-01',
        })
        asset.action_confirm()
        posted_line = asset.depreciation_line_ids.sorted('date')[0]
        posted_line.move_id = asset._create_depreciation_move(posted_line)
        original_move = posted_line.move_id

        self.env['flousflow.account.asset.modify.wizard'].create({
            'asset_id': asset.id,
            'date': '2026-04-01',
            'remaining_periods': 2,
            'new_salvage_value': 200.0,
            'reason': 'Revised useful life',
        }).action_modify()

        self.assertEqual(original_move.state, 'posted')
        self.assertIn(posted_line, asset.depreciation_line_ids)
        future = asset.depreciation_line_ids - posted_line
        self.assertEqual(len(future), 2)
        self.assertAlmostEqual(sum(future.mapped('amount')), 700.0, places=2)
        self.assertEqual(asset.salvage_value, 200.0)
        history = self.env['flousflow.account.asset.modification'].search([
            ('asset_id', '=', asset.id),
        ])
        self.assertEqual(len(history), 1)
        self.assertEqual(history.old_remaining_periods, 3)
        self.assertEqual(history.new_remaining_periods, 2)

    def test_partial_disposal_reduces_asset_and_can_be_reversed(self):
        loss = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'expense_depreciation']),
        ], limit=1)
        self.category.disposal_loss_account_id = loss
        asset = self.env['flousflow.account.asset'].create({
            'name': 'Partially Scrapped Asset', 'value': 1000.0,
            'category_id': self.category.id, 'date': '2026-01-01',
            'method_number': 4,
        })
        asset.action_confirm()

        self.env['flousflow.account.asset.disposal.wizard'].create({
            'asset_id': asset.id, 'date': '2026-04-01',
            'disposal_percentage': 25.0,
        }).action_dispose()

        disposal = asset.disposal_ids
        self.assertEqual(len(disposal), 1)
        self.assertEqual(asset.state, 'open')
        self.assertAlmostEqual(asset.value, 750.0, places=2)
        self.assertAlmostEqual(disposal.company_gross_value, 250.0, places=2)
        self.assertAlmostEqual(sum(disposal.move_id.line_ids.filtered(
            lambda line: line.account_id == loss).mapped('debit')), 250.0)

        asset.action_reverse_disposal()

        self.assertEqual(disposal.reversal_move_id.state, 'posted')
        self.assertAlmostEqual(asset.value, 1000.0, places=2)
        self.assertEqual(asset.state, 'open')
