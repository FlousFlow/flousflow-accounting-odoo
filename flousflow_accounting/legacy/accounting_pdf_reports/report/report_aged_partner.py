import time
from odoo import api, models, fields, _
from odoo.exceptions import AccessError, UserError
from odoo.tools.misc import formatLang
from odoo.tools import float_is_zero
from datetime import datetime
from dateutil.relativedelta import relativedelta


class ReportAgedPartnerBalance(models.AbstractModel):
    _name = 'report.flousflow_accounting.apr__report_agedpartnerbalance'
    _description = 'Aged Partner Balance Report'

    def _get_partner_move_lines(self, account_type, partner_ids,
                                date_from, target_move, period_length, date_basis='due_date'):
        # This method can receive the context key 'include_nullified_amount' {Boolean}
        # Do an invoice and a payment and unreconcile. The amount will be nullified
        # By default, the partner wouldn't appear in this report.
        # The context key allow it to appear
        # In case of a period_length of 30 days as of 2019-02-08, we want the following periods:
        # Name       Stop         Start
        # 1 - 30   : 2019-02-07 - 2019-01-09
        # 31 - 60  : 2019-01-08 - 2018-12-10
        # 61 - 90  : 2018-12-09 - 2018-11-10
        # 91 - 120 : 2018-11-09 - 2018-10-11
        # +120     : 2018-10-10
        periods = {}
        start = datetime.strptime(str(date_from), "%Y-%m-%d")
        date_from = datetime.strptime(str(date_from), "%Y-%m-%d").date()
        for i in range(5)[::-1]:
            stop = start - relativedelta(days=period_length)
            period_name = str((5-(i+1)) * period_length + 1) + '-' + str((5-i) * period_length)
            period_stop = (start - relativedelta(days=1)).strftime('%Y-%m-%d')
            if i == 0:
                period_name = '+' + str(4 * period_length)
            periods[str(i)] = {
                'name': period_name,
                'stop': period_stop,
                'start': (i!=0 and stop.strftime('%Y-%m-%d') or False),
            }
            start = stop

        res = []
        total = []
        cr = self.env.cr
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        # the company of the report (given by the wizard), not the default company of the user
        company = self.env['res.company'].browse(self.env.context.get('company_id')) or self.env.company
        user_currency = company.currency_id
        # a branch posts its entries in its own company: they belong to the report
        # of the parent that consolidates it
        company_ids = self.env.context.get('company_ids') or self.env['res.company'].search(
            [('id', 'child_of', company.id)]).ids
        move_state = ['draft', 'posted']
        date = self.env.context.get('date') or fields.Date.context_today(self)

        if target_move == 'posted':
            move_state = ['posted']
        # the open items as of the date: the items not reconciled yet, and the ones reconciled after it
        reconciliation_clause = '''(l.reconciled IS FALSE
            OR EXISTS(SELECT 1 FROM account_partial_reconcile p
                       WHERE p.debit_move_id = l.id AND p.max_date > %(date_from)s)
            OR EXISTS(SELECT 1 FROM account_partial_reconcile p
                       WHERE p.credit_move_id = l.id AND p.max_date > %(date_from)s))'''
        args = {
            'move_state': tuple(move_state),
            'account_type': tuple(account_type),
            'date_from': date_from,
            'company_ids': tuple(company_ids),
        }
        query = ('''
            SELECT DISTINCT l.partner_id, UPPER(res_partner.name)
            FROM account_move_line AS l left join res_partner on l.partner_id = res_partner.id, '''
                 '''account_account, account_move am
            WHERE (l.account_id = account_account.id)
                AND (l.move_id = am.id)
                AND (am.state IN %(move_state)s)
                AND (account_account.account_type IN %(account_type)s)
                AND ''' + reconciliation_clause + '''
                AND (l.date <= %(date_from)s)
                AND l.company_id IN %(company_ids)s
            ORDER BY UPPER(res_partner.name)''')
        cr.execute(query, args)
        partners = cr.dictfetchall()
        # put a total of 0
        for i in range(7):
            total.append(0)

        # Build a string like (1,2,3) for easy use in SQL query
        if not partner_ids:
            partner_ids = [partner['partner_id'] for partner in partners if partner['partner_id']]
        lines = dict((partner['partner_id'] or False, []) for partner in partners)
        if not partner_ids:
            return [], [0.0] * 7, {}
        args['partner_ids'] = tuple(partner_ids)

        aging_date = (
            'COALESCE(l.date_maturity, l.date)'
            if date_basis == 'due_date'
            else 'COALESCE(am.invoice_date, l.date)'
        )
        # the period of each item: 6 when it is not due yet, else 1 to 5 for the
        # periods '0' (the oldest) to '4' (the most recent)
        period_cases = [f'WHEN {aging_date} >= %(date_from)s THEN 6']
        for i in range(5):
            start, stop = periods[str(i)]['start'], periods[str(i)]['stop']
            args.update({f'start_{i}': start, f'stop_{i}': stop})
            if start and stop:
                condition = f'{aging_date} BETWEEN %(start_{i})s AND %(stop_{i})s'
            elif start:
                condition = f'{aging_date} >= %(start_{i})s'
            else:
                condition = f'{aging_date} <= %(stop_{i})s'
            period_cases.append(f'WHEN {condition} THEN {i + 1}')

        # the open items with what was reconciled with them until the date, in one query: an item
        # reconciled before the date and not after is settled, and left out
        query = '''
            SELECT l.id, l.partner_id, l.company_id, l.balance,
                   CASE ''' + ' '.join(period_cases) + ''' END AS period,
                   (SELECT COALESCE(SUM(p.amount), 0) FROM account_partial_reconcile p
                     WHERE p.credit_move_id = l.id AND p.max_date <= %(date_from)s) AS matched_debit,
                   (SELECT COALESCE(SUM(p.amount), 0) FROM account_partial_reconcile p
                     WHERE p.debit_move_id = l.id AND p.max_date <= %(date_from)s) AS matched_credit
            FROM account_move_line AS l, account_account, account_move am
            WHERE (l.account_id = account_account.id) AND (l.move_id = am.id)
                AND (am.state IN %(move_state)s)
                AND (account_account.account_type IN %(account_type)s)
                AND ((l.partner_id IN %(partner_ids)s) OR (l.partner_id IS NULL))
                AND ''' + reconciliation_clause + '''
                AND (l.date <= %(date_from)s)
                AND l.company_id IN %(company_ids)s'''
        cr.execute(query, args)

        # This dictionary will store the not due amount of all partners
        undue_amounts = {}
        # Each history will contain: history[1] = {'<partner_id>': <partner_debit-credit>}
        history = [{} for i in range(5)]
        MoveLine = self.env['account.move.line']
        Company = self.env['res.company']
        for row in cr.dictfetchall():
            partner_id = row['partner_id'] or False
            line_currency = Company.browse(row['company_id']).currency_id
            line_amount = line_currency._convert(row['balance'], user_currency, company, date)
            if user_currency.is_zero(line_amount):
                continue
            # the amounts reconciled with an item are in the currency of its company
            if row['matched_debit']:
                line_amount += line_currency._convert(row['matched_debit'], user_currency, company, date)
            if row['matched_credit']:
                line_amount -= line_currency._convert(row['matched_credit'], user_currency, company, date)
            if user_currency.is_zero(line_amount):
                continue
            amounts = undue_amounts if row['period'] == 6 else history[row['period'] - 1]
            amounts[partner_id] = amounts.get(partner_id, 0.0) + line_amount
            lines.setdefault(partner_id, []).append({
                'line': MoveLine.browse(row['id']),
                'amount': line_amount,
                'period': row['period'],
            })

        # the names of the partners are read together, not one partner at a time
        partner_records = self.env['res.partner'].browse(
            [partner['partner_id'] for partner in partners if partner['partner_id']])
        for partner in partners:
            if partner['partner_id'] is None:
                partner['partner_id'] = False
            at_least_one_amount = False
            values = {}
            undue_amt = 0.0
            if partner['partner_id'] in undue_amounts:  # Making sure this partner actually was found by the query
                undue_amt = undue_amounts[partner['partner_id']]

            total[6] = total[6] + undue_amt
            values['direction'] = undue_amt
            if not float_is_zero(values['direction'], precision_rounding=user_currency.rounding):
                at_least_one_amount = True

            for i in range(5):
                during = False
                if partner['partner_id'] in history[i]:
                    during = [history[i][partner['partner_id']]]
                # Adding counter
                total[(i)] = total[(i)] + (during and during[0] or 0)
                values[str(i)] = during and during[0] or 0.0
                if not float_is_zero(values[str(i)],
                                     precision_rounding=user_currency.rounding):
                    at_least_one_amount = True
            values['total'] = sum([values['direction']] + [values[str(i)] for i in range(5)])
            ## Add for total
            total[(i + 1)] += values['total']
            values['partner_id'] = partner['partner_id']
            if partner['partner_id']:
                browsed_partner = partner_records.browse(partner['partner_id']).with_prefetch(partner_records._ids)
                values['name'] = browsed_partner.name and len(
                    browsed_partner.name) >= 45 and browsed_partner.name[
                                                    0:40] + '...' or browsed_partner.name
                values['trust'] = browsed_partner.trust
            else:
                values['name'] = _('Unknown Partner')
                values['trust'] = False

            if at_least_one_amount or (self.env.context.get('include_nullified_amount')
                                       and lines[partner['partner_id']]):
                res.append(values)

        return res, total, lines

    @api.model
    def _check_interactive_report_access(self):
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_readonly',
            'account.group_account_invoice',
            'account.group_account_manager',
        )):
            raise AccessError(_('You do not have access to aged partner reports.'))

    @api.model
    def get_open_items_action(self, partner_id):
        self._check_interactive_report_access()
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError):
            raise UserError(_('Choose a valid partner.'))
        partner = self.env['res.partner'].search([('id', '=', partner_id)], limit=1)
        if not partner:
            raise UserError(_('The selected partner is unavailable.'))
        return {
            'type': 'ir.actions.client',
            'name': _('Open Items'),
            'tag': 'flousflow_accounting.apr__open_items',
            'context': {
                'default_partner_ids': [partner.commercial_partner_id.id],
                'default_result_selection': 'trade',
            },
        }

    @api.model
    def get_open_items_data(self, date_from=None, result_selection='trade',
                            target_move='posted', partner_ids=None):
        """Return open receivable/payable items as of a date using Odoo's native residual fields."""
        self._check_interactive_report_access()
        if result_selection not in ('trade', 'customer', 'supplier'):
            raise UserError(_('Choose a valid partner account type.'))
        if target_move not in ('posted', 'all'):
            raise UserError(_('Choose a valid journal entry state.'))
        date_from = fields.Date.to_date(date_from) if date_from else fields.Date.context_today(self)
        if not isinstance(partner_ids, (list, tuple)):
            partner_ids = []
        try:
            partner_ids = [int(partner_id) for partner_id in partner_ids]
        except (TypeError, ValueError):
            raise UserError(_('Choose valid partners.'))

        account_types = {
            'trade': ['asset_receivable', 'liability_payable'],
            'customer': ['asset_receivable'],
            'supplier': ['liability_payable'],
        }[result_selection]
        move_states = ['posted', 'draft'] if target_move == 'all' else ['posted']
        domain = [
            ('company_id', 'child_of', self.env.company.id),
            ('account_id.account_type', 'in', account_types),
            ('parent_state', 'in', move_states),
            ('date', '<=', date_from),
            ('open_on', '<=', date_from),
            ('partner_id', '!=', False),
        ]
        if partner_ids:
            selected_partners = self.env['res.partner'].search([('id', 'in', partner_ids)])
            if len(selected_partners) != len(set(partner_ids)):
                raise UserError(_('One or more selected partners are unavailable.'))
            domain.append(('partner_id', 'child_of', selected_partners.commercial_partner_id.ids))

        draft_domain = [
            ('company_id', 'child_of', self.env.company.id),
            ('account_id.account_type', 'in', account_types),
            ('parent_state', '=', 'draft'),
            ('date', '<=', date_from),
            ('partner_id', '!=', False),
        ]
        if partner_ids:
            draft_domain.append(('partner_id', 'child_of', selected_partners.commercial_partner_id.ids))
        unposted_count = self.env['account.move.line'].search_count(draft_domain)

        MoveLine = self.env['account.move.line'].with_context(recon_limit=date_from)
        lines = MoveLine.search(domain, order='partner_id, date, id')
        groups = {}
        totals = {'amount': 0.0, 'residual': 0.0}
        for line in lines:
            residual = line.residual_at_date
            residual_currency = line.residual_currency_at_date
            currency = line.currency_id or line.company_currency_id
            if line.company_currency_id.is_zero(residual) and currency.is_zero(residual_currency):
                continue
            partner = line.partner_id.commercial_partner_id
            row = groups.setdefault(partner.id, {
                'partner_id': partner.id,
                'name': partner.display_name,
                'lines': [],
                'amount': 0.0,
                'residual': 0.0,
            })
            move = line.move_id
            row['lines'].append({
                'id': line.id,
                'move_id': move.id,
                'label': move.name or move.ref or line.name or '',
                'no_reminder': line.no_followup,
                'invoice_date': fields.Date.to_string(move.invoice_date or line.date),
                'due_date': fields.Date.to_string(line.date_maturity) if line.date_maturity else '',
                'amount': line.balance,
                'amount_currency': line.amount_currency,
                'residual': residual,
                'residual_currency': residual_currency,
                'currency_id': currency.id,
            })
            row['amount'] += line.balance
            row['residual'] += residual
            totals['amount'] += line.balance
            totals['residual'] += residual

        return {
            'rows': list(groups.values()),
            'totals': totals,
            'date_from': fields.Date.to_string(date_from),
            'result_selection': result_selection,
            'target_move': target_move,
            'currency_id': self.env.company.currency_id.id,
            'unposted_count': unposted_count,
            'can_edit_reminder': self.env.user.has_group('account.group_account_user')
            or self.env.user.has_group('account.group_account_manager'),
            'can_send_reminder': self.env.user.has_group('account.group_account_user')
            or self.env.user.has_group('account.group_account_invoice')
            or self.env.user.has_group('account.group_account_manager'),
            'selected_partners': [
                {'id': partner.id, 'name': partner.display_name}
                for partner in self.env['res.partner'].browse(partner_ids).exists().commercial_partner_id
            ],
        }

    @api.model
    def search_open_items_partners(self, query, result_selection='trade', limit=25):
        self._check_interactive_report_access()
        if not isinstance(query, str) or len(query.strip()) < 2:
            return []
        if result_selection not in ('trade', 'customer', 'supplier'):
            return []
        account_types = {
            'trade': ['asset_receivable', 'liability_payable'],
            'customer': ['asset_receivable'],
            'supplier': ['liability_payable'],
        }[result_selection]
        try:
            limit = min(max(int(limit or 25), 1), 50)
        except (TypeError, ValueError):
            limit = 25
        partners = self.env['account.move.line'].search([
            ('company_id', 'child_of', self.env.company.id),
            ('account_id.account_type', 'in', account_types),
            ('parent_state', 'in', ('posted', 'draft')),
            ('partner_id.name', 'ilike', query.strip()),
        ], limit=limit).mapped('partner_id').commercial_partner_id
        partners = partners.sorted('display_name')
        return [{'id': partner.id, 'name': partner.display_name} for partner in partners[:limit]]

    @api.model
    def set_open_items_no_reminder(self, line_ids, value):
        self._check_interactive_report_access()
        if not isinstance(line_ids, (list, tuple)) or not line_ids:
            raise UserError(_('Choose at least one journal item.'))
        try:
            line_ids = list({int(line_id) for line_id in line_ids})
        except (TypeError, ValueError):
            raise UserError(_('Choose valid journal items.'))
        lines = self.env['account.move.line'].search([
            ('id', 'in', line_ids),
            ('company_id', 'child_of', self.env.company.id),
            ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
        ])
        if len(lines) != len(line_ids):
            raise UserError(_('One or more journal items are unavailable.'))
        lines.write({'no_followup': bool(value)})
        return True

    @api.model
    def get_open_items_partner_action(self, partner_id):
        self._check_interactive_report_access()
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError):
            raise UserError(_('Choose a valid partner.'))
        partner = self.env['res.partner'].search([('id', '=', partner_id)], limit=1)
        if not partner:
            raise UserError(_('The selected partner is unavailable.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Partner'),
            'res_model': 'res.partner',
            'res_id': partner.id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    @api.model
    def get_open_items_journal_action(self, line_ids):
        self._check_interactive_report_access()
        try:
            line_ids = list({int(line_id) for line_id in line_ids or []})
        except (TypeError, ValueError):
            raise UserError(_('Choose valid journal items.'))
        lines = self.env['account.move.line'].search([
            ('id', 'in', line_ids),
            ('company_id', 'child_of', self.env.company.id),
            ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
        ])
        if len(lines) != len(line_ids):
            raise UserError(_('One or more journal items are unavailable.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Items'),
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [('id', 'in', lines.ids)],
            'context': {'create': False},
            'target': 'current',
        }

    @api.model
    def get_open_items_reminder_action(self, partner_id):
        self._check_interactive_report_access()
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_invoice',
            'account.group_account_user',
            'account.group_account_manager',
        )):
            raise AccessError(_('You do not have access to send reminders.'))
        try:
            partner_id = int(partner_id)
        except (TypeError, ValueError):
            raise UserError(_('Choose a valid partner.'))
        partner = self.env['res.partner'].search([('id', '=', partner_id)], limit=1)
        if not partner:
            raise UserError(_('The selected partner is unavailable.'))
        action = self.env.ref('flousflow_accounting.fol__action_followup_send').read()[0]
        action['context'] = {
            **self.env.context,
            'active_model': 'res.partner',
            'active_id': partner.commercial_partner_id.id,
            'active_ids': [partner.commercial_partner_id.id],
        }
        return action

    @api.model
    def print_open_items(self, date_from=None, result_selection='trade',
                         target_move='posted', partner_ids=None):
        data = self.get_open_items_data(
            date_from=date_from,
            result_selection=result_selection,
            target_move=target_move,
            partner_ids=partner_ids,
        )
        return self.env.ref('flousflow_accounting.apr__action_report_open_items').with_context(
            discard_logo_check=True,
        ).report_action(
            self.env['account.move.line'], data={'report_data': data},
        )

    @api.model
    def get_interactive_data(self, result_selection='customer', date_from=None,
                             target_move='posted', period_length=30,
                             partner_ids=None, date_basis='due_date'):
        self._check_interactive_report_access()
        if result_selection not in ('customer', 'supplier', 'customer_supplier'):
            raise UserError(_('Choose a valid partner account type.'))
        if target_move not in ('posted', 'all'):
            raise UserError(_('Choose a valid journal entry state.'))
        if date_basis not in ('due_date', 'invoice_date'):
            raise UserError(_('Choose a valid aging date basis.'))
        try:
            period_length = int(period_length)
        except (TypeError, ValueError):
            period_length = 0
        if period_length <= 0 or period_length > 3660:
            raise UserError(_('Period length must be between 1 and 3660 days.'))
        date_from = fields.Date.to_date(date_from) if date_from else fields.Date.context_today(self)
        account_types = {
            'customer': ['asset_receivable'],
            'supplier': ['liability_payable'],
            'customer_supplier': ['asset_receivable', 'liability_payable'],
        }[result_selection]
        if not isinstance(partner_ids, (list, tuple)):
            partner_ids = []
        partner_ids = [int(partner_id) for partner_id in partner_ids if str(partner_id).isdigit()]
        rows, totals, line_map = self.with_context(company_id=self.env.company.id)._get_partner_move_lines(
            account_types, partner_ids, date_from, target_move, period_length, date_basis=date_basis,
        )
        if partner_ids:
            rows = [row for row in rows if row.get('partner_id') in partner_ids]
        result_rows = []
        for row in rows:
            partner_id = row.get('partner_id') or False
            detail_lines = []
            for detail in line_map.get(partner_id, []):
                move_line = detail['line']
                move = move_line.move_id
                detail_lines.append({
                    'id': move_line.id,
                    'move_id': move.id,
                    'label': move.name or move.ref or move_line.name or '',
                    'invoice_date': fields.Date.to_string(move.invoice_date or move_line.date),
                    'due_date': fields.Date.to_string(move_line.date_maturity) if move_line.date_maturity else '',
                    'period': detail['period'],
                    'amount': detail['amount'],
                })
            result_rows.append({
                'partner_id': partner_id,
                'name': row['name'],
                'not_due': row['direction'],
                # SQL numbers buckets oldest-to-newest; the report UI is newest-first.
                'buckets': [row[str(index)] for index in reversed(range(5))],
                'total': row['total'],
                'lines': detail_lines,
            })
        return {
            'rows': result_rows,
            'totals': {
                'not_due': totals[6],
                'buckets': list(reversed(totals[:5])),
                'total': totals[5],
            },
            'date_from': fields.Date.to_string(date_from),
            'period_length': period_length,
            'date_basis': date_basis,
            'target_move': target_move,
            'result_selection': result_selection,
            'currency_id': self.env.company.currency_id.id,
        }

    @api.model
    def search_interactive_partners(self, query, result_selection='customer', limit=25):
        self._check_interactive_report_access()
        if not isinstance(query, str) or len(query.strip()) < 2:
            return []
        if result_selection not in ('customer', 'supplier', 'customer_supplier'):
            return []
        try:
            limit = min(max(int(limit or 25), 1), 50)
        except (TypeError, ValueError):
            limit = 25
        account_types = {
            'customer': ['asset_receivable'],
            'supplier': ['liability_payable'],
            'customer_supplier': ['asset_receivable', 'liability_payable'],
        }[result_selection]
        partners = self.env['account.move.line'].search([
            ('company_id', 'child_of', self.env.company.id),
            ('account_id.account_type', 'in', account_types),
            ('parent_state', 'in', ('posted', 'draft')),
            ('partner_id.name', 'ilike', query.strip()),
        ], limit=limit).mapped('partner_id')
        return [{'id': partner.id, 'name': partner.display_name} for partner in partners[:limit]]

    @api.model
    def print_interactive_report(self, result_selection='customer', date_from=None,
                                 target_move='posted', period_length=30,
                                 partner_ids=None, date_basis='due_date', scale='unit'):
        self._check_interactive_report_access()
        if result_selection not in ('customer', 'supplier', 'customer_supplier'):
            raise UserError(_('Choose a valid partner account type.'))
        if target_move not in ('posted', 'all'):
            raise UserError(_('Choose a valid journal entry state.'))
        if date_basis not in ('due_date', 'invoice_date'):
            raise UserError(_('Choose a valid aging date basis.'))
        if scale not in ('unit', 'rounded', 'thousand', 'million'):
            raise UserError(_('Choose a valid currency scale.'))
        try:
            period_length = int(period_length)
        except (TypeError, ValueError):
            raise UserError(_('Period length must be between 1 and 3660 days.'))
        if period_length <= 0 or period_length > 3660:
            raise UserError(_('Period length must be between 1 and 3660 days.'))
        date_from = fields.Date.to_date(date_from) if date_from else fields.Date.context_today(self)
        if not isinstance(partner_ids, (list, tuple)):
            partner_ids = []
        partner_ids = [int(partner_id) for partner_id in partner_ids if str(partner_id).isdigit()]
        wizard = self.env['account.aged.trial.balance'].create({
            'result_selection': result_selection,
            'target_move': target_move,
            'date_from': date_from or fields.Date.context_today(self),
            'period_length': period_length,
            'partner_ids': [(6, 0, partner_ids or [])],
            'journal_ids': [(6, 0, self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
        })
        action = wizard.with_context(
            active_model='account.aged.trial.balance',
            active_id=wizard.id,
            date_basis=date_basis,
        ).check_report()
        # Carry the UI scale into the QWeb report without changing the accounting
        # values used by the aged-balance calculation.
        action_data = action.setdefault('data', {})
        action_data.setdefault('form', {})['scale'] = scale
        return action

    @api.model
    def _get_form_company_id(self, form):
        company = form.get('company_id')
        return company[0] if isinstance(company, (list, tuple)) else company or self.env.company.id

    @api.model
    def _get_report_values(self, docids, data=None):
        if (not data.get('form') or not self.env.context.get('active_model')
                or self.env.context.get('active_id') is None):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))

        target_move = data['form'].get('target_move', 'all')
        date_from = data['form'].get('date_from') or fields.Date.context_today(self)

        if data['form']['result_selection'] == 'customer':
            account_type = ['asset_receivable']
        elif data['form']['result_selection'] == 'supplier':
            account_type = ['liability_payable']
        else:
            account_type = ['asset_receivable', 'liability_payable']
        partner_ids = data['form']['partner_ids']
        movelines, total, dummy = self.with_context(
            company_id=self._get_form_company_id(data['form'])
        )._get_partner_move_lines(
            account_type, partner_ids, date_from, target_move, data['form']['period_length'],
            date_basis=self.env.context.get('date_basis', 'due_date'),
        )
        scale = data['form'].get('scale', 'unit')
        scale_divisor = {'unit': 1, 'rounded': 1, 'thousand': 1000, 'million': 1000000}[scale]
        rounding_unit = 'units' if scale == 'rounded' else 'decimals'
        scale_suffix = {'unit': '', 'rounded': '', 'thousand': 'k', 'million': 'M'}[scale]
        company = self.env['res.company'].browse(self._get_form_company_id(data['form']))

        def format_aged_amount(amount):
            return formatLang(
                self.env,
                (amount or 0) / scale_divisor,
                currency_obj=company.currency_id,
                rounding_unit=rounding_unit,
            ) + scale_suffix

        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_partner_lines': movelines,
            'get_direction': total,
            'format_aged_amount': format_aged_amount,
        }
