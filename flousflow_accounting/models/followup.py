# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FlousflowAccountFollowup(models.Model):
    _name = 'flousflow.account.followup'
    _description = 'FlousFlow Follow-up Configuration'
    _rec_name = 'name'

    name = fields.Char(
        string='Follow-up Configuration', related='company_id.name', readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    followup_line_ids = fields.One2many(
        'flousflow.account.followup.line', 'followup_id',
        string='Follow-up Levels', copy=True)
    automatic = fields.Boolean(
        string='Automatic Follow-up', default=False,
        help='Process configured reminders from the daily scheduled action.')

    _company_uniq = models.Constraint(
        'unique (company_id)', 'Only one follow-up per company is allowed.')

    @api.model
    def _cron_process_automatic_followup(self):
        process_date = self.env.context.get('followup_date') or fields.Date.context_today(self)
        for config in self.search([('automatic', '=', True)]):
            wizard = self.env['flousflow.account.followup.wizard'].with_company(
                config.company_id).create({
                    'company_id': config.company_id.id,
                    'date': process_date,
                })
            wizard.action_process()
        return True


class FlousflowAccountFollowupLine(models.Model):
    _name = 'flousflow.account.followup.line'
    _description = 'FlousFlow Follow-up Level'
    _order = 'delay, id'

    name = fields.Char(string='Follow-up Action', required=True)
    sequence = fields.Integer(compute='_compute_sequence', string='Sequence')
    followup_id = fields.Many2one(
        'flousflow.account.followup', string='Follow-up',
        required=True, ondelete='cascade')
    delay = fields.Integer(
        string='Due Days', required=True,
        help="Number of days after the due date to wait before sending this reminder. "
             "Can be negative to send a polite alert beforehand.")
    description = fields.Text(string='Printed Message', translate=True)
    send_email = fields.Boolean(string='Send an Email', default=True)
    send_letter = fields.Boolean(string='Send a Letter', default=True)
    manual_action = fields.Boolean(string='Manual Action', default=False)
    manual_action_note = fields.Text(string='Action To Do')
    manual_action_responsible_id = fields.Many2one(
        'res.users', string='Assign a Responsible', ondelete='set null')
    email_template_id = fields.Many2one(
        'mail.template', string='Email Template', ondelete='set null')
    repeat_every_days = fields.Integer(
        string='Repeat Every (Days)', default=0,
        help='Zero sends this level once per receivable line. A positive value repeats it after that many days.')
    company_id = fields.Many2one(related='followup_id.company_id', store=True)

    _delay_uniq = models.Constraint(
        'unique (followup_id, delay)', 'Due days of the follow-up levels must be different.')

    @api.depends('delay', 'followup_id.followup_line_ids.delay')
    def _compute_sequence(self):
        for line in self:
            delays = sorted(line.followup_id.followup_line_ids.mapped('delay'))
            if line.delay in delays:
                line.sequence = delays.index(line.delay) + 1
            else:
                line.sequence = 0

    @api.constrains('repeat_every_days')
    def _check_repeat_every_days(self):
        if any(line.repeat_every_days < 0 for line in self):
            raise ValidationError(_('Repeat interval cannot be negative.'))


class FlousflowAccountFollowupWizard(models.TransientModel):
    _name = 'flousflow.account.followup.wizard'
    _description = 'FlousFlow Follow-up Process'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    date = fields.Date(
        string='Follow-up Date', required=True,
        default=fields.Date.context_today)
    partner_ids = fields.Many2many(
        'res.partner', string='Partners',
        help="Leave empty to process all partners with overdue amounts.")

    def _overdue_lines(self):
        """Unreconciled receivable lines grouped by partner."""
        domain = [
            ('company_id', '=', self.company_id.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('full_reconcile_id', '=', False),
            ('partner_id', '!=', False),
        ]
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        return self.env['account.move.line'].search(domain)

    def _days_overdue(self, line):
        due = line.date_maturity or line.date
        return (self.date - due).days

    def _followup_config(self):
        self.ensure_one()
        return self.env['flousflow.account.followup'].search(
            [('company_id', '=', self.company_id.id)], limit=1)

    def _level_for_line(self, line, levels):
        level = False
        days = self._days_overdue(line)
        for candidate in levels:
            if days >= candidate.delay:
                level = candidate
            else:
                break
        return level

    def _should_process_line(self, line, level):
        if line.followup_line_id != level or not line.followup_date:
            return True
        if not level.repeat_every_days:
            return False
        return (self.date - line.followup_date).days >= level.repeat_every_days

    def action_process(self):
        self.ensure_one()
        config = self._followup_config()
        if not config or not config.followup_line_ids:
            raise ValidationError(
                _('No follow-up levels configured for this company.'))

        lines = self._overdue_lines()
        levels = config.followup_line_ids.sorted('delay')
        processed = 0
        for line in lines:
            level = self._level_for_line(line, levels)
            if not level or not self._should_process_line(line, level):
                continue
            line.write({
                'followup_line_id': level.id,
                'followup_date': self.date,
            })
            if level.send_email:
                partner = line.partner_id
                if level.email_template_id:
                    level.email_template_id.send_mail(
                        partner.id, force_send=False)
                else:
                    partner.message_post(
                        body=_('Reminder sent: %s') % level.name)
            if level.manual_action:
                partner = line.partner_id
                responsible = (
                    level.manual_action_responsible_id
                    or partner.payment_responsible_id
                    or self.env.user)
                partner.write({
                    'payment_next_action': level.manual_action_note,
                    'payment_next_action_date': self.date,
                    'payment_responsible_id': responsible.id,
                })
                existing_activity = self.env['mail.activity'].search([
                    ('res_model', '=', 'res.partner'),
                    ('res_id', '=', partner.id),
                    ('user_id', '=', responsible.id),
                    ('summary', '=', level.name),
                ], limit=1)
                if not existing_activity:
                    partner.activity_schedule(
                        'mail.mail_activity_data_todo',
                        date_deadline=self.date,
                        summary=level.name,
                        note=level.manual_action_note or level.description,
                        user_id=responsible.id,
                    )
            self.env['flousflow.account.followup.history'].create({
                'company_id': self.company_id.id,
                'partner_id': line.partner_id.id,
                'move_line_id': line.id,
                'level_id': level.id,
                'date': self.date,
                'email_sent': level.send_email,
                'letter_requested': level.send_letter,
                'manual_action_created': level.manual_action,
            })
            processed += 1
        return {
            'type': 'ir.actions.act_window_close' if not processed else 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Follow-up processed'),
                'message': _('%s reminder(s) sent.') % processed,
                'type': 'success',
            },
        }

    def _letter_partner_data(self):
        self.ensure_one()
        config = self._followup_config()
        if not config:
            return []
        levels = config.followup_line_ids.sorted('delay')
        partners = {}
        for line in self._overdue_lines():
            level = self._level_for_line(line, levels)
            if not level or not level.send_letter:
                continue
            partner_data = partners.setdefault(line.partner_id.id, {
                'partner': line.partner_id,
                'lines': [],
                'total': 0.0,
            })
            amount = line.amount_residual
            partner_data['lines'].append({
                'move_name': line.move_id.name,
                'date': line.date,
                'date_maturity': line.date_maturity or line.date,
                'days_overdue': self._days_overdue(line),
                'amount': amount,
                'level_name': level.name,
                'message': level.description,
            })
            partner_data['total'] += amount
        return sorted(
            partners.values(), key=lambda data: data['partner'].display_name)

    def action_print_letters(self):
        self.ensure_one()
        if not self._letter_partner_data():
            raise UserError(_(
                'No partners currently match a follow-up level configured to print letters.'))
        return self.env.ref(
            'flousflow_accounting.action_report_followup_letters'
        ).report_action(self)


class FlousflowAccountFollowupHistory(models.Model):
    _name = 'flousflow.account.followup.history'
    _description = 'Follow-up History'
    _order = 'date desc, id desc'
    _check_company_auto = True

    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    date = fields.Date(required=True, default=fields.Date.context_today, index=True)
    partner_id = fields.Many2one(
        'res.partner', required=True, ondelete='restrict', index=True)
    move_line_id = fields.Many2one(
        'account.move.line', required=True, ondelete='restrict', check_company=True)
    level_id = fields.Many2one(
        'flousflow.account.followup.line', required=True, ondelete='restrict',
        check_company=True)
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        ondelete='restrict')
    email_sent = fields.Boolean()
    letter_requested = fields.Boolean()
    manual_action_created = fields.Boolean()


