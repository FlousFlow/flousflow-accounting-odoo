from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class ReportTax(models.AbstractModel):
    _name = 'report.flousflow_accounting.apr__report_tax'
    _description = 'Tax Report'

    @api.model
    def _check_interactive_access(self):
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_readonly', 'account.group_account_invoice',
            'account.group_account_user', 'account.group_account_manager',
        )):
            raise AccessError(_('You are not allowed to view the Tax Report.'))

    @api.model
    def get_interactive_metadata(self):
        self._check_interactive_access()
        company = self.env.company
        today = fields.Date.context_today(self)
        date_from = today.replace(day=1)
        date_to = date_from + relativedelta(months=1, days=-1)
        return {
            'company_name': company.display_name,
            'currency_id': company.currency_id.id,
            'currency_symbol': company.currency_id.symbol or company.currency_id.name,
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
        }

    @api.model
    def get_interactive_data(
        self, date_from=None, date_to=None, target_move='posted',
        comparison_mode='none', comparison_periods=1,
        comparison_date_from=None, comparison_date_to=None,
        comparison_sort='descending', report_view='general',
    ):
        """Return tax totals through the same engine used by the existing PDF report."""
        self._check_interactive_access()
        if target_move not in ('posted', 'all'):
            raise ValidationError(_('Choose a valid journal entry state.'))
        if comparison_mode not in ('none', 'previous_period', 'same_period_last_year', 'custom'):
            raise ValidationError(_('Choose a valid comparison mode.'))
        if comparison_sort not in ('ascending', 'descending'):
            raise ValidationError(_('Choose a valid comparison order.'))
        if report_view not in ('general', 'account_tax', 'tax_account'):
            raise ValidationError(_('Choose a valid tax report grouping.'))
        try:
            comparison_periods = int(comparison_periods or 1)
        except (TypeError, ValueError):
            raise ValidationError(_('The number of comparison periods must be a whole number.'))
        if not 1 <= comparison_periods <= 12:
            raise ValidationError(_('Choose between one and twelve comparison periods.'))
        try:
            date_from = fields.Date.to_date(date_from)
            date_to = fields.Date.to_date(date_to)
        except (TypeError, ValueError):
            date_from = date_to = False
        if not date_from or not date_to or date_from > date_to:
            raise ValidationError(_('Choose a valid tax reporting period.'))

        company = self.env.company
        companies = self.env['res.company'].search([
            ('id', 'child_of', company.id), ('id', 'in', self.env.companies.ids),
        ])
        used_context = {
            'company_id': company.id,
            'allowed_company_ids': companies.ids,
            'company_ids': companies.ids,
        }
        options = {
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'target_move': target_move,
            'used_context': used_context,
        }
        self.env.flush_all()
        groups = self.get_lines(options)
        grouped_lines = self._get_grouped_tax_lines(options, groups, report_view)

        def totals_for(period_groups):
            return {
                group: {
                    'net': sum(line['net'] for line in lines),
                    'tax': sum(line['tax'] for line in lines),
                }
                for group, lines in period_groups.items()
            }

        periods = [{
            'current': True,
            'date_from': options['date_from'],
            'date_to': options['date_to'],
            'groups': groups,
            'totals': totals_for(groups),
            'grouped_lines': grouped_lines,
        }]
        comparison_ranges = []
        if comparison_mode == 'custom':
            try:
                comparison_start = fields.Date.to_date(comparison_date_from)
                comparison_end = fields.Date.to_date(comparison_date_to)
            except (TypeError, ValueError):
                comparison_start = comparison_end = False
            if not comparison_start or not comparison_end or comparison_start > comparison_end:
                raise ValidationError(_('Choose a valid custom comparison period.'))
            comparison_ranges.append((comparison_start, comparison_end))
        elif comparison_mode in ('previous_period', 'same_period_last_year'):
            if comparison_mode == 'same_period_last_year':
                comparison_ranges.append((date_from - relativedelta(years=1), date_to - relativedelta(years=1)))
            else:
                fiscal_dates = company.compute_fiscalyear_dates(date_from)
                is_fiscal_year = (
                    date_from == fiscal_dates['date_from'] and date_to == fiscal_dates['date_to']
                )
                is_year = is_fiscal_year or (
                    date_from.month == 1 and date_from.day == 1 and date_to.month == 12 and date_to.day == 31
                )
                quarter_start_month = ((date_from.month - 1) // 3) * 3 + 1
                is_quarter = (
                    date_from.day == 1 and date_from.month == quarter_start_month
                    and date_to == date_from + relativedelta(months=3, days=-1)
                )
                is_month = date_from.day == 1 and date_to == date_from + relativedelta(months=1, days=-1)
                for index in range(1, comparison_periods + 1):
                    if is_year:
                        if is_fiscal_year:
                            previous_fiscal_dates = company.compute_fiscalyear_dates(
                                date_from - relativedelta(years=index)
                            )
                            start = previous_fiscal_dates['date_from']
                            end = previous_fiscal_dates['date_to']
                        else:
                            start = date_from - relativedelta(years=index)
                            end = start + relativedelta(years=1, days=-1)
                    elif is_quarter:
                        start = date_from - relativedelta(months=3 * index)
                        end = start + relativedelta(months=3, days=-1)
                    elif is_month:
                        start = date_from - relativedelta(months=index)
                        end = start + relativedelta(months=1, days=-1)
                    else:
                        duration = (date_to - date_from).days + 1
                        end = date_from - relativedelta(days=duration * (index - 1) + 1)
                        start = end - relativedelta(days=duration - 1)
                    comparison_ranges.append((start, end))

        for comparison_start, comparison_end in comparison_ranges:
            comparison_options = {
                **options,
                'date_from': fields.Date.to_string(comparison_start),
                'date_to': fields.Date.to_string(comparison_end),
            }
            comparison_groups = self.get_lines(comparison_options)
            comparison_grouped_lines = self._get_grouped_tax_lines(
                comparison_options, comparison_groups, report_view
            )
            periods.append({
                'current': False,
                'date_from': comparison_options['date_from'],
                'date_to': comparison_options['date_to'],
                'groups': comparison_groups,
                'totals': totals_for(comparison_groups),
                'grouped_lines': comparison_grouped_lines,
            })
        periods.sort(
            key=lambda period: period['date_from'],
            reverse=comparison_sort != 'ascending',
        )

        draft_domain = [
            ('state', '=', 'draft'),
            ('company_id', 'in', companies.ids),
            ('date', '>=', date_from), ('date', '<=', date_to),
        ]
        draft_count = self.env['account.move'].search_count(draft_domain) if target_move == 'posted' else 0
        totals = totals_for(groups)
        return {
            'company_name': company.display_name,
            'currency_id': company.currency_id.id,
            'currency_symbol': company.currency_id.symbol or company.currency_id.name,
            'date_from': options['date_from'],
            'date_to': options['date_to'],
            'target_move': target_move,
            'draft_count': draft_count,
            'groups': groups,
            'totals': totals,
            'periods': periods,
            'comparison_mode': comparison_mode,
            'comparison_periods': comparison_periods,
            'comparison_sort': comparison_sort,
            'report_view': report_view,
        }

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        return {
            'data': data['form'],
            'lines': self.get_lines(data.get('form')),
        }

    def _sql_from_amls_one(self):
        sql = ("""SELECT "account_move_line".tax_line_id, """
               """COALESCE(SUM("account_move_line".debit-"account_move_line".credit), 0)
                    FROM %s
                    WHERE %s GROUP BY "account_move_line".tax_line_id""")
        return sql

    def _sql_from_amls_two(self):
        # the base of a withholding tax (l10n_account_withholding_tax) is the one of the payment that withholds
        # it: the invoice or the bill only carries the tax that will be withheld
        withholding = ''
        if 'is_withholding_tax' in self.env['account.tax']._fields:
            withholding = """AND NOT (COALESCE(t.is_withholding_tax, FALSE) AND EXISTS (
                                 SELECT 1 FROM account_move move
                                  WHERE move.id = "account_move_line".move_id AND move.move_type != 'entry'))"""
        sql = """SELECT r.account_tax_id, COALESCE(SUM("account_move_line".debit-"account_move_line".credit), 0)
                 FROM %s
                 INNER JOIN account_move_line_account_tax_rel r ON ("account_move_line".id = r.account_move_line_id)
                 INNER JOIN account_tax t ON (r.account_tax_id = t.id)
                 WHERE %s """ + withholding + """ GROUP BY r.account_tax_id"""
        return sql

    def _tax_sign(self, tax):
        # the balances are debit - credit: sales are credits, printed as positive figures like the purchases
        return -1 if tax['type'] == 'sale' else 1

    def _amount_sign(self, tax):
        # a withholding tax is the opposite of its base: the amount withheld is printed as a positive figure
        return -self._tax_sign(tax) if tax.get('withholding') else self._tax_sign(tax)

    def _compute_from_amls(self, options, taxes):
        #compute the tax amount
        sql = self._sql_from_amls_one()
        # only the tax that is due on the period: the one of a cash basis tax counts on its payment
        tables, where_clause, where_params = self.env['account.move.line'].with_context(tax_exigible=True)._query_get()
        query = sql % (tables, where_clause)
        self.env.cr.execute(query, where_params)
        results = self.env.cr.fetchall()
        for result in results:
            if result[0] in taxes:
                # no abs(): a net-negative period (refunds > invoices) must stay negative
                taxes[result[0]]['tax'] = self._amount_sign(taxes[result[0]]) * (result[1] or 0.0)

        #compute the net amount
        sql2 = self._sql_from_amls_two()
        query = sql2 % (tables, where_clause)
        self.env.cr.execute(query, where_params)
        results = self.env.cr.fetchall()
        for result in results:
            if result[0] in taxes:
                taxes[result[0]]['net'] = self._tax_sign(taxes[result[0]]) * (result[1] or 0.0)

    @api.model
    def get_lines(self, options):
        taxes = {}
        is_withholding = 'is_withholding_tax' in self.env['account.tax']._fields
        for tax in self.env['account.tax'].search([('type_tax_use', '!=', 'none')]):
            withholding = is_withholding and tax.is_withholding_tax
            if tax.children_tax_ids:
                for child in tax.children_tax_ids:
                    if child.type_tax_use != 'none':
                        continue
                    taxes[child.id] = {'tax_id': child.id, 'tax': 0, 'net': 0, 'name': child.name, 'type': tax.type_tax_use,
                                       'withholding': withholding}
            else:
                taxes[tax.id] = {'tax_id': tax.id, 'tax': 0, 'net': 0, 'name': tax.name, 'type': tax.type_tax_use,
                                 'withholding': withholding}
        # used_context carries company_id and journal_ids as well; building a fresh
        # context here would make the report span every company of the switcher.
        report_context = dict(options.get('used_context') or {})
        report_context.update(
            date_from=options['date_from'],
            date_to=options['date_to'],
            state=options['target_move'],
            strict_range=True,
        )
        self.with_context(**report_context)._compute_from_amls(options, taxes)
        groups = dict((tp, []) for tp in ['sale', 'purchase', 'withholding'])
        for tax in taxes.values():
            # keep 0%-rated taxes: they have no tax amount but a real base amount
            if tax['tax'] or tax['net']:
                groups['withholding' if tax['withholding'] else tax['type']].append(tax)
        return groups

    @api.model
    def _get_grouped_tax_lines(self, options, tax_groups, report_view):
        """Return account-level tax/base amounts for the two Enterprise groupings.

        Base amounts stay on the account carrying the base move line; tax amounts
        stay on the account carrying the tax move line. Each pair is grouped by
        tax and account so totals reconcile to the general tax report.
        """
        if report_view == 'general':
            return {}

        taxes = {
            line['tax_id']: {
                'tax_id': line['tax_id'],
                'name': line['name'],
                'type': line['type'],
                'group': group,
                'withholding': group == 'withholding',
            }
            for group, lines in tax_groups.items()
            for line in lines
        }
        empty = {group: [] for group in ('sale', 'purchase', 'withholding')}
        if not taxes:
            return empty

        report_context = dict(options.get('used_context') or {})
        report_context.update(
            date_from=options['date_from'],
            date_to=options['date_to'],
            state=options['target_move'],
            strict_range=True,
            tax_exigible=True,
        )
        move_lines = self.env['account.move.line'].with_context(**report_context)
        tables, where_clause, where_params = move_lines._query_get()

        by_tax_account = {}

        def add_amount(tax_id, account_id, field, amount):
            tax = taxes.get(tax_id)
            if not tax:
                return
            key = (tax_id, account_id)
            line = by_tax_account.setdefault(key, {
                **tax, 'account_id': account_id, 'net': 0.0, 'tax': 0.0,
            })
            sign = self._amount_sign(tax) if field == 'tax' else self._tax_sign(tax)
            line[field] += sign * (amount or 0.0)

        base_withholding_filter = ''
        if 'is_withholding_tax' in self.env['account.tax']._fields:
            base_withholding_filter = """AND NOT (COALESCE(t.is_withholding_tax, FALSE) AND EXISTS (
                SELECT 1 FROM account_move move
                 WHERE move.id = account_move_line.move_id AND move.move_type != 'entry'))"""

        base_query = """SELECT r.account_tax_id, account_move_line.account_id,
                            COALESCE(SUM(account_move_line.debit-account_move_line.credit), 0)
                       FROM %s
                       INNER JOIN account_move_line_account_tax_rel r
                               ON account_move_line.id = r.account_move_line_id
                       INNER JOIN account_tax t ON r.account_tax_id = t.id
                      WHERE %s %s
                   GROUP BY r.account_tax_id, account_move_line.account_id""" % (
            tables, where_clause, base_withholding_filter,
        )
        self.env.cr.execute(base_query, where_params)
        for tax_id, account_id, amount in self.env.cr.fetchall():
            add_amount(tax_id, account_id, 'net', amount)

        tax_query = """SELECT account_move_line.tax_line_id, account_move_line.account_id,
                           COALESCE(SUM(account_move_line.debit-account_move_line.credit), 0)
                      FROM %s
                     WHERE %s AND account_move_line.tax_line_id IS NOT NULL
                  GROUP BY account_move_line.tax_line_id, account_move_line.account_id""" % (
            tables, where_clause,
        )
        self.env.cr.execute(tax_query, where_params)
        for tax_id, account_id, amount in self.env.cr.fetchall():
            add_amount(tax_id, account_id, 'tax', amount)

        account_ids = {account_id for _, account_id in by_tax_account}
        accounts = self.env['account.account'].browse(list(account_ids)).exists()
        account_values = {}
        for account in accounts:
            account_company = (account.company_ids & self.env.companies)[:1] or self.env.company
            account = account.with_company(account_company)
            account_values[account.id] = {
                'account_id': account.id,
                'account_code': account.code or '',
                'account_name': account.name,
                'account_label': account.display_name,
            }

        nested = {
            'account_tax': {group: {} for group in empty},
            'tax_account': {group: {} for group in empty},
        }
        for (tax_id, account_id), line in by_tax_account.items():
            group = line['group']
            account = account_values.get(account_id)
            if not account:
                continue
            tax_line = {
                'tax_id': tax_id,
                'name': line['name'],
                'net': line['net'],
                'tax': line['tax'],
            }
            account_group = nested['account_tax'][group].setdefault(account_id, {
                **account, 'lines': {},
            })
            account_group['lines'][tax_id] = tax_line
            tax_group = nested['tax_account'][group].setdefault(tax_id, {
                'tax_id': tax_id,
                'name': line['name'],
                'accounts': {},
            })
            tax_group['accounts'][account_id] = {**account, 'net': line['net'], 'tax': line['tax']}

        result = {}
        for view, group_data in nested.items():
            result[view] = {}
            for group, values in group_data.items():
                if view == 'account_tax':
                    result[view][group] = [
                        {**account, 'lines': sorted(account['lines'].values(), key=lambda line: line['name'])}
                        for account in sorted(values.values(), key=lambda item: item['account_label'].casefold())
                    ]
                else:
                    result[view][group] = [
                        {**tax, 'accounts': sorted(tax['accounts'].values(), key=lambda item: item['account_label'].casefold())}
                        for tax in sorted(values.values(), key=lambda item: item['name'])
                    ]
        return result
