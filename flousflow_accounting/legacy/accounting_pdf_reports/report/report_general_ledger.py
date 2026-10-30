import time
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class ReportGeneralLedger(models.AbstractModel):
    _name = 'report.flousflow_accounting.apr__report_general_ledger'
    _description = 'General Ledger Report'

    @api.model
    def _get_interactive_period_dates(
        self, period_type, period_anchor=None, custom_date_from=None, custom_date_to=None,
    ):
        if period_type not in ('month', 'quarter', 'fiscal_year', 'custom'):
            raise ValidationError(_('Choose a valid reporting period.'))
        try:
            anchor = fields.Date.to_date(period_anchor) or fields.Date.context_today(self)
        except (TypeError, ValueError):
            raise ValidationError(_('Choose a valid reporting period.'))

        if period_type == 'custom':
            try:
                date_from = fields.Date.to_date(custom_date_from)
                date_to = fields.Date.to_date(custom_date_to)
            except (TypeError, ValueError):
                date_from = date_to = False
            if not date_from or not date_to or date_from > date_to:
                raise ValidationError(_('Choose a valid custom date range.'))
        elif period_type == 'month':
            date_from = anchor.replace(day=1)
            date_to = date_from + relativedelta(months=1, days=-1)
        elif period_type == 'quarter':
            date_from = anchor.replace(month=((anchor.month - 1) // 3) * 3 + 1, day=1)
            date_to = date_from + relativedelta(months=3, days=-1)
        else:
            fiscal_dates = self.env.company.compute_fiscalyear_dates(anchor)
            date_from, date_to = fiscal_dates['date_from'], fiscal_dates['date_to']
        return fields.Date.to_string(date_from), fields.Date.to_string(date_to)

    @api.model
    def get_interactive_data(self, date_from=None, date_to=None, target_move='posted',
                             cash_basis=False, account_ids=None, period_type=None,
                             period_anchor=None, custom_date_from=None, custom_date_to=None):
        """Return General Ledger totals, loading move lines only for requested accounts."""
        if not self.env.user.has_group('account.group_account_readonly'):
            raise AccessError(_('You are not allowed to view the General Ledger.'))
        if target_move not in ('posted', 'all'):
            target_move = 'posted'
        if period_type:
            date_from, date_to = self._get_interactive_period_dates(
                period_type, period_anchor, custom_date_from, custom_date_to
            )
        try:
            date_from = fields.Date.to_date(date_from) if date_from else False
            date_to = fields.Date.to_date(date_to) if date_to else fields.Date.context_today(self)
        except (TypeError, ValueError):
            raise ValidationError(_('Enter valid report dates.'))
        if date_from and date_to and date_from > date_to:
            raise ValidationError(_('The start date must be on or before the end date.'))

        company = self.env.company
        companies = self.env['res.company'].search([('id', 'child_of', company.id)])
        journals = self.env['account.journal'].search([('company_id', 'in', companies.ids)])
        accounts = self.env['account.account'].search([('company_ids', 'in', companies.ids)])
        if account_ids:
            try:
                selected_ids = {int(account_id) for account_id in
                                ([account_ids] if isinstance(account_ids, (str, int)) else account_ids)}
            except (TypeError, ValueError):
                raise ValidationError(_('Invalid account selection.'))
            accounts = accounts.filtered(lambda account: account.id in selected_ids)
        used_context = {
            'company_id': company.id,
            'journal_ids': journals.ids,
            'date_from': fields.Date.to_string(date_from) if date_from else False,
            'date_to': fields.Date.to_string(date_to),
            'strict_range': bool(date_from),
            'state': target_move,
            # This is the same tax-exigible filter used by Odoo's Cash Basis Method.
            'tax_exigible': bool(cash_basis),
        }
        self.env.flush_all()
        account_lines = self.with_context(used_context)._get_account_move_entry(
            accounts,
            analytic_account_ids=False,
            partner_ids=False,
            init_balance=True,
            sortby='sort_date',
            display_account='movement',
        )

        result_lines = []
        for account_line in account_lines:
            account = accounts.filtered(lambda record: record.id == account_line['account_id'])[:1]
            if not account:
                continue
            move_lines = []
            if account_ids:
                for line in account_line['move_lines']:
                    move_lines.append({
                        'id': line.get('lid') or 0,
                        'date': fields.Date.to_string(line['ldate']) if line.get('ldate') else False,
                        'journal_code': line.get('lcode') or '',
                        'partner_name': line.get('partner_name') or '',
                        'label': line.get('lname') or '',
                        'move_name': line.get('move_name') or '',
                        'currency_id': line.get('currency_id') or False,
                        'currency_code': line.get('currency_code') or '',
                        'amount_currency': line.get('amount_currency') or 0.0,
                        'debit': line.get('debit') or 0.0,
                        'credit': line.get('credit') or 0.0,
                        'balance': line.get('balance') or 0.0,
                    })
            result_line = {
                'account_id': account.id,
                'code': account_line['code'] or '',
                'name': account_line['name'],
                'debit': account_line['debit'],
                'credit': account_line['credit'],
                'balance': account_line['balance'],
            }
            if account_ids:
                result_line['move_lines'] = move_lines
            result_lines.append(result_line)

        draft_count = 0
        if target_move == 'posted':
            draft_domain = [
                ('state', '=', 'draft'),
                ('company_id', 'in', companies.ids),
                ('journal_id', 'in', journals.ids),
                ('date', '<=', date_to),
            ]
            draft_count = self.env['account.move'].search_count(draft_domain)

        return {
            'lines': result_lines,
            'date_from': fields.Date.to_string(date_from) if date_from else False,
            'date_to': fields.Date.to_string(date_to),
            'target_move': target_move,
            'cash_basis': bool(cash_basis),
            'draft_count': draft_count,
            'company_id': company.id,
            'company_ids': companies.ids,
            'company_name': company.name,
            'journal_ids': journals.ids,
            'currency_id': company.currency_id.id,
            'currency_symbol': company.currency_id.symbol,
            'totals': {
                'debit': sum(line['debit'] for line in result_lines),
                'credit': sum(line['credit'] for line in result_lines),
                'balance': sum(line['balance'] for line in result_lines),
            },
        }

    def _get_account_move_entry(self, accounts, analytic_account_ids,
                                partner_ids, init_balance,
                                sortby, display_account):
        """
        :param:
                accounts: the recordset of accounts
                analytic_account_ids: the recordset of analytic accounts
                init_balance: boolean value of initial_balance
                sortby: sorting by date or partner and journal
                display_account: type of account(receivable, payable and both)

        Returns a dictionary of accounts with following key and value {
                'code': account code,
                'name': account name,
                'debit': sum of total debit amount,
                'credit': sum of total credit amount,
                'balance': total balance,
                'amount_currency': sum of amount_currency,
                'move_lines': list of move line
        }
        """
        cr = self.env.cr
        MoveLine = self.env['account.move.line']
        move_lines = {x: [] for x in accounts.ids}

        # Prepare initial sql query and Get the initial move lines
        if init_balance:
            context = dict(self.env.context)
            context['date_from'] = self.env.context.get('date_from')
            context['date_to'] = False
            context['initial_bal'] = True
            if analytic_account_ids:
                context['analytic_account_ids'] = analytic_account_ids
            if partner_ids:
                context['partner_ids'] = partner_ids
            init_tables, init_where_clause, init_where_params = MoveLine.with_context(context)._query_get()
            init_wheres = [""]
            if init_where_clause.strip():
                init_wheres.append(init_where_clause.strip())
            init_filters = " AND ".join(init_wheres)
            filters = init_filters.replace('"account_move_line__move_id"', '"m"')
            filters = filters.replace('"account_move_line".', '"l".')
            sql = ("""SELECT 0 AS lid, l.account_id AS account_id, '' AS ldate,
                '' AS lcode, 0.0 AS amount_currency, 
                '' AS analytic_account_id, '' AS lref, 
                'Initial Balance' AS lname, COALESCE(SUM(l.debit),0.0) AS debit, 
                COALESCE(SUM(l.credit),0.0) AS credit, 
                COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) as balance, 
                '' AS lpartner_id,\
                '' AS move_name, '' AS move_id, '' AS currency_code,\
                NULL AS currency_id,\
                '' AS invoice_id, '' AS invoice_type, '' AS invoice_number,\
                '' AS partner_name\
                FROM account_move_line l\
                LEFT JOIN account_move m ON (l.move_id=m.id)\
                LEFT JOIN res_currency c ON (l.currency_id=c.id)\
                LEFT JOIN res_partner p ON (l.partner_id=p.id)\
                JOIN account_journal j ON (l.journal_id=j.id)\
                WHERE l.account_id IN %s""" + filters + ' GROUP BY l.account_id')
            params = (tuple(accounts.ids),) + tuple(init_where_params)
            cr.execute(sql, params)
            for row in cr.dictfetchall():
                move_lines[row.pop('account_id')].append(row)

        sql_sort = 'l.date, l.move_id, l.id'
        if sortby == 'sort_journal_partner':
            sql_sort = 'j.code, p.name, l.move_id, l.id'

        # Prepare sql query base on selected parameters from wizard
        context = dict(self.env.context)
        if analytic_account_ids:
            context['analytic_account_ids'] = analytic_account_ids
        if partner_ids:
            context['partner_ids'] = partner_ids
        tables, where_clause, where_params = MoveLine.with_context(context)._query_get()
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        filters = filters.replace('"account_move_line__move_id"', '"m"')
        filters = filters.replace('"account_move_line".', '"l".')

        # Get move lines base on sql query and Calculate the total balance of move lines
        sql = ('''SELECT l.id AS lid, l.account_id AS account_id, 
            l.date AS ldate, j.code AS lcode, l.currency_id, 
            l.amount_currency, '' AS analytic_account_id,
            l.ref AS lref, l.name AS lname, COALESCE(l.debit,0) AS debit, 
            COALESCE(l.credit,0) AS credit, 
            COALESCE(SUM(l.debit),0) - COALESCE(SUM(l.credit), 0) AS balance,\
            m.name AS move_name, c.symbol AS currency_code, 
            p.name AS partner_name\
            FROM account_move_line l\
            JOIN account_move m ON (l.move_id=m.id)\
            LEFT JOIN res_currency c ON (l.currency_id=c.id)\
            LEFT JOIN res_partner p ON (l.partner_id=p.id)\
            JOIN account_journal j ON (l.journal_id=j.id)\
            JOIN account_account acc ON (l.account_id = acc.id) \
            WHERE l.account_id IN %s ''' + filters + ''' GROUP BY l.id, 
            l.account_id, l.date, j.code, l.currency_id, l.amount_currency, 
            l.ref, l.name, m.name, c.symbol, p.name ORDER BY ''' + sql_sort)
        params = (tuple(accounts.ids),) + tuple(where_params)
        cr.execute(sql, params)

        # the running balance of each account: what its previous lines (and the initial balance) add up to,
        # summed as the lines come, not again from the first line for each one
        previous = {}
        for account_id, lines in move_lines.items():
            balance = 0
            for line in lines:
                balance += line['debit'] - line['credit']
            previous[account_id] = balance
        for row in cr.dictfetchall():
            account_id = row.pop('account_id')
            row['balance'] += previous[account_id]
            previous[account_id] += row['debit'] - row['credit']
            move_lines[account_id].append(row)

        # Calculate the debit, credit and balance for Accounts
        account_res = []
        for account in accounts:
            currency = account.currency_id and account.currency_id or self.env.company.currency_id
            res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance'])
            res['code'] = account.code
            res['account_id'] = account.id
            res['name'] = account.name
            res['move_lines'] = move_lines[account.id]
            for line in res.get('move_lines'):
                res['debit'] += line['debit']
                res['credit'] += line['credit']
                res['balance'] = line['balance']
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'movement' and res.get('move_lines'):
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(res['balance']):
                account_res.append(res)
        return account_res

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get('active_model'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_ids', []))
        init_balance = data['form'].get('initial_balance', True)
        sortby = data['form'].get('sortby', 'sort_date')
        display_account = data['form']['display_account']
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]
        analytic_account_ids = False
        if data['form'].get('analytic_account_ids', False):
            analytic_account_ids = self.env['account.analytic.account'].search(
                [('id', 'in', data['form']['analytic_account_ids'])])
        partner_ids = False
        if data['form'].get('partner_ids', False):
            partner_ids = self.env['res.partner'].search(
                [('id', 'in', data['form']['partner_ids'])])
        if model == 'account.account':
            accounts = docs
        else:
            domain = []
            if data['form'].get('account_ids', False):
                domain.append(('id', 'in', data['form']['account_ids']))
            accounts = self.env['account.account'].search(domain)
        accounts_res = self.with_context(
            data['form'].get('used_context', {}))._get_account_move_entry(
            accounts,
            analytic_account_ids,
            partner_ids,
            init_balance, sortby, display_account)
        return {
            'doc_ids': docids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'Accounts': accounts_res,
            'print_journal': codes,
            'accounts': accounts,
            'partner_ids': partner_ids,
            'analytic_account_ids': analytic_account_ids,
        }
