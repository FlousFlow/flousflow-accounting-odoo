from datetime import datetime, time
from io import BytesIO

import xlsxwriter
from odoo import fields
from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition
from werkzeug.exceptions import Forbidden, NotFound


READ_GROUPS = (
    "account.group_account_readonly",
    "account.group_account_invoice",
    "account.group_account_user",
    "account.group_account_manager",
)
SCOPES = {"receivable", "non_trade_receivable", "payable", "non_trade_payable"}
SCALES = {
    "unit": (1, "#,##0.00;[Red](#,##0.00)"),
    "rounded": (1, "#,##0;[Red](#,##0)"),
    "thousand": (1000, "#,##0.00;[Red](#,##0.00)"),
    "million": (1000000, "#,##0.00;[Red](#,##0.00)"),
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


def build_customer_statement_xlsx(data, scopes, scale, company_currency, foreign_currencies):
    """Export the filtered statement summary and line details to an RTL workbook."""
    divisor, number_format = SCALES[scale]
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    meta_format = workbook.add_format({"font_color": "#666666"})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
    partner_format = workbook.add_format({"bold": True, "bg_color": "#E9ECEF", "top": 1})
    partner_amount_format = workbook.add_format({"bold": True, "bg_color": "#E9ECEF", "top": 1, "num_format": number_format})
    amount_format = workbook.add_format({"num_format": number_format})
    total_format = workbook.add_format({"bold": True, "top": 2})
    total_amount_format = workbook.add_format({"bold": True, "top": 2, "num_format": number_format})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
    foreign_formats = {}

    def foreign_format(currency_id):
        if currency_id not in foreign_formats:
            currency = foreign_currencies.get(currency_id)
            decimals = max(0, min(currency.decimal_places if currency else 2, 6))
            pattern = "#,##0" + ("." + "0" * decimals if decimals else "")
            symbol = ((currency.symbol or currency.name) if currency else "").replace('"', '""')
            if currency and currency.position == "before":
                positive = f'"{symbol}" {pattern}'
            else:
                positive = f'{pattern} "{symbol}"' if symbol else pattern
            foreign_formats[currency_id] = workbook.add_format({"num_format": f"{positive};[Red]({positive})"})
        return foreign_formats[currency_id]

    sheet = workbook.add_worksheet("Customer Statement")
    sheet.right_to_left()
    report_title = "Vendor Statement" if scopes and all(
        scope in ("payable", "non_trade_payable") for scope in scopes
    ) else "Customer Statement"
    sheet.write_string(0, 0, f"{report_title} — {data['company_name']}", title_format)
    sheet.write_string(1, 0, f"Period: {data['date_from']} to {data['date_to']}", meta_format)
    sheet.write_string(2, 0, f"Entries: {data['target_move'].title()} | Currency: {company_currency.name} | Scale: {scale}", meta_format)
    headers = ["Partner", "Document", "Date", "Due Date", "Reference", f"Amount ({company_currency.name})", "Amount in Currency", "Currency"]
    for column, label in enumerate(headers):
        sheet.write_string(4, column, label, header_format)

    row = 5
    total = 0.0
    for partner in data["partners"]:
        sheet.merge_range(row, 0, row, 4, partner["name"], partner_format)
        sheet.write_number(row, 5, partner["amount"] / divisor, partner_amount_format)
        for column in (6, 7):
            sheet.write_blank(row, column, None, partner_format)
        total += partner["amount"]
        row += 1
        for line in partner["lines"]:
            sheet.write_string(row, 0, partner["name"])
            sheet.write_string(row, 1, line.get("label") or "")
            for column, key in ((2, "date"), (3, "date_maturity")):
                value = fields.Date.to_date(line[key]) if line.get(key) else None
                if value:
                    sheet.write_datetime(row, column, datetime.combine(value, time.min), date_format)
                else:
                    sheet.write_blank(row, column, None)
            sheet.write_string(row, 4, line.get("reference") or "")
            sheet.write_number(row, 5, line["amount"] / divisor, amount_format)
            currency_id = line.get("currency_id")
            sheet.write_number(row, 6, line.get("amount_currency") or 0.0, foreign_format(currency_id))
            sheet.write_string(row, 7, line.get("currency_name") or "")
            row += 1

    sheet.merge_range(row, 0, row, 4, "Total", total_format)
    sheet.write_number(row, 5, total / divisor, total_amount_format)
    sheet.write_blank(row, 6, None, total_format)
    sheet.write_blank(row, 7, None, total_format)
    for column, width in enumerate((28, 28, 14, 14, 24, 22, 22, 14)):
        sheet.set_column(column, column, width)
    sheet.freeze_panes(5, 0)
    sheet.autofilter(4, 0, max(4, row - 1), len(headers) - 1)
    workbook.close()
    return output.getvalue()


class CustomerStatementExportController(Controller):

    @route("/accounting_pdf_reports/customer_statement/export", type="http", auth="user")
    def export_customer_statement(
        self,
        period_type="month",
        period_anchor=None,
        custom_date_from=None,
        custom_date_to=None,
        account_scopes="receivable,payable",
        partner_ids="",
        partner_tag_ids="",
        target_move="posted",
        scale="unit",
        **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if period_type not in ("month", "quarter", "fiscal_year", "custom"):
            raise NotFound()
        if target_move not in ("posted", "draft", "all") or scale not in SCALES:
            raise NotFound()
        scopes = list(dict.fromkeys(account_scopes.split(",")))
        if not scopes or any(scope not in SCOPES for scope in scopes):
            raise NotFound()
        partner_ids = _parse_ids(partner_ids)
        partner_tag_ids = _parse_ids(partner_tag_ids)

        report = request.env["report.flousflow_accounting.apr__customer_statement_data"]
        data = report.get_interactive_data(
            period_type=period_type,
            period_anchor=period_anchor,
            custom_date_from=custom_date_from,
            custom_date_to=custom_date_to,
            account_scopes=scopes,
            partner_ids=partner_ids,
            partner_tag_ids=partner_tag_ids,
            target_move=target_move,
        )
        data = {**data, "target_move": target_move}
        currency_ids = {
            line["currency_id"]
            for partner in data["partners"]
            for line in partner["lines"]
            if line.get("currency_id")
        }
        currencies = request.env["res.currency"].browse(list(currency_ids))
        body = build_customer_statement_xlsx(
            data, scopes, scale, request.env.company.currency_id,
            {currency.id: currency for currency in currencies},
        )
        filename = f"customer-statement-{data['date_from']}-to-{data['date_to']}.xlsx"
        return request.make_response(body, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])
