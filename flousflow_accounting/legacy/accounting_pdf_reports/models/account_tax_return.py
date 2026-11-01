from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountTaxReturn(models.Model):
    _name = 'account.tax.return'
    _description = 'Tax Return'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True
    _order = 'date_to desc, id desc'

    name = fields.Char(required=True, copy=False, readonly=True, default='New', tracking=True)
    return_type = fields.Selection([
        ('annual_corporate_tax', 'Annual Closing: Corporate Tax'),
        ('tax', 'Tax Return'),
    ], string='Return Type', required=True, default='annual_corporate_tax', tracking=True)
    date_from = fields.Date(
        string='Start Date', required=True, tracking=True,
        default=lambda self: self._default_period_dates()['date_from'],
    )
    date_to = fields.Date(
        string='End Date', required=True, tracking=True,
        default=lambda self: self._default_period_dates()['date_to'],
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        index=True, tracking=True,
    )
    state = fields.Selection([
        ('to_review', 'To Review'),
        ('to_submit', 'To Submit'),
        ('submitted', 'Submitted'),
        ('paid', 'Paid'),
    ], string='Status', required=True, default='to_review', tracking=True, index=True)
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True, copy=False)
    reviewed_on = fields.Datetime(readonly=True, copy=False)
    submitted_by = fields.Many2one('res.users', string='Submitted By', readonly=True, copy=False)
    submitted_on = fields.Datetime(readonly=True, copy=False)
    paid_by = fields.Many2one('res.users', string='Marked Paid By', readonly=True, copy=False)
    paid_on = fields.Datetime(readonly=True, copy=False)
    note = fields.Text(string='Internal Notes')
    check_ids = fields.One2many(
        'account.working.file.check', 'tax_return_id', string='Review Checks', copy=True,
    )
    check_count = fields.Integer(compute='_compute_check_progress')
    reviewed_check_count = fields.Integer(compute='_compute_check_progress')
    check_progress = fields.Float(compute='_compute_check_progress')

    _period_unique = models.Constraint(
        'UNIQUE(company_id, return_type, date_from, date_to)',
        'A tax return of this type already exists for this company and period.',
    )

    @api.depends('check_ids', 'check_ids.state')
    def _compute_check_progress(self):
        for record in self:
            record.check_count = len(record.check_ids)
            record.reviewed_check_count = len(record.check_ids.filtered(
                lambda check: check.state != 'pending'
            ))
            record.check_progress = (
                100.0 * record.reviewed_check_count / record.check_count
                if record.check_count else 0.0
            )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if 'check_ids' in fields_list:
            templates = self.env['account.working.file.template'].search([
                ('active', '=', True), ('scope', '=', 'tax_return'),
            ])
            values['check_ids'] = [fields.Command.create({
                'sequence': template.sequence,
                'section': template.section,
                'name': template.name,
                'description': template.description,
                'template_id': template.id,
                'evidence_required': template.evidence_required,
            }) for template in templates]
        return values

    @api.model_create_multi
    def create(self, vals_list):
        templates = self.env['account.working.file.template'].search([
            ('active', '=', True), ('scope', '=', 'tax_return'),
        ])
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('account.tax.return') or _('New')
            if 'check_ids' not in vals and templates:
                vals['check_ids'] = [fields.Command.create({
                    'sequence': template.sequence,
                    'section': template.section,
                    'name': template.name,
                    'description': template.description,
                    'template_id': template.id,
                    'evidence_required': template.evidence_required,
                }) for template in templates]
        return super().create(vals_list)

    @api.model
    def _default_period_dates(self):
        previous_year = fields.Date.context_today(self) - relativedelta(years=1)
        return self.env.company.compute_fiscalyear_dates(previous_year)

    @api.constrains('date_from', 'date_to')
    def _check_period(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_('The start date must be before or equal to the end date.'))

    def action_open_tax_report(self):
        self.ensure_one()
        if self.return_type == 'annual_corporate_tax':
            return {
                'type': 'ir.actions.act_window',
                'name': _('Profit and Loss'),
                'res_model': 'accounting.report',
                'view_mode': 'form',
                'view_id': self.env.ref('flousflow_accounting.apr__accounting_report_view').id,
                'target': 'new',
                'context': {
                    'default_account_report_id': self.env.ref(
                        'flousflow_accounting.apr__account_financial_report_profitandloss0').id,
                    'default_company_id': self.company_id.id,
                    'default_date_from': self.date_from,
                    'default_date_to': self.date_to,
                    'default_target_move': 'posted',
                },
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tax Report'),
            'res_model': 'account.tax.report.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('flousflow_accounting.apr__accounting_tax_report_view').id,
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
                'default_period': 'custom',
                'default_date_from': self.date_from,
                'default_date_to': self.date_to,
            },
        }

    def action_open_tax_closing(self):
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Only an Accounting Administrator can create a tax closing entry.'))
        if self.state == 'to_review':
            raise UserError(_('Review the tax report before creating a closing entry.'))
        if self.return_type != 'tax':
            raise UserError(_('Tax closing entries are only available for periodic tax returns.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Close Tax Period'),
            'res_model': 'account.tax.closing.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_company_id': self.company_id.id,
                'default_date_from': self.date_from,
                'default_date_to': self.date_to,
            },
        }

    def action_mark_reviewed(self):
        for record in self:
            if record.state != 'to_review':
                raise UserError(_('Only returns awaiting review can be marked as reviewed.'))
            record.write({
                'state': 'to_submit',
                'reviewed_by': self.env.user.id,
                'reviewed_on': fields.Datetime.now(),
            })

    def action_mark_submitted(self):
        for record in self:
            if record.state != 'to_submit':
                raise UserError(_('Review the return before marking it as submitted.'))
            record.write({
                'state': 'submitted',
                'submitted_by': self.env.user.id,
                'submitted_on': fields.Datetime.now(),
            })

    def action_mark_paid(self):
        for record in self:
            if record.state != 'submitted':
                raise UserError(_('Only a submitted return can be marked as paid.'))
            record.write({
                'state': 'paid',
                'paid_by': self.env.user.id,
                'paid_on': fields.Datetime.now(),
            })
