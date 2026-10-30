import time
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.flousflow_accounting.apr__report_trialbalance'
    _description = 'Trial Balance Report'

    @api.model
    def get_interactive_data(self, period_type='month', period_anchor=None,
                             custom_date_from=None, custom_date_to=None,
                             target_move='posted', journal_ids=None,
                             display_account='movement', comparison=False,
                             cash_basis=False):
        if not self.env.user.has_group('account.group_account_readonly'):
            raise AccessError(_('You are not allowed to view the Trial Balance.'))
        if target_move not in ('posted', 'all'):
            target_move = 'posted'
        if display_account not in ('all', 'movement', 'not_zero'):
            raise ValidationError(_('Choose a valid account display option.'))

        report_period = self.env['report.flousflow_accounting.apr__report_general_ledger']
        date_from, date_to = report_period._get_interactive_period_dates(
            period_type, period_anchor, custom_date_from, custom_date_to
        )
        date_from, date_to = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        company = self.env.company
        companies = self.env['res.company'].search([('id', 'child_of', company.id)])
        journals = self.env['account.journal'].search([('company_id', 'in', companies.ids)])
        no_journals_selected = journal_ids is not False and journal_ids is not None and not journal_ids
        if journal_ids is not False and journal_ids is not None:
            try:
                raw_journal_ids = [journal_ids] if isinstance(journal_ids, (str, int)) else journal_ids
                selected_journal_ids = {int(item) for item in raw_journal_ids}
            except (TypeError, ValueError):
                raise ValidationError(_('Invalid journal selection.'))
            journals = journals.filtered(lambda journal: journal.id in selected_journal_ids)
        accounts = self.env['account.account'].search([('company_ids', 'in', companies.ids)])
        if no_journals_selected:
            accounts = self.env['account.account']

        def balances_for(start_date, end_date):
            if not accounts or not journals:
                return {}
            used_context = {
                'company_id': company.id,
                'journal_ids': journals.ids,
                'date_from': fields.Date.to_string(start_date) if start_date else False,
                'date_to': fields.Date.to_string(end_date),
                'strict_range': bool(start_date),
                'state': target_move,
                'tax_exigible': bool(cash_basis),
            }
            return {
                item['account_id']: item
                for item in self.with_context(used_context)._get_accounts(accounts, 'all')
            }

        current = balances_for(date_from, date_to)
        opening = balances_for(False, date_from - relativedelta(days=1)) if date_from else {}
        previous = {}
        previous_opening = {}
        previous_from = previous_to = False
        if comparison:
            duration = (date_to - date_from).days + 1
            previous_to = date_from - relativedelta(days=1)
            previous_from = previous_to - relativedelta(days=duration - 1)
            previous = balances_for(previous_from, previous_to)
            previous_opening = balances_for(False, previous_from - relativedelta(days=1))

        lines = []
        for account in accounts:
            period = current.get(account.id, {})
            start = opening.get(account.id, {})
            closing_balance = (start.get('balance') or 0.0) + (period.get('balance') or 0.0)
            if display_account == 'movement' and not (
                period.get('debit') or period.get('credit')
            ):
                continue
            if display_account == 'not_zero' and (account.currency_id or company.currency_id).is_zero(closing_balance):
                continue
            line = {
                'account_id': account.id,
                'code': account.code or '',
                'name': account.name,
                'opening_balance': start.get('balance') or 0.0,
                'debit': period.get('debit') or 0.0,
                'credit': period.get('credit') or 0.0,
                'balance': closing_balance,
            }
            if comparison:
                prior = previous.get(account.id, {})
                prior_start = previous_opening.get(account.id, {})
                line.update({
                    'opening_balance_cmp': prior_start.get('balance') or 0.0,
                    'debit_cmp': prior.get('debit') or 0.0,
                    'credit_cmp': prior.get('credit') or 0.0,
                    'balance_cmp': (prior_start.get('balance') or 0.0)
                        + (prior.get('balance') or 0.0),
                })
            lines.append(line)

        draft_count = 0
        if target_move == 'posted':
            draft_count = self.env['account.move'].search_count([
                ('state', '=', 'draft'),
                ('company_id', 'in', companies.ids),
                ('journal_id', 'in', journals.ids),
                ('date', '<=', date_to),
            ])
        return {
            'lines': lines,
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
            'previous_date_from': fields.Date.to_string(previous_from) if previous_from else False,
            'previous_date_to': fields.Date.to_string(previous_to) if previous_to else False,
            'comparison': bool(comparison),
            'cash_basis': bool(cash_basis),
            'draft_count': draft_count,
            'company_id': company.id,
            'company_name': company.name,
            'currency_id': company.currency_id.id,
            'journal_ids': journals.ids,
            'journals': [{'id': journal.id, 'name': journal.display_name} for journal in journals],
            'totals': {
                key: sum(line[key] for line in lines)
                for key in ('opening_balance', 'debit', 'credit', 'balance')
            },
        }

    def _get_accounts(self, accounts, display_account):
        """ compute the balance, debit and credit for the provided accounts
            :Arguments:
                `accounts`: list of accounts record,
                `display_account`: it's used to display either all accounts or those accounts which balance is > 0
            :Returns a list of dictionary of Accounts with following key and value
                `name`: Account name,
                `code`: Account code,
                `credit`: total amount of credit,
                `debit`: total amount of debit,
                `balance`: total amount of balance,
        """

        account_result = {}
        # Prepare sql query base on selected parameters from wizard
        tables, where_clause, where_params = self.env['account.move.line']._query_get()
        tables = tables.replace('"','')
        if not tables:
            tables = 'account_move_line'
        wheres = [""]
        if where_clause.strip():
            wheres.append(where_clause.strip())
        filters = " AND ".join(wheres)
        # compute the balance, debit and credit for the provided accounts
        request = ("SELECT account_id AS id, SUM(debit) AS debit, SUM(credit) AS credit, "
                   "(SUM(debit) - SUM(credit)) AS balance" +\
                   " FROM " + tables + " WHERE account_id IN %s " + filters + " GROUP BY account_id")
        params = (tuple(accounts.ids),) + tuple(where_params)
        self.env.cr.execute(request, params)
        for row in self.env.cr.dictfetchall():
            account_result[row.pop('id')] = row

        account_res = []
        for account in accounts:
            res = dict((fn, 0.0) for fn in ['credit', 'debit', 'balance'])
            currency = account.currency_id and account.currency_id or self.env.company.currency_id
            res['account_id'] = account.id
            res['code'] = account.code
            res['name'] = account.name
            if account.id in account_result:
                res['debit'] = account_result[account.id].get('debit')
                res['credit'] = account_result[account.id].get('credit')
                res['balance'] = account_result[account.id].get('balance')
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(res['balance']):
                account_res.append(res)
            if display_account == 'movement' and (
                    not currency.is_zero(res['debit']) or not currency.is_zero(res['credit'])):
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
        display_account = data['form'].get('display_account')
        accounts = docs if model == 'account.account' else self.env['account.account'].search([])
        context = data['form'].get('used_context')
        analytic_accounts = []
        if data['form'].get('analytic_account_ids'):
            analytic_account_ids = self.env['account.analytic.account'].browse(data['form'].get('analytic_account_ids'))
            context['analytic_account_ids'] = analytic_account_ids
            analytic_accounts = [account.name for account in analytic_account_ids]
        account_res = self.with_context(context)._get_accounts(accounts, display_account)
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]
        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'print_journal': codes,
            'analytic_accounts': analytic_accounts,
            'time': time,
            'Accounts': account_res,
        }
