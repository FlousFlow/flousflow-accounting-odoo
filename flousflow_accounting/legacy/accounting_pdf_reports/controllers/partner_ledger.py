from datetime import datetime, time
from io import BytesIO

import xlsxwriter
from odoo import fields, _
from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition
from werkzeug.exceptions import Forbidden, NotFound


READ_GROUPS = (
    "account.group_account_readonly",
    "account.group_account_invoice",
    "account.group_account_user",
    "account.group_account_manager",
)
SCALES = {
    "unit": (1, "#,##0.00;[Red](#,##0.00)"),
    "rounded": (1, "#,##0;[Red](#,##0)"),
    "thousand": (1000, "#,##0.00;[Red](#,##0.00)"),
    "million": (1000000, "#,##0.00;[Red](#,##0.00)"),
}
ACCOUNT_TYPES = {
    "trade": ("asset_receivable", "liability_payable"),
    "receivable": ("asset_receivable",),
    "payable": ("liability_payable",),
}


def _parse_ids(value):
    if not value:
        return []
    try:
        ids = [int(item) for item in value.split(",")]
    except (AttributeError, TypeError, ValueError):
        raise NotFound() from None
    if any(record_id <= 0 for record_id in ids):
        raise NotFound()
    return list(dict.fromkeys(ids))


def build_partner_ledger_xlsx(report, partner_rows, move_lines, company_currency, scale="unit"):
    """Build a workbook containing the filtered Partner Ledger and its details."""
    divisor, number_format = SCALES[scale]
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    metadata_format = workbook.add_format({"font_color": "#666666"})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
    partner_format = workbook.add_format({"bold": True, "bg_color": "#E9ECEF", "top": 1})
    partner_amount_format = workbook.add_format({"num_format": number_format, "bold": True, "bg_color": "#E9ECEF", "top": 1})
    total_format = workbook.add_format({"bold": True, "top": 2})
    total_amount_format = workbook.add_format({"num_format": number_format, "bold": True, "top": 2})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
    amount_format = workbook.add_format({"num_format": number_format})
    foreign_formats = {}

    sheet = workbook.add_worksheet("Partner Ledger")
    sheet.right_to_left()
    sheet.write_string(0, 0, f"Partner Ledger — {report['company_name']}", title_format)
    sheet.write_string(1, 0, f"Period: {report['date_from']} to {report['date_to']}", metadata_format)
    entry_state = "Posted Entries" if report["target_move"] == "posted" else "All Entries"
    sheet.write_string(2, 0, f"Entries: {entry_state}", metadata_format)
    sheet.write_string(3, 0, f"Currency: {company_currency.name} | Scale: {scale}", metadata_format)

    headers = [
        "Journal", "Account", "Date", "Due Date", "Matching",
        f"Debit ({company_currency.name})", f"Credit ({company_currency.name})",
        "Amount Currency", f"Balance ({company_currency.name})",
    ]
    for column, label in enumerate(headers):
        sheet.write_string(5, column, label, header_format)

    selected_partner_ids = [partner["id"] for partner in partner_rows]
    by_partner = {partner_id: [] for partner_id in selected_partner_ids}
    running_balance = dict.fromkeys(selected_partner_ids, 0.0)
    for line in move_lines:
        partner_id = line.partner_id.commercial_partner_id.id
        running_balance[partner_id] += line.debit - line.credit
        by_partner[partner_id].append((line, running_balance[partner_id]))

    def foreign_amount_format(currency):
        if currency.id not in foreign_formats:
            decimals = max(0, min(currency.decimal_places, 6))
            places = "." + ("0" * decimals) if decimals else ""
            symbol = (currency.symbol or currency.name or "").replace('"', '""')
            amount_pattern = f"#,##0{places}"
            positive = f'"{symbol}" {amount_pattern}' if currency.position == "before" else f'{amount_pattern} "{symbol}"'
            negative = f'[Red]({positive})'
            foreign_formats[currency.id] = workbook.add_format({"num_format": f"{positive};{negative}"})
        return foreign_formats[currency.id]

    row = 6
    totals = {"debit": 0.0, "credit": 0.0, "balance": 0.0}
    for partner in partner_rows:
        sheet.merge_range(row, 0, row, 4, partner["name"], partner_format)
        sheet.write_number(row, 5, partner["debit"] / divisor, partner_amount_format)
        sheet.write_number(row, 6, partner["credit"] / divisor, partner_amount_format)
        sheet.write_blank(row, 7, None, partner_format)
        sheet.write_number(row, 8, partner["balance"] / divisor, partner_amount_format)
        totals["debit"] += partner["debit"]
        totals["credit"] += partner["credit"]
        totals["balance"] += partner["balance"]
        row += 1
        for line, balance in by_partner[partner["id"]]:
            sheet.write_string(row, 0, line.journal_id.code or "")
            sheet.write_string(row, 1, line.account_id.display_name or "")
            sheet.write_datetime(row, 2, datetime.combine(fields.Date.to_date(line.date), time.min), date_format)
            if line.date_maturity:
                sheet.write_datetime(row, 3, datetime.combine(fields.Date.to_date(line.date_maturity), time.min), date_format)
            else:
                sheet.write_blank(row, 3, None)
            sheet.write_string(row, 4, line.matching_number or "")
            sheet.write_number(row, 5, line.debit / divisor, amount_format)
            sheet.write_number(row, 6, line.credit / divisor, amount_format)
            if line.currency_id and line.currency_id != company_currency:
                sheet.write_number(
                    row, 7, line.amount_currency / divisor,
                    foreign_amount_format(line.currency_id),
                )
            else:
                sheet.write_blank(row, 7, None)
            sheet.write_number(row, 8, balance / divisor, amount_format)
            row += 1

    sheet.merge_range(row, 0, row, 4, "Total", total_format)
    sheet.write_number(row, 5, totals["debit"] / divisor, total_amount_format)
    sheet.write_number(row, 6, totals["credit"] / divisor, total_amount_format)
    sheet.write_blank(row, 7, None, total_format)
    sheet.write_number(row, 8, totals["balance"] / divisor, total_amount_format)
    for column, width in enumerate((16, 34, 14, 14, 16, 20, 20, 22, 20)):
        sheet.set_column(column, column, width)
    sheet.freeze_panes(6, 0)
    sheet.autofilter(5, 0, max(5, row - 1), len(headers) - 1)
    workbook.close()
    return output.getvalue()


