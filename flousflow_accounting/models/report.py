# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
import io

from dateutil.relativedelta import relativedelta
import xlsxwriter

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class FlousflowAccountReport(models.TransientModel):
    _name = 'flousflow.account.report'
    _description = 'FlousFlow Financial Report'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    report_type = fields.Selection(
        [('profit_loss', 'Profit & Loss'),
         ('balance_sheet', 'Balance Sheet'),
         ('cash_flow', 'Cash Flow Statement'),
         ('trial_balance', 'Trial Balance'),
         ('general_ledger', 'General Ledger'),
         ('journal_audit', 'Journal Audit'),
         ('tax_report', 'Tax Report'),
         ('partner_ledger', 'Partner Ledger'),
         ('customer_statement', 'Customer Statement'),
         ('vendor_statement', 'Vendor Statement'),
         ('account_statement', 'Account Statement'),
         ('executive_summary', 'Executive Summary'),
         ('annual_report', 'Annual Report'),
         ('aged_receivable', 'Aged Receivable'),
         ('aged_payable', 'Aged Payable')],
        string='Report', required=True, default='profit_loss')
    line_ids = fields.One2many(
        'flousflow.account.report.line', 'report_id', string='Lines', readonly=True)
    visible_line_ids = fields.One2many(
        'flousflow.account.report.line', 'report_id',
        string='Visible Lines', compute='_compute_visible_line_ids')
    comparison_mode = fields.Selection(
        [('none', 'No Comparison'),
         ('previous_period', 'Previous Period'),
         ('previous_year', 'Same Period Last Year'),
         ('custom_date', 'Custom Date')],
        string='Comparison', default='none', required=True)
    comparison_date = fields.Date(string='Comparison Date')
    date_filter = fields.Selection(
        [('current_month', 'This Month'),
         ('current_quarter', 'This Quarter'),
         ('current_year', 'This Year'),
         ('custom', 'Custom Period')],
        string='Period', default='current_year', required=True)
    display_mode = fields.Selection(
        [('expanded', 'Expanded'), ('collapsed', 'Collapsed')],
        string='Details', default='expanded', required=True)
    target_move = fields.Selection(
        [('posted', 'Posted Entries Only'), ('all', 'All Entries')],
        string='Entries', default='posted', required=True)
    journal_ids = fields.Many2many(
        'account.journal', string='Journals', check_company=True)
    account_ids = fields.Many2many(
        'account.account', string='Accounts', check_company=True)
    partner_ids = fields.Many2many('res.partner', string='Partners')
    preset_id = fields.Many2one(
        'flousflow.account.report.preset', string='Saved Filter',
        domain="[('company_id', '=', company_id), ('report_type', '=', report_type)]")
    preset_name = fields.Char(string='Save Filter As')
    report_note = fields.Text(
        string='Report Notes',
        help='Internal explanation, review conclusion, or assumptions printed with this report.')
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency', readonly=True)

    @api.depends('report_type')
    def _compute_display_name(self):
        """Use the business report title in breadcrumbs instead of the model name."""
        labels = dict(self._fields['report_type']._description_selection(self.env))
        for report in self:
            report.display_name = labels.get(
                report.report_type, _('Financial Report'))

    @api.depends('line_ids', 'line_ids.move_id', 'display_mode')
    def _compute_visible_line_ids(self):
        for report in self:
            report.visible_line_ids = (
                report.line_ids.filtered(lambda line: not line.move_id)
                if report.display_mode == 'collapsed'
                else report.line_ids
            )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for report in self:
            if report.date_from and report.date_to and report.date_from > report.date_to:
                raise ValidationError(_('Start date must be before end date.'))

    @api.onchange('date_filter')
    def _onchange_date_filter(self):
        today = fields.Date.today()
        for report in self:
            if report.date_filter == 'current_month':
                report.date_from = today.replace(day=1)
                report.date_to = today
            elif report.date_filter == 'current_quarter':
                quarter_month = ((today.month - 1) // 3) * 3 + 1
                report.date_from = today.replace(month=quarter_month, day=1)
                report.date_to = today
            elif report.date_filter == 'current_year':
                report.date_from = today.replace(month=1, day=1)
                report.date_to = today

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.today()
        if not res.get('date_from'):
            res['date_from'] = today.replace(month=1, day=1)
        if not res.get('date_to'):
            res['date_to'] = today
        if res.get('report_type') == 'annual_report':
            company = self.env['res.company'].browse(
                res.get('company_id') or self.env.company.id)
            fiscal_year = company.compute_fiscalyear_dates(today)
            res.update({
                'date_from': fiscal_year['date_from'],
                'date_to': fiscal_year['date_to'],
                'date_filter': 'custom',
                'comparison_mode': 'previous_year',
            })
        return res

    def _base_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        return domain + self._option_domain()

    def _option_domain(self):
        self.ensure_one()
        domain = []
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))
        if self.account_ids:
            domain.append(('account_id', 'in', self.account_ids.ids))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        return domain

    def _generate_from_template(self, code, date_from=None):
        """Render a declarative report template into self.line_ids."""
        self.ensure_one()
        template = self.env['flousflow.account.report.template'].search(
            [('code', '=', code)], limit=1)
        if not template:
            return
        rows = template._compute_lines(
            self.company_id,
            self.date_from if date_from is None else date_from,
            self.date_to,
            extra_domain=self._option_domain(),
            target_move=self.target_move)
        vals = []
        for seq, row in enumerate(rows, start=1):
            vals.append((0, 0, {
                'sequence': seq,
                'name': ('    ' * row['level']) + row['name'],
                'code': row['code'],
                'balance': row['amount'],
                'level': row['level'],
                'is_total': row['is_total'],
                'is_section': row['is_section'],
            }))
        self.line_ids = vals

    def action_generate(self):
        self.ensure_one()
        self.line_ids = [(5, 0, 0)]
        if self.report_type == 'profit_loss':
            self._generate_profit_loss()
        elif self.report_type == 'balance_sheet':
            self._generate_balance_sheet()
        elif self.report_type == 'general_ledger':
            self._generate_general_ledger()
        elif self.report_type == 'trial_balance':
            self._generate_trial_balance()
        elif self.report_type == 'journal_audit':
            self._generate_journal_audit()
        elif self.report_type == 'cash_flow':
            self._generate_cash_flow()
        elif self.report_type == 'tax_report':
            self._generate_tax_report()
        elif self.report_type == 'partner_ledger':
            self._generate_partner_ledger()
        elif self.report_type == 'customer_statement':
            self._generate_partner_statement('asset_receivable')
        elif self.report_type == 'vendor_statement':
            self._generate_partner_statement('liability_payable')
        elif self.report_type == 'account_statement':
            self._generate_account_statement()
        elif self.report_type == 'executive_summary':
            self._generate_executive_summary()
        elif self.report_type == 'annual_report':
            self._generate_annual_report()
        elif self.report_type == 'aged_receivable':
            self._generate_aged(receivable=True)
        elif self.report_type == 'aged_payable':
            self._generate_aged(receivable=False)
        if self.comparison_mode != 'none':
            self._apply_comparison()
        statement_types = ('customer_statement', 'vendor_statement')
        view = self.env.ref(
            'flousflow_accounting.flousflow_partner_statement_view_form'
            if self.report_type in statement_types
            else 'flousflow_accounting.flousflow_account_report_view_form')
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view.id,
            'views': [(view.id, 'form')],
            'target': 'current',
        }

    @api.model
    def get_interactive_report_data(
            self, report_type, date_to, date_from=None, target_move='posted',
            comparison_mode='none', company_id=None, comparison_date=None,
            date_filter='custom'):
        """Generate a read-only report payload for the OWL statement screen."""
        supported_types = {
            'balance_sheet', 'profit_loss', 'cash_flow', 'trial_balance',
            'general_ledger',
        }
        if report_type not in supported_types:
            raise ValidationError(_('This report is not available in the interactive viewer.'))
        if target_move not in {'posted', 'all'}:
            raise ValidationError(_('Invalid journal entry status filter.'))
        if comparison_mode not in {
                'none', 'previous_year', 'previous_period', 'custom_date'}:
            raise ValidationError(_('Invalid comparison option.'))
        if date_filter not in {
                'current_month', 'current_quarter', 'current_year', 'custom'}:
            raise ValidationError(_('Invalid reporting period.'))

        try:
            date_to = fields.Date.to_date(date_to)
            date_from = fields.Date.to_date(date_from) if date_from else None
            comparison_date = (
                fields.Date.to_date(comparison_date) if comparison_date else None)
        except (TypeError, ValueError):
            raise ValidationError(_('Enter valid report dates.'))
        if not date_to:
            raise ValidationError(_('A report date is required.'))
        company = self.env['res.company'].browse(company_id or self.env.company.id).exists()
        if not company or company not in self.env.companies:
            raise AccessError(_('You cannot read accounting reports for this company.'))
        if date_filter == 'current_month':
            date_from = date_to.replace(day=1)
            date_to = date_to + relativedelta(day=31)
        elif date_filter == 'current_quarter':
            quarter_month = ((date_to.month - 1) // 3) * 3 + 1
            date_from = date_to.replace(month=quarter_month, day=1)
            date_to = date_from + relativedelta(months=3, days=-1)
        elif date_filter == 'current_year':
            fiscal_dates = company.compute_fiscalyear_dates(date_to)
            date_from = fiscal_dates['date_from']
            date_to = fiscal_dates['date_to']
        else:
            date_from = date_from or date_to.replace(month=1, day=1)
        if date_from > date_to:
            raise ValidationError(_('The start date must not be later than the report date.'))
        if comparison_mode == 'custom_date' and not comparison_date:
            raise ValidationError(_('Choose a date for the comparison.'))

        report = self.create({
            'company_id': company.id,
            'report_type': report_type,
            'date_from': date_from,
            'date_to': date_to,
            'comparison_mode': comparison_mode,
            'comparison_date': comparison_date,
            'date_filter': date_filter,
            'target_move': target_move,
        })
        report.action_generate()
        report_lines = report.line_ids.sorted(lambda line: (line.sequence, line.id))
        draft_count = self.env['account.move.line'].search_count([
            ('company_id', '=', company.id),
            ('date', '<=', date_to),
            ('parent_state', '=', 'draft'),
        ])
        arabic_labels = {
            'Revenue': 'الإيرادات', 'Operating Revenue': 'إيرادات التشغيل',
            'Other Revenue': 'إيرادات أخرى', 'Total Revenue': 'إجمالي الإيرادات',
            'Expenses': 'المصروفات', 'Cost of Revenue': 'تكلفة الإيرادات',
            'Operating Expenses': 'مصروفات التشغيل',
            'Depreciation & Amortization': 'الإهلاك والإطفاء',
            'Other Expenses': 'مصروفات أخرى', 'Total Expenses': 'إجمالي المصروفات',
            'Net Profit': 'صافي الربح', 'Assets': 'الأصول',
            'Current Assets': 'الأصول المتداولة', 'Bank & Cash': 'البنك والنقدية',
            'Receivables': 'الذمم المدينة', 'Prepayments': 'المدفوعات المقدمة',
            'Total Current Assets': 'إجمالي الأصول المتداولة',
            'Fixed Assets': 'الأصول الثابتة', 'Non-current Assets': 'الأصول غير المتداولة',
            'Total Fixed Assets': 'إجمالي الأصول الثابتة', 'Total Assets': 'إجمالي الأصول',
            'Liabilities': 'الخصوم', 'Current Liabilities': 'الخصوم المتداولة',
            'Payables': 'الذمم الدائنة', 'Credit Cards': 'بطاقات الائتمان',
            'Non-current Liabilities': 'الخصوم غير المتداولة',
            'Total Current Liabilities': 'إجمالي الخصوم المتداولة',
            'Total Liabilities': 'إجمالي الخصوم', 'Equity': 'حقوق الملكية',
            'Retained Earnings': 'الأرباح المحتجزة',
            'Current Year Income': 'دخل السنة الحالية',
            'Current Year Expenses': 'مصروفات السنة الحالية',
            'Current Year Earnings': 'أرباح السنة الحالية',
            'Total Equity': 'إجمالي حقوق الملكية',
            'Unallocated Profit / Loss': 'أرباح / خسائر غير موزعة',
        } if (self.env.lang or '').startswith('ar') else {}
        ui_arabic = {
            'Balance': 'الرصيد', 'Opening Balance': 'الرصيد الافتتاحي',
            'Debit': 'مدين', 'Credit': 'دائن', 'Closing Balance': 'الرصيد الختامي',
            'Date': 'التاريخ', 'Partner': 'الشريك', 'Currency': 'العملة',
            'Month': 'شهر', 'Quarter': 'ربع السنة', 'Fiscal Year': 'السنة المالية',
            'Custom Dates': 'تواريخ مخصصة', 'From': 'من', 'To': 'إلى', 'As of': 'كما في',
            'Search accounts or entries': 'ابحث في الحسابات أو القيود',
            'Posted Entries': 'القيود المُرحّلة', 'All Entries': 'كل القيود',
            'Compare': 'مقارنة', 'Comparison period': 'فترة المقارنة',
            'Comparison presentation': 'طريقة عرض المقارنة', 'No Comparison': 'بدون مقارنة',
            'Previous Period': 'الفترة السابقة', 'Same Period Last Year': 'نفس الفترة من العام الماضي',
            'Custom Date': 'تاريخ مخصص', 'Compare to': 'مقارنة مع',
            'Percentage': 'نسبة مئوية', 'Difference': 'الفرق',
            'Percentage Change': 'نسبة التغير', 'Print': 'طباعة',
            'PDF': 'PDF', 'XLSX': 'XLSX', 'Fold All': 'طي الكل', 'Unfold All': 'توسيع الكل',
        } if (self.env.lang or '').startswith('ar') else {}
        ui_label = lambda value: ui_arabic.get(value, self.env._(value))
        lines_payload = []
        for index, line in enumerate(report_lines):
            next_line = report_lines[index + 1:index + 2]
            line_name = (line.name or '').strip()
            if report_type in ('profit_loss', 'balance_sheet', 'cash_flow') and not line.account_id:
                line_name = arabic_labels.get(line_name, self.env._(line_name))
            lines_payload.append({
                'id': line.id,
                'code': line.code,
                'name': line_name,
                'label': (
                    '%s %s' % (line.code, line_name)
                    if report_type == 'trial_balance' and line.account_id
                    else line_name),
                'level': line.level,
                'is_section': line.is_section,
                'is_total': line.is_total,
                'balance': line.balance,
                'opening_balance': line.opening_balance,
                'debit': line.debit,
                'credit': line.credit,
                'closing_balance': line.closing_balance,
                'account_id': line.account_id.id,
                'date': fields.Date.to_string(line.date) if line.date else False,
                'partner_name': line.partner_id.display_name or False,
                'currency_name': line.currency_id.name or False,
                'move_name': line.move_name or False,
                'reference': line.reference or False,
                'running_balance': line.running_balance,
                'comparison_balance': line.comparison_balance,
                'has_amount': (
                    bool(line.account_id)
                    if report_type in ('trial_balance', 'general_ledger')
                    else not line.is_section),
                'has_children': bool(next_line and next_line.level > line.level),
            })
        return {
            'report_id': report.id,
            'report_type': report_type,
            'title': dict(self._fields['report_type']._description_selection(self.env)).get(report_type),
            'company_name': company.display_name,
            'currency_symbol': company.currency_id.symbol,
            'currency_position': company.currency_id.position,
            'ui_labels': {
                'balance': ui_label('Balance'), 'opening_balance': ui_label('Opening Balance'),
                'debit': ui_label('Debit'), 'credit': ui_label('Credit'),
                'closing_balance': ui_label('Closing Balance'), 'date': ui_label('Date'),
                'partner': ui_label('Partner'), 'currency': ui_label('Currency'),
                'month': ui_label('Month'), 'quarter': ui_label('Quarter'),
                'fiscal_year': ui_label('Fiscal Year'), 'custom_dates': ui_label('Custom Dates'),
                'from': ui_label('From'), 'to': ui_label('To'), 'as_of': ui_label('As of'),
                'search_ledger': ui_label('Search accounts or entries'),
                'posted_entries': ui_label('Posted Entries'), 'all_entries': ui_label('All Entries'),
                'compare': ui_label('Compare'), 'comparison_period': ui_label('Comparison period'),
                'comparison_presentation': ui_label('Comparison presentation'),
                'no_comparison': ui_label('No Comparison'), 'previous_period': ui_label('Previous Period'),
                'previous_year': ui_label('Same Period Last Year'), 'custom_date': ui_label('Custom Date'),
                'compare_to': ui_label('Compare to'), 'percentage': ui_label('Percentage'),
                'difference': ui_label('Difference'), 'percentage_change': ui_label('Percentage Change'),
                'print': ui_label('Print'), 'pdf': ui_label('PDF'), 'xlsx': ui_label('XLSX'),
                'fold_all': ui_label('Fold All'), 'unfold_all': ui_label('Unfold All'),
            },
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'comparison_mode': comparison_mode,
            'comparison_date': fields.Date.to_string(comparison_date) if comparison_date else False,
            'date_filter': date_filter,
            'draft_move_count': draft_count,
            'lines': lines_payload,
        }

    @api.model
    def get_interactive_drilldown_action(self, report_id, line_code, amount_type=None):
        """Open the account move lines that make up a statement row."""
        report = self.browse(report_id).exists()
        if not report:
            raise UserError(_('The report has expired. Refresh it and try again.'))
        report.ensure_one()
        if report.company_id not in self.env.companies:
            raise AccessError(_('You cannot read accounting reports for this company.'))

        move_id = False
        if report.report_type in ('trial_balance', 'general_ledger'):
            report_line = report.line_ids.filtered(
                lambda item: item.code == line_code and item.account_id)[:1]
            if (not report_line and report.report_type == 'general_ledger'
                    and str(line_code).isdigit()):
                report_line = report.line_ids.filtered(
                    lambda item: item.id == int(line_code) and item.account_id)[:1]
            if not report_line:
                raise UserError(_('This ledger row has no account-level drill-down.'))
            account_ids = report_line.account_id.ids
            account_types = set()
            move_id = report_line.move_id.id if report.report_type == 'general_ledger' else False
        else:
            template = self.env['flousflow.account.report.template'].search([
                ('code', '=', report.report_type),
                '|', ('company_id', '=', False), ('company_id', '=', report.company_id.id),
            ], limit=1)
            template_line = template.line_ids.filtered(lambda item: item.code == line_code)[:1]
            if not template_line:
                raise UserError(_('This statement row has no account-level drill-down.'))

            account_ids = set()
            account_types = set()
            seen = set()

            def collect(line):
                if line.id in seen:
                    return
                seen.add(line.id)
                if line.formula:
                    for token in line.formula.split():
                        referenced = template.line_ids.filtered(
                            lambda item, code=token.lstrip('+-'): item.code == code)[:1]
                        if referenced:
                            collect(referenced)
                elif line.account_ids or line.account_types:
                    account_ids.update(line.account_ids.ids)
                    account_types.update(
                        item.strip() for item in (line.account_types or '').split(',')
                        if item.strip())
                else:
                    for child in line.child_line_ids:
                        collect(child)

            collect(template_line)
        if not account_ids and not account_types:
            raise UserError(_('This statement row has no account-level drill-down.'))

        domain = [
            ('company_id', '=', report.company_id.id),
            ('date', '<=', report.date_to),
        ]
        if report.report_type in ('profit_loss', 'cash_flow', 'trial_balance'):
            domain.append(('date', '>=', report.date_from))
        elif report.report_type == 'general_ledger':
            domain.append(('date', '>=', report.date_from))
        if report.report_type == 'trial_balance' and amount_type == 'opening_balance':
            domain = [
                ('company_id', '=', report.company_id.id),
                ('date', '<', report.date_from),
            ]
        elif report.report_type == 'trial_balance' and amount_type == 'closing_balance':
            domain = [
                ('company_id', '=', report.company_id.id),
                ('date', '<=', report.date_to),
            ]
        if report.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        if move_id:
            domain.append(('move_id', '=', move_id))
        account_domain = []
        if account_ids and account_types:
            account_domain = ['|', ('account_id', 'in', sorted(account_ids)),
                              ('account_id.account_type', 'in', sorted(account_types))]
        elif account_ids:
            account_domain = [('account_id', 'in', sorted(account_ids))]
        else:
            account_domain = [('account_id.account_type', 'in', sorted(account_types))]
        action = self.env['ir.actions.actions']._for_xml_id(
            'account.action_account_moves_all_a')
        action['domain'] = domain + account_domain
        action['context'] = {'create': False}
        return action

    @api.model
    def get_interactive_export_action(self, report_id, export_format):
        report = self.browse(report_id).exists()
        if not report:
            raise UserError(_('The report has expired. Refresh it and try again.'))
        report.ensure_one()
        if report.company_id not in self.env.companies:
            raise AccessError(_('You cannot export accounting reports for this company.'))
        if export_format == 'pdf':
            return report.action_print()
        if export_format == 'xlsx':
            return report.action_export_xlsx()
        raise ValidationError(_('Unsupported report export format.'))

    def _generate_annual_report(self):
        """Combine the three core statements for the selected fiscal year."""
        self.ensure_one()
        sections = (
            (_('Profit & Loss'), self._generate_profit_loss),
            (_('Balance Sheet'), self._generate_balance_sheet),
            (_('Cash Flow Statement'), self._generate_cash_flow),
        )
        values = []
        sequence = 1
        for title, generator in sections:
            self.line_ids = [(5, 0, 0)]
            generator()
            values.append((0, 0, {
                'sequence': sequence,
                'name': title,
                'code': 'annual_%s' % sequence,
                'is_section': True,
            }))
            sequence += 1
            for line in self.line_ids:
                row = line.copy_data({'report_id': self.id})[0]
                row.update({
                    'sequence': sequence,
                    'name': ('    ' * (line.level + 1)) + (line.name or ''),
                    'level': line.level + 1,
                })
                values.append((0, 0, row))
                sequence += 1
        self.line_ids = [(5, 0, 0)] + values

    def action_unfold_all(self):
        self.ensure_one()
        self.display_mode = 'expanded'
        return self.action_generate()

    def action_fold_all(self):
        self.ensure_one()
        self.display_mode = 'collapsed'
        return self.action_generate()

    def action_save_preset(self):
        self.ensure_one()
        if not self.preset_name:
            raise UserError(_('Enter a name for the saved filter.'))
        values = {
            'name': self.preset_name,
            'user_id': self.env.user.id,
            'company_id': self.company_id.id,
            'report_type': self.report_type,
            'date_filter': self.date_filter,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'comparison_mode': self.comparison_mode,
            'comparison_date': self.comparison_date,
            'target_move': self.target_move,
            'display_mode': self.display_mode,
            'journal_ids': [(6, 0, self.journal_ids.ids)],
            'account_ids': [(6, 0, self.account_ids.ids)],
            'partner_ids': [(6, 0, self.partner_ids.ids)],
        }
        preset_model = self.env['flousflow.account.report.preset']
        preset = preset_model.search([
            ('name', '=', self.preset_name),
            ('user_id', '=', self.env.user.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if preset:
            preset.write(values)
        else:
            preset = preset_model.create(values)
        self.preset_id = preset
        self.preset_name = False
        return self.action_generate()

    def action_apply_preset(self):
        self.ensure_one()
        if not self.preset_id:
            raise UserError(_('Select a saved filter first.'))
        preset = self.preset_id
        self.write({
            'company_id': preset.company_id.id,
            'report_type': preset.report_type,
            'date_filter': preset.date_filter,
            'date_from': preset.date_from,
            'date_to': preset.date_to,
            'comparison_mode': preset.comparison_mode,
            'comparison_date': preset.comparison_date,
            'target_move': preset.target_move,
            'display_mode': preset.display_mode,
            'journal_ids': [(6, 0, preset.journal_ids.ids)],
            'account_ids': [(6, 0, preset.account_ids.ids)],
            'partner_ids': [(6, 0, preset.partner_ids.ids)],
        })
        if self.date_filter != 'custom':
            self._onchange_date_filter()
        return self.action_generate()

    def action_print(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Generate the report before printing it.'))
        return self.env.ref(
            'flousflow_accounting.action_report_financial_statement'
        ).report_action(self)

    def _line_comparison_key(self, line):
        return (
            line.account_id.id, line.partner_id.id, line.journal_id.id,
            line.tax_id.id, line.code or '', line.name or '')

    def _comparison_dates(self):
        self.ensure_one()
        if self.comparison_mode == 'previous_year':
            return (
                self.date_from - relativedelta(years=1),
                self.date_to - relativedelta(years=1),
            )
        period_days = (self.date_to - self.date_from).days + 1
        if self.comparison_mode == 'custom_date':
            if not self.comparison_date:
                raise ValidationError(_('Choose a date for the comparison.'))
            return (
                self.comparison_date - relativedelta(days=period_days - 1),
                self.comparison_date,
            )
        previous_to = self.date_from - relativedelta(days=1)
        return (
            previous_to - relativedelta(days=period_days - 1),
            previous_to,
        )

    def _apply_comparison(self):
        self.ensure_one()
        previous_from, previous_to = self._comparison_dates()
        previous = self.create({
            'company_id': self.company_id.id,
            'report_type': self.report_type,
            'date_from': previous_from,
            'date_to': previous_to,
            'comparison_mode': 'none',
            'target_move': self.target_move,
            'journal_ids': [(6, 0, self.journal_ids.ids)],
            'account_ids': [(6, 0, self.account_ids.ids)],
            'partner_ids': [(6, 0, self.partner_ids.ids)],
        })
        previous.action_generate()
        previous_by_key = {
            self._line_comparison_key(line): line.balance
            for line in previous.line_ids
        }
        for line in self.line_ids:
            comparison = previous_by_key.get(self._line_comparison_key(line), 0.0)
            line.comparison_balance = comparison
            line.variance = line.balance - comparison
        previous.unlink()

    def _apply_previous_period_comparison(self):
        """Backward-compatible entry point for existing custom integrations."""
        self.ensure_one()
        self.comparison_mode = 'previous_period'
        self._apply_comparison()

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Generate the report before exporting it.'))
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet(_('Financial Report')[:31])
        title_format = workbook.add_format({'bold': True, 'font_size': 14})
        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#714B67', 'font_color': '#FFFFFF'})
        money_format = workbook.add_format({'num_format': '#,##0.00;[Red]-#,##0.00'})
        percentage_format = workbook.add_format({'num_format': '0.00%'})
        worksheet.write(0, 0, dict(self._fields['report_type'].selection)[self.report_type], title_format)
        worksheet.write(1, 0, _('Company'))
        worksheet.write(1, 1, self.company_id.display_name)
        worksheet.write(2, 0, _('Period'))
        worksheet.write(2, 1, '%s - %s' % (self.date_from, self.date_to))
        if self.report_note:
            worksheet.write(3, 0, _('Report Notes'))
            worksheet.write(3, 1, self.report_note)
        detailed = self.report_type in (
            'general_ledger', 'partner_ledger', 'customer_statement',
            'vendor_statement', 'account_statement')
        if detailed:
            headers = [
                _('Date'), _('Entry'), _('Reference'), _('Partner'),
                _('Account'), _('Label'), _('Debit'), _('Credit'),
                _('Balance'), _('Running Balance')]
        elif self.report_type == 'tax_report':
            headers = [
                _('Tax'), _('Tax Base'), _('Debit'), _('Credit'), _('Balance')]
        else:
            headers = [
                _('Label'), _('Code'), _('Debit'), _('Credit'), _('Balance')]
        if self.comparison_mode != 'none':
            headers += [_('Comparison'), _('Variance'), _('Variance %')]
        for column, header in enumerate(headers):
            worksheet.write(4, column, header, header_format)
        for row, line in enumerate(self.line_ids, start=5):
            if detailed:
                worksheet.write(row, 0, str(line.date or ''))
                worksheet.write(row, 1, line.move_name or '')
                worksheet.write(row, 2, line.reference or '')
                worksheet.write(row, 3, line.partner_id.display_name or '')
                worksheet.write(row, 4, line.account_id.display_name or '')
                worksheet.write(row, 5, line.name or '')
                for column, amount in enumerate(
                        (line.debit, line.credit, line.balance,
                         line.running_balance), start=6):
                    worksheet.write_number(row, column, amount, money_format)
            else:
                worksheet.write(row, 0, line.name or '')
                if self.report_type == 'tax_report':
                    worksheet.write_number(
                        row, 1, line.tax_base_amount, money_format)
                else:
                    worksheet.write(row, 1, line.code or '')
                for column, amount in enumerate(
                        (line.debit, line.credit, line.balance), start=2):
                    worksheet.write_number(row, column, amount, money_format)
            if self.comparison_mode != 'none':
                comparison_column = 10 if detailed else 5
                worksheet.write_number(
                    row, comparison_column, line.comparison_balance, money_format)
                worksheet.write_number(
                    row, comparison_column + 1, line.variance, money_format)
                worksheet.write_number(
                    row, comparison_column + 2, line.variance_percent / 100.0,
                    percentage_format)
        worksheet.set_column(0, 0, 15 if detailed else 40)
        worksheet.set_column(1, 5 if detailed else 1, 22)
        worksheet.set_column(2, len(headers) - 1, 16)
        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': 'financial_report_%s_%s.xlsx' % (self.report_type, self.date_to),
            'type': 'binary',
            'raw': output.getvalue(),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def action_open_all_entries(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'account.action_account_moves_all_a')
        action['name'] = _('Report Journal Items')
        action['domain'] = self._base_domain()
        action['context'] = {'create': False}
        return action

    # ------------------------------------------------------------------
    # Profit & Loss (declarative engine)
    # ------------------------------------------------------------------
    def _generate_profit_loss(self):
        self._generate_from_template('profit_loss')

    # ------------------------------------------------------------------
    # Balance Sheet (declarative engine)
    # ------------------------------------------------------------------
    def _generate_balance_sheet(self):
        self._generate_from_template('balance_sheet', date_from=False)

    # ------------------------------------------------------------------
    # General Ledger
    # ------------------------------------------------------------------
    def _generate_general_ledger(self):
        move_lines = self.env['account.move.line'].search(
            self._base_domain(), order='account_id, date, move_id, id')
        values = []
        sequence = 1
        for account in move_lines.account_id.sorted(lambda item: item.code or ''):
            account_lines = move_lines.filtered(
                lambda item, current=account: item.account_id == current)
            opening = self._account_balance_before(account)
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s %s - Opening Balance', account.code, account.name),
                'code': account.code,
                'account_id': account.id,
                'balance': opening,
                'running_balance': opening,
                'is_section': True,
                'level': 0,
            }))
            sequence += 1
            running = opening
            for line in account_lines:
                running += line.balance
                values.append((0, 0, {
                    'sequence': sequence,
                    'name': line.name or line.move_name,
                    'date': line.date,
                    'maturity_date': line.date_maturity,
                    'move_id': line.move_id.id,
                    'move_name': line.move_name,
                    'reference': line.ref,
                    'account_id': account.id,
                    'partner_id': line.partner_id.id,
                    'journal_id': line.journal_id.id,
                    'currency_id': line.currency_id.id,
                    'amount_currency': line.amount_currency,
                    'debit': line.debit,
                    'credit': line.credit,
                    'balance': line.balance,
                    'running_balance': running,
                    'level': 1,
                }))
                sequence += 1
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s %s - Total', account.code, account.name),
                'code': account.code,
                'account_id': account.id,
                'debit': sum(account_lines.mapped('debit')),
                'credit': sum(account_lines.mapped('credit')),
                'balance': sum(account_lines.mapped('balance')),
                'running_balance': running,
                'is_total': True,
                'level': 1,
            }))
            sequence += 1
        self.line_ids = values

    def _generate_trial_balance(self):
        opening_groups = self.env['account.move.line']._read_group([
            ('company_id', '=', self.company_id.id),
            ('date', '<', self.date_from),
        ] + ([('parent_state', '=', 'posted')]
             if self.target_move == 'posted' else [])
        + self._option_domain(),
        groupby=['account_id'], aggregates=['balance:sum'])
        period_groups = self.env['account.move.line']._read_group(
            self._base_domain(), groupby=['account_id'],
            aggregates=['debit:sum', 'credit:sum', 'balance:sum'])
        values_by_account = {}
        for account, opening in opening_groups:
            if account:
                values_by_account[account.id] = {
                    'account': account,
                    'opening': opening or 0.0,
                    'debit': 0.0,
                    'credit': 0.0,
                    'movement': 0.0,
                }
        for account, debit, credit, movement in period_groups:
            if not account:
                continue
            values = values_by_account.setdefault(account.id, {
                'account': account,
                'opening': 0.0,
                'debit': 0.0,
                'credit': 0.0,
                'movement': 0.0,
            })
            values.update({
                'debit': debit or 0.0,
                'credit': credit or 0.0,
                'movement': movement or 0.0,
            })
        self.line_ids = [(0, 0, {
            'sequence': sequence,
            'name': values['account'].name,
            'code': values['account'].code,
            'account_id': values['account'].id,
            'opening_balance': values['opening'],
            'debit': values['debit'],
            'credit': values['credit'],
            'balance': values['movement'],
            'closing_balance': values['opening'] + values['movement'],
        }) for sequence, values in enumerate(
            sorted(values_by_account.values(), key=lambda item: item['account'].code),
            start=1)] + [(0, 0, {
                'sequence': len(values_by_account) + 1,
                'name': _('Total'),
                'code': 'total_trial_balance',
                'is_total': True,
                'opening_balance': sum(item['opening'] for item in values_by_account.values()),
                'debit': sum(item['debit'] for item in values_by_account.values()),
                'credit': sum(item['credit'] for item in values_by_account.values()),
                'balance': sum(item['movement'] for item in values_by_account.values()),
                'closing_balance': sum(
                    item['opening'] + item['movement']
                    for item in values_by_account.values()),
            })]

    def _generate_journal_audit(self):
        groups = self.env['account.move.line']._read_group(
            self._base_domain(),
            groupby=['journal_id'],
            aggregates=['debit:sum', 'credit:sum', 'balance:sum'],
        )
        self.line_ids = [(0, 0, {
            'sequence': sequence,
            'name': journal.display_name,
            'code': journal.code,
            'journal_id': journal.id,
            'debit': debit or 0.0,
            'credit': credit or 0.0,
            'balance': balance or 0.0,
        }) for sequence, (journal, debit, credit, balance) in enumerate(groups, start=1)
            if journal]

    def _generate_cash_flow(self):
        cash_types = ('asset_cash',)
        investing_types = ('asset_fixed', 'asset_non_current')
        financing_types = ('equity', 'equity_unaffected', 'liability_non_current')
        moves = self.env['account.move'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('line_ids.account_id.account_type', 'in', cash_types),
        ] + ([('state', '=', 'posted')] if self.target_move == 'posted' else [])
        + ([('journal_id', 'in', self.journal_ids.ids)] if self.journal_ids else []))
        totals = {'operating': 0.0, 'investing': 0.0, 'financing': 0.0}
        cash_flow_tags = {
            'operating': self.env.ref(
                'account.account_tag_operating', raise_if_not_found=False),
            'investing': self.env.ref(
                'account.account_tag_investing', raise_if_not_found=False),
            'financing': self.env.ref(
                'account.account_tag_financing', raise_if_not_found=False),
        }
        for move in moves:
            cash_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type in cash_types
            )
            cash_change = sum(cash_lines.mapped('balance'))
            counterpart_lines = move.line_ids - cash_lines
            counterpart_types = set(counterpart_lines.filtered(
                lambda line: line.account_id.account_type not in cash_types
            ).mapped('account_id.account_type'))
            counterpart_tags = counterpart_lines.account_id.tag_ids
            # The standard chart assigns cash-flow tags to counterpart
            # accounts. Respect those explicit classifications before falling
            # back to account types for charts that do not use the tags.
            if cash_flow_tags['investing'] in counterpart_tags:
                bucket = 'investing'
            elif cash_flow_tags['financing'] in counterpart_tags:
                bucket = 'financing'
            elif cash_flow_tags['operating'] in counterpart_tags:
                bucket = 'operating'
            elif counterpart_types.intersection(investing_types):
                bucket = 'investing'
            elif counterpart_types.intersection(financing_types):
                bucket = 'financing'
            else:
                bucket = 'operating'
            totals[bucket] += cash_change
        labels = {
            'operating': _('Operating Activities'),
            'investing': _('Investing Activities'),
            'financing': _('Financing Activities'),
        }
        cash_domain = [
            ('company_id', '=', self.company_id.id),
            ('account_id.account_type', 'in', cash_types),
        ]
        if self.target_move == 'posted':
            cash_domain.append(('parent_state', '=', 'posted'))
        if self.journal_ids:
            cash_domain.append(('journal_id', 'in', self.journal_ids.ids))
        opening_group = self.env['account.move.line']._read_group(
            cash_domain + [('date', '<', self.date_from)],
            aggregates=['balance:sum'])
        closing_group = self.env['account.move.line']._read_group(
            cash_domain + [('date', '<=', self.date_to)],
            aggregates=['balance:sum'])
        opening_cash = opening_group[0][0] if opening_group else 0.0
        closing_cash = closing_group[0][0] if closing_group else 0.0
        vals = [(0, 0, {
            'sequence': 1,
            'name': _('Opening Cash and Cash Equivalents'),
            'code': 'opening_cash',
            'balance': opening_cash or 0.0,
            'is_section': True,
        })]
        vals += [(0, 0, {
            'sequence': sequence + 1,
            'name': labels[code],
            'code': code,
            'balance': totals[code],
        }) for sequence, code in enumerate(('operating', 'investing', 'financing'), start=1)]
        vals.append((0, 0, {
            'sequence': 5,
            'name': _('Net Increase (Decrease) in Cash'),
            'code': 'net_cash_flow',
            'balance': sum(totals.values()),
            'is_total': True,
        }))
        vals.append((0, 0, {
            'sequence': 6,
            'name': _('Closing Cash and Cash Equivalents'),
            'code': 'closing_cash',
            'balance': closing_cash or 0.0,
            'is_total': True,
        }))
        self.line_ids = vals

    def _generate_tax_report(self):
        groups = self.env['account.move.line']._read_group(
            self._base_domain() + [('tax_line_id', '!=', False)],
            groupby=['tax_line_id'],
            aggregates=['tax_base_amount:sum', 'debit:sum', 'credit:sum'],
        )
        self.line_ids = [(0, 0, {
            'sequence': sequence,
            'name': tax.display_name,
            'tax_id': tax.id,
            # Align the base with the report's tax sign convention:
            # sales (credit tax) are positive, purchases (debit tax) negative.
            'tax_base_amount': -(tax_base_amount or 0.0),
            'debit': debit or 0.0,
            'credit': credit or 0.0,
            'balance': (credit or 0.0) - (debit or 0.0),
        }) for sequence, (tax, tax_base_amount, debit, credit) in enumerate(
            groups, start=1)
            if tax]

    # ------------------------------------------------------------------
    # Partner Ledger
    # ------------------------------------------------------------------
    def _partner_balance_before(self, partner, date_from):
        groups = self.env['account.move.line']._read_group(
            [('company_id', '=', self.company_id.id),
             ('date', '<', date_from),
             ('partner_id', '=', partner.id),
             ('account_id.account_type', 'in',
              ['asset_receivable', 'liability_payable'])]
            + ([('parent_state', '=', 'posted')]
               if self.target_move == 'posted' else [])
            + self._option_domain(),
            aggregates=['debit:sum', 'credit:sum'])
        if groups and groups[0]:
            debit, credit = groups[0]
            return (debit or 0.0) - (credit or 0.0)
        return 0.0

    def _generate_partner_ledger(self):
        account_types = ['asset_receivable', 'liability_payable']
        period_lines = self.env['account.move.line'].search(
            self._base_domain() + [
                ('account_id.account_type', 'in', account_types),
                ('partner_id', '!=', False),
            ], order='partner_id, date, move_id, id')
        opening_groups = self.env['account.move.line']._read_group([
            ('company_id', '=', self.company_id.id),
            ('date', '<', self.date_from),
            ('account_id.account_type', 'in', account_types),
            ('partner_id', '!=', False),
        ] + ([('parent_state', '=', 'posted')]
             if self.target_move == 'posted' else [])
        + self._option_domain(),
            groupby=['partner_id'], aggregates=['balance:sum'])
        opening_by_partner = {
            partner.id: opening or 0.0
            for partner, opening in opening_groups if partner
        }
        partners = (period_lines.partner_id | self.env['res.partner'].browse(
            opening_by_partner)).sorted(lambda partner: partner.name or '')
        values = []
        sequence = 1
        for partner in partners:
            opening = opening_by_partner.get(partner.id, 0.0)
            partner_lines = period_lines.filtered(
                lambda line, current=partner: line.partner_id == current)
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s - Opening Balance', partner.display_name),
                'partner_id': partner.id,
                'balance': opening,
                'running_balance': opening,
                'is_section': True,
            }))
            sequence += 1
            running = opening
            for line in partner_lines:
                running += line.balance
                values.append((0, 0, {
                    'sequence': sequence,
                    'name': line.name or line.move_name,
                    'date': line.date,
                    'maturity_date': line.date_maturity,
                    'move_id': line.move_id.id,
                    'move_name': line.move_name,
                    'reference': line.ref,
                    'account_id': line.account_id.id,
                    'partner_id': partner.id,
                    'journal_id': line.journal_id.id,
                    'currency_id': line.currency_id.id,
                    'amount_currency': line.amount_currency,
                    'debit': line.debit,
                    'credit': line.credit,
                    'balance': line.balance,
                    'running_balance': running,
                }))
                sequence += 1
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s - Total', partner.display_name),
                'partner_id': partner.id,
                'debit': sum(partner_lines.mapped('debit')),
                'credit': sum(partner_lines.mapped('credit')),
                'balance': running,
                'running_balance': running,
                'is_total': True,
            }))
            sequence += 1
        self.line_ids = values

    def _statement_move_domain(self, account_type=None):
        domain = self._base_domain()
        if account_type:
            domain.append(('account_id.account_type', '=', account_type))
        return domain

    def _generate_partner_statement(self, account_type):
        if not self.partner_ids:
            raise UserError(_('Select at least one partner for a partner statement.'))
        lines = self.env['account.move.line'].search(
            self._statement_move_domain(account_type),
            order='partner_id, date, move_id, id')
        values = []
        sequence = 1
        for partner in self.partner_ids.sorted(lambda item: item.name or ''):
            opening = self._partner_balance_before(partner, self.date_from)
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s - Opening Balance', partner.display_name),
                'partner_id': partner.id,
                'balance': opening,
                'running_balance': opening,
                'is_section': True,
            }))
            sequence += 1
            running = opening
            partner_lines = lines.filtered(lambda item: item.partner_id == partner)
            for line in partner_lines:
                running += line.balance
                values.append((0, 0, {
                    'sequence': sequence,
                    'name': line.name or line.move_name,
                    'date': line.date,
                    'maturity_date': line.date_maturity,
                    'move_id': line.move_id.id,
                    'move_name': line.move_name,
                    'reference': line.ref,
                    'account_id': line.account_id.id,
                    'partner_id': partner.id,
                    'journal_id': line.journal_id.id,
                    'currency_id': line.currency_id.id,
                    'amount_currency': line.amount_currency,
                    'debit': line.debit,
                    'credit': line.credit,
                    'balance': line.balance,
                    'running_balance': running,
                }))
                sequence += 1
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s - Total', partner.display_name),
                'partner_id': partner.id,
                'debit': sum(partner_lines.mapped('debit')),
                'credit': sum(partner_lines.mapped('credit')),
                'balance': running,
                'running_balance': running,
                'is_total': True,
            }))
            sequence += 1
        self.line_ids = values

    def _account_balance_before(self, account):
        groups = self.env['account.move.line']._read_group([
            ('company_id', '=', self.company_id.id),
            ('account_id', '=', account.id),
            ('date', '<', self.date_from),
        ] + ([('parent_state', '=', 'posted')]
             if self.target_move == 'posted' else [])
        + self._option_domain(),
            aggregates=['balance:sum'])
        return (groups[0][0] or 0.0) if groups else 0.0

    def _generate_account_statement(self):
        if not self.account_ids:
            raise UserError(_('Select at least one account for an account statement.'))
        lines = self.env['account.move.line'].search(
            self._base_domain(), order='account_id, date, move_id, id')
        values = []
        sequence = 1
        for account in self.account_ids.sorted(lambda item: item.code or ''):
            opening = self._account_balance_before(account)
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s %s - Opening Balance', account.code, account.name),
                'account_id': account.id,
                'balance': opening,
                'running_balance': opening,
                'is_section': True,
            }))
            sequence += 1
            running = opening
            account_lines = lines.filtered(lambda item: item.account_id == account)
            for line in account_lines:
                running += line.balance
                values.append((0, 0, {
                    'sequence': sequence,
                    'name': line.name or line.move_name,
                    'date': line.date,
                    'maturity_date': line.date_maturity,
                    'move_id': line.move_id.id,
                    'move_name': line.move_name,
                    'reference': line.ref,
                    'account_id': account.id,
                    'partner_id': line.partner_id.id,
                    'journal_id': line.journal_id.id,
                    'currency_id': line.currency_id.id,
                    'amount_currency': line.amount_currency,
                    'debit': line.debit,
                    'credit': line.credit,
                    'balance': line.balance,
                    'running_balance': running,
                }))
                sequence += 1
            values.append((0, 0, {
                'sequence': sequence,
                'name': _('%s %s - Total', account.code, account.name),
                'account_id': account.id,
                'debit': sum(account_lines.mapped('debit')),
                'credit': sum(account_lines.mapped('credit')),
                'balance': running,
                'running_balance': running,
                'is_total': True,
            }))
            sequence += 1
        self.line_ids = values

    def _balance_by_types(self, account_types, cumulative=False):
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date', '<=', self.date_to),
            ('account_id.account_type', 'in', account_types),
        ]
        if not cumulative:
            domain.append(('date', '>=', self.date_from))
        if self.target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        groups = self.env['account.move.line']._read_group(
            domain + self._option_domain(), aggregates=['balance:sum'])
        return (groups[0][0] or 0.0) if groups else 0.0

    def _generate_executive_summary(self):
        receivables = self._balance_by_types(['asset_receivable'], cumulative=True)
        payables = -self._balance_by_types(['liability_payable'], cumulative=True)
        cash = self._balance_by_types(['asset_cash'], cumulative=True)
        revenue = -self._balance_by_types(['income', 'income_other'])
        expenses = self._balance_by_types([
            'expense', 'expense_direct_cost', 'expense_depreciation', 'expense_other'])
        rows = [
            (_('Cash and Bank'), 'cash', cash),
            (_('Receivables'), 'receivables', receivables),
            (_('Payables'), 'payables', payables),
            (_('Revenue'), 'revenue', revenue),
            (_('Expenses'), 'expenses', expenses),
            (_('Net Profit'), 'net_profit', revenue - expenses),
        ]
        self.line_ids = [(0, 0, {
            'sequence': sequence,
            'name': name,
            'code': code,
            'balance': amount,
            'is_total': code == 'net_profit',
        }) for sequence, (name, code, amount) in enumerate(rows, 1)]

    # ------------------------------------------------------------------
    # Aged Receivable / Payable
    # ------------------------------------------------------------------
    def _residual_at_date(self, line):
        """Company-currency residual reconstructed at the report cutoff."""
        self.ensure_one()
        matched_credit = sum(line.matched_credit_ids.filtered(
            lambda partial: partial.max_date <= self.date_to
        ).mapped('amount'))
        matched_debit = sum(line.matched_debit_ids.filtered(
            lambda partial: partial.max_date <= self.date_to
        ).mapped('amount'))
        return line.balance - matched_credit + matched_debit

    def _generate_aged(self, receivable=True):
        account_types = ['asset_receivable'] if receivable else ['liability_payable']
        lines = self.env['account.move.line'].search(
            [('company_id', '=', self.company_id.id),
             ('date', '<=', self.date_to),
                ('account_id.account_type', 'in', account_types),
             ('partner_id', '!=', False),
            ] + ([('parent_state', '=', 'posted')]
                 if self.target_move == 'posted' else [])
            + self._option_domain())
        today = self.date_to
        buckets = {
            'current': 0.0,
            '1_30': 0.0,
            '31_60': 0.0,
            '61_90': 0.0,
            '90_plus': 0.0,
        }
        partners = {}
        for line in lines:
            residual = self._residual_at_date(line)
            if self.company_id.currency_id.is_zero(residual):
                continue
            pid = line.partner_id.id
            data = partners.setdefault(pid, {'partner': line.partner_id, **buckets.copy()})
            maturity = line.date_maturity or line.date
            days = (today - maturity).days
            if days <= 0:
                key = 'current'
            elif days <= 30:
                key = '1_30'
            elif days <= 60:
                key = '31_60'
            elif days <= 90:
                key = '61_90'
            else:
                key = '90_plus'
            data[key] += residual if receivable else -residual

        vals = []
        for seq, (pid, data) in enumerate(sorted(partners.items(), key=lambda x: x[1]['partner'].name or ''), start=1):
            vals.append((0, 0, {
                'sequence': seq,
                'name': data['partner'].name,
                'partner_id': pid,
                'bucket_current': data['current'],
                'bucket_1_30': data['1_30'],
                'bucket_31_60': data['31_60'],
                'bucket_61_90': data['61_90'],
                'bucket_90_plus': data['90_plus'],
                'balance': sum((data['current'], data['1_30'], data['31_60'],
                                data['61_90'], data['90_plus'])),
            }))
        self.line_ids = vals


