# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FlousflowAccountWorkingFile(models.Model):
    _name = 'flousflow.account.working.file'
    _description = 'Accounting Audit Working File'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(default=lambda self: _('New'), readonly=True, copy=False)
    title = fields.Char(required=True, tracking=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    owner_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, check_company=True, tracking=True)
    reviewer_id = fields.Many2one('res.users', check_company=True, tracking=True)
    account_ids = fields.Many2many('account.account', string='Accounts', check_company=True)
    move_ids = fields.Many2many('account.move', string='Journal Entries', check_company=True)
    attachment_ids = fields.Many2many(
        'ir.attachment', 'flousflow_working_file_attachment_rel',
        'working_file_id', 'attachment_id', string='Evidence Attachments')
    objective = fields.Text(required=True)
    procedures = fields.Html(sanitize=True)
    findings = fields.Html(sanitize=True)
    conclusion = fields.Html(sanitize=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('in_review', 'In Review'),
         ('approved', 'Approved'), ('cancelled', 'Cancelled')],
        default='draft', required=True, tracking=True, copy=False)
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('flousflow.account.working.file') or _('New')
        return super().create(vals_list)

    @api.constrains('period_start', 'period_end')
    def _check_period(self):
        if self.filtered(lambda record: record.period_end < record.period_start):
            raise ValidationError(_('Period end must be on or after period start.'))

    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only draft working files can be submitted.'))
            if not record.reviewer_id:
                raise UserError(_('Select a reviewer before submitting.'))
            record.state = 'in_review'
        return True

    def action_approve(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only Accounting Managers can approve working files.'))
        for record in self:
            if record.state != 'in_review':
                raise UserError(_('Only working files in review can be approved.'))
            record.write({'state': 'approved', 'approved_by_id': self.env.user.id, 'approved_date': fields.Datetime.now()})
        return True

    def action_cancel(self):
        if self.filtered(lambda record: record.state == 'approved'):
            raise UserError(_('Approved working files cannot be cancelled.'))
        self.write({'state': 'cancelled'})
        return True

    def action_reset_draft(self):
        if self.filtered(lambda record: record.state == 'approved'):
            raise UserError(_('Approved working files cannot return to draft.'))
        self.write({'state': 'draft'})
        return True

    def write(self, vals):
        protected = {'title', 'date', 'period_start', 'period_end', 'company_id',
                     'owner_id', 'reviewer_id', 'account_ids', 'move_ids',
                     'attachment_ids', 'objective', 'procedures', 'findings', 'conclusion'}
        if protected.intersection(vals) and self.filtered(lambda record: record.state == 'approved'):
            raise UserError(_('Approved working files are read-only.'))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda record: record.state != 'draft'):
            raise UserError(_('Only draft working files can be deleted.'))
        return super().unlink()
