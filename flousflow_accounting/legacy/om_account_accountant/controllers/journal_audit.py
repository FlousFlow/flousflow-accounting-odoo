from io import BytesIO

import xlsxwriter
from werkzeug.exceptions import Forbidden, NotFound

from odoo.http import Controller, request, route
from odoo.http.stream import content_disposition


XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
READ_GROUPS = (
    "account.group_account_readonly",
    "account.group_account_user",
    "account.group_account_manager",
)


class JournalAuditController(Controller):

    @route("/om_account_accountant/journal_audit/xlsx", type="http", auth="user")
    def journal_audit_xlsx(
        self, date_from=None, date_to=None, target_move="posted",
        include_payments="0", scale="1", **kwargs,
    ):
        if not any(request.env.user.has_group(group) for group in READ_GROUPS):
            raise Forbidden()
        if target_move not in ("posted", "draft", "all"):
            raise NotFound()
        try:
            scale = int(scale)
        except (TypeError, ValueError):
            raise NotFound()
        if scale not in (1, 1000, 1000000):
            raise NotFound()

        include_payments = include_payments in ("1", "true", "True")
        report = request.env["account.journal.audit.report"]
        data = report.get_report_data(date_from, date_to, target_move, include_payments)
        currency = request.env.company.currency_id
        amount_label = currency.name
        if scale == 1000:
            amount_label = f"k{amount_label}"
        elif scale == 1000000:
            amount_label = f"M{amount_label}"

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        title = workbook.add_format({"bold": True, "font_size": 14})
        header = workbook.add_format({"bold": True, "bg_color": "#D9E0E7", "border": 1})
        amount_format = workbook.add_format({"num_format": "#,##0.00;[Red](#,##0.00)"})
        journals_sheet = workbook.add_worksheet("Journals")
        journals_sheet.write(0, 0, f"Journal Audit — {data['company_name']} — {date_from} to {date_to}", title)
        journal_headers = ["Journal", "Document Type", "Documents", "To Review", f"Debit ({amount_label})", f"Credit ({amount_label})", f"Balance ({amount_label})"]
        for column, label in enumerate(journal_headers):
            journals_sheet.write(2, column, label, header)
        for row_index, journal in enumerate(data["journals"], start=3):
            journals_sheet.write_string(row_index, 0, journal["name"])
            journals_sheet.write_string(row_index, 1, journal["document_type"])
            journals_sheet.write_number(row_index, 2, journal["documents"])
            journals_sheet.write_number(row_index, 3, journal["to_review"])
            for column, key in enumerate(("debit", "credit", "balance"), start=4):
                journals_sheet.write_number(row_index, column, journal[key] / scale, amount_format)
        for column, width in enumerate((36, 24, 14, 14, 20, 20, 20)):
            journals_sheet.set_column(column, column, width)
        journals_sheet.freeze_panes(3, 0)
        journals_sheet.autofilter(2, 0, max(2, len(data["journals"]) + 2), len(journal_headers) - 1)

        accounts_sheet = workbook.add_worksheet("Accounts")
        account_headers = ["Journal", "Document Type", "Account Code", "Account", f"Debit ({amount_label})", f"Credit ({amount_label})", f"Balance ({amount_label})"]
        for column, label in enumerate(account_headers):
            accounts_sheet.write(0, column, label, header)
        row_index = 1
        for journal in data["journals"]:
            for account in journal["accounts"]:
                accounts_sheet.write_string(row_index, 0, journal["name"])
                accounts_sheet.write_string(row_index, 1, journal["document_type"])
                accounts_sheet.write_string(row_index, 2, account["code"])
                accounts_sheet.write_string(row_index, 3, account["name"])
                for column, key in enumerate(("debit", "credit", "balance"), start=4):
                    accounts_sheet.write_number(row_index, column, account[key] / scale, amount_format)
                row_index += 1
        for column, width in enumerate((36, 24, 18, 40, 20, 20, 20)):
            accounts_sheet.set_column(column, column, width)
        accounts_sheet.freeze_panes(1, 0)
        accounts_sheet.autofilter(0, 0, max(0, row_index - 1), len(account_headers) - 1)

        entries_sheet = workbook.add_worksheet("Entries")
        entry_headers = ["Date", "Journal", "Document", "Reference", "Type", "State", "Review", f"Debit ({amount_label})", f"Credit ({amount_label})", f"Balance ({amount_label})"]
        for column, label in enumerate(entry_headers):
            entries_sheet.write(0, column, label, header)
        row_index = 1
        unique_journals = {journal["journal_id"]: journal["name"] for journal in data["journals"]}
        for journal_id, journal_name in unique_journals.items():
            offset = 0
            while True:
                page = report.get_journal_moves(
                    journal_id, date_from, date_to, target_move,
                    include_payments, offset, 200,
                )
                for move in page["rows"]:
                    entries_sheet.write_string(row_index, 0, move["date"] or "")
                    entries_sheet.write_string(row_index, 1, journal_name)
                    entries_sheet.write_string(row_index, 2, move["name"] or "")
                    entries_sheet.write_string(row_index, 3, move["ref"] or "")
                    entries_sheet.write_string(row_index, 4, move["document_type"] or "")
                    entries_sheet.write_string(row_index, 5, move["state"] or "")
                    entries_sheet.write_string(row_index, 6, move["review_state"] or "")
                    for column, key in enumerate(("debit", "credit", "balance"), start=7):
                        entries_sheet.write_number(row_index, column, move[key] / scale, amount_format)
                    row_index += 1
                offset = page["offset"]
                if not page["has_more"]:
                    break
        for column, width in enumerate((13, 34, 24, 32, 22, 12, 18, 20, 20, 20)):
            entries_sheet.set_column(column, column, width)
        entries_sheet.freeze_panes(1, 0)
        entries_sheet.autofilter(0, 0, max(0, row_index - 1), len(entry_headers) - 1)

        taxes_sheet = workbook.add_worksheet("Taxes")
        taxes_sheet.write(0, 0, f"Tax Summary — {data['company_name']} — {date_from} to {date_to}", title)
        tax_headers = ["Tax", f"Base Amount ({amount_label})", f"Tax Amount ({amount_label})"]
        for column, label in enumerate(tax_headers):
            taxes_sheet.write(2, column, label, header)
        for row_index, tax in enumerate(data["taxes"], start=3):
            taxes_sheet.write_string(row_index, 0, tax["name"])
            taxes_sheet.write_number(row_index, 1, tax["base"] / scale, amount_format)
            taxes_sheet.write_number(row_index, 2, tax["balance"] / scale, amount_format)
        taxes_sheet.set_column(0, 0, 36)
        taxes_sheet.set_column(1, 2, 24)
        taxes_sheet.freeze_panes(3, 0)

        journal_taxes_sheet = workbook.add_worksheet("Journal Taxes")
        journal_taxes_sheet.write(0, 0, f"Applied Taxes by Journal — {data['company_name']} — {date_from} to {date_to}", title)
        journal_tax_headers = ["Journal", "Document Type", "Tax", f"Base Amount ({amount_label})", f"Tax Amount ({amount_label})"]
        for column, label in enumerate(journal_tax_headers):
            journal_taxes_sheet.write(2, column, label, header)
        row_index = 3
        for journal in data["journals"]:
            for tax in journal["taxes"]:
                journal_taxes_sheet.write_string(row_index, 0, journal["name"])
                journal_taxes_sheet.write_string(row_index, 1, journal["document_type"])
                journal_taxes_sheet.write_string(row_index, 2, tax["name"])
                journal_taxes_sheet.write_number(row_index, 3, tax["base"] / scale, amount_format)
                journal_taxes_sheet.write_number(row_index, 4, tax["balance"] / scale, amount_format)
                row_index += 1
        for column, width in enumerate((34, 24, 36, 24, 24)):
            journal_taxes_sheet.set_column(column, column, width)
        journal_taxes_sheet.freeze_panes(3, 0)
        journal_taxes_sheet.autofilter(2, 0, max(2, row_index - 1), len(journal_tax_headers) - 1)

        workbook.close()
        filename = f"journal-audit-{date_from}-{date_to}.xlsx"
        return request.make_response(output.getvalue(), [
            ("Content-Type", XLSX_CONTENT_TYPE),
            ("Content-Disposition", content_disposition(filename)),
        ])
