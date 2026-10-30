from datetime import timedelta

from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountDeferredScheduleReport(models.AbstractModel):
    _name = "account.deferred.schedule.report"
    _description = "Deferred Expense and Revenue Report"

    @api.model
    def _check_report_access(self):
        if not any(self.env.user.has_group(group) for group in (
            "account.group_account_readonly",
            "account.group_account_invoice",
            "account.group_account_user",
            "account.group_account_manager",
        )):
            raise AccessError(_("You are not allowed to read deferred schedule reports."))

    @api.model
    def _get_period_ranges(
        self, period_type="month", period=None, period_anchor=None,
        date_from=None, date_to=None, comparison_periods=0,
    ):
        if period_type not in ("month", "quarter", "fiscal_year", "custom"):
            raise ValidationError(_("Choose a valid reporting period."))
        try:
            anchor = fields.Date.to_date(period_anchor)
            if not anchor and period:
                anchor = fields.Date.to_date(f"{period}-01")
            anchor = anchor or fields.Date.context_today(self)
        except (TypeError, ValueError):
            raise ValidationError(_("Choose a valid reporting period."))

        if period_type == "custom":
            try:
                current_from = fields.Date.to_date(date_from)
                current_to = fields.Date.to_date(date_to)
            except (TypeError, ValueError):
                current_from = current_to = False
            if not current_from or not current_to or current_from > current_to:
                raise ValidationError(_("Choose a valid custom date range."))
            duration = (current_to - current_from).days + 1
        elif period_type == "month":
            current_from = anchor.replace(day=1)
            current_to = current_from + relativedelta(months=1, days=-1)
        elif period_type == "quarter":
            current_from = anchor.replace(month=((anchor.month - 1) // 3) * 3 + 1, day=1)
            current_to = current_from + relativedelta(months=3, days=-1)
        else:
            fiscal_dates = self.env.company.compute_fiscalyear_dates(anchor)
            current_from = fiscal_dates["date_from"]
            current_to = fiscal_dates["date_to"]

        ranges = []
        for offset in range(comparison_periods + 1):
            if offset == 0:
                start, end = current_from, current_to
            elif period_type == "month":
                start = current_from - relativedelta(months=offset)
                end = start + relativedelta(months=1, days=-1)
            elif period_type == "quarter":
                start = current_from - relativedelta(months=3 * offset)
                end = start + relativedelta(months=3, days=-1)
            elif period_type == "fiscal_year":
                previous_anchor = current_from - relativedelta(years=offset)
                fiscal_dates = self.env.company.compute_fiscalyear_dates(previous_anchor)
                start, end = fiscal_dates["date_from"], fiscal_dates["date_to"]
            else:
                end = current_from - timedelta(days=(duration * (offset - 1) + 1))
                start = end - timedelta(days=duration - 1)
            key = f"{fields.Date.to_string(start)}:{fields.Date.to_string(end)}"
            if period_type == "month":
                label = start.strftime("%B %Y")
            elif period_type == "quarter":
                label = f"Q{((start.month - 1) // 3) + 1} {start.year}"
            elif period_type == "fiscal_year":
                label = str(start.year)
            else:
                label = f"{fields.Date.to_string(start)} – {fields.Date.to_string(end)}"
            ranges.append({
                "key": key,
                "date_from": fields.Date.to_string(start),
                "date_to": fields.Date.to_string(end),
                "label": label,
            })
        return ranges

    @api.model
    def _get_period_dates(self, period):
        """Keep the earlier month-only drill-down contract available."""
        period_range = self._get_period_ranges("month", period=period)[0]
        return fields.Date.to_date(period_range["date_from"]), fields.Date.to_date(period_range["date_to"])

    @api.model
    def _validate_filters(self, report_type, group_by, target_move):
        if report_type not in ("expense", "revenue"):
            raise ValidationError(_("Unsupported deferred report."))
        if group_by not in ("account", "category", "product"):
            raise ValidationError(_("Unsupported grouping."))
        if target_move not in ("posted", "all"):
            raise ValidationError(_("Unsupported journal entry filter."))

    @api.model
    def _get_move_domain(self, report_type, date_from, date_to, target_move):
        asset_type = "purchase" if report_type == "expense" else "sale"
        domain = [
            ("company_id", "=", self.env.company.id),
            ("date", ">=", date_from),
            ("date", "<=", date_to),
            ("depreciation_asset_id", "!=", False),
            ("depreciation_asset_id.category_id.type", "=", asset_type),
            ("asset_entry_type", "=", "depreciation"),
            ("state", "!=", "cancel"),
        ]
        if target_move == "posted":
            domain.append(("state", "=", "posted"))
        return domain

    @api.model
    def _get_group(self, report_type, group_by, asset, account):
        if group_by == "account":
            group = account
        elif group_by == "category":
            group = asset.category_id
        else:
            group = asset.invoice_line_id.product_id or asset
        if not group:
            return False, False, False, False
        group_model = group._name
        return f"{group_by}:{group_model}:{group.id}", group.id, group.display_name, group_model

    @api.model
    def _collect_periods(self, report_type, periods, group_by, target_move, journal_ids):
        oldest_start = min(fields.Date.to_date(period["date_from"]) for period in periods)
        current_end = max(fields.Date.to_date(period["date_to"]) for period in periods)
        domain = self._get_move_domain(report_type, oldest_start, current_end, target_move)
        if journal_ids:
            domain.append(("journal_id", "in", journal_ids))
        moves = self.env["account.move"].search(domain, order="date, name, id")
        rows_by_period = {period["key"]: {} for period in periods}
        if not moves:
            return rows_by_period

        asset_by_id = {asset.id: asset for asset in moves.depreciation_asset_id}
        if report_type == "expense":
            account_by_asset = {
                asset_id: asset.category_id.account_depreciation_expense_id.id
                for asset_id, asset in asset_by_id.items()
            }
            sign = 1
        else:
            account_by_asset = {
                asset_id: asset.category_id.account_depreciation_id.id
                for asset_id, asset in asset_by_id.items()
            }
            sign = -1
        account_ids = list({account_id for account_id in account_by_asset.values() if account_id})
        lines = self.env["account.move.line"].search([
            ("move_id", "in", moves.ids),
            ("account_id", "in", account_ids),
            ("company_id", "=", self.env.company.id),
        ]) if account_ids else self.env["account.move.line"]

        recognized_by_move = {}
        account_by_move = {}
        for line in lines:
            asset_id = line.move_id.depreciation_asset_id.id
            if line.account_id.id != account_by_asset.get(asset_id):
                continue
            recognized_by_move[line.move_id.id] = recognized_by_move.get(line.move_id.id, 0.0) + sign * line.balance
            account_by_move[line.move_id.id] = line.account_id

        for move in moves:
            asset = asset_by_id.get(move.depreciation_asset_id.id)
            account = account_by_move.get(move.id)
            key, group_id, name, group_model = self._get_group(report_type, group_by, asset, account)
            if not key:
                continue
            period = next(
                (period for period in periods
                 if fields.Date.to_date(period["date_from"]) <= move.date <= fields.Date.to_date(period["date_to"])),
                None,
            )
            if not period:
                continue
            rows = rows_by_period[period["key"]]
            row = rows.setdefault(key, {
                "key": key,
                "group_id": group_id,
                "group_model": group_model,
                "name": name,
                "amount": 0.0,
                "entries": 0,
                "move_ids": [],
                "details": {},
            })
            move_amount = recognized_by_move.get(move.id, 0.0)
            row["amount"] += move_amount
            row["entries"] += 1
            row["move_ids"].append(move.id)
            detail = row["details"].setdefault(asset.id, {
                "key": f"asset:{asset.id}",
                "asset_id": asset.id,
                "name": asset.display_name,
                "amount": 0.0,
                "entries": 0,
            })
            detail["amount"] += move_amount
            detail["entries"] += 1
        return rows_by_period

    @api.model
    def get_report_data(
        self, report_type, period, group_by="account", target_move="posted",
        compare_previous=False, hide_zero=False, journal_ids=None,
        comparison_periods=None, comparison_mode="amount", sort_order="desc",
        period_type="month", period_anchor=None, date_from=None, date_to=None,
    ):
        """Aggregate the local asset/revenue-recognition board using posted journal amounts."""
        self._check_report_access()
        self._validate_filters(report_type, group_by, target_move)
        journal_ids = self._validate_journals(journal_ids)
        if comparison_periods is None:
            comparison_periods = 1 if compare_previous else 0
        try:
            comparison_periods = int(comparison_periods)
        except (TypeError, ValueError):
            raise ValidationError(_("Choose a valid number of comparison periods."))
        if not 0 <= comparison_periods <= 120:
            raise ValidationError(_("The number of comparison periods must be between 0 and 120."))
        if comparison_mode not in ("amount", "percentage"):
            raise ValidationError(_("Unsupported comparison method."))
        if sort_order not in ("asc", "desc"):
            raise ValidationError(_("Unsupported report sort order."))
        period_ranges = self._get_period_ranges(
            period_type, period, period_anchor, date_from, date_to, comparison_periods
        )
        period_keys = [period_range["key"] for period_range in period_ranges]
        period_rows = self._collect_periods(
            report_type, period_ranges, group_by, target_move, journal_ids
        )
        current_key = period_keys[0]
        current = period_rows[current_key]
        currency = self.env.company.currency_id
        rows = []
        all_keys = set().union(*(period_data.keys() for period_data in period_rows.values()))
        for key in all_keys:
            now = current.get(key, {})
            before = period_rows.get(period_keys[1], {}).get(key, {}) if comparison_periods else {}
            amount = now.get("amount", 0.0)
            previous_amount = before.get("amount", 0.0)
            period_values = {
                period_key: period_rows[period_key].get(key, {}).get("amount", 0.0)
                for period_key in period_keys
            }
            details_by_asset = {}
            for period_key in period_keys:
                for asset_id, period_detail in period_rows[period_key].get(key, {}).get("details", {}).items():
                    detail = details_by_asset.setdefault(asset_id, {
                        "key": period_detail["key"],
                        "asset_id": asset_id,
                        "name": period_detail["name"],
                        "period_entries": {key: 0 for key in period_keys},
                        "period_values": {key: 0.0 for key in period_keys},
                    })
                    detail["period_entries"][period_key] = period_detail["entries"]
                    detail["period_values"][period_key] = period_detail["amount"]
            period_move_ids = {
                period_key: period_rows[period_key].get(key, {}).get("move_ids", [])
                for period_key in period_keys
            }
            if hide_zero and all(currency.is_zero(value) for value in period_values.values()):
                continue
            base = now or next(
                period_rows[period_key][key]
                for period_key in period_keys[1:]
                if key in period_rows[period_key]
            )
            comparison_values = {}
            for period_key in period_keys[1:]:
                compared_amount = period_values[period_key]
                if comparison_mode == "percentage":
                    comparison_values[period_key] = (
                        ((amount - compared_amount) / abs(compared_amount)) * 100
                        if not currency.is_zero(compared_amount)
                        else (0.0 if currency.is_zero(amount) else None)
                    )
                else:
                    comparison_values[period_key] = amount - compared_amount
            detail_rows = []
            for detail in details_by_asset.values():
                detail_values = detail["period_values"]
                detail_comparison_values = {}
                for period_key in period_keys[1:]:
                    compared_amount = detail_values[period_key]
                    detail_comparison_values[period_key] = (
                        ((detail_values[current_key] - compared_amount) / abs(compared_amount)) * 100
                        if comparison_mode == "percentage" and not currency.is_zero(compared_amount)
                        else (0.0 if currency.is_zero(detail_values[current_key]) else None)
                        if comparison_mode == "percentage"
                        else detail_values[current_key] - compared_amount
                    )
                if hide_zero and all(currency.is_zero(value) for value in detail_values.values()):
                    continue
                detail_rows.append({
                    **detail,
                    "amount": detail_values[current_key],
                    "entries": detail["period_entries"][current_key],
                    "comparison_values": detail_comparison_values,
                })
            detail_rows.sort(key=lambda detail: detail["name"].casefold())
            sort_value = (
                comparison_values.get(period_keys[1], amount)
                if comparison_periods else amount
            )
            rows.append({
                "key": key,
                "group_id": base["group_id"],
                "group_model": base["group_model"],
                "name": base["name"],
                "entries": now.get("entries", 0),
                "amount": amount,
                "previous_amount": previous_amount,
                "period_values": period_values,
                "period_move_ids": period_move_ids,
                "comparison_values": comparison_values,
                "sort_value": sort_value,
                "move_ids": period_move_ids.get(current_key, []),
                "details": detail_rows,
            })
        rows.sort(key=lambda row: (
            row["sort_value"] is None,
            (
                -row["sort_value"] if sort_order == "desc" else row["sort_value"]
            ) if row["sort_value"] is not None else 0.0,
            row["name"].casefold(),
        ))
        return {
            "report_type": report_type,
            "period": period_ranges[0]["key"],
            "period_type": period_type,
            "period_anchor": period_ranges[0]["date_from"],
            "date_from": period_ranges[0]["date_from"],
            "date_to": period_ranges[0]["date_to"],
            "periods": period_ranges,
            "current_period_key": current_key,
            "comparison_periods": comparison_periods,
            "comparison_mode": comparison_mode,
            "sort_order": sort_order,
            "previous_period": period_keys[1] if comparison_periods else False,
            "group_by": group_by,
            "rows": rows,
            "currency_id": currency.id,
            "company_name": self.env.company.display_name,
            "journals": [
                {"id": journal.id, "name": journal.display_name}
                for journal in self.env["account.journal"].search([
                    ("company_id", "=", self.env.company.id),
                    ("type", "in", ("general", "purchase", "sale", "bank", "cash")),
                ], order="sequence, name, id")
            ],
        }

    @api.model
    def _validate_journals(self, journal_ids):
        try:
            ids = sorted({int(journal_id) for journal_id in (journal_ids or [])})
        except (TypeError, ValueError):
            raise ValidationError(_("Choose valid journals."))
        journals = self.env["account.journal"].search([
            ("id", "in", ids),
            ("company_id", "=", self.env.company.id),
        ]) if ids else self.env["account.journal"]
        if ids and set(ids) != set(journals.ids):
            raise AccessError(_("One or more selected journals are outside the active company."))
        return ids

    @api.model
    def get_group_move_domain(
        self, report_type, period, group_by, group_id, target_move="posted",
        group_model=None, journal_ids=None, date_to=None,
    ):
        self._check_report_access()
        self._validate_filters(report_type, group_by, target_move)
        journal_ids = self._validate_journals(journal_ids)
        if date_to:
            try:
                date_from = fields.Date.to_date(period)
                date_to = fields.Date.to_date(date_to)
            except (TypeError, ValueError):
                date_from = date_to = False
            if not date_from or not date_to or date_from > date_to:
                raise ValidationError(_("Choose a valid reporting period."))
        else:
            date_from, date_to = self._get_period_dates(period)
        domain = self._get_move_domain(report_type, date_from, date_to, target_move)
        if journal_ids:
            domain.append(("journal_id", "in", journal_ids))
        group_id = int(group_id)
        if group_by == "category":
            domain.append(("depreciation_asset_id.category_id", "=", group_id))
        elif group_by == "product":
            if group_model == "product.product":
                domain.append(("depreciation_asset_id.invoice_line_id.product_id", "=", group_id))
            else:
                domain.append(("depreciation_asset_id", "=", group_id))
        else:
            account_field = "account_depreciation_expense_id" if report_type == "expense" else "account_depreciation_id"
            domain.append((f"depreciation_asset_id.category_id.{account_field}", "=", group_id))
        return domain
