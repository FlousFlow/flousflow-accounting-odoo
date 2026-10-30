from io import BytesIO

import xlsxwriter
from odoo import _
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
GROUP_LABELS = {
    "sale": "Sales",
    "purchase": "Purchases",
    "withholding": "Withholding",
}


def build_tax_report_xlsx(
    data, scale="unit", company_currency="", labels=None,
    total_label="Total", empty_label="No tax on this period.",
):
    """Build an XLSX workbook from the same grouped values as the interactive report."""
    labels = labels or GROUP_LABELS
    divisor, number_format = SCALES[scale]
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    title_format = workbook.add_format({"bold": True, "font_size": 14})
    metadata_format = workbook.add_format({"font_color": "#666666"})
    header_format = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
    group_format = workbook.add_format({"bold": True, "bg_color": "#E9ECEF"})
    total_format = workbook.add_format({"bold": True, "top": 1})
    amount_format = workbook.add_format({"num_format": number_format})
    total_amount_format = workbook.add_format({"num_format": number_format, "bold": True, "top": 1})

    sheet = workbook.add_worksheet("Tax Report")
    sheet.right_to_left()
    sheet.write_string(0, 0, f"Tax Report — {data['company_name']}", title_format)
    sheet.write_string(1, 0, f"Period: {data['date_from']} to {data['date_to']}", metadata_format)
    entry_label = "Posted Entries" if data["target_move"] == "posted" else "All Entries"
    sheet.write_string(2, 0, f"Entries: {entry_label}", metadata_format)
    sheet.write_string(3, 0, f"Currency: {company_currency} | Scale: {scale}", metadata_format)
    periods = data.get("periods") or [{
        "current": True,
        "date_from": data["date_from"],
        "date_to": data["date_to"],
        "groups": data["groups"],
        "totals": data["totals"],
    }]
    sheet.write_string(5, 0, "Account" if data.get("report_view") == "account_tax" else "Tax", header_format)
    for index, period in enumerate(periods):
        column = 1 + index * 2
        label = f"{period['date_from']} – {period['date_to']}"
        sheet.merge_range(4, column, 4, column + 1, label, header_format)
        sheet.write_string(5, column, f"Net ({company_currency})", header_format)
        sheet.write_string(5, column + 1, f"Tax ({company_currency})", header_format)

    row = 6
    has_lines = False
    report_view = data.get("report_view", "general")
    if report_view in ("account_tax", "tax_account"):
        for key, label in GROUP_LABELS.items():
            if not any(period.get("grouped_lines", {}).get(report_view, {}).get(key) for period in periods):
                continue
            has_lines = True
            sheet.merge_range(row, 0, row, len(periods) * 2, labels[key], group_format)
            row += 1
            parents = {}
            for period in periods:
                for parent in period.get("grouped_lines", {}).get(report_view, {}).get(key, []):
                    parent_id = parent["account_id"] if report_view == "account_tax" else parent["tax_id"]
                    parent_label = parent["account_label"] if report_view == "account_tax" else parent["name"]
                    parents.setdefault(parent_id, {"label": parent_label, "children": {}})
                    children = parent["lines"] if report_view == "account_tax" else parent["accounts"]
                    for child in children:
                        child_id = child["tax_id"] if report_view == "account_tax" else child["account_id"]
                        child_label = child["name"] if report_view == "account_tax" else child["account_label"]
                        parents[parent_id]["children"].setdefault(child_id, child_label)

            for parent_id, parent in sorted(parents.items(), key=lambda item: item[1]["label"].casefold()):
                sheet.write_string(row, 0, parent["label"], group_format)
                row += 1
                for child_id, child_label in sorted(parent["children"].items(), key=lambda item: item[1].casefold()):
                    sheet.write_string(row, 0, f"    {child_label}")
                    for index, period in enumerate(periods):
                        period_parents = period.get("grouped_lines", {}).get(report_view, {}).get(key, [])
                        if report_view == "account_tax":
                            period_parent = next((item for item in period_parents if item["account_id"] == parent_id), {})
                            period_line = next((item for item in period_parent.get("lines", [])
                                                if item["tax_id"] == child_id), {})
                        else:
                            period_parent = next((item for item in period_parents if item["tax_id"] == parent_id), {})
                            period_line = next((item for item in period_parent.get("accounts", [])
                                                if item["account_id"] == child_id), {})
                        column = 1 + index * 2
                        sheet.write_number(row, column, period_line.get("net", 0.0) / divisor, amount_format)
                        sheet.write_number(row, column + 1, period_line.get("tax", 0.0) / divisor, amount_format)
                    row += 1
            sheet.write_string(row, 0, f"{total_label} {labels[key]}", total_format)
            for index, period in enumerate(periods):
                totals = period["totals"].get(key, {"net": 0.0, "tax": 0.0})
                column = 1 + index * 2
                sheet.write_number(row, column, totals["net"] / divisor, total_amount_format)
                sheet.write_number(row, column + 1, totals["tax"] / divisor, total_amount_format)
            row += 1
    else:
        for key, label in GROUP_LABELS.items():
            if not any(period["groups"].get(key) for period in periods):
                continue
            has_lines = True
            sheet.merge_range(row, 0, row, len(periods) * 2, labels[key], group_format)
            row += 1
            tax_lines = {
                line["tax_id"]: line
                for period in periods for line in period["groups"].get(key, [])
            }
            for line in tax_lines.values():
                sheet.write_string(row, 0, line["name"] or "")
                for index, period in enumerate(periods):
                    period_line = next((item for item in period["groups"].get(key, [])
                                        if item["tax_id"] == line["tax_id"]), {})
                    column = 1 + index * 2
                    sheet.write_number(row, column, period_line.get("net", 0.0) / divisor, amount_format)
                    sheet.write_number(row, column + 1, period_line.get("tax", 0.0) / divisor, amount_format)
                row += 1
            sheet.write_string(row, 0, f"{total_label} {labels[key]}", total_format)
            for index, period in enumerate(periods):
                totals = period["totals"].get(key, {"net": 0.0, "tax": 0.0})
                column = 1 + index * 2
                sheet.write_number(row, column, totals["net"] / divisor, total_amount_format)
                sheet.write_number(row, column + 1, totals["tax"] / divisor, total_amount_format)
            row += 1

    if not has_lines:
        sheet.merge_range(row, 0, row, len(periods) * 2, empty_label, metadata_format)
        row += 1

    sheet.set_column(0, 0, 42)
    sheet.set_column(1, len(periods) * 2, 22)
    sheet.freeze_panes(6, 0)
    sheet.autofilter(5, 0, max(5, row - 1), len(periods) * 2)
    workbook.close()
    return output.getvalue()


