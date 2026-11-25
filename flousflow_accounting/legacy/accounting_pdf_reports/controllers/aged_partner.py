from datetime import datetime, time
from io import BytesIO

import xlsxwriter
from odoo import _, fields
from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition
from werkzeug.exceptions import Forbidden, NotFound


READ_GROUPS = (
    "account.group_account_readonly",
    "account.group_account_invoice",
    "account.group_account_manager",
)
SCALES = {
    "unit": (1, "#,##0.00;[Red](#,##0.00)"),
    "rounded": (1, "#,##0;[Red](#,##0)"),
    "thousand": (1000, "#,##0.00;[Red](#,##0.00)"),
    "million": (1000000, "#,##0.00;[Red](#,##0.00)"),
}
RESULT_LABELS = {
    "customer": "Aged Receivable",
    "supplier": "Aged Payable",
    "customer_supplier": "Receivable and Payable",
}
BASIS_LABELS = {
    "due_date": "Based on due date",
    "invoice_date": "Based on invoice date",
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


def build_aged_partner_xlsx(data, currency, scale="unit"):
    """Build an XLSX workbook from the interactive aged report result."""
    divisor, number_format = SCALES[scale]
    period_length = data["period_length"]
    bucket_labels = [
        f"1-{period_length}",
        f"{period_length + 1}-{period_length * 2}",
        f"{period_length * 2 + 1}-{period_length * 3}",
        f"{period_length * 3 + 1}-{period_length * 4}",
        f"{_('Older')} > {period_length * 4}",
    ]
    amount_headers = [
        f"{_('Not Due')} ({currency.name})",
        *(f"{label} ({currency.name})" for label in bucket_labels),
        f"{_('Total')} ({currency.name})",
    ]

    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    metadata_format = workbook.add_format({"font_color": "#666666"})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
    amount_format = workbook.add_format({"num_format": number_format})
    total_format = workbook.add_format({"bold": True, "top": 2})
    total_amount_format = workbook.add_format({"num_format": number_format, "bold": True, "top": 2})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})

    report_name = _(RESULT_LABELS[data["result_selection"]])
    sheet = workbook.add_worksheet(_("Aging Summary"))
    sheet.right_to_left()
    sheet.write_string(0, 0, report_name, title_format)
    sheet.write_string(1, 0, f"{_('As of date')}: {data['date_from']}", metadata_format)
    sheet.write_string(2, 0, f"{_('Aging basis')}: {_(BASIS_LABELS[data['date_basis']])}", metadata_format)
    entry_state = "Posted Entries" if data["target_move"] == "posted" else "All Entries"
    sheet.write_string(3, 0, f"{_('Target moves')}: {_(entry_state)}", metadata_format)
    sheet.write_string(4, 0, f"{_('Period length')}: {period_length} {_('days')} | {_('Currency')}: {currency.name} | {_('Scale')}: {scale}", metadata_format)

    headers = [_('Partner'), *amount_headers]
    header_row = 6
    for column, label in enumerate(headers):
        sheet.write_string(header_row, column, label, header_format)

    row_index = header_row + 1
    if not data["rows"]:
        sheet.merge_range(row_index, 0, row_index, len(headers) - 1, _("No data found"), metadata_format)
        row_index += 1
    else:
        for partner in data["rows"]:
            sheet.write_string(row_index, 0, partner["name"] or "")
            values = [partner["not_due"], *partner["buckets"], partner["total"]]
            for column, value in enumerate(values, start=1):
                sheet.write_number(row_index, column, value / divisor, amount_format)
            row_index += 1

    total_values = [data["totals"]["not_due"], *data["totals"]["buckets"], data["totals"]["total"]]
    sheet.write_string(row_index, 0, _("Total"), total_format)
    for column, value in enumerate(total_values, start=1):
        sheet.write_number(row_index, column, value / divisor, total_amount_format)
    sheet.set_column(0, 0, 38)
    sheet.set_column(1, len(headers) - 1, 20)
    sheet.freeze_panes(header_row + 1, 1)
    if data["rows"]:
        sheet.autofilter(header_row, 0, row_index - 1, len(headers) - 1)

    details = workbook.add_worksheet(_("Aging Details"))
    details.right_to_left()
    detail_headers = [_("Partner"), _("Journal Item"), _("Invoice Date"), _("Due Date"), _("Aging Bucket"), f"{_('Balance')} ({currency.name})"]
    for column, label in enumerate(detail_headers):
        details.write_string(0, column, label, header_format)
    detail_row = 1
    for partner in data["rows"]:
        for line in partner["lines"]:
            period = line["period"]
            if period == 6:
                bucket = _("Not Due")
            elif period == 5:
                bucket = bucket_labels[0]
            elif period in (1, 2, 3, 4):
                bucket = bucket_labels[5 - period]
            else:
                bucket = ""
            details.write_string(detail_row, 0, partner["name"] or "")
            details.write_string(detail_row, 1, line["label"] or "")
            for column, date_value in ((2, line["invoice_date"]), (3, line["due_date"])):
                if date_value:
                    details.write_datetime(
                        detail_row, column,
                        datetime.combine(fields.Date.to_date(date_value), time.min),
                        date_format,
                    )
                else:
                    details.write_blank(detail_row, column, None, date_format)
            details.write_string(detail_row, 4, bucket)
            details.write_number(detail_row, 5, line["amount"] / divisor, amount_format)
            detail_row += 1
    details.set_column(0, 0, 38)
    details.set_column(1, 1, 28)
    details.set_column(2, 4, 18)
    details.set_column(5, 5, 22)
    details.freeze_panes(1, 0)
    if detail_row > 1:
        details.autofilter(0, 0, detail_row - 1, len(detail_headers) - 1)

    workbook.close()
    return output.getvalue()


class AgedPartnerExportController(Controller):

    @route("/accounting_pdf_reports/aged_partner/export", type="http", auth="user")
    def export_aged_partner(
        self, result_selection="customer", date_from=None, target_move="posted",
        period_length="30", partner_ids="", date_basis="due_date", scale="unit", **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if (result_selection not in RESULT_LABELS or target_move not in ("posted", "all")
                or date_basis not in ("due_date", "invoice_date") or scale not in SCALES):
            raise NotFound()
        try:
            period_length = int(period_length)
            report_date = fields.Date.to_date(date_from) if date_from else fields.Date.context_today(request.env.user)
        except (TypeError, ValueError):
            raise NotFound() from None
        if not 1 <= period_length <= 3660:
            raise NotFound()

        report = request.env["report.flousflow_accounting.apr__report_agedpartnerbalance"]
        data = report.get_interactive_data(
            result_selection=result_selection,
            date_from=report_date,
            target_move=target_move,
            period_length=period_length,
            partner_ids=_parse_ids(partner_ids),
            date_basis=date_basis,
        )
        body = build_aged_partner_xlsx(data, request.env.company.currency_id, scale=scale)
        filename = f"aged-report-{result_selection}-{data['date_from']}.xlsx"
        return request.make_response(body, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])
