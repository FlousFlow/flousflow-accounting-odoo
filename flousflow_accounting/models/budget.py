# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FlousflowBudget(models.Model):
    _name = 'flousflow.account.budget'
    _description = 'FlousFlow Budget'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Budget Name', required=True, tracking=True)
    user_id = fields.Many2one(
        'res.users', string='Responsible', default=lambda self: self.env.user)
    date_from = fields.Date(string='Start Date', required=True, tracking=True)
    date_to = fields.Date(string='End Date', required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    state = fields.Selection(
        [('draft', 'Draft'), ('confirm', 'Confirmed'), ('validate', 'Validated'),
         ('done', 'Done'), ('cancel', 'Cancelled')],
        string='Status', default='draft', required=True, copy=False,
        tracking=True, readonly=True)
    line_ids = fields.One2many(
        'flousflow.account.budget.line', 'budget_id', string='Budget Lines', copy=True)

    def action_confirm(self):
        return self._transition('draft', 'confirm')

    def action_validate(self):
        return self._transition('confirm', 'validate')

    def action_done(self):
        return self._transition('validate', 'done')

    def action_cancel(self):
        invalid = self.filtered(lambda budget: budget.state in ('done', 'cancel'))
        if invalid:
            raise UserError(_('Done or cancelled budgets cannot be cancelled.'))
        self.write({'state': 'cancel'})
        return True

    def action_draft(self):
        return self._transition(('confirm', 'cancel'), 'draft')

    def _transition(self, source_states, target_state):
        allowed = {source_states} if isinstance(source_states, str) else set(source_states)
        if any(budget.state not in allowed for budget in self):
            raise UserError(_(
                'This budget transition is not allowed from the current status.'))
        self.write({'state': target_state})
        return True

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for budget in self:
            if budget.date_from > budget.date_to:
                raise ValidationError(_('Start date must be before end date.'))
            if any(
                    line.date_from < budget.date_from
                    or line.date_to > budget.date_to
                    for line in budget.line_ids):
                raise ValidationError(_(
                    'Budget line dates must stay within the budget period.'))


class FlousflowBudgetLine(models.Model):
    _name = 'flousflow.account.budget.line'
    _description = 'FlousFlow Budget Line'
    _order = 'date_from, id'

    budget_id = fields.Many2one(
        'flousflow.account.budget', string='Budget',
        ondelete='cascade', required=True, index=True)
    name = fields.Char(compute='_compute_name', string='Label')
    account_ids = fields.Many2many(
        'account.account', 'flousflow_budget_account_rel',
        'line_id', 'account_id', string='Accounts', check_company=True)
    analytic_account_ids = fields.Many2many(
        'account.analytic.account', 'flousflow_budget_analytic_account_rel',
        'line_id', 'analytic_account_id', string='Analytic Accounts',
        check_company=True)
    date_from = fields.Date(string='Start Date', required=True)
    date_to = fields.Date(string='End Date', required=True)
    company_id = fields.Many2one(
        related='budget_id.company_id', string='Company',
        store=True, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    planned_amount = fields.Monetary(
        string='Planned Amount', required=True,
        help="Positive amount for revenue, negative amount for cost.")
    practical_amount = fields.Monetary(
        compute='_compute_practical_amount', string='Actual Amount',
        help="Amount really earned or spent.")
    theoretical_amount = fields.Monetary(
        compute='_compute_theoretical_amount', string='Theoretical Amount',
        help="Amount expected at this date (prorated by time).")
    percentage = fields.Float(
        compute='_compute_percentage', string='Achievement (%)',
        help="Actual vs theoretical. Above 100% means over budget for revenue.")
    is_above_budget = fields.Boolean(compute='_compute_above_budget', string='Above Budget')
    state = fields.Selection(related='budget_id.state', string='Budget State', readonly=True)

    @api.depends('budget_id.name', 'account_ids')
    def _compute_name(self):
        for line in self:
            name = line.budget_id.name or ''
            if line.account_ids:
                name = '%s (%s)' % (name, ', '.join(line.account_ids.mapped('code') or []))
            line.name = name

    @api.depends('account_ids', 'analytic_account_ids', 'date_from', 'date_to')
    def _compute_practical_amount(self):
        for line in self:
            line.practical_amount = 0.0
            if not line.account_ids or not line.date_from or not line.date_to:
                continue
            if line.analytic_account_ids:
                analytic_domain = [
                    ('company_id', '=', line.company_id.id),
                    ('date', '>=', line.date_from),
                    ('date', '<=', line.date_to),
                    ('auto_account_id', 'in', line.analytic_account_ids.ids),
                    ('general_account_id', 'in', line.account_ids.ids),
                ]
                groups = self.env['account.analytic.line']._read_group(
                    analytic_domain, aggregates=['amount:sum'])
                line.practical_amount = (groups[0][0] if groups else 0.0) or 0.0
                continue
            domain = [
                ('account_id', 'in', line.account_ids.ids),
                ('company_id', '=', line.company_id.id),
                ('parent_state', '=', 'posted'),
                ('date', '>=', line.date_from),
                ('date', '<=', line.date_to),
            ]
            groups = self.env['account.move.line']._read_group(
                domain, aggregates=['debit:sum', 'credit:sum'])
            if groups:
                debit, credit = groups[0]
                line.practical_amount = (credit or 0.0) - (debit or 0.0)

    @api.depends('planned_amount', 'date_from', 'date_to')
    def _compute_theoretical_amount(self):
        today = fields.Date.today()
        for line in self:
            if not line.date_from or not line.date_to:
                line.theoretical_amount = line.planned_amount
                continue
            total = (line.date_to - line.date_from).days
            elapsed = (today - line.date_from).days
            if elapsed <= 0:
                line.theoretical_amount = 0.0
            elif total > 0 and today < line.date_to:
                line.theoretical_amount = (elapsed / total) * line.planned_amount
            else:
                line.theoretical_amount = line.planned_amount

    @api.depends('practical_amount', 'theoretical_amount')
    def _compute_percentage(self):
        for line in self:
            if line.theoretical_amount:
                line.percentage = (line.practical_amount / line.theoretical_amount) * 100.0
            else:
                line.percentage = 0.0

    @api.depends('practical_amount', 'theoretical_amount')
    def _compute_above_budget(self):
        for line in self:
            line.is_above_budget = bool(
                line.theoretical_amount
                and (line.practical_amount / line.theoretical_amount) > 1.0)

    @api.constrains('date_from', 'date_to', 'budget_id')
    def _check_line_dates(self):
        for line in self:
            if line.date_from > line.date_to:
                raise ValidationError(_('Line start date must be before end date.'))
            if (line.date_from < line.budget_id.date_from
                    or line.date_to > line.budget_id.date_to):
                raise ValidationError(
                    _('Budget line dates must stay within the budget period.'))

    def action_open_entries(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'account.action_account_moves_all_a')
        action['domain'] = [
            ('account_id', 'in', self.account_ids.ids),
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        return action