class PartnerLedgerExportController(Controller):

    @route("/accounting_pdf_reports/partner_ledger/export", type="http", auth="user")
    def export_partner_ledger(
        self,
        period_type="fiscal_year",
        period_anchor=None,
        custom_date_from=None,
        custom_date_to=None,
        target_move="posted",
        account_scope="trade",
        partner_ids="",
        partner_tag_ids="",
        search="",
        scale="unit",
        **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if period_type not in ("fiscal_year", "custom") or target_move not in ("posted", "all"):
            raise NotFound()
        if account_scope not in ACCOUNT_TYPES or scale not in SCALES:
            raise NotFound()
        selected_partner_ids = _parse_ids(partner_ids)
        selected_tag_ids = _parse_ids(partner_tag_ids)

        report_model = request.env["report.flousflow_accounting.apr__report_partnerledger"]
        report_data = report_model.get_interactive_data(
            period_type=period_type,
            period_anchor=period_anchor,
            custom_date_from=custom_date_from,
            custom_date_to=custom_date_to,
            target_move=target_move,
            partner_ids=selected_partner_ids,
            account_scope=account_scope,
            partner_tag_ids=selected_tag_ids,
        )
        report_data["account_scope"] = account_scope
        partner_rows = report_data["partners"]
        if search and search.strip():
            query = search.strip().casefold()
            partner_rows = [partner for partner in partner_rows if query in partner["name"].casefold()]
        partner_record_ids = [partner["id"] for partner in partner_rows]
        if partner_record_ids:
            domain = [
                ("company_id", "in", report_data["company_ids"]),
                ("account_id.account_type", "in", ACCOUNT_TYPES[account_scope]),
                ("account_id.active", "=", True),
                ("partner_id.commercial_partner_id", "in", partner_record_ids),
                ("date", ">=", report_data["date_from"]),
                ("date", "<=", report_data["date_to"]),
                ("parent_state", "in", ("posted", "draft") if target_move == "all" else ("posted",)),
                ("display_type", "not in", ("line_section", "line_note")),
            ]
            move_lines = request.env["account.move.line"].search(domain, order="date, move_id, id")
        else:
            move_lines = request.env["account.move.line"]
        body = build_partner_ledger_xlsx(
            report_data, partner_rows, move_lines, request.env.company.currency_id, scale=scale,
        )
        filename = f"partner-ledger-{report_data['date_from']}-to-{report_data['date_to']}.xlsx"
        return request.make_response(body, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])
