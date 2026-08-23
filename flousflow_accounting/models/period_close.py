# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class FlousflowAccountPeriodClose(models.Model):
    _name = 'flousflow.account.period.close'
    _description = 'Accounting Period Close'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end desc, id desc'
    _check_company_auto = True

    name = fields.Char(required=True, copy=False, default=lambda self: _('New'), tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True, tracking=True)
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    close_type = fields.Selection(
        [('month', 'Month'), ('quarter', 'Quarter'), ('year', 'Fiscal Year')],
        required=True, default='month', tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('review', 'In Review'), ('approved', 'Approved'),
         ('closed', 'Closed')],
        required=True, default='draft', copy=False, tracking=True)
    responsible_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        domain="[('share', '=', False)]", tracking=True)
    reviewer_id = fields.Many2one(
        'res.users', required=True, domain="[('share', '=', False)]", tracking=True)
    task_ids = fields.One2many(
        'flousflow.account.period.close.task', 'close_id', string='Close Checklist', copy=True)
    working_file_ids = fields.Many2many(
        'flousflow.account.working.file', relation='ff_period_close_workfile_rel',
        column1='close_id', column2='working_file_id', string='Audit Working Files',
        domain="[('company_id', '=', company_id)]", check_company=True)
    draft_move_count = fields.Integer(compute='_compute_control_counts')
    incomplete_task_count = fields.Integer(compute='_compute_control_counts')
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    approved_date = fields.Datetime(readonly=True, copy=False)
    closed_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    closed_date = fields.Datetime(readonly=True, copy=False)
    apply_tax_lock = fields.Boolean(default=True)
    apply_sales_lock = fields.Boolean(default=True)
    apply_purchase_lock = fields.Boolean(default=True)
    apply_hard_lock = fields.Boolean(
        help='Hard lock is irreversible from normal accounting settings. Use only for finalized periods.')
    notes = fields.Text()

    @api.depends('company_id', 'date_end', 'task_ids.done', 'task_ids.required')
    def _compute_control_counts(self):
        Move = self.env['account.move']
        for close in self:
            close.draft_move_count = Move.search_count([
                ('company_id', '=', close.company_id.id),
                ('state', '=', 'draft'),
                ('date', '<=', close.date_end),
            ]) if close.company_id and close.date_end else 0
            close.incomplete_task_count = len(close.task_ids.filtered(
                lambda task: task.required and not task.done))

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for close in self:
            if close.date_start and close.date_end and close.date_start > close.date_end:
                raise ValidationError(_('The closing start date must be on or before the end date.'))

    @api.constrains('company_id', 'date_start', 'date_end')
    def _check_overlapping_period(self):
        for close in self:
            if not close.company_id or not close.date_start or not close.date_end:
                continue
            overlap = self.search_count([
                ('id', '!=', close.id),
                ('company_id', '=', close.company_id.id),
                ('date_start', '<=', close.date_end),
                ('date_end', '>=', close.date_start),
            ])
            if overlap:
                raise ValidationError(_('An accounting close already overlaps this company and period.'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for close in records:
            if close.name == _('New'):
                close.name = self.env['ir.sequence'].next_by_code(
                    'flousflow.account.period.close') or _('New')
            if not close.task_ids:
                close._create_default_tasks()
        return records

    def write(self, vals):
        protected = {
            'company_id', 'date_start', 'date_end', 'close_type', 'reviewer_id',
            'task_ids', 'apply_tax_lock', 'apply_sales_lock',
            'apply_purchase_lock', 'apply_hard_lock',
        }
        if protected.intersection(vals) and any(close.state in ('approved', 'closed') for close in self):
            raise UserError(_('An approved or closed period cannot be changed.'))
        return super().write(vals)

    def unlink(self):
        if any(close.state != 'draft' for close in self):
            raise UserError(_('Only draft period closes can be deleted.'))
        return super().unlink()

    def _create_default_tasks(self):
        task_names = [
            _('Post and validate all journal entries'),
            _('Review receivables, payables and reconciliations'),
            _('Review taxes and tax accounts'),
            _('Review inventory accruals and valuation'),
            _('Post depreciation and deferred recognition'),
            _('Review trial balance and financial statements'),
        ]
        for close in self:
            close.task_ids = [(0, 0, {'name': name, 'sequence': sequence * 10})
                              for sequence, name in enumerate(task_names, 1)]

    def _check_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only an Accounting Manager can approve or close a period.'))
        if any(close.company_id not in self.env.user.company_ids for close in self):
            raise AccessError(
                _('You cannot approve or close a period for a company outside your allowed companies.'))

    def action_submit(self):
        for close in self:
            if close.state != 'draft':
                raise UserError(_('Only a draft period can be submitted.'))
            if close.draft_move_count:
                raise UserError(_(
                    'There are %(count)s draft journal entries dated on or before %(date)s.',
                    count=close.draft_move_count, date=close.date_end))
            if close.incomplete_task_count:
                raise UserError(_('Complete every required closing checklist item first.'))
            close.state = 'review'

    def action_approve(self):
        self._check_manager()
        for close in self:
            if close.state != 'review':
                raise UserError(_('Only a period in review can be approved.'))
            if close.reviewer_id != self.env.user:
                raise UserError(_('Only the assigned reviewer can approve this period.'))
            close.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })

    def action_close(self):
        self._check_manager()
        for close in self:
            if close.state != 'approved':
                raise UserError(_('Only an approved period can be closed.'))
            if close.draft_move_count:
                raise UserError(_('Draft journal entries were added after approval. Review the period again.'))
            lock_values = {'fiscalyear_lock_date': close.date_end}
            if close.apply_tax_lock:
                lock_values['tax_lock_date'] = close.date_end
            if close.apply_sales_lock:
                lock_values['sale_lock_date'] = close.date_end
            if close.apply_purchase_lock:
                lock_values['purchase_lock_date'] = close.date_end
            if close.apply_hard_lock:
                lock_values['hard_lock_date'] = close.date_end
            # Accounting managers intentionally do not receive broad res.company
            # write access. Elevate only this verified standard lock-date write.
            close.company_id.sudo().write(lock_values)
            close.write({
                'state': 'closed',
                'closed_by_id': self.env.user.id,
                'closed_date': fields.Datetime.now(),
            })

    def action_reset_to_draft(self):
        self._check_manager()
        for close in self:
            if close.state not in ('review', 'approved'):
                raise UserError(_('Only an in-review or approved period can return to draft.'))
            close.write({
                'state': 'draft', 'approved_by_id': False, 'approved_date': False,
            })

    def action_open_draft_moves(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('account.action_account_moves_all')
        action['domain'] = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'draft'),
            ('date', '<=', self.date_end),
        ]
        return action


class FlousflowAccountPeriodCloseTask(models.Model):
    _name = 'flousflow.account.period.close.task'
    _description = 'Accounting Period Close Task'
    _order = 'sequence, id'
    _check_company_auto = True

    close_id = fields.Many2one(
        'flousflow.account.period.close', required=True, ondelete='cascade',
        index=True, check_company=True)
    company_id = fields.Many2one(related='close_id.company_id', store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    required = fields.Boolean(default=True)
    done = fields.Boolean()
    done_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    done_date = fields.Datetime(readonly=True, copy=False)
    note = fields.Char()

    def write(self, vals):
        if any(task.close_id.state in ('approved', 'closed') for task in self):
            raise UserError(_('Checklist items cannot change after period approval.'))
        if 'done' in vals:
            vals = dict(vals)
            vals.update({
                'done_by_id': self.env.user.id if vals['done'] else False,
                'done_date': fields.Datetime.now() if vals['done'] else False,
            })
        return super().write(vals)

    def unlink(self):
        if any(task.close_id.state != 'draft' for task in self):
            raise UserError(_('Checklist items can only be deleted while the period is draft.'))
        return super().unlink()