class TaxReportExportController(Controller):

    @route("/accounting_pdf_reports/tax_report/export", type="http", auth="user")
    def export_tax_report(
        self, date_from=None, date_to=None, target_move="posted", scale="unit",
        comparison_mode="none", comparison_periods=1,
        comparison_date_from=None, comparison_date_to=None,
        comparison_sort="descending", report_view="general", **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if (target_move not in ("posted", "all") or scale not in SCALES
                or comparison_mode not in ("none", "previous_period", "same_period_last_year", "custom")
                or comparison_sort not in ("ascending", "descending")
                or report_view not in ("general", "account_tax", "tax_account")):
            raise NotFound()

        report = request.env["report.flousflow_accounting.apr__report_tax"]
        data = report.get_interactive_data(
            date_from, date_to, target_move, comparison_mode,
            comparison_periods, comparison_date_from, comparison_date_to,
            comparison_sort, report_view,
        )
        labels = {key: _(label) for key, label in GROUP_LABELS.items()}
        body = build_tax_report_xlsx(
            data,
            scale,
            request.env.company.currency_id.name,
            labels=labels,
            total_label=_("Total"),
            empty_label=_("No tax on this period."),
        )
        filename = f"tax-report-{data['date_from']}-to-{data['date_to']}.xlsx"
        return request.make_response(body, [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ])