class FlousflowAccountPaymentPromise(models.Model):
    _name = 'flousflow.account.payment.promise'
    _description = 'Customer Promise to Pay'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'promise_date desc, id desc'
    _check_company_auto = True

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, tracking=True)
    partner_id = fields.Many2one('res.partner', required=True, tracking=True, domain="[('customer_rank', '>', 0)]")
    move_line_id = fields.Many2one(
        'account.move.line', check_company=True, tracking=True,
        domain="[('company_id', '=', company_id), ('partner_id', '=', partner_id), ('account_id.account_type', '=', 'asset_receivable'), ('reconciled', '=', False)]")
    currency_id = fields.Many2one(related='company_id.currency_id')
    amount = fields.Monetary(required=True, tracking=True)
    promise_date = fields.Date(required=True, tracking=True)
    responsible_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, tracking=True)
    state = fields.Selection([
        ('open', 'Open'), ('kept', 'Kept'), ('broken', 'Broken'), ('cancelled', 'Cancelled'),
    ], default='open', required=True, tracking=True)
    notes = fields.Text()
    resolved_date = fields.Date(readonly=True, copy=False)

    @api.constrains('amount')
    def _check_amount(self):
        if any(record.amount <= 0 for record in self):
            raise ValidationError(_('Promise amount must be positive.'))

    @api.constrains('move_line_id', 'partner_id', 'company_id')
    def _check_source_line(self):
        for record in self.filtered('move_line_id'):
            if record.move_line_id.company_id != record.company_id or record.move_line_id.partner_id.commercial_partner_id != record.partner_id.commercial_partner_id:
                raise ValidationError(_('The promised journal item must belong to the same customer and company.'))

    def _resolve(self, state):
        for record in self:
            if record.state != 'open':
                raise UserError(_('Only an open promise can be resolved.'))
            record.write({'state': state, 'resolved_date': fields.Date.context_today(record)})

    def action_mark_kept(self):
        self._resolve('kept')

    def action_mark_broken(self):
        self._resolve('broken')

    def action_cancel(self):
        self._resolve('cancelled')
