from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

# movements of an asset over the period, in company currency
MOVEMENT_KEYS = (
    'cost_opening', 'cost_additions', 'cost_disposals', 'cost_closing',
    'depreciation_opening', 'depreciation_acquired', 'depreciation_charge', 'depreciation_disposals',
    'depreciation_closing', 'nbv_opening', 'nbv_closing', 'salvage_value',
)

# categories side by side in one table of the movement statement
STATEMENT_COLUMNS_PER_TABLE = 5


class AssetDepreciationSchedule(models.TransientModel):
    _name = 'asset.depreciation.schedule'
    _description = 'Depreciation Schedule'

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date(string='Start Date', required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string='End Date', required=True, default=lambda self: self._default_date_to())
    category_ids = fields.Many2many(
        'account.asset.category', string='Asset Categories',
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        help="Leave empty to include every asset category.",
    )
    group_by_category = fields.Boolean(string='Group the Register by Category', default=True)
    target_move = fields.Selection(
        [('posted', 'Posted Entries'), ('draft', 'Draft Entries'), ('all', 'All Entries')],
        string='Target Moves', default='posted', required=True,
    )
    excel_report_available = fields.Boolean(compute='_compute_excel_report_available')

    def _compute_excel_report_available(self):
        self.excel_report_available = bool(self._get_excel_report())

    def _get_excel_report(self):
        # the Excel export comes with the Accounting Excel Reports module
        return self.env.ref(
            'accounting_excel_reports.action_report_depreciation_schedule_excel', raise_if_not_found=False)

    def _default_date_from(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_from']

    def _default_date_to(self):
        return self.env.company.compute_fiscalyear_dates(fields.Date.context_today(self))['date_to']

    def _get_assets(self):
        domain = [
            ('company_id', '=', self.company_id.id),
            ('category_id.type', '=', 'purchase'),
            ('state', 'in', ('open', 'paused', 'close')),
            ('date', '<=', self.date_to),
            '|', ('disposal_date', '=', False), ('disposal_date', '>=', self.date_from),
        ]
        if self.category_ids:
            domain.append(('category_id', 'in', self.category_ids.ids))
        return self.env['account.asset.asset'].with_context(active_test=False).search(
            domain, order='category_id, date, id')

    def _get_asset_movements(self, asset):
        """Movements of the cost and accumulated depreciation for this asset and filter."""
        company = self.company_id
        currency = company.currency_id

        def convert(amount, date):
            return asset.currency_id._convert(amount, currency, company, date)

        acquired_before = asset.date < self.date_from
        board_moves = asset._get_board_moves()
        if self.target_move in ('posted', 'draft'):
            board_moves = board_moves.filtered(lambda move: move.state == self.target_move)
        else:
            board_moves = board_moves.filtered(lambda move: move.state != 'cancel')
        partial_disposals = board_moves.filtered(lambda m: m.asset_entry_type == 'partial_disposal')
        # the asset as acquired, before its partial disposals
        cost = convert(asset.value, asset.date) + sum(
            convert(move.asset_disposed_value, asset.date) for move in partial_disposals)
        # depreciation already recorded before the asset was entered in Odoo
        imported = convert(asset.opening_depreciation, asset.date) + sum(
            convert(move.asset_disposed_opening, asset.date) for move in partial_disposals)
        movements = dict.fromkeys(MOVEMENT_KEYS, 0.0)
        movements['cost_opening' if acquired_before else 'cost_additions'] = cost
        movements['depreciation_opening' if acquired_before else 'depreciation_acquired'] = imported
        for move in board_moves.filtered(lambda m: m.date <= self.date_to):
            before_period = move.date < self.date_from and acquired_before
            if move.asset_entry_type == 'partial_disposal':
                disposed_cost, disposed_depreciation = asset._get_disposed_company_amounts(
                    move.asset_disposed_value, move.asset_disposed_opening, -move.asset_depreciation_amount, move.date)
                if before_period:
                    movements['cost_opening'] -= disposed_cost
                    movements['depreciation_opening'] -= disposed_depreciation
                else:
                    movements['cost_disposals'] += disposed_cost
                    movements['depreciation_disposals'] += disposed_depreciation
                continue
            amount = convert(move.asset_depreciation_amount, move.date)
            movements['depreciation_opening' if move.date < self.date_from else 'depreciation_charge'] += amount
        if asset.disposal_date and asset.disposal_date <= self.date_to:
            # what is left of the asset leaves the books
            movements['cost_disposals'] += (
                movements['cost_opening'] + movements['cost_additions'] - movements['cost_disposals'])
            movements['depreciation_disposals'] += (
                movements['depreciation_opening'] + movements['depreciation_acquired']
                + movements['depreciation_charge'] - movements['depreciation_disposals'])
        movements['cost_closing'] = (
            movements['cost_opening'] + movements['cost_additions'] - movements['cost_disposals'])
        movements['depreciation_closing'] = (
            movements['depreciation_opening'] + movements['depreciation_acquired'] + movements['depreciation_charge']
            - movements['depreciation_disposals'])
        movements['nbv_opening'] = movements['cost_opening'] - movements['depreciation_opening']
        movements['nbv_closing'] = movements['cost_closing'] - movements['depreciation_closing']
        movements['salvage_value'] = convert(asset.salvage_value, asset.date) + sum(
            convert(move.asset_disposed_salvage, asset.date) for move in partial_disposals)
        return {key: currency.round(value) for key, value in movements.items()}

    def _get_life_label(self, asset):
        if asset.method_time == 'rate':
            return _('%s %%/yr', asset.method_rate)
        if asset.method_time == 'end':
            return _('until %s', format_date(self.env, asset.method_end))
        return _('%s m', asset.method_number * asset.method_period)

    def _get_register_line(self, asset):
        movements = self._get_asset_movements(asset)
        cost = movements['cost_opening'] + movements['cost_additions']
        depreciable = cost - movements['salvage_value']
        depreciated = (
            movements['depreciation_opening'] + movements['depreciation_acquired'] + movements['depreciation_charge'])
        return {
            'asset': asset,
            'code': asset.code or '',
            'life': self._get_life_label(asset),
            'cost': cost,
            'disposed_nbv': movements['cost_disposals'] - movements['depreciation_disposals'],
            'is_disposed': bool(asset.disposal_date and asset.disposal_date <= self.date_to),
            'is_partly_disposed': bool(movements['cost_disposals']) and not (
                asset.disposal_date and asset.disposal_date <= self.date_to),
            # share of the depreciable value already depreciated at the end of the period (or at the disposal)
            'depreciated_percent': round(100.0 * depreciated / depreciable) if depreciable else 0,
            **movements,
        }

    def _get_schedule_data(self):
        """ :return: dictionary with
            register: list of groups {'name', 'lines', 'totals'} (one group when not grouped by category)
            categories: list of {'name', 'movements'}, one per category
            total: movements of all the assets
        """
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('The start date must be before the end date.'))
        currency = self.company_id.currency_id
        by_category = {}
        for asset in self._get_assets():
            line = self._get_register_line(asset)
            by_category.setdefault(asset.category_id, []).append(line)

        def add_up(lines):
            totals = dict.fromkeys(MOVEMENT_KEYS + ('cost', 'disposed_nbv'), 0.0)
            for line in lines:
                for key in totals:
                    totals[key] += line[key]
            return {key: currency.round(value) for key, value in totals.items()}

        categories = [{'name': category.name, 'movements': add_up(lines)} for category, lines in by_category.items()]
        all_lines = [line for lines in by_category.values() for line in lines]
        if self.group_by_category:
            register = [{'name': category.name, 'lines': lines, 'totals': add_up(lines)}
                        for category, lines in by_category.items()]
        else:
            register = [{'name': _('All Assets'), 'lines': all_lines, 'totals': add_up(all_lines)}] if all_lines else []
        return {'register': register, 'categories': categories, 'total': add_up(all_lines)}

    @api.model
    def get_interactive_metadata(self):
        company = self.env.company
        dates = company.compute_fiscalyear_dates(fields.Date.context_today(self))
        categories = self.env['account.asset.category'].search_read(
            [('type', '=', 'purchase'), ('company_id', '=', company.id)],
            ['name'], order='name, id',
        )
        return {
            'company_name': company.display_name,
            'currency_name': company.currency_id.name,
            'currency_symbol': company.currency_id.symbol,
            'currency_position': company.currency_id.position,
            'currency_digits': company.currency_id.decimal_places,
            'date_from': fields.Date.to_string(dates['date_from']),
            'date_to': fields.Date.to_string(dates['date_to']),
            'categories': categories,
        }

    @api.model
    def get_interactive_period_dates(self, anchor_date):
        dates = self.env.company.compute_fiscalyear_dates(fields.Date.to_date(anchor_date))
        return {
            'date_from': fields.Date.to_string(dates['date_from']),
            'date_to': fields.Date.to_string(dates['date_to']),
        }

    @api.model
    def get_interactive_data(self, date_from, date_to, category_ids=None, target_move='posted'):
        if target_move not in ('posted', 'draft', 'all'):
            raise UserError(_('Unsupported target move filter.'))
        wizard = self.new({
            'company_id': self.env.company.id,
            'date_from': date_from,
            'date_to': date_to,
            'category_ids': [(6, 0, category_ids or [])],
            'target_move': target_move,
            'group_by_category': True,
        })
        schedule = wizard._get_schedule_data()

        def asset_row(line):
            asset = line['asset']
            method_label = dict(asset._fields['method']._description_selection(self.env)).get(
                asset.method, asset.method)
            movements = line
            if asset.method_time == 'rate':
                annual_rate = asset.method_rate
            elif asset.method_time == 'number':
                life_months = asset.method_number * asset.method_period
                annual_rate = 1200.0 / life_months if life_months else 0.0
            elif asset.method_end:
                life_months = asset._get_lifetime_months()
                annual_rate = 1200.0 / life_months if life_months else 0.0
            else:
                annual_rate = 0.0
            return {
                'id': asset.id,
                'category': asset.category_id.display_name,
                'date': fields.Date.to_string(asset.date),
                'method': method_label,
                'rate': annual_rate,
                'asset_opening': movements['cost_opening'],
                'asset_additions': movements['cost_additions'],
                'asset_disposals': movements['cost_disposals'],
                'asset_closing': movements['cost_closing'],
                'depreciation_opening': movements['depreciation_opening'],
                'depreciation_additions': movements['depreciation_acquired'] + movements['depreciation_charge'],
                'depreciation_disposals': movements['depreciation_disposals'],
                'depreciation_closing': movements['depreciation_closing'],
                'nbv_opening': movements['nbv_opening'],
                'nbv_additions': movements['cost_additions'] - movements['depreciation_acquired'],
                'nbv_decrease': movements['depreciation_charge'] + line['disposed_nbv'],
                'nbv_closing': movements['nbv_closing'],
            }

        def group_totals(lines):
            total = self.env.company.currency_id
            amounts = [asset_row(line) for line in lines]
            keys = (
                'asset_opening', 'asset_additions', 'asset_disposals', 'asset_closing',
                'depreciation_opening', 'depreciation_additions', 'depreciation_disposals', 'depreciation_closing',
                'nbv_opening', 'nbv_additions', 'nbv_decrease', 'nbv_closing',
            )
            return {key: total.round(sum(row[key] for row in amounts)) for key in keys}

        return {
            'company_name': wizard.company_id.display_name,
            'currency_name': wizard.company_id.currency_id.name,
            'currency_symbol': wizard.company_id.currency_id.symbol,
            'currency_position': wizard.company_id.currency_id.position,
            'currency_digits': wizard.company_id.currency_id.decimal_places,
            'date_from': fields.Date.to_string(wizard.date_from),
            'date_to': fields.Date.to_string(wizard.date_to),
            'target_move': target_move,
            'groups': [{
                'id': group['lines'][0]['asset'].category_id.id,
                'name': group['name'],
                'rows': [asset_row(line) for line in group['lines']],
                'totals': group_totals(group['lines']),
            } for group in schedule['register']],
            'total': group_totals([line for group in schedule['register'] for line in group['lines']]),
        }

    @api.model
    def action_print_interactive(self, date_from, date_to, category_ids=None, target_move='posted'):
        wizard = self.create({
            'company_id': self.env.company.id,
            'date_from': date_from,
            'date_to': date_to,
            'category_ids': [(6, 0, category_ids or [])],
            'target_move': target_move,
            'group_by_category': True,
        })
        wizard._get_schedule_data()
        return self.env.ref('flousflow_accounting.ast__action_report_depreciation_schedule').report_action(wizard)

    def _get_statement_rows(self, categories):
        """ Rows of the movement statement: (section, label, key, sign). A depreciation reduces the value, so it
        is shown negative. The row of the depreciation recorded before the acquisition only shows when used. """
        date_from = format_date(self.env, self.date_from)
        date_to = format_date(self.env, self.date_to)
        rows = [
            (_('Cost'), _('At %s', date_from), 'cost_opening', 1),
            (_('Cost'), _('Additions'), 'cost_additions', 1),
            (_('Cost'), _('Disposals'), 'cost_disposals', -1),
            (_('Cost'), _('At %s', date_to), 'cost_closing', 1),
            (_('Accumulated depreciation'), _('At %s', date_from), 'depreciation_opening', -1),
            (_('Accumulated depreciation'), _('On acquired assets'), 'depreciation_acquired', -1),
            (_('Accumulated depreciation'), _('Charge for the period'), 'depreciation_charge', -1),
            (_('Accumulated depreciation'), _('Disposals'), 'depreciation_disposals', 1),
            (_('Accumulated depreciation'), _('At %s', date_to), 'depreciation_closing', -1),
            (_('Net book value'), _('At %s', date_from), 'nbv_opening', 1),
            (_('Net book value'), _('At %s', date_to), 'nbv_closing', 1),
        ]
        if not any(category['movements']['depreciation_acquired'] for category in categories):
            rows = [row for row in rows if row[2] != 'depreciation_acquired']
        return rows

    def _get_statement_tables(self, categories, total):
        """ The categories split in tables narrow enough for the page, the total in the last one. """
        columns = [(category['name'], category['movements']) for category in categories]
        tables = [columns[index:index + STATEMENT_COLUMNS_PER_TABLE]
                  for index in range(0, len(columns), STATEMENT_COLUMNS_PER_TABLE)] or [[]]
        tables[-1] = tables[-1] + [(_('Total'), total)]
        return tables

    def action_print_excel(self):
        self.ensure_one()
        report = self._get_excel_report()
        if not report:
            raise UserError(_('Install the Accounting Excel Reports module to export the schedule to Excel.'))
        # checks the dates before the download starts
        self._get_schedule_data()
        return report.report_action(self, config=False)

    def action_print(self):
        self.ensure_one()
        return self.env.ref('flousflow_accounting.ast__action_report_depreciation_schedule').report_action(self)


class ReportDepreciationSchedule(models.AbstractModel):
    _name = 'report.flousflow_accounting.ast__report_depreciation_schedule'
    _description = 'Depreciation Schedule Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['asset.depreciation.schedule'].browse(docids)
        schedule = wizard._get_schedule_data()
        return {
            'doc_ids': docids,
            'doc_model': 'asset.depreciation.schedule',
            'docs': wizard,
            'schedule': schedule,
            'statement_rows': wizard._get_statement_rows(schedule['categories']),
            'statement_tables': wizard._get_statement_tables(schedule['categories'], schedule['total']),
            'currency': wizard.company_id.currency_id,
        }
