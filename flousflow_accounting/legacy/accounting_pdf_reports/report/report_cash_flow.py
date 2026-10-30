import time
from collections import defaultdict
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain

# Section and line of the statement for the cash paid or received against an account of a type, when the
# account does not choose its section
TYPE_FLOWS = {
    'asset_receivable': ('operating', 'receivable'),
    'liability_payable': ('operating', 'payable'),
    'income': ('operating', 'income'),
    'income_other': ('operating', 'income'),
    'expense': ('operating', 'expense'),
    'expense_other': ('operating', 'expense'),
    'expense_direct_cost': ('operating', 'expense'),
    'expense_depreciation': ('operating', 'expense'),
    'liability_current': ('operating', 'current_liability'),
    'asset_current': ('operating', 'current_asset'),
    'asset_prepayments': ('operating', 'current_asset'),
    'liability_credit_card': ('operating', 'credit_card'),
    'asset_fixed': ('investing', 'fixed_asset'),
    'asset_non_current': ('investing', 'fixed_asset'),
    'liability_non_current': ('financing', 'borrowing'),
    'equity': ('financing', 'equity'),
    'equity_unaffected': ('financing', 'equity'),
    'off_balance': ('unclassified', 'other'),
}
LINE_ORDER = (
    'receivable', 'payable', 'income', 'expense', 'current_liability', 'current_asset', 'credit_card',
    'unmatched', 'transfer', 'fixed_asset', 'borrowing', 'equity', 'other',
)
# The cash is followed through the reconciliations of the transit accounts (outstanding receipts and payments,
# suspense, internal transfers) to find what it was paid for, this many steps at most.
MAX_TRANSIT_DEPTH = 4


