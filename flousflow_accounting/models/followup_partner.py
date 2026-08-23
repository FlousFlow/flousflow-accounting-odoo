# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    followup_line_id = fields.Many2one(
        'flousflow.account.followup.line', string='Follow-up Level')
    followup_date = fields.Date(string='Latest Follow-up')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    total_overdue = fields.Monetary(
        compute='_compute_total_overdue', string='Total Overdue', readonly=True,
        groups='account.group_account_invoice,account.group_account_readonly')
    latest_followup_level_id = fields.Many2one(
        'flousflow.account.followup.line', string='Latest Follow-up Level',
        compute='_compute_followup')
    latest_followup_date = fields.Date(
        string='Latest Follow-up Date', compute='_compute_followup')
    payment_next_action = fields.Text(string='Next Action')
    payment_next_action_date = fields.Date(string='Next Action Date')
    payment_responsible_id = fields.Many2one(
        'res.users', string='Responsible', ondelete='set null')

    def _open_flousflow_statement(self, report_type, title):
        self.ensure_one()
        report = self.env['flousflow.account.report'].create({
            'company_id': self.env.company.id,
            'report_type': report_type,
            'partner_ids': [(6, 0, self.commercial_partner_id.ids)],
        })
        report.action_generate()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': 'flousflow.account.report',
            'res_id': report.id,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'flousflow_accounting.flousflow_partner_statement_view_form').id,
            'target': 'current',
        }

    def action_open_customer_statement(self):
        return self._open_flousflow_statement(
            'customer_statement', _('Customer Statement'))

    def action_open_vendor_statement(self):
        return self._open_flousflow_statement(
            'vendor_statement', _('Vendor Statement'))

    @api.depends_context('allowed_company_ids')
    def _compute_total_overdue(self):
        amounts = {}
        if self.ids:
            groups = self.env['account.move.line']._read_group([
                ('partner_id', 'in', self.ids),
                ('company_id', 'in', self.env.companies.ids),
                ('account_id.account_type', '=', 'asset_receivable'),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('date_maturity', '<', fields.Date.context_today(self)),
            ], ['partner_id'], ['amount_residual:sum'])
            amounts = {
                partner.id: amount_residual
                for partner, amount_residual in groups
            }
        for partner in self:
            partner.total_overdue = amounts.get(partner.id, 0.0)

    def _receivable_amls(self):
        return self.env['account.move.line'].search([
            ('partner_id', 'in', self.ids),
            ('company_id', 'in', self.env.companies.ids),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('full_reconcile_id', '=', False),
        ])

    @api.depends('credit')
    def _compute_followup(self):
        amls = self._receivable_amls()
        by_partner = {}
        for aml in amls:
            by_partner.setdefault(aml.partner_id.id, []).append(aml)
        for partner in self:
            latest_level = False
            latest_date = False
            for aml in by_partner.get(partner.id, []):
                if aml.followup_line_id and (
                        not latest_level or
                        latest_level.delay < aml.followup_line_id.delay):
                    latest_level = aml.followup_line_id
                if aml.followup_date and (
                        not latest_date or latest_date < aml.followup_date):
                    latest_date = aml.followup_date
            partner.latest_followup_level_id = (
                latest_level.id if latest_level else False)
            partner.latest_followup_date = latest_date
