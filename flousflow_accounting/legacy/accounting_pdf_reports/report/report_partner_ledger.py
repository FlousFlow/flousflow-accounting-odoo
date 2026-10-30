import time
from odoo import api, models, _
from odoo.exceptions import AccessError, UserError, ValidationError


# the amounts the report sums, as the template asks for them
SUMMED_FIELDS = ('debit', 'credit', 'debit - credit')
# the template asks for the lines partner by partner: they are read for this many partners at once
LINES_BATCH = 500


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.flousflow_accounting.apr__report_partnerledger'
    _description = 'Partner Ledger Report'

    @api.model
    def get_interactive_data(self, period_type='fiscal_year', period_anchor=None,
                             custom_date_from=None, custom_date_to=None,
                             target_move='posted', partner_ids=None,
                             account_scope='trade', partner_tag_ids=None):
        """Return the interactive Partner Ledger using the same posted move lines as the PDF."""
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_readonly', 'account.group_account_invoice',
            'account.group_account_user', 'account.group_account_manager',
        )):
            raise AccessError(_('You are not allowed to view the Partner Ledger.'))
        if target_move not in ('posted', 'all'):
            raise ValidationError(_('Choose a valid journal entry state.'))
        if account_scope not in ('trade', 'receivable', 'payable'):
            raise ValidationError(_('Choose a valid partner account type.'))
        date_from, date_to = self.env[
            'report.flousflow_accounting.apr__report_general_ledger'
        ]._get_interactive_period_dates(
            period_type, period_anchor, custom_date_from, custom_date_to
        )
        company = self.env.company
        companies = self.env['res.company'].search([('id', 'child_of', company.id)])
        account_types = {
            'trade': ('asset_receivable', 'liability_payable'),
            'receivable': ('asset_receivable',),
            'payable': ('liability_payable',),
        }[account_scope]
        accounts = self.env['account.account'].search([
            ('company_ids', 'in', companies.ids), ('active', '=', True),
            ('account_type', 'in', account_types),
        ])
        domain = [
            ('company_id', 'in', companies.ids), ('account_id', 'in', accounts.ids),
            ('partner_id', '!=', False), ('date', '>=', date_from), ('date', '<=', date_to),
            ('parent_state', 'in', ('posted', 'draft') if target_move == 'all' else ('posted',)),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if partner_ids:
            try:
                ids = list({int(value) for value in partner_ids})
            except (TypeError, ValueError):
                raise ValidationError(_('Invalid partner selection.'))
            found = self.env['res.partner'].search([('id', 'in', ids)])
            if len(found) != len(ids):
                raise ValidationError(_('One or more selected partners are unavailable.'))
            domain.append(('partner_id.commercial_partner_id', 'in', found.mapped('commercial_partner_id').ids))
        if partner_tag_ids:
            try:
                tag_ids = list({int(value) for value in partner_tag_ids})
            except (TypeError, ValueError):
                raise ValidationError(_('Invalid partner tag selection.'))
            tags = self.env['res.partner.category'].search([('id', 'in', tag_ids)])
            if len(tags) != len(tag_ids):
                raise ValidationError(_('One or more selected partner tags are unavailable.'))
            domain.append(('partner_id.commercial_partner_id.category_id', 'in', tags.ids))

        MoveLine = self.env['account.move.line']
        grouped = MoveLine._read_group(
            domain, groupby=['partner_id'], aggregates=['debit:sum', 'credit:sum']
        )
        partner_totals = {}
        for partner_record, debit, credit in grouped:
            partner = partner_record.commercial_partner_id
            totals = partner_totals.setdefault(partner.id, {'debit': 0.0, 'credit': 0.0})
            totals['debit'] += debit or 0.0
            totals['credit'] += credit or 0.0
        partners = self.env['res.partner'].browse(list(partner_totals)).sorted(
            lambda partner: (partner.name or '').casefold()
        )
        draft_count = 0
        if target_move == 'posted':
            journals = self.env['account.journal'].search([('company_id', 'in', companies.ids)])
            draft_count = self.env['account.move'].search_count([
                ('state', '=', 'draft'),
                ('company_id', 'in', companies.ids),
                ('journal_id', 'in', journals.ids),
                ('date', '<=', date_to),
            ])
        return {
            'partners': [{
                'id': partner.id,
                'name': partner.display_name,
                'debit': partner_totals[partner.id]['debit'],
                'credit': partner_totals[partner.id]['credit'],
                'balance': partner_totals[partner.id]['debit'] - partner_totals[partner.id]['credit'],
                'lines': [],
            } for partner in partners],
            'date_from': date_from, 'date_to': date_to,
            'company_ids': companies.ids, 'currency_id': company.currency_id.id,
            'company_name': company.name, 'target_move': target_move,
            'draft_count': draft_count,
        }

    @api.model
    def get_partner_filter_options(self, partner_ids=None):
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_readonly', 'account.group_account_invoice',
            'account.group_account_user', 'account.group_account_manager',
        )):
            raise AccessError(_('You are not allowed to view the Partner Ledger.'))
        try:
            ids = list({int(value) for value in (partner_ids or [])})
        except (TypeError, ValueError):
            raise ValidationError(_('Invalid partner selection.'))
        companies = self.env['res.company'].search([('id', 'child_of', self.env.company.id)])
        domain = [('parent_id', '=', False), ('company_id', 'in', [False] + companies.ids)]
        if ids:
            partners = self.env['res.partner'].search(domain + [('id', 'in', ids)])
            if len(partners) != len(ids):
                raise ValidationError(_('One or more selected partners are unavailable.'))
        else:
            partners = self.env['res.partner']
        tags = self.env['res.partner.category'].search([], order='name', limit=200)
        return {
            'partners': [{'id': partner.id, 'name': partner.display_name} for partner in partners],
            'tags': [{'id': tag.id, 'name': tag.name} for tag in tags],
        }

    @api.model
    def search_interactive_partners(self, query, limit=40):
        if not any(self.env.user.has_group(group) for group in (
            'account.group_account_readonly', 'account.group_account_invoice',
            'account.group_account_user', 'account.group_account_manager',
        )):
            raise AccessError(_('You are not allowed to view the Partner Ledger.'))
        try:
            limit = min(max(int(limit or 40), 1), 100)
        except (TypeError, ValueError):
            limit = 40
        if not isinstance(query, str) or len(query.strip()) < 2:
            return []
        companies = self.env['res.company'].search([('id', 'child_of', self.env.company.id)])
        partners = self.env['res.partner'].search([
            ('parent_id', '=', False), ('company_id', 'in', [False] + companies.ids),
            ('name', 'ilike', query.strip()),
        ], order='name', limit=limit)
        return [{'id': partner.id, 'name': partner.display_name} for partner in partners]

    @api.model
    def get_interactive_partner_lines(self, partner_id, date_from, date_to,
                                      target_move='posted', account_scope='trade'):
        """Load details only after a partner row is expanded."""
        data = self.get_interactive_data(
            period_type='custom', custom_date_from=date_from, custom_date_to=date_to,
            target_move=target_move, partner_ids=[partner_id], account_scope=account_scope,
        )
        partner = self.env['res.partner'].browse(int(partner_id)).commercial_partner_id
        company_ids = data['company_ids']
        account_types = {
            'trade': ('asset_receivable', 'liability_payable'),
            'receivable': ('asset_receivable',), 'payable': ('liability_payable',),
        }[account_scope]
        domain = [
            ('company_id', 'in', company_ids), ('account_id.account_type', 'in', account_types),
            ('account_id.active', '=', True), ('partner_id.commercial_partner_id', '=', partner.id),
            ('date', '>=', date_from), ('date', '<=', date_to),
            ('parent_state', 'in', ('posted', 'draft') if target_move == 'all' else ('posted',)),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        lines = self.env['account.move.line'].search(domain, order='date, move_id, id')
        running = 0.0
        result = []
        for line in lines:
            running += line.debit - line.credit
            result.append({
                'id': line.id, 'move_id': line.move_id.id, 'date': line.date,
                'due_date': line.date_maturity, 'journal': line.journal_id.name,
                'account': line.account_id.code,
                'matching': line.matching_number or '',
                'label': line.move_id.name or line.move_id.ref or line.name or '',
                'debit': line.debit, 'credit': line.credit, 'balance': running,
                'amount_currency': line.amount_currency,
                'currency_id': line.currency_id.id if line.currency_id else False,
            })
        return result

    def _lines(self, data, partner):
        return self._lines_by_partner(data, partner.ids)[partner.id]

    def _lines_by_partner(self, data, partner_ids):
        """ The journal items of the partners, by partner, in one query """
        full_account = {partner_id: [] for partner_id in partner_ids}
        if not partner_ids:
            return full_account
        currency = self.env['res.currency']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        lang_code = self.env.context.get('lang') or 'en_US'
        params = ([lang_code, tuple(partner_ids), tuple(data['computed']['move_state']),
                   tuple(data['computed']['account_ids'])] + query_get_data[2])
        query = ("""
            SELECT "account_move_line".id, "account_move_line".partner_id, "account_move_line".date, j.code, COALESCE(acc.name->>%s, acc.name->>'en_US') as a_name, """
                 '''"account_move_line".ref, m.name as move_name, "account_move_line".name, '''
                 '''"account_move_line".debit, "account_move_line".credit, "account_move_line".amount_currency,'''
                 '''"account_move_line".currency_id, c.symbol AS currency_code
            FROM ''' + query_get_data[0] + """
            LEFT JOIN account_journal j ON ("account_move_line".journal_id = j.id)
            LEFT JOIN account_account acc ON ("account_move_line".account_id = acc.id)
            LEFT JOIN res_currency c ON ("account_move_line".currency_id=c.id)
            LEFT JOIN account_move m ON (m.id="account_move_line".move_id)
            WHERE "account_move_line".partner_id IN %s
                AND m.state IN %s
                AND "account_move_line".account_id IN %s AND """ + query_get_data[1] + reconcile_clause + """
                ORDER BY "account_move_line".date, "account_move_line".move_id, "account_move_line".id""")
        self.env.cr.execute(query, tuple(params))
        progress = dict.fromkeys(partner_ids, 0.0)
        for r in self.env.cr.dictfetchall():
            partner_id = r.pop('partner_id')
            # move name, reference and label often repeat each other - the label
            # frequently ends with the move name - so anything a part already says is
            # dropped rather than printed twice
            parts = []
            for field_name in ('move_name', 'ref', 'name'):
                value = (r[field_name] or '').strip()
                if value in ('', '/') or any(value in kept for kept in parts):
                    continue
                parts = [kept for kept in parts if kept not in value]
                parts.append(value)
            r['displayed_name'] = ' - '.join(parts)
            progress[partner_id] += r['debit'] - r['credit']
            r['progress'] = progress[partner_id]
            r['currency_id'] = currency.browse(r.get('currency_id'))
            full_account[partner_id].append(r)
        return full_account

    def _sum_partner(self, data, partner, field):
        if field not in SUMMED_FIELDS:
            return
        return self._sum_by_partner(data, partner.ids)[partner.id][field]

    def _confirmation_closing_balance(self, data, partner):
        """Return the partner's cumulative selected-account balance through date_to."""
        form = data['form']
        context = dict(form.get('used_context', {}))
        context.pop('date_from', None)
        context.pop('strict_range', None)
        context.pop('initial_bal', None)
        context['date_to'] = form['date_to']
        move_line_model = self.env['account.move.line'].with_context(context)
        query_data = move_line_model._query_get([
            ('partner_id.commercial_partner_id', '=', partner.commercial_partner_id.id),
            ('account_id', 'in', data['computed']['account_ids']),
        ])
        self.env.cr.execute(
            'SELECT COALESCE(sum("account_move_line".debit - "account_move_line".credit), 0) '
            'FROM %s WHERE %s' % (query_data[0], query_data[1]),
            tuple(query_data[2]),
        )
        return self.env.cr.fetchone()[0]

    def _sum_by_partner(self, data, partner_ids):
        """ The debit, the credit and the balance of the partners, in one query """
        result = {partner_id: dict.fromkeys(SUMMED_FIELDS, 0.0) for partner_id in partner_ids}
        if not partner_ids:
            return result
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '

        params = ([tuple(partner_ids), tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])]
                  + query_get_data[2])
        # the columns are qualified: the domain may join a table holding the same ones,
        # which PostgreSQL then refuses as an ambiguous reference
        query = """SELECT "account_move_line".partner_id,
                    COALESCE(sum("account_move_line".debit), 0),
                    COALESCE(sum("account_move_line".credit), 0),
                    COALESCE(sum("account_move_line".debit - "account_move_line".credit), 0)
                FROM """ + query_get_data[0] + """, account_move AS m
                WHERE "account_move_line".partner_id IN %s
                    AND m.id = "account_move_line".move_id
                    AND m.state IN %s
                    AND "account_move_line".account_id IN %s
                    AND """ + query_get_data[1] + reconcile_clause + """
                GROUP BY "account_move_line".partner_id"""
        self.env.cr.execute(query, tuple(params))
        for partner_id, debit, credit, balance in self.env.cr.fetchall():
            result[partner_id] = {'debit': debit, 'credit': credit, 'debit - credit': balance}
        return result

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        data['computed'] = {}

        obj_partner = self.env['res.partner']
        query_get_data = self.env['account.move.line'].with_context(data['form'].get('used_context', {}))._query_get()
        data['computed']['move_state'] = ['draft', 'posted']
        if data['form'].get('target_move', 'all') == 'posted':
            data['computed']['move_state'] = ['posted']
        result_selection = data['form'].get('result_selection', 'customer')
        if result_selection == 'supplier':
            data['computed']['ACCOUNT_TYPE'] = ['liability_payable']
        elif result_selection == 'customer':
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable']
        else:
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable', 'liability_payable']

        self.env.cr.execute("""
            SELECT a.id
            FROM account_account a
            WHERE a.account_type IN %s
            AND a.active""", (tuple(data['computed']['ACCOUNT_TYPE']),))
        data['computed']['account_ids'] = [a for (a,) in self.env.cr.fetchall()]
        params = [tuple(data['computed']['move_state']), tuple(data['computed']['account_ids'])] + query_get_data[2]
        reconcile_clause = "" if data['form']['reconciled'] else ' AND "account_move_line".full_reconcile_id IS NULL '
        query = """
            SELECT DISTINCT "account_move_line".partner_id
            FROM """ + query_get_data[0] + """, account_account AS account, account_move AS am
            WHERE "account_move_line".partner_id IS NOT NULL
                AND "account_move_line".account_id = account.id
                AND am.id = "account_move_line".move_id
                AND am.state IN %s
                AND "account_move_line".account_id IN %s
                AND account.active
                AND """ + query_get_data[1] + reconcile_clause
        self.env.cr.execute(query, tuple(params))
        if data['form']['partner_ids']:
            partner_ids = data['form']['partner_ids']
        else:
            partner_ids = [res['partner_id'] for res in
                           self.env.cr.dictfetchall()]
        partners = obj_partner.browse(partner_ids)
        partners = sorted(partners, key=lambda x: (x.ref or '', x.name or ''))

        # the template asks for the amounts and the lines of each partner: they are read
        # beforehand, in a few queries instead of a few for each partner
        sums = self._sum_by_partner(data, [partner.id for partner in partners])
        position = {partner.id: index for index, partner in enumerate(partners)}
        batch = {}

        def lines(data, partner):
            if partner.id not in batch:
                start = position.get(partner.id)
                if start is None:
                    return self._lines(data, partner)
                batch.clear()
                batch.update(self._lines_by_partner(
                    data, [p.id for p in partners[start:start + LINES_BATCH]]))
            return batch.pop(partner.id)

        def sum_partner(data, partner, field):
            if field not in SUMMED_FIELDS:
                return
            if partner.id not in sums:
                return self._sum_partner(data, partner, field)
            return sums[partner.id][field]

        return {
            'doc_ids': partner_ids,
            'doc_model': self.env['res.partner'],
            'data': data,
            'docs': partners,
            'time': time,
            'lines': lines,
            'sum_partner': sum_partner,
            'confirmation_closing_balance': lambda partner: self._confirmation_closing_balance(
                data, partner
            ),
        }
