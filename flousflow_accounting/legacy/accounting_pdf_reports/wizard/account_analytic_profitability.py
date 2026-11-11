from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountAnalyticProfitability(models.TransientModel):
    _name = 'account.analytic.profitability'
    _description = 'Analytic Profitability Report'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string='From',
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
    )
    date_to = fields.Date(
        string='To',
        required=True,
        default=fields.Date.context_today,
    )
    analytic_plan_id = fields.Many2one(
        'account.analytic.plan',
        string='Analytic Plan',
    )
    analytic_account_ids = fields.Many2many(
        'account.analytic.account',
        string='Analytic Accounts',
    )
    posted_only = fields.Boolean(string='Posted Entries Only', default=True)
    line_ids = fields.One2many(
        'account.analytic.profitability.line',
        'report_id',
        string='Profitability by Analytic Account',
    )
    movement_count = fields.Integer(compute='_compute_totals')
    total_revenue = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_cogs = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_operating_expenses = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_other_income = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_other_expenses = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    total_net_profit = fields.Monetary(compute='_compute_totals', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)

    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        for report in self:
            if report.date_from and report.date_to and report.date_from > report.date_to:
                raise ValidationError(_('The start date must be before or equal to the end date.'))

    @api.depends('line_ids', 'line_ids.revenue', 'line_ids.cogs',
                 'line_ids.operating_expenses', 'line_ids.other_income',
                 'line_ids.other_expenses', 'line_ids.movement_count')
    def _compute_totals(self):
        for report in self:
            report.movement_count = sum(report.line_ids.mapped('movement_count'))
            report.total_revenue = sum(report.line_ids.mapped('revenue'))
            report.total_cogs = sum(report.line_ids.mapped('cogs'))
            report.total_operating_expenses = sum(report.line_ids.mapped('operating_expenses'))
            report.total_other_income = sum(report.line_ids.mapped('other_income'))
            report.total_other_expenses = sum(report.line_ids.mapped('other_expenses'))
            report.total_net_profit = sum(report.line_ids.mapped('net_profit'))

    def _analytic_line_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.posted_only:
            domain.append(('move_line_id.move_id.state', '=', 'posted'))
        if self.analytic_plan_id:
            domain.append(('account_id.plan_id', '=', self.analytic_plan_id.id))
        if self.analytic_account_ids:
            domain.append(('account_id', 'in', self.analytic_account_ids.ids))
        return domain

    @api.model
    def _classify_amount(self, line):
        amount = line.amount
        account_type = line.general_account_id.account_type or ''
        if account_type == 'income':
            return {'revenue': amount}
        if account_type.startswith('income'):
            return {'other_income': amount}
        if account_type == 'expense_direct_cost':
            return {'cogs': -amount}
        if account_type.startswith('expense'):
            return {'operating_expenses': -amount}
        # Balance-sheet analytic lines (inventory, receivable, payable, cash,
        # and similar accounts) are deliberately excluded from a P&L report.
        # They may carry analytic distributions for auditability, but must not
        # inflate income or expenses.
        return {}

    def _populate_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        grouped = {}
        analytic_lines = self.env['account.analytic.line'].search(self._analytic_line_domain())
        for line in analytic_lines:
            classified = self._classify_amount(line)
            if not classified:
                continue
            key = line.account_id.id
            values = grouped.setdefault(key, {
                'analytic_account_id': key,
                'movement_count': 0,
                'revenue': 0.0,
                'cogs': 0.0,
                'operating_expenses': 0.0,
                'other_income': 0.0,
                'other_expenses': 0.0,
            })
            values['movement_count'] += 1
            for field, amount in classified.items():
                values[field] += amount
        for values in grouped.values():
            values['net_profit'] = (
                values['revenue']
                + values['other_income']
                - values['cogs']
                - values['operating_expenses']
                - values['other_expenses']
            )
            values['margin_percent'] = (
                values['net_profit'] / values['revenue']
                if values['revenue'] else 0.0
            )
            values['report_id'] = self.id
        if grouped:
            self.env['account.analytic.profitability.line'].create(list(grouped.values()))
        return analytic_lines

    def action_generate(self):
        self.ensure_one()
        self._populate_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Analytic Profitability'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_print(self):
        self.ensure_one()
        self._populate_lines()
        return self.env.ref(
            'flousflow_accounting.apr__action_report_analytic_profitability'
        ).report_action(self, config=False)

    def action_view_movements(self):
        self.ensure_one()
        action = self.env.ref('analytic.account_analytic_line_action_entries').read()[0]
        action['name'] = _('Analytic Movements')
        action['domain'] = self._analytic_line_domain()
        action['context'] = {
            'search_default_group_by_analytic_account': 1,
            'search_default_profit_loss_accounts': 1,
        }
        return action


class AccountAnalyticProfitabilityLine(models.TransientModel):
    _name = 'account.analytic.profitability.line'
    _description = 'Analytic Profitability Report Line'
    _order = 'analytic_account_id'

    report_id = fields.Many2one(
        'account.analytic.profitability',
        required=True,
        ondelete='cascade',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        required=True,
        readonly=True,
    )
    movement_count = fields.Integer(string='Movements', readonly=True)
    revenue = fields.Monetary(string='Revenue', readonly=True, currency_field='currency_id')
    cogs = fields.Monetary(string='Cost of Goods Sold', readonly=True, currency_field='currency_id')
    operating_expenses = fields.Monetary(string='Operating Expenses', readonly=True, currency_field='currency_id')
    other_income = fields.Monetary(string='Other Income', readonly=True, currency_field='currency_id')
    other_expenses = fields.Monetary(string='Other Expenses', readonly=True, currency_field='currency_id')
    net_profit = fields.Monetary(string='Net Profit', readonly=True, currency_field='currency_id')
    margin_percent = fields.Float(string='Margin %', readonly=True)
    currency_id = fields.Many2one(related='report_id.currency_id', readonly=True)