class FlousflowAccountReportPreset(models.Model):
    _name = 'flousflow.account.report.preset'
    _description = 'FlousFlow Financial Report Saved Filter'
    _order = 'name, id'

    name = fields.Char(required=True)
    user_id = fields.Many2one(
        'res.users', required=True, default=lambda self: self.env.user,
        ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade')
    report_type = fields.Selection(
        [('profit_loss', 'Profit & Loss'),
         ('balance_sheet', 'Balance Sheet'),
         ('cash_flow', 'Cash Flow Statement'),
         ('trial_balance', 'Trial Balance'),
         ('general_ledger', 'General Ledger'),
         ('journal_audit', 'Journal Audit'),
         ('tax_report', 'Tax Report'),
         ('partner_ledger', 'Partner Ledger'),
         ('customer_statement', 'Customer Statement'),
         ('vendor_statement', 'Vendor Statement'),
         ('account_statement', 'Account Statement'),
         ('executive_summary', 'Executive Summary'),
         ('aged_receivable', 'Aged Receivable'),
         ('aged_payable', 'Aged Payable')],
        required=True)
    date_filter = fields.Selection(
        [('current_month', 'This Month'),
         ('current_quarter', 'This Quarter'),
         ('current_year', 'This Year'),
         ('custom', 'Custom Period')],
        required=True, default='current_year')
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    comparison_mode = fields.Selection(
        [('none', 'No Comparison'),
         ('previous_period', 'Previous Period'),
         ('previous_year', 'Same Period Last Year'),
         ('custom_date', 'Custom Date')],
        required=True, default='none')
    comparison_date = fields.Date(string='Comparison Date')
    target_move = fields.Selection(
        [('posted', 'Posted Entries Only'), ('all', 'All Entries')],
        required=True, default='posted')
    display_mode = fields.Selection(
        [('expanded', 'Expanded'), ('collapsed', 'Collapsed')],
        required=True, default='expanded')
    journal_ids = fields.Many2many(
        'account.journal', string='Journals', check_company=True)
    account_ids = fields.Many2many(
        'account.account', string='Accounts', check_company=True)
    partner_ids = fields.Many2many('res.partner', string='Partners')

    _name_user_company_uniq = models.Constraint(
        'unique (name, user_id, company_id)',
        'Saved filter names must be unique per user and company.')

    @api.model_create_multi
    def create(self, vals_list):
        """Keep personal report filters personal outside the web form too."""
        for values in vals_list:
            owner_id = values.get('user_id', self.env.user.id)
            if owner_id != self.env.user.id:
                raise AccessError(
                    _('You can only create saved report filters for yourself.'))
        return super().create(vals_list)

    def write(self, values):
        if 'user_id' in values and values['user_id'] != self.env.user.id:
            raise AccessError(
                _('You cannot transfer a saved report filter to another user.'))
        return super().write(values)

    @api.constrains('user_id', 'company_id')
    def _check_user_company(self):
        for preset in self:
            if preset.company_id not in preset.user_id.company_ids:
                raise ValidationError(
                    _('The saved filter company must be allowed for its owner.'))


class FlousflowAccountReportLine(models.TransientModel):
    _name = 'flousflow.account.report.line'
    _description = 'FlousFlow Financial Report Line'
    _order = 'sequence, id'

    report_id = fields.Many2one(
        'flousflow.account.report', string='Report', ondelete='cascade', readonly=True)
    sequence = fields.Integer(string='Sequence')
    name = fields.Char(string='Label')
    code = fields.Char(string='Code')
    account_id = fields.Many2one('account.account', string='Account')
    partner_id = fields.Many2one('res.partner', string='Partner')
    journal_id = fields.Many2one('account.journal', string='Journal')
    move_id = fields.Many2one('account.move', string='Journal Entry')
    date = fields.Date(string='Date')
    maturity_date = fields.Date(string='Due Date')
    move_name = fields.Char(string='Entry Number')
    reference = fields.Char(string='Reference')
    currency_id = fields.Many2one('res.currency', string='Currency')
    amount_currency = fields.Monetary(string='Amount in Currency', currency_field='currency_id')
    tax_id = fields.Many2one('account.tax', string='Tax')
    tax_base_amount = fields.Float(string='Tax Base')
    is_total = fields.Boolean(string='Is Total')
    is_section = fields.Boolean(string='Is Section')
    level = fields.Integer(string='Level')
    debit = fields.Float(string='Debit')
    credit = fields.Float(string='Credit')
    balance = fields.Float(string='Balance')
    opening_balance = fields.Float(string='Opening Balance')
    closing_balance = fields.Float(string='Closing Balance')
    bucket_current = fields.Float(string='Current')
    bucket_1_30 = fields.Float(string='1 - 30')
    bucket_31_60 = fields.Float(string='31 - 60')
    bucket_61_90 = fields.Float(string='61 - 90')
    bucket_90_plus = fields.Float(string='90+')
    comparison_balance = fields.Float(string='Comparison')
    variance = fields.Float(string='Variance')
    variance_percent = fields.Float(
        string='Variance %', compute='_compute_variance_percent')
    running_balance = fields.Float(string='Running Balance')

    @api.depends('comparison_balance', 'variance')
    def _compute_variance_percent(self):
        for line in self:
            line.variance_percent = (
                line.variance / abs(line.comparison_balance) * 100.0
                if line.comparison_balance else 0.0
            )

    def action_open_entries(self):
        self.ensure_one()
        report = self.report_id
        if report.report_type in ('aged_receivable', 'aged_payable'):
            account_type = (
                'asset_receivable' if report.report_type == 'aged_receivable'
                else 'liability_payable')
            domain = [
                ('company_id', '=', report.company_id.id),
                ('date', '<=', report.date_to),
                ('account_id.account_type', '=', account_type),
            ]
            if report.target_move == 'posted':
                domain.append(('parent_state', '=', 'posted'))
            domain += report._option_domain()
        else:
            domain = report._base_domain()
        if self.account_id:
            domain.append(('account_id', '=', self.account_id.id))
        elif self.partner_id:
            domain += [
                ('partner_id', '=', self.partner_id.id),
                ('account_id.account_type', 'in',
                 ['asset_receivable', 'liability_payable']),
            ]
        elif self.journal_id:
            domain.append(('journal_id', '=', self.journal_id.id))
        elif self.tax_id:
            domain.append(('tax_line_id', '=', self.tax_id.id))
        else:
            raise UserError(_('This summary line has no direct journal-item drill-down.'))
        action = self.env['ir.actions.actions']._for_xml_id(
            'account.action_account_moves_all_a')
        action['domain'] = domain
        action['context'] = {'create': False}
        return action

    def action_open_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('This line is not linked to a journal entry.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
