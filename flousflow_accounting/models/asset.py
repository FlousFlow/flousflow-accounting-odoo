# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
import calendar
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FlousflowAssetCategory(models.Model):
    _name = 'flousflow.account.asset.category'
    _description = 'FlousFlow Asset Category'
    _inherit = ['mail.thread']
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string='Asset Model', required=True, index=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(default=True)
    group_id = fields.Many2one(
        'flousflow.account.asset.group', string='Asset Group',
        check_company=True)
    recognition_type = fields.Selection(
        [('asset', 'Asset Depreciation'),
         ('expense', 'Deferred Expense'),
         ('revenue', 'Deferred Revenue')],
        required=True, default='asset')

    asset_account_id = fields.Many2one(
        'account.account', string='Asset / Deferred Expense Account',
        domain=[('account_type', 'in', ('asset_fixed', 'asset_prepayments'))],
        check_company=True,
        help="Account used to record the purchase of the asset at its original price.")
    depreciation_account_id = fields.Many2one(
        'account.account', string='Accumulated Depreciation Account',
        domain=[('account_type', '=', 'asset_fixed')], check_company=True,
        help="Account used in the depreciation entries to decrease the asset value.")
    expense_account_id = fields.Many2one(
        'account.account', string='Expense Account',
        domain=[('account_type', 'in', ('expense', 'expense_depreciation'))],
        check_company=True,
        help="Account used in the periodical entries to record the depreciation expense.")
    deferred_revenue_account_id = fields.Many2one(
        'account.account', string='Deferred Revenue Account',
        domain=[('account_type', 'in', ('liability_current', 'liability_non_current'))],
        check_company=True)
    revenue_account_id = fields.Many2one(
        'account.account', string='Revenue Account',
        domain=[('account_type', 'in', ('income', 'income_other'))],
        check_company=True)
    disposal_loss_account_id = fields.Many2one(
        'account.account', string='Asset Disposal Loss Account',
        domain=[('account_type', 'in', ('expense', 'expense_depreciation'))],
        check_company=True)
    disposal_gain_account_id = fields.Many2one(
        'account.account', string='Asset Disposal Gain Account',
        domain=[('account_type', 'in', ('income', 'income_other'))],
        check_company=True)
    disposal_clearing_account_id = fields.Many2one(
        'account.account', string='Asset Disposal Clearing Account',
        domain=[('account_type', '=', 'asset_current')], check_company=True,
        help='Use this account on the customer invoice line for an asset sale.')
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        domain=[('type', '=', 'general')],
        check_company=True,
        default=lambda self: self._default_journal())

    method = fields.Selection(
        [('linear', 'Straight Line'), ('degressive', 'Declining Balance'),
         ('degressive_then_linear', 'Declining then Straight Line')],
        string='Computation Method', required=True, default='linear')
    method_number = fields.Integer(
        string='Number of Depreciations', default=5,
        help="The number of depreciations needed to fully depreciate the asset.")
    method_period = fields.Integer(
        string='Period Length (Months)', default=12, required=True,
        help="Time between two depreciations, in months.")
    method_progress_factor = fields.Float(
        string='Declining Factor', default=0.3,
        help="Factor used by the declining balance method.")
    prorata = fields.Boolean(
        string='Prorata Temporis',
        help="First depreciation is computed from the asset date instead of a full period.")
    prorata_computation_type = fields.Selection(
        [('none', 'No Prorata'),
         ('constant_periods', 'Constant Periods'),
         ('daily_computation', 'Based on Days per Period')],
        string='Computation', required=True, default='none')
    auto_create_asset = fields.Selection(
        [('no', 'No Automatic Asset'), ('draft', 'Create in Draft'),
         ('validate', 'Create and Validate')],
        string='Automatic Asset Creation', default='no', required=True)

    @api.model
    def _default_journal(self):
        return self.env['account.journal'].search(
            [('type', '=', 'general'), ('company_id', '=', self.env.company.id)],
            limit=1)

    @api.constrains('method_number', 'method_period', 'method_progress_factor')
    def _check_depreciation_params(self):
        for cat in self:
            if cat.method_number <= 0:
                raise ValidationError(_('Number of depreciations must be positive.'))
            if cat.method_period <= 0:
                raise ValidationError(_('Period length must be positive.'))
            if cat.method in ('degressive', 'degressive_then_linear') and not (
                    0 < cat.method_progress_factor <= 1):
                raise ValidationError(_('Declining factor must be between 0 and 1.'))

    @api.constrains(
        'recognition_type', 'asset_account_id', 'depreciation_account_id',
        'expense_account_id', 'deferred_revenue_account_id', 'revenue_account_id')
    def _check_recognition_accounts(self):
        for category in self:
            if category.recognition_type == 'asset' and not all((
                    category.asset_account_id,
                    category.depreciation_account_id,
                    category.expense_account_id)):
                raise ValidationError(_(
                    'Asset categories require asset, accumulated depreciation, '
                    'and depreciation expense accounts.'))
            if category.recognition_type == 'expense' and not all((
                    category.asset_account_id, category.expense_account_id)):
                raise ValidationError(_(
                    'Deferred expense categories require deferred and expense accounts.'))
            if (category.recognition_type == 'expense'
                    and category.asset_account_id.account_type != 'asset_prepayments'):
                raise ValidationError(_(
                    'Deferred expenses must use a prepayments account.'))
            if category.recognition_type == 'revenue' and not all((
                    category.deferred_revenue_account_id,
                    category.revenue_account_id)):
                raise ValidationError(_(
                    'Deferred revenue categories require deferred and revenue accounts.'))

    @api.constrains(
        'auto_create_asset', 'asset_account_id', 'company_id', 'recognition_type')
    def _check_automatic_asset_account_unique(self):
        for category in self.filtered(
                lambda item: item.auto_create_asset != 'no'
                and item.recognition_type == 'asset' and item.asset_account_id):
            duplicate = self.search_count([
                ('id', '!=', category.id),
                ('company_id', '=', category.company_id.id),
                ('recognition_type', '=', 'asset'),
                ('asset_account_id', '=', category.asset_account_id.id),
                ('auto_create_asset', '!=', 'no'),
            ])
            if duplicate:
                raise ValidationError(_(
                    'Only one automatic asset category can use the same asset '
                    'account in a company.'))


