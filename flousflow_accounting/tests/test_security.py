# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class TestAccountingSecurity(TransactionCase):
    """Accounting-owned records must follow the active company boundary."""

    def test_company_models_have_global_company_rules(self):
        model_names = {
            'flousflow.account.asset.category',
            'flousflow.account.asset.group',
            'flousflow.account.asset',
            'flousflow.account.asset.depreciation.line',
            'flousflow.account.asset.modification',
            'flousflow.account.asset.disposal',
            'flousflow.account.budget',
            'flousflow.account.budget.line',
            'flousflow.account.followup',
            'flousflow.account.followup.line',
            'flousflow.account.followup.history',
            'flousflow.account.fiscal.year',
            'flousflow.account.recurring',
            'flousflow.account.recurring.line',
            'flousflow.account.report.template',
            'flousflow.account.report.template.line',
            'flousflow.account.report.preset',
            'flousflow.account.loan',
            'flousflow.account.loan.line',
            'flousflow.account.working.file',
            'flousflow.account.period.close',
            'flousflow.account.period.close.task',
            'flousflow.account.tax.return',
            'flousflow.account.tax.return.line',
            'flousflow.account.payment.promise',
        }
        models = self.env['ir.model'].search([('model', 'in', list(model_names))])
        covered = set(self.env['ir.rule'].search([
            ('model_id', 'in', models.ids),
            ('global', '=', True),
        ]).mapped('model_id.model'))
        self.assertEqual(covered, model_names)

    def test_followup_history_isolated_by_allowed_company_context(self):
        other_company = self.env['res.company'].create({'name': 'Other Accounting Co'})
        self.env.user.company_ids |= other_company
        partner = self.env['res.partner'].create({'name': 'Scoped Partner'})
        level = self.env['flousflow.account.followup'].create({
            'followup_line_ids': [(0, 0, {'name': 'Scoped Level', 'delay': 0})],
        }).followup_line_ids
        receivable = self.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
        ], limit=1)
        if not receivable:
            self.skipTest('No receivable account is available')
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': '2026-01-01',
            'line_ids': [(0, 0, {
                'account_id': receivable.id, 'debit': 10.0,
                'partner_id': partner.id, 'name': 'Scoped line',
            }), (0, 0, {
                'account_id': receivable.id, 'credit': 10.0,
                'partner_id': partner.id, 'name': 'Scoped counterpart',
            })],
        })
        history = self.env['flousflow.account.followup.history'].create({
            'date': '2026-01-01',
            'partner_id': partner.id,
            'move_line_id': move.line_ids[0].id,
            'level_id': level.id,
        })
        accountant = self.env['res.users'].create({
            'name': 'Scoped Accountant',
            'login': 'scoped.accountant@example.com',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, (self.env.company | other_company).ids)],
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
        })
        visible = self.env['flousflow.account.followup.history'].with_user(
            accountant).with_context(
            allowed_company_ids=other_company.ids,
        ).search([('id', '=', history.id)])
        self.assertFalse(visible)

    def test_saved_report_filters_are_private_to_the_owner(self):
        preset = self.env['flousflow.account.report.preset'].create({
            'name': 'Private filter',
            'report_type': 'general_ledger',
            'date_filter': 'custom',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        })
        accountant = self.env['res.users'].create({
            'name': 'Other Report User',
            'login': 'other.report.user@example.com',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
        })

        visible = self.env['flousflow.account.report.preset'].with_user(
            accountant).search([('id', '=', preset.id)])

        self.assertFalse(visible)

    def test_saved_report_filter_owner_cannot_be_spoofed(self):
        accountant = self.env['res.users'].create({
            'name': 'Preset Owner Check User',
            'login': 'preset.owner.check@example.com',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, self.env.company.ids)],
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('account.group_account_user').id,
            ])],
        })
        preset_model = self.env['flousflow.account.report.preset'].with_user(
            accountant)
        values = {
            'name': 'Impersonated filter',
            'user_id': self.env.user.id,
            'company_id': self.env.company.id,
            'report_type': 'general_ledger',
            'date_filter': 'custom',
            'date_from': '2026-01-01',
            'date_to': '2026-12-31',
        }

        with self.assertRaises(AccessError):
            preset_model.create(values)
