# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class FlousflowAccountPaymentBatch(models.Model):
    _name = 'flousflow.account.payment.batch'
    _description = 'FlousFlow Payment Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc, id desc'
    _check_company_auto = True

    name = fields.Char(
        string='Batch Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'), tracking=True)
    date = fields.Date(
        string='Batch Date', required=True, default=fields.Date.context_today,
        tracking=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='restrict', tracking=True)
    journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True,
        domain="[('company_id', '=', company_id), ('type', 'in', ('bank', 'cash'))]",
        tracking=True)
    payment_type = fields.Selection(
        [('inbound', 'Receive'), ('outbound', 'Send')], required=True,
        default='outbound', tracking=True)
    currency_id = fields.Many2one(
        'res.currency', compute='_compute_currency_id', store=True, readonly=True)
    payment_ids = fields.Many2many(
        'account.payment', 'flousflow_payment_batch_payment_rel',
        'batch_id', 'payment_id', string='Payments', check_company=True,
        domain="[('company_id', '=', company_id), ('journal_id', '=', journal_id), "
               "('payment_type', '=', payment_type), ('state', '=', 'draft')]",
        tracking=True)
    payment_count = fields.Integer(compute='_compute_totals')
    amount_total = fields.Monetary(
        string='Total Amount', compute='_compute_totals', currency_field='currency_id')
    state = fields.Selection(
        [('draft', 'Draft'), ('submitted', 'Submitted'),
         ('approved', 'Approved'), ('posted', 'Posted'),
         ('cancelled', 'Cancelled')],
        default='draft', required=True, copy=False, tracking=True)
    submitted_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    approved_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    submitted_at = fields.Datetime(readonly=True, copy=False)
    approved_at = fields.Datetime(readonly=True, copy=False)
    note = fields.Text(string='Internal Notes')

    @api.depends('journal_id.currency_id', 'company_id.currency_id')
    def _compute_currency_id(self):
        for batch in self:
            batch.currency_id = batch.journal_id.currency_id or batch.company_id.currency_id

    @api.depends('payment_ids', 'payment_ids.amount')
    def _compute_totals(self):
        for batch in self:
            batch.payment_count = len(batch.payment_ids)
            batch.amount_total = sum(batch.payment_ids.mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get('name', _('New')) == _('New'):
                values['name'] = self.env['ir.sequence'].next_by_code(
                    'flousflow.account.payment.batch') or _('New')
        return super().create(vals_list)

    def _check_manager(self):
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(_('Only Accounting Managers can approve or post payment batches.'))

    def _validate_payments(self):
        for batch in self:
            if not batch.payment_ids:
                raise ValidationError(_('Add at least one payment to the batch.'))
            invalid = batch.payment_ids.filtered(
                lambda payment: payment.company_id != batch.company_id
                or payment.journal_id != batch.journal_id
                or payment.payment_type != batch.payment_type
                or payment.currency_id != batch.currency_id
                or payment.state != 'draft')
            if invalid:
                raise ValidationError(_(
                    'Every payment must be draft and use the batch company, journal, '
                    'currency, and payment direction.'))

    def action_submit(self):
        for batch in self:
            if batch.state != 'draft':
                raise UserError(_('Only draft payment batches can be submitted.'))
            batch._validate_payments()
            batch.write({
                'state': 'submitted',
                'submitted_by_id': self.env.user.id,
                'submitted_at': fields.Datetime.now(),
            })
        return True

    def action_approve(self):
        self._check_manager()
        for batch in self:
            if batch.company_id not in self.env.user.company_ids:
                raise AccessError(_('You cannot approve a batch outside your allowed companies.'))
            if batch.state != 'submitted':
                raise UserError(_('Only submitted payment batches can be approved.'))
            batch._validate_payments()
            batch.write({
                'state': 'approved',
                'approved_by_id': self.env.user.id,
                'approved_at': fields.Datetime.now(),
            })
        return True

    def action_post(self):
        self._check_manager()
        for batch in self:
            if batch.state != 'approved':
                raise UserError(_('Only approved payment batches can be posted.'))
            batch._validate_payments()
            batch.payment_ids.action_post()
            batch.state = 'posted'
        return True

    def action_cancel(self):
        for batch in self:
            if batch.state == 'posted':
                raise UserError(_(
                    'A posted batch cannot be cancelled. Cancel or reverse its standard '
                    'payments individually to preserve the accounting audit trail.'))
            batch.state = 'cancelled'
        return True

    def action_reset_to_draft(self):
        for batch in self:
            if batch.state != 'cancelled':
                raise UserError(_('Only cancelled payment batches can return to draft.'))
            if batch.payment_ids.filtered(lambda payment: payment.state != 'draft'):
                raise UserError(_('All payments must be draft before resetting the batch.'))
            batch.state = 'draft'
        return True

    def unlink(self):
        if self.filtered(lambda batch: batch.state != 'draft'):
            raise UserError(_('Only draft payment batches can be deleted.'))
        return super().unlink()
