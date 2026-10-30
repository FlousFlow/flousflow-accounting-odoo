from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.addons.base.models.ir_actions_report import IrActionsReport
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAnnualReportDocument(AccountTestInvoicingCommon):

    def test_new_report_title_placeholder_matches_enterprise(self):
        view = self.env.ref("flousflow_accounting.apr__view_annual_report_document_form")

        self.assertIn(
            'placeholder="Example, Annual Financial Overview FY"',
            view.arch_db,
        )

    def test_default_period_is_the_previous_calendar_year(self):
        today = fields.Date.context_today(self.env.user)
        defaults = self.env["account.annual.report.document"].default_get([
            "date_from", "date_to",
        ])

        self.assertEqual(defaults["date_from"], today.replace(year=today.year - 1, month=1, day=1))
        self.assertEqual(defaults["date_to"], today.replace(year=today.year - 1, month=12, day=31))

    def test_new_report_copies_the_selected_template_sections(self):
        report = self.env["account.annual.report.document"].create({
            "name": "FY 2026 Annual Report",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })

        self.assertEqual(report.template_id, self.env.ref(
            "flousflow_accounting.apr__annual_report_template_standard",
        ))
        self.assertEqual(
            report.section_ids.sorted("sequence").mapped("name"),
            [
                "Company Overview", "Executive Summary", "Financial Performance",
                "Financial Position", "Cash Flow", "Notes and Attachments",
            ],
        )
        self.assertEqual(report.company_id, self.env.company)
        self.assertIn(self.env.user, report.responsible_user_ids)

    def test_report_rejects_a_reversed_date_range(self):
        with self.assertRaises(ValidationError):
            self.env["account.annual.report.document"].create({
                "name": "Invalid period",
                "date_from": "2026-12-31",
                "date_to": "2026-01-01",
            })

    def test_report_content_renders_as_html(self):
        report = self.env["account.annual.report.document"].create({
            "name": "Annual Report Render Check",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "section_ids": [(0, 0, {
                "sequence": 10,
                "name": "Management Review",
                "content": "<p>Revenue increased during the year.</p>",
            })],
        })

        html, report_type = self.env["ir.actions.report"]._render_qweb_html(
            "flousflow_accounting.apr__report_annual_document", report.ids,
        )
        body = html.decode() if isinstance(html, bytes) else str(html)

        self.assertEqual(report_type, "html")
        self.assertIn("Annual Report Render Check", body)
        self.assertIn("Management Review", body)
        self.assertIn("Revenue increased during the year.", body)

    def test_print_action_saves_a_downloadable_pdf(self):
        report = self.env["account.annual.report.document"].create({
            "name": "Annual PDF Check",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        pdf_data = b"%PDF-1.4 annual report test"

        with patch.object(IrActionsReport, "_render_qweb_pdf", return_value=(pdf_data, "pdf")):
            action = report.action_print_pdf()

        attachment = self.env["ir.attachment"].search([
            ("res_model", "=", report._name),
            ("res_id", "=", report.id),
            ("name", "=", "Annual PDF Check.pdf"),
        ], order="id desc", limit=1)
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn("/web/content/%s?download=true" % attachment.id, action["url"])
        self.assertEqual(bytes(attachment.raw), pdf_data)