class FlousflowAccountAssetGroup(models.Model):
    _name = 'flousflow.account.asset.group'
    _description = 'FlousFlow Asset Group'
    _parent_store = True
    _order = 'complete_name, id'
    _check_company_auto = True

    name = fields.Char(required=True, index=True)
    complete_name = fields.Char(
        compute='_compute_complete_name', store=True, recursive=True)
    parent_id = fields.Many2one(
        'flousflow.account.asset.group', string='Parent Group',
        index=True, ondelete='restrict', check_company=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        'flousflow.account.asset.group', 'parent_id', string='Child Groups')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(default=True)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for group in self:
            group.complete_name = (
                '%s / %s' % (group.parent_id.complete_name, group.name)
                if group.parent_id else group.name)

    @api.constrains('parent_id')
    def _check_parent_company(self):
        if self.filtered(
                lambda group: group.parent_id
                and group.parent_id.company_id != group.company_id):
            raise ValidationError(_('The parent asset group must belong to the same company.'))

class FlousflowAccountAsset(models.Model):
    _name = 'flousflow.account.asset'
    _description = 'FlousFlow Asset'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _order = 'date desc, id desc'
    _check_company_auto = True

    name = fields.Char(string='Asset Name', required=True, tracking=True)
    code = fields.Char(string='Reference', size=32, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id)
    value = fields.Monetary(string='Gross Value', required=True, tracking=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Company Currency')
    company_value = fields.Monetary(
        string='Historical Company Value', currency_field='company_currency_id',
        compute='_compute_company_value', store=True, readonly=True)
    salvage_value = fields.Monetary(
        string='Salvage Value', default=0.0,
        help="Amount that is not depreciated and remains at the end.")
    date = fields.Date(
        string='Purchase Date', required=True,
        default=fields.Date.context_today, tracking=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Running'), ('paused', 'Paused'),
         ('close', 'Closed'), ('cancelled', 'Cancelled')],
        string='Status', required=True, default='draft', copy=False, tracking=True)
    active = fields.Boolean(default=True)
    source_move_line_id = fields.Many2one(
        'account.move.line', string='Source Vendor Bill Line', copy=False,
        check_company=True, ondelete='restrict',
        domain="[('move_id.move_type', '=', 'in_invoice'), ('move_id.state', '=', 'posted')]" )
    source_move_id = fields.Many2one(
        'account.move', related='source_move_line_id.move_id',
        string='Source Vendor Bill', store=True, readonly=True)
    partner_id = fields.Many2one(
        'res.partner', related='source_move_id.partner_id',
        string='Vendor', store=True, readonly=True)

    category_id = fields.Many2one(
        'flousflow.account.asset.category', string='Model', required=True,
        change_default=True, tracking=True, check_company=True)
    group_id = fields.Many2one(
        'flousflow.account.asset.group', string='Asset Group',
        check_company=True)
    recognition_type = fields.Selection(
        related='category_id.recognition_type', store=True, readonly=True)
    method = fields.Selection(
        [('linear', 'Straight Line'), ('degressive', 'Declining Balance'),
         ('degressive_then_linear', 'Declining then Straight Line')],
        string='Computation Method', required=True, default='linear')
    method_number = fields.Integer(string='Number of Depreciations', default=5)
    method_period = fields.Integer(string='Period Length (Months)', default=12, required=True)
    method_progress_factor = fields.Float(string='Declining Factor', default=0.3)
    prorata = fields.Boolean(string='Prorata Temporis', default=False)
    prorata_computation_type = fields.Selection(
        [('none', 'No Prorata'),
         ('constant_periods', 'Constant Periods'),
         ('daily_computation', 'Based on Days per Period')],
        string='Computation', required=True, default='none')

    value_residual = fields.Monetary(
        compute='_compute_value_residual', string='Residual Value',
        store=False)
    depreciation_line_ids = fields.One2many(
        'flousflow.account.asset.depreciation.line', 'asset_id',
        string='Depreciation Lines')
    modification_ids = fields.One2many(
        'flousflow.account.asset.modification', 'asset_id',
        string='Modifications', readonly=True)
    disposal_ids = fields.One2many(
        'flousflow.account.asset.disposal', 'asset_id',
        string='Disposals', readonly=True)
    disposal_move_id = fields.Many2one(
        'account.move', string='Disposal Entry', readonly=True, copy=False,
        check_company=True)
    disposal_reversal_move_id = fields.Many2one(
        'account.move', string='Disposal Reversal', readonly=True, copy=False,
        check_company=True)
    disposal_source_move_line_id = fields.Many2one(
        'account.move.line', string='Asset Sale Invoice Line', readonly=True,
        copy=False, check_company=True, ondelete='restrict')
    disposal_source_move_id = fields.Many2one(
        related='disposal_source_move_line_id.move_id',
        string='Asset Sale Invoice', store=True, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        source_ids = [vals.get('source_move_line_id') for vals in vals_list
                      if vals.get('source_move_line_id')]
        duplicates = self.search([('source_move_line_id', 'in', source_ids)])
        if duplicates:
            raise ValidationError(_(
                'An asset already exists for one of the selected vendor bill lines.'))
        if len(source_ids) != len(set(source_ids)):
            raise ValidationError(_(
                'A vendor bill line can only create one asset.'))
        for incoming in vals_list:
            vals = dict(incoming)
            category = self.env['flousflow.account.asset.category'].browse(
                vals.get('category_id')).exists()
            if category:
                vals.setdefault('company_id', category.company_id.id)
                vals.setdefault('group_id', category.group_id.id)
                vals.setdefault('method', category.method)
                vals.setdefault('method_number', category.method_number)
                vals.setdefault('method_period', category.method_period)
                vals.setdefault(
                    'method_progress_factor', category.method_progress_factor)
                vals.setdefault('prorata', category.prorata)
                vals.setdefault(
                    'prorata_computation_type',
                    category.prorata_computation_type
                    if category.prorata_computation_type != 'none'
                    else ('daily_computation' if category.prorata else 'none'))
            source = self.env['account.move.line'].browse(
                vals.get('source_move_line_id')).exists()
            if source:
                if source.move_id.move_type != 'in_invoice' or source.move_id.state != 'posted':
                    raise ValidationError(_(
                        'Assets can only be created from posted vendor bill lines.'))
                vals.setdefault('company_id', source.company_id.id)
                vals.setdefault('name', source.name or source.move_id.name)
                vals.setdefault('date', source.move_id.invoice_date or source.date)
                vals.setdefault('currency_id', source.currency_id.id)
                vals.setdefault('analytic_distribution', source.analytic_distribution)
                amount = (
                    abs(source.amount_currency)
                    if source.currency_id != source.company_currency_id
                    else abs(source.balance))
                vals.setdefault('value', amount)
            prepared.append(vals)
        assets = super().create(prepared)
        assets.source_move_id.invalidate_recordset([
            'flousflow_asset_ids', 'flousflow_asset_count'])
        return assets

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.category_id:
            self.method = self.category_id.method
            self.method_number = self.category_id.method_number
            self.method_period = self.category_id.method_period
            self.method_progress_factor = self.category_id.method_progress_factor
            self.prorata = self.category_id.prorata
            self.prorata_computation_type = (
                self.category_id.prorata_computation_type
                if self.category_id.prorata_computation_type != 'none'
                else ('daily_computation' if self.category_id.prorata else 'none'))
            self.group_id = self.category_id.group_id

    @api.depends(
        'value', 'currency_id', 'company_id.currency_id', 'date',
        'source_move_line_id.balance', 'disposal_ids.company_gross_value',
        'disposal_ids.asset_gross_value', 'disposal_ids.reversal_move_id.state')
    def _compute_company_value(self):
        for asset in self:
            active_disposals = asset.disposal_ids.filtered(
                lambda disposal: disposal.reversal_move_id.state != 'posted')
            if asset.source_move_line_id:
                acquisition_value = abs(asset.source_move_line_id.balance)
            elif asset.currency_id and asset.company_id and asset.date:
                original_asset_value = asset.value + sum(
                    active_disposals.mapped('asset_gross_value'))
                acquisition_value = asset.currency_id._convert(
                    original_asset_value, asset.company_id.currency_id,
                    asset.company_id, asset.date)
            else:
                acquisition_value = asset.value
            asset.company_value = acquisition_value - sum(
                active_disposals.mapped('company_gross_value'))

    @api.depends(
        'value', 'salvage_value', 'depreciation_line_ids.amount',
        'depreciation_line_ids.move_id.state',
        'depreciation_line_ids.reversal_move_id.state',
        'disposal_ids.asset_accumulated_value',
        'disposal_ids.reversal_move_id.state')
    def _compute_value_residual(self):
        for asset in self:
            posted = sum(asset.depreciation_line_ids.filtered(
                lambda line: line.move_id.state == 'posted'
                and line.reversal_move_id.state != 'posted'
            ).mapped('amount'))
            disposed_depreciation = sum(asset.disposal_ids.filtered(
                lambda disposal: disposal.reversal_move_id.state != 'posted'
            ).mapped('asset_accumulated_value'))
            asset.value_residual = asset.value - posted + disposed_depreciation

    @api.constrains('value', 'salvage_value')
    def _check_values(self):
        for asset in self:
            if asset.value < 0:
                raise ValidationError(_('Gross value cannot be negative.'))
            if asset.salvage_value < 0 or asset.salvage_value > asset.value:
                raise ValidationError(
                    _('Salvage value must be between 0 and the gross value.'))

    def unlink(self):
        for asset in self:
            if asset.state != 'draft':
                raise UserError(_('You can only delete draft assets.'))
        return super().unlink()

    # ------------------------------------------------------------------
    # Depreciation board
    # ------------------------------------------------------------------
    def compute_depreciation_board(self):
        """(Re)build the depreciation lines for the asset."""
        for asset in self:
            if asset.state != 'draft':
                raise UserError(_('Depreciation board can only be recomputed while the asset is draft.'))
            asset.depreciation_line_ids.unlink()
            asset._build_depreciation_lines()

    def _rebuild_future_lines(self, start_date, remaining_periods):
        self.ensure_one()
        future = self.depreciation_line_ids.filtered(lambda line: not line.move_id)
        future.unlink()
        posted_amount = sum(self.depreciation_line_ids.filtered(
            lambda line: line.move_id.state == 'posted'
            and line.reversal_move_id.state != 'posted').mapped('amount'))
        posted_amount -= sum(self.disposal_ids.filtered(
            lambda disposal: disposal.reversal_move_id.state != 'posted'
        ).mapped('asset_accumulated_value'))
        remaining_amount = self.value - self.salvage_value - posted_amount
        if remaining_amount < 0:
            raise ValidationError(_(
                'The revised salvage value exceeds the remaining depreciable value.'))
        if not remaining_periods or self.currency_id.is_zero(remaining_amount):
            return
        sequence = max(self.depreciation_line_ids.mapped('sequence') or [0])
        allocated = 0.0
        for index in range(remaining_periods):
            if index == remaining_periods - 1:
                amount = remaining_amount - allocated
            elif self.method == 'degressive':
                residual = remaining_amount - allocated
                amount = min(
                    residual * self.method_progress_factor,
                    residual / (remaining_periods - index))
            elif self.method == 'degressive_then_linear':
                residual = remaining_amount - allocated
                amount = max(
                    residual * self.method_progress_factor,
                    residual / (remaining_periods - index))
            else:
                amount = remaining_amount / remaining_periods
            amount = self.currency_id.round(amount)
            allocated += amount
            self.env['flousflow.account.asset.depreciation.line'].create({
                'asset_id': self.id,
                'sequence': sequence + index + 1,
                'date': start_date + relativedelta(
                    months=self.method_period * (index + 1)),
                'amount': amount,
            })

    def _build_depreciation_lines(self):
        self.ensure_one()
        depreciable = self.value - self.salvage_value
        if depreciable <= 0:
            return
        number = self.method_number
        period_months = self.method_period
        base_amount = depreciable / number
        first_date = self._first_depreciation_date(period_months)

        daily_prorata = (
            self.prorata_computation_type == 'daily_computation' or self.prorata)
        line_count = number + 1 if daily_prorata else number
        for i in range(line_count):
            residual = depreciable - sum(self.depreciation_line_ids.mapped('amount'))
            remaining_periods = line_count - i
            if self.method == 'linear':
                amount = base_amount
                if daily_prorata and i == 0:
                    amount = base_amount * self._first_period_fraction(period_months)
                elif daily_prorata and i == line_count - 1:
                    amount = residual
            elif self.method == 'degressive_then_linear':
                if i == line_count - 1:
                    amount = residual
                else:
                    amount = max(
                        residual * self.method_progress_factor,
                        residual / remaining_periods)
            else:  # declining balance
                if i == line_count - 1:
                    amount = residual
                else:
                    amount = min(
                        residual * self.method_progress_factor,
                        residual / remaining_periods)
            if daily_prorata and i == 0 and self.method != 'linear':
                amount *= self._first_period_fraction(period_months)
            # Last line absorbs rounding difference
            if i == line_count - 1:
                amount = residual
            self.env['flousflow.account.asset.depreciation.line'].create({
                'asset_id': self.id,
                'sequence': i + 1,
                'date': first_date + relativedelta(months=period_months * i),
                'amount': round(amount, 2),
            })

    def _first_depreciation_date(self, period_months):
        """First depreciation date = last day of the purchase period (aligned to
        calendar year for yearly periods, calendar month for monthly periods)."""
        d = self.date
        if period_months % 12 == 0 and period_months >= 12:
            return date(d.year, 12, 31)
        if period_months == 1:
            return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        return d + relativedelta(months=period_months)

    def _first_period_fraction(self, period_months):
        """Fraction of the first depreciation period remaining from the purchase
        date (prorata temporis)."""
        period_end = self._first_depreciation_date(period_months)
        period_start = period_end - relativedelta(months=period_months)
        period_days = (period_end - period_start).days or 1
        remaining = (period_end - self.date).days + 1
        return max(0.0, min(1.0, remaining / period_days))

    # ------------------------------------------------------------------
    # State actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        for asset in self:
            if asset.state != 'draft':
                continue
            if not asset.depreciation_line_ids:
                asset._build_depreciation_lines()
            asset.state = 'open'

    def action_close(self):
        for asset in self:
            if asset.state not in ('open', 'paused'):
                raise UserError(_('Only running or paused assets can be closed.'))
            if any(not line.move_id for line in asset.depreciation_line_ids):
                raise UserError(
                    _('You cannot close an asset with unposted depreciation lines.'))
            asset.state = 'close'

    def action_pause(self):
        for asset in self:
            if asset.state != 'open':
                raise UserError(_('Only running assets can be paused.'))
            asset.state = 'paused'
        return True

    def action_resume(self):
        for asset in self:
            if asset.state != 'paused':
                raise UserError(_('Only paused assets can be resumed.'))
            asset.state = 'open'
        return True

    def action_cancel(self):
        """Cancel recognition and reverse every posted entry without deleting it."""
        today = fields.Date.context_today(self)
        for asset in self:
            if asset.state == 'cancelled':
                continue
            for line in asset.depreciation_line_ids.filtered(
                    lambda item: item.move_id.state == 'posted'
                    and not item.reversal_move_id):
                reversal = line.move_id._reverse_moves([{
                    'date': today,
                    'ref': _('Reversal: %s') % (line.move_id.ref or asset.name),
                }], cancel=True)
                line.reversal_move_id = reversal.id
            asset.state = 'cancelled'
        return True

    def action_open_disposal_wizard(self):
        self.ensure_one()
        if self.state not in ('open', 'paused'):
            raise UserError(_('Only running or paused assets can be disposed.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dispose Asset'),
            'res_model': 'flousflow.account.asset.disposal.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_asset_id': self.id},
        }

    def action_open_modify_wizard(self):
        self.ensure_one()
        if self.state not in ('open', 'paused'):
            raise UserError(_('Only running or paused assets can be modified.'))
        remaining = len(self.depreciation_line_ids.filtered(lambda line: not line.move_id))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Modify Asset'),
            'res_model': 'flousflow.account.asset.modify.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_asset_id': self.id,
                'default_remaining_periods': remaining,
                'default_new_salvage_value': self.salvage_value,
            },
        }

    def action_reverse_disposal(self):
        today = fields.Date.context_today(self)
        for asset in self:
            disposal = asset.disposal_ids.filtered(
                lambda item: item.reversal_move_id.state != 'posted'
            ).sorted('date', reverse=True)[:1]
            if not disposal:
                raise UserError(_('There is no active disposal entry to reverse.'))
            reversal = disposal.move_id._reverse_moves([{
                'date': today,
                'ref': _('Reversal: %s') % disposal.move_id.ref,
            }], cancel=True)
            disposal.reversal_move_id = reversal.id
            if disposal.percentage < 100:
                remaining_periods = len(asset.depreciation_line_ids.filtered(
                    lambda line: not line.move_id))
                asset.value += disposal.asset_gross_value
                asset.salvage_value += disposal.asset_salvage_value
                if remaining_periods:
                    asset._rebuild_future_lines(today, remaining_periods)
            asset.write({
                'disposal_reversal_move_id': reversal.id,
                'state': 'open',
            })
        return True

    # ------------------------------------------------------------------
    # Posting depreciation
    # ------------------------------------------------------------------
    def _create_depreciation_move(self, line):
        self.ensure_one()
        cat = self.category_id
        company_currency = self.company_id.currency_id
        company_amount = self.currency_id._convert(
            line.amount, company_currency, self.company_id, line.date)
        foreign_currency_values = {}
        if self.currency_id != company_currency:
            foreign_currency_values['currency_id'] = self.currency_id.id
        if cat.recognition_type == 'revenue':
            debit_account = cat.deferred_revenue_account_id
            credit_account = cat.revenue_account_id
            label = _('Revenue Recognition: %s') % self.name
        elif cat.recognition_type == 'expense':
            debit_account = cat.expense_account_id
            credit_account = cat.asset_account_id
            label = _('Expense Recognition: %s') % self.name
        else:
            debit_account = cat.expense_account_id
            credit_account = cat.depreciation_account_id
            label = _('Depreciation: %s') % self.name
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': line.date,
            'journal_id': cat.journal_id.id,
            'company_id': self.company_id.id,
            'ref': label,
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'debit': company_amount,
                    'credit': 0.0,
                    'amount_currency': line.amount,
                    'name': label,
                    'analytic_distribution': self.analytic_distribution,
                    **foreign_currency_values,
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': company_amount,
                    'amount_currency': -line.amount,
                    'name': label,
                    **foreign_currency_values,
                }),
            ],
        })
        move.action_post()
        return move

    def post_depreciation_lines(self):
        """Post all unposted depreciation lines whose date is due."""
        for asset in self:
            if asset.state != 'open':
                raise UserError(_('Only running assets can post depreciation.'))
            due = asset.depreciation_line_ids.filtered(
                lambda l: not l.move_id and l.date <= fields.Date.context_today(self))
            if not due:
                continue
            for line in due:
                move = asset._create_depreciation_move(line)
                line.move_id = move.id
            # auto-close when fully posted
            if all(l.move_id for l in asset.depreciation_line_ids):
                asset.state = 'close'
        return True


