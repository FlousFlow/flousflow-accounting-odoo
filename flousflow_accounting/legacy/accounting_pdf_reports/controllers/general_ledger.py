import csv
from io import BytesIO, StringIO

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


class GeneralLedgerExportController(Controller):

    @route("/accounting_pdf_reports/general_ledger/export", type="http", auth="user")
    def export_general_ledger(
        self, export_format="xlsx", date_from=None, date_to=None,
        target_move="posted", cash_basis="0", scale="unit", search="", **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if export_format not in ("xlsx", "csv") or target_move not in ("posted", "all"):
            raise NotFound()
        if cash_basis not in ("0", "1", "false", "true") or scale not in SCALES:
            raise NotFound()

        report = request.env["report.flousflow_accounting.apr__report_general_ledger"]
        cash_basis = cash_basis in ("1", "true")
        summary = report.get_interactive_data(date_from, date_to, target_move, cash_basis)
        query = search.strip().casefold()
        if query:
            summary["lines"] = [
                line for line in summary["lines"]
                if query in f"{line['code']} {line['name']}".casefold()
            ]
        details = report.get_interactive_data(
            date_from, date_to, target_move, cash_basis,
            [line["account_id"] for line in summary["lines"]],
        )
        detail_by_account = {line["account_id"]: line for line in details["lines"]}
        divisor, number_format = SCALES[scale]
        filename = f"general-ledger-{summary['date_from'] or 'all'}-to-{summary['date_to']}.{export_format}"

        if export_format == "csv":
            output = StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow([
                "Type", "Account Code", "Account", "Date", "Journal", "Entry",
                "Partner", "Currency", "Label", "Debit", "Credit", "Balance",
            ])
            for account in summary["lines"]:
                writer.writerow([
                    "Account Total", account["code"], account["name"], "", "", "", "", "", "",
                    account["debit"] / divisor, account["credit"] / divisor,
                    account["balance"] / divisor,
                ])
                detail = detail_by_account.get(account["account_id"], {})
                for move_line in detail.get("move_lines", []):
                    writer.writerow([
                        "Entry", account["code"], account["name"], move_line["date"] or "",
                        move_line["journal_code"], move_line["move_name"], move_line["partner_name"],
                        move_line["currency_code"], move_line["label"],
                        move_line["debit"] / divisor, move_line["credit"] / divisor,
                        move_line["balance"] / divisor,
                    ])
            body = output.getvalue().encode("utf-8-sig")
            content_type = "text/csv; charset=utf-8"
        else:
            output = BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            title = workbook.add_format({"bold": True, "font_size": 14})
            header = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
            amount = workbook.add_format({"num_format": number_format})
            summary_sheet = workbook.add_worksheet("General Ledger")
            summary_sheet.write(0, 0, f"General Ledger — {summary['company_name']}", title)
            summary_headers = ["Account Code", "Account", "Debit", "Credit", "Balance"]
            for column, label in enumerate(summary_headers):
                summary_sheet.write(2, column, label, header)
            for row_index, account in enumerate(summary["lines"], start=3):
                summary_sheet.write_string(row_index, 0, account["code"])
                summary_sheet.write_string(row_index, 1, account["name"])
                summary_sheet.write_number(row_index, 2, account["debit"] / divisor, amount)
                summary_sheet.write_number(row_index, 3, account["credit"] / divisor, amount)
                summary_sheet.write_number(row_index, 4, account["balance"] / divisor, amount)
            summary_sheet.set_column(0, 0, 16)
            summary_sheet.set_column(1, 1, 42)
            summary_sheet.set_column(2, 4, 20)
            summary_sheet.freeze_panes(3, 0)
            summary_sheet.autofilter(2, 0, max(2, len(summary["lines"]) + 2), 4)

            entries = workbook.add_worksheet("Journal Items")
            entry_headers = [
                "Account Code", "Account", "Date", "Journal", "Entry", "Partner",
                "Currency", "Label", "Debit", "Credit", "Balance",
            ]
            for column, label in enumerate(entry_headers):
                entries.write(0, column, label, header)
            row_index = 1
            for account in summary["lines"]:
                detail = detail_by_account.get(account["account_id"], {})
                for move_line in detail.get("move_lines", []):
                    entries.write_string(row_index, 0, account["code"])
                    entries.write_string(row_index, 1, account["name"])
                    entries.write_string(row_index, 2, move_line["date"] or "Initial Balance")
                    entries.write_string(row_index, 3, move_line["journal_code"])
                    entries.write_string(row_index, 4, move_line["move_name"])
                    entries.write_string(row_index, 5, move_line["partner_name"])
                    entries.write_string(row_index, 6, move_line["currency_code"])
                    entries.write_string(row_index, 7, move_line["label"])
                    entries.write_number(row_index, 8, move_line["debit"] / divisor, amount)
                    entries.write_number(row_index, 9, move_line["credit"] / divisor, amount)
                    entries.write_number(row_index, 10, move_line["balance"] / divisor, amount)
                    row_index += 1
            for column, width in enumerate((16, 42, 14, 14, 24, 30, 12, 42, 18, 18, 18)):
                entries.set_column(column, column, width)
            entries.freeze_panes(1, 0)
            entries.autofilter(0, 0, max(0, row_index - 1), len(entry_headers) - 1)
            workbook.close()
            body = output.getvalue()
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        return request.make_response(body, [
            ("Content-Type", content_type),
            ("Content-Disposition", content_disposition(filename)),
        ])
