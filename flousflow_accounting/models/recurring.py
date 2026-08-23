# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


_logger = logging.getLogger(__name__)


class FlousflowAccountRecurring(models.Model):
    _name = 'flousflow.account.recurring'
    _description = 'FlousFlow Recurring Payment'
    _rec_name = 'name'
    _order = 'date_begin desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Reference', readonly=True, copy=False)
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary(string='Amount', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        domain=[('type', 'in', ('bank', 'cash'))], check_company=True)
    payment_type = fields.Selection(
        [('inbound', 'Receive Money'), ('outbound', 'Send Money')],
        string='Payment Type', required=True, default='outbound')
    recurring_period = fields.Selection(
        [('days', 'Days'), ('weeks', 'Weeks'),
         ('months', 'Months'), ('years', 'Years')],
        string='Recurring Period', required=True, default='months')
    recurring_interval = fields.Integer(
        string='Interval', required=True, default=1)
    date_begin = fields.Date(string='Start Date', required=True)
    date_end = fields.Date(string='End Date', required=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Done')],
        string='Status', default='draft', required=True, copy=False)
    description = fields.Text(string='Description')
    line_ids = fields.One2many(
        'flousflow.account.recurring.line', 'recurring_id',
        string='Scheduled Payments')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                company = self.env['res.company'].browse(
                    vals.get('company_id')) if vals.get('company_id') else self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(
                    company).next_by_code(
                    'flousflow.account.recurring') or _('New')
        return super().create(vals_list)

    @api.constrains('amount', 'recurring_interval')
    def _check_positive_values(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('Amount must be greater than zero.'))
            if rec.recurring_interval <= 0:
                raise ValidationError(_('Recurring interval must be greater than zero.'))

    @api.constrains('date_begin', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_end < rec.date_begin:
                raise ValidationError(_('End date must be after start date.'))

    def _next_date(self, current):
        self.ensure_one()
        period = self.recurring_period
        interval = self.recurring_interval
        if period == 'days':
            return current + relativedelta(days=interval)
        if period == 'weeks':
            return current + relativedelta(weeks=interval)
        if period == 'months':
            return current + relativedelta(months=interval)
        return current + relativedelta(years=interval)

    def action_generate_schedule(self):
        for rec in self:
            if rec.state == 'done':
                continue
            rec.line_ids.unlink()
            current = rec.date_begin
            lines = []
            while current <= rec.date_end:
                lines.append((0, 0, {
                    'partner_id': rec.partner_id.id,
                    'amount': rec.amount,
                    'date': current,
                    'journal_id': rec.journal_id.id,
                    'company_id': rec.company_id.id,
                }))
                current = rec._next_date(current)
            rec.write({'line_ids': lines, 'state': 'done'})
        return True

    def action_reset(self):
        for rec in self:
            if rec.line_ids.filtered('payment_id'):
                raise ValidationError(
                    _('You cannot reset a recurring payment that has already '
                      'generated payments.'))
            rec.line_ids.unlink()
            rec.state = 'draft'

    def action_generate_payments(self):
        due = self.env['flousflow.account.recurring.line'].search([
            ('recurring_id', 'in', self.ids),
            ('date', '<=', date.today()),
            ('state', '=', 'draft'),
        ])
        for line in due:
            line.action_create_payment()
        return True

    def unlink(self):
        for rec in self:
            if rec.state == 'done':
                raise ValidationError(_('You cannot delete a done recurring payment.'))
        return super().unlink()


class FlousflowAccountRecurringLine(models.Model):
    _name = 'flousflow.account.recurring.line'
    _description = 'FlousFlow Recurring Payment Line'
    _order = 'date, id'

    recurring_id = fields.Many2one(
        'flousflow.account.recurring', string='Recurring Payment',
        ondelete='cascade', required=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, check_company=True)
    amount = fields.Monetary(string='Amount', required=True)
    date = fields.Date(string='Date', required=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    payment_id = fields.Many2one(
        'account.payment', string='Payment', readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Scheduled'), ('in_process', 'In Process'),
         ('paid', 'Paid'), ('cancelled', 'Cancelled')],
        compute='_compute_state', string='Status', store=True)

    @api.depends('payment_id.state')
    def _compute_state(self):
        for line in self:
            line.state = (
                line._payment_line_state(line.payment_id.state)
                if line.payment_id else 'draft')

    def action_create_payment(self):
        self.ensure_one()
        if self.payment_id:
            if self.payment_id.state == 'draft':
                self.payment_id.action_post()
            return self.payment_id
        rec = self.recurring_id
        partner_type = 'customer' if rec.payment_type == 'inbound' else 'supplier'
        payment = self.env['account.payment'].create({
            'payment_type': rec.payment_type,
            'partner_type': partner_type,
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date,
            'memo': rec.name or _('Recurring payment'),
        })
        payment.action_post()
        self.payment_id = payment.id
        return payment

    @api.model
    def _cron_generate_due_payments(self, batch_size=100):
        candidates = self.search([
            ('date', '<=', fields.Date.context_today(self)),
            ('payment_id', '=', False),
        ], order='date, id', limit=batch_size)
        for candidate in candidates:
            try:
                with self.env.cr.savepoint():
                    line = candidate.try_lock_for_update(limit=1)
                    if (line and not line.payment_id
                            and line.date <= fields.Date.context_today(line)):
                        line.with_company(line.company_id).action_create_payment()
            except Exception:
                _logger.exception(
                    'Could not generate recurring payment for schedule line %s.',
                    candidate.id)
        return True

    @api.model
    def _payment_line_state(self, payment_state):
        if payment_state == 'paid':
            return 'paid'
        if payment_state in ('canceled', 'rejected'):
            return 'cancelled'
        return 'in_process'