class FlousflowAssetDepreciationLine(models.Model):
    _name = 'flousflow.account.asset.depreciation.line'
    _description = 'FlousFlow Asset Depreciation Line'
    _order = 'sequence, id'

    asset_id = fields.Many2one(
        'flousflow.account.asset', string='Asset',
        required=True, ondelete='cascade', readonly=True)
    sequence = fields.Integer(string='Sequence')
    date = fields.Date(string='Depreciation Date', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False)
    reversal_move_id = fields.Many2one(
        'account.move', string='Reversal Entry', readonly=True, copy=False)
    move_check = fields.Boolean(
        compute='_compute_move_check', string='Posted', store=False)

    currency_id = fields.Many2one(related='asset_id.currency_id')
    company_id = fields.Many2one(related='asset_id.company_id', store=True)

    @api.depends('move_id.state', 'reversal_move_id.state')
    def _compute_move_check(self):
        for line in self:
            line.move_check = (
                line.move_id.state == 'posted'
                and line.reversal_move_id.state != 'posted')

    def unlink(self):
        for line in self:
            if line.move_id:
                raise UserError(_('You cannot delete a posted depreciation line.'))
        return super().unlink()


class AccountMove(models.Model):
    _inherit = 'account.move'

    flousflow_asset_ids = fields.Many2many(
        'flousflow.account.asset', compute='_compute_flousflow_assets',
        string='FlousFlow Assets')
    flousflow_asset_count = fields.Integer(compute='_compute_flousflow_assets')

    def action_post(self):
        result = super().action_post()
        vendor_bills = self.filtered(
            lambda move: move.move_type == 'in_invoice' and move.state == 'posted')
        if not vendor_bills:
            return result
        categories = self.env['flousflow.account.asset.category'].search([
            ('company_id', 'in', vendor_bills.company_id.ids),
            ('recognition_type', '=', 'asset'),
            ('auto_create_asset', '!=', 'no'),
            ('asset_account_id', '!=', False),
        ])
        category_by_key = {
            (category.company_id.id, category.asset_account_id.id): category
            for category in categories
        }
        existing_source_ids = set(self.env['flousflow.account.asset'].search([
            ('source_move_id', 'in', vendor_bills.ids),
        ]).source_move_line_id.ids)
        values = []
        modes = []
        for line in vendor_bills.invoice_line_ids.filtered(
                lambda item: item.display_type == 'product'
                and item.id not in existing_source_ids):
            category = category_by_key.get((line.company_id.id, line.account_id.id))
            if category:
                values.append({
                    'category_id': category.id,
                    'source_move_line_id': line.id,
                })
                modes.append(category.auto_create_asset)
        if values:
            assets = self.env['flousflow.account.asset'].create(values)
            for asset, mode in zip(assets, modes):
                if mode == 'validate':
                    asset.action_confirm()
        return result

    @api.depends('invoice_line_ids')
    def _compute_flousflow_assets(self):
        assets = self.env['flousflow.account.asset'].search([
            ('source_move_id', 'in', self.ids),
        ]) if self.ids else self.env['flousflow.account.asset']
        for move in self:
            linked = assets.filtered(lambda asset: asset.source_move_id == move)
            move.flousflow_asset_ids = linked
            move.flousflow_asset_count = len(linked)

    def action_open_flousflow_assets(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assets'),
            'res_model': 'flousflow.account.asset',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.flousflow_asset_ids.ids)],
            'context': {'default_company_id': self.company_id.id},
        }

    def action_create_flousflow_assets(self):
        self.ensure_one()
        if self.move_type != 'in_invoice' or self.state != 'posted':
            raise UserError(_('Assets can only be created from posted vendor bills.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Assets'),
            'res_model': 'flousflow.account.asset.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
                'active_model': self._name,
                'active_id': self.id,
            },
        }


