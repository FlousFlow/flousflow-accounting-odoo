from datetime import date
from io import BytesIO
from zipfile import ZipFile

from odoo import fields
from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestJournalAuditPeriods(AccountTestInvoicingCommon, HttpCase):

    def test_fiscal_year_range_uses_active_company_settings(self):
        company = self.env.company
        company.write({
            "fiscalyear_last_day": 30,
            "fiscalyear_last_month": "6",
        })
        anchor = date(2026, 10, 28)

        result = self.env["account.journal.audit.report"].get_fiscal_year_range(anchor)

        self.assertEqual(result, {
            "date_from": "2026-07-01",
            "date_to": "2027-06-30",
        })

    def test_fiscal_year_range_defaults_to_today(self):
        today = fields.Date.context_today(self.env.company)
        expected = self.env.company.compute_fiscalyear_dates(today)

        result = self.env["account.journal.audit.report"].get_fiscal_year_range()

        self.assertEqual(result["date_from"], fields.Date.to_string(expected["date_from"]))
        self.assertEqual(result["date_to"], fields.Date.to_string(expected["date_to"]))

    def test_journal_audit_groups_documents_and_account_totals(self):
        tax = self.company_data["default_tax_purchase"]
        invoice = self.init_invoice(
            "in_invoice", amounts=[100.0], taxes=[tax], invoice_date="2026-01-15", post=True,
        )
        self.init_invoice(
            "in_invoice", partner=invoice.partner_id, amounts=[50.0], taxes=[tax],
            invoice_date="2026-01-20", post=True,
        )

        result = self.env["account.journal.audit.report"].get_report_data(
            "2026-01-01", "2026-01-31", "posted", include_payments=True,
        )

        invoice_group = next(
            row for row in result["journals"]
            if row["journal_id"] == invoice.journal_id.id and row["move_type"] == "in_invoice"
        )
        self.assertEqual(invoice_group["document_type"], "Invoice")
        self.assertEqual(invoice_group["documents"], 2)
        self.assertTrue(invoice_group["accounts"])
        self.assertAlmostEqual(
            sum(account["debit"] for account in invoice_group["accounts"]),
            invoice_group["debit"],
        )
        self.assertAlmostEqual(
            sum(account["credit"] for account in invoice_group["accounts"]),
            invoice_group["credit"],
        )
        self.assertEqual(len(invoice_group["taxes"]), 1)
        self.assertEqual(invoice_group["taxes"][0]["id"], tax.id)
        self.assertAlmostEqual(invoice_group["taxes"][0]["base"], 150.0)
        overall_tax = next(tax_row for tax_row in result["taxes"] if tax_row["id"] == tax.id)
        self.assertAlmostEqual(overall_tax["base"], invoice_group["taxes"][0]["base"])

    def test_journal_audit_xlsx_includes_journal_tax_details(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/om_account_accountant/journal_audit/xlsx?date_from=2026-01-01"
            "&date_to=2026-01-31&target_move=posted&include_payments=0&scale=1"
        )
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as workbook:
            workbook_xml = workbook.read("xl/workbook.xml").decode()
            shared_strings = workbook.read("xl/sharedStrings.xml").decode(errors="replace")
        self.assertIn("Journal Taxes", workbook_xml)
        self.assertIn("Applied Taxes by Journal", shared_strings)
