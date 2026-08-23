# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class FlousflowAccountTaxReturn(models.Model):
    _name = 'flousflow.account.tax.return'
    _description = 'Tax Return Review'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_to desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _('New'), copy=False, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    fiscal_country_id = fields.Many2one(related='company_id.account_fiscal_country_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('review', 'In Review'),
        ('approved', 'Approved'), ('closed', 'Closed'),
    ], default='draft', required=True, tracking=True)
    responsible_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, tracking=True)
    reviewer_id = fields.Many2one('res.users', required=True, tracking=True)
    line_ids = fields.One2many('flousflow.account.tax.return.line', 'return_id', copy=False)
    total_amount = fields.Monetary(compute='_compute_controls')
    draft_tax_move_count = fields.Integer(compute='_compute_controls')
    working_file_ids = fields.Many2many(
        'flousflow.account.working.file', relation='ff_tax_return_workfile_rel',
        column1='return_id', column2='working_file_id', check_company=True,
        domain="[('company_id', '=', company_id)]", string='Audit Evidence')
    notes = fields.Text()
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)
    closed_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    closed_date = fields.Datetime(readonly=True, copy=False)

    @api.depends('line_ids.amount', 'company_id', 'date_from', 'date_to')
    def _compute_controls(self):
        for record in self:
            record.total_amount = sum(record.line_ids.mapped('amount'))
            record.draft_tax_move_count = self.env['account.move'].search_count([
                ('company_id', '=', record.company_id.id),
                ('state', '=', 'draft'),
                ('date', '>=', record.date_from), ('date', '<=', record.date_to),
                '|', ('line_ids.tax_line_id', '!=', False), ('line_ids.tax_tag_ids', '!=', False),
            ]) if record.company_id and record.date_from and record.date_to else 0

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_('Tax return start date must be on or before its end date.'))

    @api.constrains('company_id', 'date_from', 'date_to')
    def _check_overlap(self):
        for record in self:
            if record.company_id and record.date_from and record.date_to and self.search_count([
                ('id', '!=', record.id), ('company_id', '=', record.company_id.id),
                ('state', '!=', 'draft'), ('date_from', '<=', record.date_to),
                ('date_to', '>=', record.date_from),
            ]):
                raise ValidationError(_('A submitted tax return already overlaps this period.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.name == _('New'):
                record.name = self.env['ir.sequence'].next_by_code('flousflow.account.tax.return') or _('New')
        return records

    def write(self, vals):
        protected = {'company_id', 'date_from', 'date_to', 'reviewer_id', 'line_ids'}
        if protected.intersection(vals) and any(record.state in ('approved', 'closed') for record in self):
            raise UserError(_('An approved or closed tax return cannot be changed.'))
        return super().write(vals)

    def unlink(self):
        if any(record.state != 'draft' for record in self):
            raise UserError(_('Only draft tax returns can be deleted.'))
        return super().unlink()

    def _check_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only an Accounting Manager can approve or close a tax return.'))
        if any(record.company_id not in self.env.user.company_ids for record in self):
            raise AccessError(_('The tax return company is outside your allowed companies.'))

    def action_prepare(self):
        for record in self:
            if record.state != 'draft':
                raise UserError(_('Only a draft tax return can be prepared.'))
            tags = self.env['account.account.tag'].search([
                ('applicability', '=', 'taxes'),
                ('country_id', 'in', [False, record.fiscal_country_id.id]),
            ])
            lines = self.env['account.move.line'].search([
                ('company_id', '=', record.company_id.id), ('parent_state', '=', 'posted'),
                ('date', '>=', record.date_from), ('date', '<=', record.date_to),
                ('tax_tag_ids', 'in', tags.ids),
            ])
            amounts = {tag.id: 0.0 for tag in tags}
            for line in lines:
                for tag in line.tax_tag_ids & tags:
                    amounts[tag.id] += -line.balance if tag.balance_negate else line.balance
            used_tags = tags.filtered(lambda tag: not record.currency_id.is_zero(amounts[tag.id]))
            if not used_tags:
                raise UserError(_('No posted localization tax-tag amounts were found for this period.'))
            record.line_ids = [(5, 0, 0)] + [(0, 0, {
                'tag_id': tag.id, 'amount': amounts[tag.id],
            }) for tag in used_tags.sorted(lambda tag: (tag.name, tag.id))]

    def action_submit(self):
        for record in self:
            if record.state != 'draft' or not record.line_ids:
                raise UserError(_('Prepare the draft tax return before submitting it.'))
            if record.draft_tax_move_count:
                raise UserError(_('Post or remove all draft tax entries in this period first.'))
            record.state = 'review'

    def action_approve(self):
        self._check_manager()
        for record in self:
            if record.state != 'review' or record.reviewer_id != self.env.user:
                raise UserError(_('Only the assigned reviewer can approve a return in review.'))
            record.write({'state': 'approved', 'approved_by_id': self.env.user.id, 'approved_date': fields.Datetime.now()})

    def action_close(self):
        self._check_manager()
        for record in self:
            if record.state != 'approved':
                raise UserError(_('Only an approved tax return can be closed.'))
            if record.draft_tax_move_count:
                raise UserError(_('Draft tax entries were added after approval.'))
            current_lock = record.company_id.tax_lock_date
            if not current_lock or current_lock < record.date_to:
                record.company_id.sudo().write({'tax_lock_date': record.date_to})
            record.write({'state': 'closed', 'closed_by_id': self.env.user.id, 'closed_date': fields.Datetime.now()})


class FlousflowAccountTaxReturnLine(models.Model):
    _name = 'flousflow.account.tax.return.line'
    _description = 'Tax Return Grid Line'
    _order = 'tag_id, id'
    _check_company_auto = True

    return_id = fields.Many2one('flousflow.account.tax.return', required=True, ondelete='cascade', check_company=True)
    company_id = fields.Many2one(related='return_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='return_id.currency_id')
    tag_id = fields.Many2one('account.account.tag', required=True, readonly=True)
    amount = fields.Monetary(required=True, readonly=True)