class FlousflowAssetCreateWizard(models.TransientModel):
    _name = 'flousflow.account.asset.create.wizard'
    _description = 'Create Assets from Vendor Bill'
    _check_company_auto = True

    move_id = fields.Many2one(
        'account.move', required=True, readonly=True, check_company=True)
    company_id = fields.Many2one(related='move_id.company_id')
    category_id = fields.Many2one(
        'flousflow.account.asset.category', required=True, check_company=True,
        domain="[('company_id', '=', company_id), ('recognition_type', '=', 'asset')]")
    line_ids = fields.Many2many(
        'account.move.line', string='Vendor Bill Lines', required=True,
        domain="[('move_id', '=', move_id), ('display_type', '=', 'product')]",
        check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('move_id', self.env.context.get('active_id'))
        return super().create(vals_list)

    def action_create_assets(self):
        self.ensure_one()
        if self.move_id.move_type != 'in_invoice' or self.move_id.state != 'posted':
            raise ValidationError(_(
                'Assets can only be created from posted vendor bills.'))
        if any(line.move_id != self.move_id for line in self.line_ids):
            raise ValidationError(_('Every selected line must belong to this vendor bill.'))
        assets = self.env['flousflow.account.asset'].create([{
            'category_id': self.category_id.id,
            'source_move_line_id': line.id,
        } for line in self.line_ids])
        return {
            'type': 'ir.actions.act_window',
            'name': _('Assets'),
            'res_model': 'flousflow.account.asset',
            'view_mode': 'list,form',
            'domain': [('id', 'in', assets.ids)],
            'res_ids': assets.ids,
        }


class FlousflowAssetModification(models.Model):
    _name = 'flousflow.account.asset.modification'
    _description = 'Asset Schedule Modification'
    _order = 'date desc, id desc'
    _check_company_auto = True

    asset_id = fields.Many2one(
        'flousflow.account.asset', required=True, ondelete='restrict',
        check_company=True, index=True)
    company_id = fields.Many2one(related='asset_id.company_id', store=True)
    currency_id = fields.Many2one(related='asset_id.currency_id')
    date = fields.Date(required=True, index=True)
    reason = fields.Char(required=True)
    old_salvage_value = fields.Monetary(readonly=True)
    new_salvage_value = fields.Monetary(readonly=True)
    old_remaining_periods = fields.Integer(readonly=True)
    new_remaining_periods = fields.Integer(readonly=True)
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        ondelete='restrict')


