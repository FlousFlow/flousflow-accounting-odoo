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


def build_open_items_xlsx(data, scale, company_currency, currencies):
    divisor, number_format = SCALES[scale]
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    metadata_format = workbook.add_format({"font_color": "#666666"})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
    partner_format = workbook.add_format({"bold": True, "bg_color": "#E9ECEF", "top": 1})
    partner_amount_format = workbook.add_format({
        "num_format": number_format, "bold": True, "bg_color": "#E9ECEF", "top": 1,
    })
    amount_format = workbook.add_format({"num_format": number_format})
    total_format = workbook.add_format({"bold": True, "top": 2})
    total_amount_format = workbook.add_format({"num_format": number_format, "bold": True, "top": 2})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
    foreign_formats = {}

    def foreign_format(currency_id):
        if currency_id not in foreign_formats:
            currency = currencies.get(currency_id)
            decimals = max(0, min(currency.decimal_places if currency else 2, 6))
            pattern = "#,##0" + ("." + "0" * decimals if decimals else "")
            symbol = ((currency.symbol or currency.name) if currency else "").replace('"', '""')
            positive = f'"{symbol}" {pattern}' if currency and currency.position == "before" else f'{pattern} "{symbol}"'
            foreign_formats[currency_id] = workbook.add_format({
                "num_format": f"{positive};[Red]({positive})",
            })
        return foreign_formats[currency_id]

    sheet = workbook.add_worksheet("Open Items")
    sheet.right_to_left()
    sheet.write_string(0, 0, "Open Items", title_format)
    sheet.write_string(1, 0, f"As of: {data['date_from']}", metadata_format)
    sheet.write_string(2, 0, f"Currency: {company_currency.name} | Scale: {scale}", metadata_format)
    if data.get("unposted_count"):
        sheet.write_string(3, 0, f"Unposted journal items: {data['unposted_count']}", metadata_format)

    headers = [
        "No Reminder", "Invoice Date", "Due Date", "Journal Item",
        f"Amount ({company_currency.name})", "Amount Currency",
        f"Residual ({company_currency.name})", "Residual Currency",
    ]
    for column, label in enumerate(headers):
        sheet.write_string(5, column, label, header_format)

    row_index = 6
    for partner in data["rows"]:
        sheet.merge_range(row_index, 0, row_index, 3, partner["name"], partner_format)
        sheet.write_number(row_index, 4, partner["amount"] / divisor, partner_amount_format)
        sheet.write_blank(row_index, 5, None, partner_format)
        sheet.write_number(row_index, 6, partner["residual"] / divisor, partner_amount_format)
        sheet.write_blank(row_index, 7, None, partner_format)
        row_index += 1
        for line in partner["lines"]:
            sheet.write_string(row_index, 0, "Yes" if line["no_reminder"] else "No")
            for column, key in ((1, "invoice_date"), (2, "due_date")):
                if line[key]:
                    sheet.write_datetime(
                        row_index, column,
                        datetime.combine(fields.Date.to_date(line[key]), time.min), date_format,
                    )
                else:
                    sheet.write_blank(row_index, column, None)
            sheet.write_string(row_index, 3, line["label"] or "")
            sheet.write_number(row_index, 4, line["amount"] / divisor, amount_format)
            currency = currencies.get(line["currency_id"])
            if currency and currency != company_currency:
                sheet.write_number(
                    row_index, 5, line["amount_currency"] / divisor,
                    foreign_format(line["currency_id"]),
                )
                sheet.write_number(
                    row_index, 7, line["residual_currency"] / divisor,
                    foreign_format(line["currency_id"]),
                )
            else:
                sheet.write_blank(row_index, 5, None)
                sheet.write_blank(row_index, 7, None)
            sheet.write_number(row_index, 6, line["residual"] / divisor, amount_format)
            row_index += 1

    totals = data["totals"]
    sheet.merge_range(row_index, 0, row_index, 3, "Total Open Items", total_format)
    sheet.write_number(row_index, 4, totals["amount"] / divisor, total_amount_format)
    sheet.write_blank(row_index, 5, None, total_format)
    sheet.write_number(row_index, 6, totals["residual"] / divisor, total_amount_format)
    sheet.write_blank(row_index, 7, None, total_format)
    for column, width in enumerate((14, 15, 15, 34, 21, 22, 21, 22)):
        sheet.set_column(column, column, width)
    sheet.freeze_panes(6, 0)
    sheet.autofilter(5, 0, max(5, row_index - 1), len(headers) - 1)
    workbook.close()
    return output.getvalue()


class OpenItemsExportController(Controller):

    @route("/accounting_pdf_reports/open_items/export", type="http", auth="user")
    def export_open_items(
        self, date_from=None, result_selection="trade", target_move="posted",
        partner_ids="", scale="unit", **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if result_selection not in ("trade", "customer", "supplier"):
            raise NotFound()
        if target_move not in ("posted", "all") or scale not in SCALES:
            raise NotFound()
        partner_ids = _parse_ids(partner_ids)
        report = request.env["report.flousflow_accounting.apr__report_agedpartnerbalance"]
        data = report.get_open_items_data(
            date_from=date_from,
            result_selection=result_selection,
            target_move=target_move,
            partner_ids=partner_ids,
        )
        currency_ids = {
            line["currency_id"]
            for partner in data["rows"]
            for line in partner["lines"]
            if line.get("currency_id")
        }
        currencies = request.env["res.currency"].browse(list(currency_ids))
        currency_map = {currency.id: currency for currency in currencies}
        body = build_open_items_xlsx(
            data, scale, request.env.company.currency_id, currency_map,
        )
        filename = f"open-items-{data['date_from']}.xlsx"
        return request.make_response(body, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])
