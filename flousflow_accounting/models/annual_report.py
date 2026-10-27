# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting

from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FlousflowAnnualReportTemplate(models.Model):
    _name = 'flousflow.account.annual.report.template'
    _description = 'FlousFlow Annual Report Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name, id'
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    description = fields.Text()
    company_id = fields.Many2one('res.company', tracking=True)
    active = fields.Boolean(default=True)
    content = fields.Html(
        sanitize=True,
        help='Reusable report structure and narrative. Accounting statements are generated separately.')


class FlousflowAnnualReport(models.Model):
    _name = 'flousflow.account.annual.report'
    _description = 'FlousFlow Annual Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _check_company_auto = True

    title = fields.Char(required=True, tracking=True)
    status = fields.Selection(
        [('draft', 'Draft'), ('in_progress', 'In Progress'), ('done', 'Completed')],
        required=True, default='draft', tracking=True, index=True)
    start_date = fields.Date(required=True, tracking=True)
    end_date = fields.Date(required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        tracking=True, index=True)
    responsible_user_ids = fields.Many2many(
        'res.users', 'ff_annual_report_responsible_rel', 'report_id', 'user_id',
        string='Responsibles', default=lambda self: [Command.set(self.env.user.ids)])
    template_id = fields.Many2one(
        'flousflow.account.annual.report.template', string='Annual Report Template',
        check_company=True, tracking=True)
    content = fields.Html(sanitize=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    @api.constrains('start_date', 'end_date')
    def _check_report_dates(self):
        for report in self:
            if report.start_date and report.end_date and report.start_date > report.end_date:
                raise ValidationError(_('The report start date must be before its end date.'))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for values in vals_list:
            vals = dict(values)
            template_id = vals.get('template_id')
            if template_id and not vals.get('content'):
                vals['content'] = self.env[
                    'flousflow.account.annual.report.template'].browse(
                        template_id).content
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if 'status' in vals:
            raise UserError(_('Change the report status through its workflow buttons.'))
        protected = {
            'title', 'start_date', 'end_date', 'company_id',
            'responsible_user_ids', 'template_id', 'content',
        }
        if protected.intersection(vals) and any(report.status == 'done' for report in self):
            raise UserError(_('A completed annual report cannot be edited.'))
        return super().write(vals)

    def _check_responsible(self):
        if not self.env.user.has_group('account.group_account_manager') and any(
                self.env.user not in report.responsible_user_ids for report in self):
            raise UserError(_('Only assigned report users or Accounting Managers can update this report.'))

    def action_start(self):
        self._check_responsible()
        if any(report.status != 'draft' for report in self):
            raise UserError(_('Only draft annual reports can be started.'))
        return super(FlousflowAnnualReport, self).write({'status': 'in_progress'})

    def action_complete(self):
        self._check_responsible()
        if any(report.status != 'in_progress' for report in self):
            raise UserError(_('Only in-progress annual reports can be completed.'))
        return super(FlousflowAnnualReport, self).write({'status': 'done'})

    def action_reset_to_draft(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can reopen a completed annual report.'))
        if any(report.status != 'done' for report in self):
            raise UserError(_('Only completed annual reports can be reopened.'))
        return super(FlousflowAnnualReport, self).write({'status': 'draft'})

    def action_generate_financial_statements(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Annual Financial Statements'),
            'res_model': 'flousflow.account.report',
            'view_mode': 'form',
            'view_id': self.env.ref(
                'flousflow_accounting.flousflow_account_report_view_form').id,
            'target': 'current',
            'context': {
                'default_report_type': 'annual_report',
                'default_company_id': self.company_id.id,
                'default_date_from': self.start_date,
                'default_date_to': self.end_date,
                'default_date_filter': 'custom',
                'default_comparison_mode': 'previous_year',
                'default_report_note': self.title,
            },
        }

    def action_print_report(self):
        self.ensure_one()
        return self.env.ref(
            'flousflow_accounting.action_report_annual_report_record').report_action(self)

    def unlink(self):
        if any(report.status != 'draft' for report in self):
            raise UserError(_('Only draft annual reports can be deleted.'))
        return super().unlink()