class FlousflowAssetModifyWizard(models.TransientModel):
    _name = 'flousflow.account.asset.modify.wizard'
    _description = 'Modify Asset Schedule'
    _check_company_auto = True

    asset_id = fields.Many2one(
        'flousflow.account.asset', required=True, check_company=True)
    company_id = fields.Many2one(related='asset_id.company_id')
    currency_id = fields.Many2one(related='asset_id.currency_id')
    date = fields.Date(required=True, default=fields.Date.context_today)
    remaining_periods = fields.Integer(required=True)
    new_salvage_value = fields.Monetary(required=True)
    reason = fields.Char(required=True)

    @api.constrains('remaining_periods', 'new_salvage_value')
    def _check_values(self):
        for wizard in self:
            if wizard.remaining_periods <= 0:
                raise ValidationError(_('Remaining periods must be positive.'))
            if wizard.new_salvage_value < 0:
                raise ValidationError(_('Salvage value cannot be negative.'))

    def action_modify(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state not in ('open', 'paused'):
            raise ValidationError(_('Only running or paused assets can be modified.'))
        old_future = asset.depreciation_line_ids.filtered(lambda line: not line.move_id)
        old_remaining = len(old_future)
        posted_amount = sum(asset.depreciation_line_ids.filtered(
            lambda line: line.move_id.state == 'posted'
            and line.reversal_move_id.state != 'posted').mapped('amount'))
        if self.new_salvage_value > asset.value - posted_amount:
            raise ValidationError(_(
                'The revised salvage value exceeds the remaining asset value.'))
        self.env['flousflow.account.asset.modification'].create({
            'asset_id': asset.id,
            'date': self.date,
            'reason': self.reason,
            'old_salvage_value': asset.salvage_value,
            'new_salvage_value': self.new_salvage_value,
            'old_remaining_periods': old_remaining,
            'new_remaining_periods': self.remaining_periods,
        })
        asset.write({
            'salvage_value': self.new_salvage_value,
            'method_number': len(asset.depreciation_line_ids - old_future)
            + self.remaining_periods,
        })
        asset._rebuild_future_lines(self.date, self.remaining_periods)
        return {'type': 'ir.actions.act_window_close'}


class FlousflowAssetDisposal(models.Model):
    _name = 'flousflow.account.asset.disposal'
    _description = 'Asset Disposal History'
    _order = 'date desc, id desc'
    _check_company_auto = True

    asset_id = fields.Many2one(
        'flousflow.account.asset', required=True, ondelete='restrict',
        check_company=True, index=True)
    company_id = fields.Many2one(related='asset_id.company_id', store=True)
    currency_id = fields.Many2one(related='asset_id.currency_id')
    company_currency_id = fields.Many2one(related='asset_id.company_currency_id')
    date = fields.Date(required=True, index=True)
    reason = fields.Char(required=True)
    disposal_type = fields.Selection(
        [('scrap', 'Scrap'), ('sale', 'Sale')], required=True)
    percentage = fields.Float(required=True)
    asset_gross_value = fields.Monetary(readonly=True)
    asset_accumulated_value = fields.Monetary(readonly=True)
    asset_salvage_value = fields.Monetary(readonly=True)
    company_gross_value = fields.Monetary(
        currency_field='company_currency_id', readonly=True)
    company_accumulated_value = fields.Monetary(
        currency_field='company_currency_id', readonly=True)
    proceeds = fields.Monetary(
        currency_field='company_currency_id', readonly=True)
    move_id = fields.Many2one(
        'account.move', required=True, ondelete='restrict', check_company=True)
    reversal_move_id = fields.Many2one(
        'account.move', readonly=True, ondelete='restrict', check_company=True)
    sale_move_line_id = fields.Many2one(
        'account.move.line', readonly=True, ondelete='restrict', check_company=True)
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        ondelete='restrict')