class ReportCashFlow(models.AbstractModel):
    _name = 'report.flousflow_accounting.apr__report_cash_flow'
    _description = 'Cash Flow Statement'

    @api.model
    def _get_line_labels(self):
        return {
            'receivable': _('Cash received from customers'),
            'payable': _('Cash paid to suppliers'),
            'income': _('Other income received'),
            'expense': _('Expenses paid'),
            'current_liability': _('Taxes, salaries and other current liabilities'),
            'current_asset': _('Other current assets'),
            'credit_card': _('Credit cards'),
            'unmatched': _('Payments not matched yet'),
            'transfer': _('Cash in transit between cash accounts'),
            'fixed_asset': _('Fixed and non-current assets'),
            'borrowing': _('Borrowings'),
            'equity': _('Equity'),
            'other': _('Other'),
        }

    @api.model
    def _get_display_sections(self, cash_flow):
        """Group calculated flows into the same fixed rows shown by the client report."""
        activities = {
            'operating': (
                ('receivable', _('Payments received from customers'),
                 lambda line: line['key'] == 'receivable'),
                ('income', _('Operating income'), lambda line: line['key'] == 'income'),
                ('payable', _('Payments made to suppliers'), lambda line: line['key'] == 'payable'),
                ('expense', _('Operating expenses'),
                 lambda line: line['key'] not in ('receivable', 'income', 'payable')),
            ),
            'investing': (
                ('income', _('Income'), lambda line: line['amount'] > 0),
                ('expense', _('Expenses'), lambda line: line['amount'] < 0),
            ),
            'financing': (
                ('income', _('Income'), lambda line: line['amount'] > 0),
                ('expense', _('Expenses'), lambda line: line['amount'] < 0),
            ),
            'unclassified': (
                ('income', _('Income'), lambda line: line['amount'] > 0),
                ('expense', _('Expenses'), lambda line: line['amount'] < 0),
            ),
        }
        section_names = {
            'operating': _('Cash Flows from Operating Activities'),
            'investing': _('Cash Flows from Investing and Non-current Activities'),
            'financing': _('Cash Flows from Financing Activities'),
            'unclassified': _('Cash Flows from Unclassified Activities'),
        }
        display_sections = []
        for section in cash_flow['sections']:
            grouped_lines = []
            for key, label, predicate in activities.get(section['activity'], ()):
                source_lines = [line for line in section['lines'] if predicate(line)]
                grouped_lines.append({
                    'key': key,
                    'name': label,
                    'amount': sum(line['amount'] for line in source_lines),
                    'accounts': [account for line in source_lines for account in line['accounts']],
                })
            display_sections.append({
                **section,
                'name': section_names.get(section['activity'], section['name']),
                'lines': grouped_lines,
                'total': sum(line['amount'] for line in grouped_lines),
            })
        return display_sections

    @api.model
    def _get_transit_accounts(self, company):
        journals = self.env['account.journal'].sudo().search([('company_id', 'child_of', company.id)])
        method_lines = self.env['account.payment.method.line'].sudo().search([('journal_id', 'in', journals.ids)])
        return (company.transfer_account_id | company.account_journal_suspense_account_id
                | journals.suspense_account_id | method_lines.payment_account_id).sudo(False)

    @api.model
    def _get_line_domain(self, form, company):
        states = {
            'posted': ('posted',),
            'draft': ('draft',),
            'all': ('draft', 'posted'),
        }.get(form['target_move'], ('posted',))
        domain = Domain('company_id', 'child_of', company.id) & Domain('parent_state', 'in', states)
        if form.get('journal_filter_enabled') and not form.get('journal_ids'):
            domain &= Domain('id', '=', 0)
        elif form.get('journal_ids'):
            domain &= Domain('journal_id', 'in', form['journal_ids'])
        return domain

    @api.model
    def _classify(self, account):
        """ :return: (section, line) of the statement for the cash paid or received against `account` """
        activity, line = TYPE_FLOWS.get(account.account_type, ('operating', 'other'))
        return account.cash_flow_activity or activity, line

    @api.model
    def _allocate(self, move_line, amount, transit_accounts, flows, flow_line_ids=None, depth=0):
        """ Add `amount` of cash to the flows of what `move_line` stands for. A line on a transit account
        (e.g. outstanding receipts) stands for the lines it is reconciled with, in proportion. """

        def add_flow(key, value, source_line):
            flows[key] += value
            if flow_line_ids is not None:
                flow_line_ids[key].add(source_line.id)

        account = move_line.account_id
        if account.account_type == 'asset_cash':
            add_flow(('operating', 'transfer', False), amount, move_line)
            return
        if account in transit_accounts and depth < MAX_TRANSIT_DEPTH:
            total = abs(move_line.balance)
            matched_share = 0.0
            for partial in (move_line.matched_debit_ids | move_line.matched_credit_ids) if total else []:
                counterpart = partial.debit_move_id if partial.credit_move_id == move_line else partial.credit_move_id
                if not counterpart.balance:
                    continue
                share = partial.amount / total
                matched_share += share
                for other in counterpart.move_id.line_ids - counterpart:
                    if other.account_id and other.balance:
                        self._allocate(
                            other,
                            amount * share * other.balance / -counterpart.balance,
                            transit_accounts,
                            flows,
                            flow_line_ids=flow_line_ids,
                            depth=depth + 1,
                        )
            if matched_share < 1.0:
                add_flow(('operating', 'unmatched', False), amount * (1.0 - matched_share), move_line)
            return
        activity, line = self._classify(account)
        add_flow((activity, line, account.id), amount, move_line)

    @api.model
    def _get_cash_flow(self, form):
        """ :return: dictionary with the opening, closing and net change of the cash and the sections of the
                     statement: list of {activity, name, lines: [{key, name, amount, accounts}], total} """
        company_id = form['company_id'][0] if isinstance(form['company_id'], (list, tuple)) else form['company_id']
        company = self.env['res.company'].browse(company_id)
        currency = company.currency_id
        date_from, date_to = form['date_from'], form['date_to']
        if not date_from or not date_to:
            raise UserError(_('Set the start and end dates of the cash flow statement.'))
        MoveLine = self.env['account.move.line']
        cash_domain = self._get_line_domain(form, company) & Domain('account_id.account_type', '=', 'asset_cash')

        [(opening,)] = MoveLine._read_group(cash_domain & Domain('date', '<', date_from), aggregates=['balance:sum'])
        cash_lines = MoveLine.search(cash_domain & Domain('date', '>=', date_from) & Domain('date', '<=', date_to))
        net_change = sum(cash_lines.mapped('balance'))

        transit_accounts = self._get_transit_accounts(company)
        flows = defaultdict(float)
        flow_line_ids = defaultdict(set)
        for move in cash_lines.move_id:
            for move_line in move.line_ids:
                if move_line.account_id and move_line.account_id.account_type != 'asset_cash' and move_line.balance:
                    self._allocate(
                        move_line,
                        -move_line.balance,
                        transit_accounts,
                        flows,
                        flow_line_ids=flow_line_ids,
                    )

        labels = self._get_line_labels()
        Account = self.env['account.account']
        sections = []
        for activity, activity_name in Account._fields['cash_flow_activity']._description_selection(self.env):
            lines = []
            for line_key in LINE_ORDER:
                keys = [key for key in flows if key[:2] == (activity, line_key)]
                if not keys:
                    continue
                line_accounts = sorted((
                    {
                        'account_id': account.id,
                        'code': account.code or '',
                        'name': account.name,
                        'amount': currency.round(flows[key]),
                        'line_ids': sorted(flow_line_ids[key]),
                    }
                    for key in keys if key[2]
                    for account in [Account.browse(key[2])]
                ), key=lambda values: values['code'])
                amount = currency.round(sum(flows[key] for key in keys))
                if currency.is_zero(amount) and all(currency.is_zero(values['amount']) for values in line_accounts):
                    continue
                lines.append({
                    'key': line_key,
                    'name': labels[line_key],
                    'amount': amount,
                    'accounts': line_accounts,
                    'line_ids': sorted({line_id for key in keys for line_id in flow_line_ids[key]}),
                })
            sections.append({
                'activity': activity,
                'name': activity_name,
                'lines': lines,
                'total': currency.round(sum(line['amount'] for line in lines)),
            })

        # the flows are shares of the cash lines: the rounding of the shares is left in the largest line
        difference = currency.round(net_change - sum(section['total'] for section in sections))
        if not currency.is_zero(difference):
            section = max(sections, key=lambda s: max((abs(line['amount']) for line in s['lines']), default=0.0))
            if section['lines']:
                line = max(section['lines'], key=lambda line: abs(line['amount']))
                line['amount'] = currency.round(line['amount'] + difference)
                section['total'] = currency.round(section['total'] + difference)

        return {
            'sections': sections,
            'opening': currency.round(opening),
            'net_change': currency.round(net_change),
            'closing': currency.round(opening + net_change),
            'currency': currency,
            'company': company,
        }

    @api.model
    def _check_interactive_report_access(self):
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_readonly',
            'account.group_account_invoice',
            'account.group_account_user',
            'account.group_account_manager',
        )):
            raise AccessError(_('You do not have access to the cash flow report.'))

    @api.model
    def get_interactive_metadata(self):
        self._check_interactive_report_access()
        company = self.env.company
        today = fields.Date.context_today(self)
        previous_month_end = today.replace(day=1) - relativedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)
        fiscal_dates = company.compute_fiscalyear_dates(today)
        journals = self.env['account.journal'].search(
            [('company_id', 'child_of', company.id)], order='code, id'
        )
        return {
            'company_id': company.id,
            'company_name': company.display_name,
            'currency_id': company.currency_id.id,
            'default_date_from': fields.Date.to_string(previous_month_start),
            'default_date_to': fields.Date.to_string(previous_month_end),
            'fiscal_year_date_from': fields.Date.to_string(fiscal_dates['date_from']),
            'fiscal_year_date_to': fields.Date.to_string(fiscal_dates['date_to']),
            'journals': [{'id': journal.id, 'name': journal.display_name} for journal in journals],
        }

    @api.model
    def get_interactive_period_dates(self, anchor_date=None):
        self._check_interactive_report_access()
        anchor_date = fields.Date.to_date(anchor_date) if anchor_date else fields.Date.context_today(self)
        fiscal_dates = self.env.company.compute_fiscalyear_dates(anchor_date)
        return {
            'date_from': fields.Date.to_string(fiscal_dates['date_from']),
            'date_to': fields.Date.to_string(fiscal_dates['date_to']),
        }

    @api.model
    def get_interactive_data(self, date_from=None, date_to=None, target_move='posted',
                             journal_ids=None, journal_filter_enabled=False):
        self._check_interactive_report_access()
        if target_move not in ('posted', 'draft', 'all'):
            raise UserError(_('Choose a valid journal entry state.'))
        try:
            date_from = fields.Date.to_date(date_from)
            date_to = fields.Date.to_date(date_to)
        except (TypeError, ValueError):
            date_from = date_to = False
        if not date_from or not date_to or date_from > date_to:
            raise UserError(_('Set a valid start and end date for the cash flow statement.'))
        if not isinstance(journal_ids, (list, tuple)):
            journal_ids = []
        try:
            journal_ids = list({int(journal_id) for journal_id in journal_ids if str(journal_id).isdigit()})
        except (TypeError, ValueError):
            journal_ids = []
        allowed_journals = self.env['account.journal'].search([
            ('id', 'in', journal_ids),
            ('company_id', 'child_of', self.env.company.id),
        ])
        form = {
            'date_from': date_from,
            'date_to': date_to,
            'target_move': target_move,
            'journal_ids': allowed_journals.ids,
            'journal_filter_enabled': bool(journal_filter_enabled),
            'company_id': self.env.company.id,
        }
        report = self.with_context(allowed_company_ids=self.env.companies.ids)
        cash_flow = report._get_cash_flow(form)
        return {
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'target_move': target_move,
            'journal_filter_enabled': bool(journal_filter_enabled),
            'journal_names': allowed_journals.mapped('display_name'),
            'company_id': cash_flow['company'].id,
            'company_name': cash_flow['company'].display_name,
            'currency_id': cash_flow['company'].currency_id.id,
            'opening': cash_flow['opening'],
            'net_change': cash_flow['net_change'],
            'closing': cash_flow['closing'],
            'sections': [{
                'activity': section['activity'],
                'name': section['name'],
                'total': section['total'],
                'lines': [{
                    'key': line['key'],
                    'name': line['name'],
                    'amount': line['amount'],
                    'line_ids': line['line_ids'],
                    'accounts': line['accounts'],
                } for line in section['lines']],
            } for section in cash_flow['sections']],
        }

    @api.model
    def print_interactive_report(self, date_from=None, date_to=None, target_move='posted',
                                 journal_ids=None, journal_filter_enabled=False,
                                 display_detail='summary'):
        self._check_interactive_report_access()
        if target_move not in ('posted', 'draft', 'all'):
            raise UserError(_('Choose a valid journal entry state.'))
        if display_detail not in ('summary', 'accounts'):
            raise UserError(_('Choose a valid cash flow display mode.'))
        date_from = fields.Date.to_date(date_from) if date_from else False
        date_to = fields.Date.to_date(date_to) if date_to else False
        if not date_from or not date_to or date_from > date_to:
            raise UserError(_('Set a valid start and end date for the cash flow statement.'))
        if not isinstance(journal_ids, (list, tuple)):
            journal_ids = []
        try:
            journal_ids = list({int(journal_id) for journal_id in journal_ids if str(journal_id).isdigit()})
        except (TypeError, ValueError):
            journal_ids = []
        journals = self.env['account.journal'].search([
            ('id', 'in', journal_ids),
            ('company_id', 'child_of', self.env.company.id),
        ])
        wizard = self.env['account.cash.flow.report'].create({
            'company_id': self.env.company.id,
            'date_from': date_from,
            'date_to': date_to,
            'target_move': 'all' if target_move in ('all', 'draft') else 'posted',
            'display_detail': display_detail,
            'journal_ids': [(6, 0, journals.ids if journal_filter_enabled else self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
        })
        if target_move == 'draft':
            # Keep the existing PDF report engine supporting only Posted/All choices.
            # The interactive report itself can still be restricted to drafts.
            wizard.target_move = 'all'
        return wizard.with_context(
            active_model='account.cash.flow.report',
            active_id=wizard.id,
            cash_flow_target_move=target_move,
        )._print_report({
            'form': {
                **wizard.read(['date_from', 'date_to', 'journal_ids', 'company_id', 'display_detail'])[0],
                'target_move': target_move,
            }
        })

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the reconciliations are read through the ORM, the totals with a grouped query: write the changes first
        self.env.flush_all()
        form = data['form']
        cash_flow = self._get_cash_flow(form)
        journals = self.env['account.journal'].browse(form.get('journal_ids') or [])
        return {
            'doc_ids': docids,
            'doc_model': 'account.cash.flow.report',
            'data': form,
            'docs': self.env['account.cash.flow.report'].browse(docids),
            'time': time,
            'print_journal': journals.mapped('code'),
            'cash_flow': cash_flow,
            'display_sections': self._get_display_sections(cash_flow),
        }
