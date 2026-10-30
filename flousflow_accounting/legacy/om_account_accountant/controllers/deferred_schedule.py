from io import BytesIO

import xlsxwriter
from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition
from werkzeug.exceptions import Forbidden, NotFound

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
READ_GROUPS = (
    "account.group_account_readonly",
    "account.group_account_invoice",
    "account.group_account_user",
    "account.group_account_manager",
)


class DeferredScheduleController(Controller):

    @route("/om_account_accountant/deferred_schedule/xlsx", type="http", auth="user")
    def deferred_schedule_xlsx(
        self, report_type=None, period=None, group_by="account", target_move="posted",
        compare_previous="0", hide_zero="0", scale="1", journal_ids="",
        comparison_periods=None, comparison_mode="amount", sort_order="desc",
        period_type="month", period_anchor=None, date_from=None, date_to=None, **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if report_type not in ("expense", "revenue"):
            raise NotFound()
        try:
            scale = int(scale)
        except (TypeError, ValueError):
            raise NotFound()
        if scale not in (1, 1000, 1000000):
            raise NotFound()

        compare_previous = compare_previous in ("1", "true", "True")
        hide_zero = hide_zero in ("1", "true", "True")
        if comparison_periods in (None, ""):
            comparison_periods = 1 if compare_previous else 0
        try:
            comparison_periods = int(comparison_periods)
        except (TypeError, ValueError):
            raise NotFound()
        if not 0 <= comparison_periods <= 120:
            raise NotFound()
        if comparison_mode not in ("amount", "percentage") or sort_order not in ("asc", "desc"):
            raise NotFound()
        journal_tokens = [value for value in journal_ids.split(",") if value]
        if any(not value.isdigit() for value in journal_tokens):
            raise NotFound()
        journal_ids = [int(value) for value in journal_tokens]
        report = request.env["account.deferred.schedule.report"]
        data = report.get_report_data(
            report_type, period, group_by, target_move, compare_previous, hide_zero, journal_ids,
            comparison_periods, comparison_mode, sort_order,
            period_type, period_anchor, date_from, date_to,
        )
        currency = request.env.company.currency_id
        unit = currency.name if scale == 1 else f"{'k' if scale == 1000 else 'M'}{currency.name}"
        title = "Deferred Expenses" if report_type == "expense" else "Deferred Revenues"

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        title_format = workbook.add_format({"bold": True, "font_size": 14})
        header = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
        amount_format = workbook.add_format({"num_format": "#,##0.00;[Red](#,##0.00)"})
        percentage_format = workbook.add_format({"num_format": "0.00%;[Red](0.00%)"})

        summary = workbook.add_worksheet("Schedule")
        summary.write(0, 0, f"{title} — {data['company_name']} — {data['periods'][0]['label']}", title_format)
        summary_headers = ["Group", "Entries", f"Recognized Amount ({unit})"]
        if comparison_periods:
            summary_headers.extend(
                f"{period_range['label']} Comparison ({'%' if comparison_mode == 'percentage' else unit})"
                for period_range in data["periods"][1:]
            )
        for column, label in enumerate(summary_headers):
            summary.write(2, column, label, header)
        for row_index, row in enumerate(data["rows"], start=3):
            summary.write_string(row_index, 0, row["name"])
            summary.write_number(row_index, 1, row["entries"])
            summary.write_number(row_index, 2, row["amount"] / scale, amount_format)
            for column, period_range in enumerate(data["periods"][1:], start=3):
                period_key = period_range["key"]
                comparison_value = row["comparison_values"][period_key]
                if comparison_value is not None:
                    summary.write_number(
                        row_index, column,
                        comparison_value / 100 if comparison_mode == "percentage" else comparison_value / scale,
                        percentage_format if comparison_mode == "percentage" else amount_format,
                    )
        summary.set_column(0, 0, 40)
        summary.set_column(1, 1, 14)
        summary.set_column(2, len(summary_headers) - 1, 24)
        summary.freeze_panes(3, 0)
        summary.autofilter(2, 0, max(2, len(data["rows"]) + 2), len(summary_headers) - 1)

        entries = workbook.add_worksheet("Entries")
        entry_headers = ["Period", "Date", "Journal", "Entry", "Reference", "Deferred Item", "State", f"Recognized Amount ({unit})"]
        for column, label in enumerate(entry_headers):
            entries.write(0, column, label, header)
        period_move_pairs = list(dict.fromkeys(
            (period_range["key"], move_id)
            for row in data["rows"]
            for period_range in data["periods"]
            for move_id in row["period_move_ids"].get(period_range["key"], [])
        ))
        period_label_by_key = {period_range["key"]: period_range["label"] for period_range in data["periods"]}
        move_ids = list(dict.fromkeys(move_id for _period_key, move_id in period_move_pairs))
        moves = request.env["account.move"].browse(move_ids).exists()
        move_by_id = {move.id: move for move in moves}
        sign = 1 if report_type == "expense" else -1
        row_index = 1
        for period_key, move_id in sorted(
            period_move_pairs,
            key=lambda pair: (
                pair[0], move_by_id[pair[1]].date, move_by_id[pair[1]].name, pair[1]
            ),
        ):
            move = move_by_id[move_id]
            asset = move.depreciation_asset_id
            account = (
                asset.category_id.account_depreciation_expense_id
                if report_type == "expense"
                else asset.category_id.account_depreciation_id
            )
            amount = sum(
                sign * line.balance
                for line in move.line_ids
                if line.account_id == account
            )
            entries.write_string(row_index, 0, period_label_by_key[period_key])
            entries.write_string(row_index, 1, str(move.date or ""))
            entries.write_string(row_index, 2, move.journal_id.display_name or "")
            entries.write_string(row_index, 3, move.name or "")
            entries.write_string(row_index, 4, move.ref or "")
            entries.write_string(row_index, 5, asset.name or "")
            entries.write_string(row_index, 6, move.state or "")
            entries.write_number(row_index, 7, amount / scale, amount_format)
            row_index += 1
        for column, width in enumerate((12, 13, 30, 24, 32, 40, 12, 24)):
            entries.set_column(column, column, width)
        entries.freeze_panes(1, 0)
        entries.autofilter(0, 0, max(0, row_index - 1), len(entry_headers) - 1)

        workbook.close()
        filename = f"{report_type}-deferred-{data['date_from']}-to-{data['date_to']}.xlsx"
        return request.make_response(output.getvalue(), [
            ("Content-Type", XLSX_CONTENT_TYPE),
            ("Content-Disposition", content_disposition(filename)),
        ])
