from io import BytesIO

import xlsxwriter
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


def build_cash_flow_xlsx(data, scale, company_currency):
    """Create a workbook from the same categorized amounts as the interactive report."""
    divisor, number_format = SCALES[scale]
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    metadata_format = workbook.add_format({"font_color": "#666666"})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
    section_format = workbook.add_format({"bold": True, "bg_color": "#E9ECEF"})
    total_format = workbook.add_format({"bold": True, "top": 1})
    amount_format = workbook.add_format({"num_format": number_format})
    total_amount_format = workbook.add_format({"num_format": number_format, "bold": True, "top": 1})

    sheet = workbook.add_worksheet("Cash Flow")
    sheet.write(0, 0, f"Cash Flow Statement — {data['company_name']}", title_format)
    sheet.write(1, 0, f"Period: {data['date_from']} to {data['date_to']}", metadata_format)
    sheet.write(2, 0, f"Currency: {company_currency} | Scale: {scale}", metadata_format)
    entry_state = {
        "posted": "Posted Entries",
        "draft": "Draft Entries",
        "all": "All Entries",
    }[data["target_move"]]
    sheet.write(3, 0, f"Entries: {entry_state}", metadata_format)
    journal_label = ", ".join(data["journal_names"]) if data["journal_filter_enabled"] else "All Journals"
    sheet.write(4, 0, f"Journals: {journal_label}", metadata_format)
    headers = ["Activity", "Description", "Account Code", "Account", "Amount"]
    for column, label in enumerate(headers):
        sheet.write(6, column, label, header_format)

    row = 7
    sheet.write_string(row, 1, "Cash and cash equivalents at the beginning of the period")
    sheet.write_number(row, 4, data["opening"] / divisor, amount_format)
    row += 1
    for section in data["sections"]:
        sheet.write_string(row, 0, section["name"], section_format)
        row += 1
        for line in section["lines"]:
            sheet.write_string(row, 0, section["name"])
            sheet.write_string(row, 1, line["name"])
            sheet.write_number(row, 4, line["amount"] / divisor, amount_format)
            row += 1
            for account in line["accounts"]:
                sheet.write_string(row, 0, section["name"])
                sheet.write_string(row, 1, line["name"])
                sheet.write_string(row, 2, account["code"] or "")
                sheet.write_string(row, 3, account["name"] or "")
                sheet.write_number(row, 4, account["amount"] / divisor, amount_format)
                row += 1
        sheet.write_string(row, 1, f"Total {section['name']}", total_format)
        sheet.write_number(row, 4, section["total"] / divisor, total_amount_format)
        row += 1

    sheet.write_string(row, 1, "Net increase (decrease) in cash and cash equivalents", total_format)
    sheet.write_number(row, 4, data["net_change"] / divisor, total_amount_format)
    row += 1
    sheet.write_string(row, 1, "Cash and cash equivalents at the end of the period", total_format)
    sheet.write_number(row, 4, data["closing"] / divisor, total_amount_format)
    sheet.set_column(0, 0, 27)
    sheet.set_column(1, 1, 54)
    sheet.set_column(2, 2, 17)
    sheet.set_column(3, 3, 42)
    sheet.set_column(4, 4, 21)
    sheet.freeze_panes(7, 0)
    sheet.autofilter(6, 0, max(6, row - 1), len(headers) - 1)
    workbook.close()
    return output.getvalue()


class CashFlowExportController(Controller):

    @route("/accounting_pdf_reports/cash_flow/export", type="http", auth="user")
    def export_cash_flow(
        self,
        date_from=None,
        date_to=None,
        target_move="posted",
        journal_ids="",
        journal_filter_enabled="0",
        scale="unit",
        **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if target_move not in ("posted", "draft", "all") or scale not in SCALES:
            raise NotFound()
        try:
            selected_journals = [int(value) for value in journal_ids.split(",") if value.isdigit()]
        except (AttributeError, ValueError):
            raise NotFound() from None
        filter_enabled = journal_filter_enabled in ("1", "true")
        if journal_filter_enabled not in ("0", "1", "false", "true"):
            raise NotFound()

        report = request.env["report.flousflow_accounting.apr__report_cash_flow"]
        data = report.get_interactive_data(
            date_from,
            date_to,
            target_move,
            selected_journals,
            filter_enabled,
        )
        body = build_cash_flow_xlsx(data, scale, request.env.company.currency_id.name)
        filename = f"cash-flow-{data['date_from']}-to-{data['date_to']}.xlsx"
        return request.make_response(body, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])