class FlousflowAssetDisposalWizard(models.TransientModel):
    _name = 'flousflow.account.asset.disposal.wizard'
    _description = 'Dispose Asset'
    _check_company_auto = True

    asset_id = fields.Many2one(
        'flousflow.account.asset', required=True, check_company=True)
    company_id = fields.Many2one(related='asset_id.company_id')
    date = fields.Date(required=True, default=fields.Date.context_today)
    reason = fields.Char(required=True, default=lambda self: _('Scrapped'))
    disposal_type = fields.Selection(
        [('scrap', 'Scrap'), ('sale', 'Sale')], required=True, default='scrap')
    disposal_percentage = fields.Float(
        string='Disposal Percentage', required=True, default=100.0)
    sale_move_line_id = fields.Many2one(
        'account.move.line', string='Posted Customer Invoice Line',
        check_company=True,
        domain="[('move_id.move_type', '=', 'out_invoice'), ('move_id.state', '=', 'posted'), ('company_id', '=', company_id)]")

    @api.constrains('disposal_percentage')
    def _check_disposal_percentage(self):
        if any(
                wizard.disposal_percentage <= 0
                or wizard.disposal_percentage > 100
                for wizard in self):
            raise ValidationError(_('Disposal percentage must be above 0 and at most 100.'))

    def action_dispose(self):
        self.ensure_one()
        asset = self.asset_id
        if asset.state not in ('open', 'paused'):
            raise ValidationError(_('Only running or paused assets can be disposed.'))
        if asset.disposal_ids.filtered(
                lambda disposal: disposal.percentage == 100
                and disposal.reversal_move_id.state != 'posted'):
            raise ValidationError(_('This asset already has an active disposal entry.'))
        category = asset.category_id
        active_depreciations = asset.depreciation_line_ids.filtered(
            lambda line: line.move_id.state == 'posted'
            and line.reversal_move_id.state != 'posted'
        )
        accumulated_total = sum(active_depreciations.move_id.line_ids.filtered(
            lambda line: line.account_id == category.depreciation_account_id
        ).mapped('credit'))
        disposed_accumulated = sum(asset.disposal_ids.filtered(
            lambda disposal: disposal.reversal_move_id.state != 'posted'
        ).mapped('company_accumulated_value'))
        accumulated_available = accumulated_total - disposed_accumulated
        ratio = self.disposal_percentage / 100.0
        gross_value = asset.company_value * ratio
        accumulated = accumulated_available * ratio
        residual = gross_value - accumulated
        posted_asset_total = sum(active_depreciations.mapped('amount'))
        disposed_asset_accumulated = sum(asset.disposal_ids.filtered(
            lambda disposal: disposal.reversal_move_id.state != 'posted'
        ).mapped('asset_accumulated_value'))
        asset_accumulated = (
            posted_asset_total - disposed_asset_accumulated) * ratio
        asset_gross = asset.value * ratio
        asset_salvage = asset.salvage_value * ratio
        proceeds = 0.0
        sale_line = self.sale_move_line_id
        if self.disposal_type == 'sale':
            if not sale_line or sale_line.move_id.move_type != 'out_invoice' \
                    or sale_line.move_id.state != 'posted':
                raise ValidationError(_('Select a line from a posted customer invoice.'))
            if not category.disposal_clearing_account_id \
                    or not category.disposal_gain_account_id:
                raise ValidationError(_(
                    'Configure disposal clearing and gain accounts on the category.'))
            if sale_line.account_id != category.disposal_clearing_account_id:
                raise ValidationError(_(
                    'The customer invoice line must use the category disposal clearing account.'))
            if self.env['flousflow.account.asset.disposal'].search_count([
                    ('sale_move_line_id', '=', sale_line.id),
                    ('reversal_move_id', '=', False)]):
                raise ValidationError(_(
                    'This customer invoice line is already linked to another asset disposal.'))
            proceeds = abs(sale_line.balance)
        label = _('Asset Disposal: %s (%s)') % (asset.name, self.reason)
        lines = [{
            'account_id': category.asset_account_id.id,
            'credit': gross_value,
            'name': label,
        }]
        if accumulated:
            lines.append({
                'account_id': category.depreciation_account_id.id,
                'debit': accumulated,
                'name': label,
            })
        if proceeds:
            lines.append({
                'account_id': category.disposal_clearing_account_id.id,
                'debit': proceeds,
                'name': label,
            })
        difference = residual - proceeds
        if difference > 0:
            if not category.disposal_loss_account_id:
                raise ValidationError(_(
                    'Configure an asset disposal loss account on the asset category.'))
            lines.append({
                'account_id': category.disposal_loss_account_id.id,
                'debit': difference,
                'name': label,
            })
        elif difference < 0:
            lines.append({
                'account_id': category.disposal_gain_account_id.id,
                'credit': -difference,
                'name': label,
            })
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.date,
            'journal_id': category.journal_id.id,
            'company_id': asset.company_id.id,
            'ref': label,
            'line_ids': [(0, 0, values) for values in lines],
        })
        move.action_post()
        disposal = self.env['flousflow.account.asset.disposal'].create({
            'asset_id': asset.id,
            'date': self.date,
            'reason': self.reason,
            'disposal_type': self.disposal_type,
            'percentage': self.disposal_percentage,
            'asset_gross_value': asset_gross,
            'asset_accumulated_value': asset_accumulated,
            'asset_salvage_value': asset_salvage,
            'company_gross_value': gross_value,
            'company_accumulated_value': accumulated,
            'proceeds': proceeds,
            'move_id': move.id,
            'sale_move_line_id': sale_line.id,
        })
        if self.disposal_percentage < 100:
            remaining_periods = len(asset.depreciation_line_ids.filtered(
                lambda line: not line.move_id))
            asset.value -= asset_gross
            asset.salvage_value -= asset_salvage
            if remaining_periods:
                asset._rebuild_future_lines(self.date, remaining_periods)
        asset.write({
            'disposal_move_id': move.id,
            'disposal_reversal_move_id': False,
            'disposal_source_move_line_id': sale_line.id,
            'state': 'close' if self.disposal_percentage == 100 else asset.state,
        })
        return {'type': 'ir.actions.act_window_close'}
