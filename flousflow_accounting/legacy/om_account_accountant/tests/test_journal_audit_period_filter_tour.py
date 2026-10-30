from odoo import Command, fields
from odoo.tests import HttpCase, tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestJournalAuditPeriodFilterTour(AccountTestInvoicingCommon, HttpCase):

    def test_journal_audit_period_filter(self):
        action = self.env.ref("flousflow_accounting.acc__action_journal_audit")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_journal_audit_period_filter",
            login="admin",
        )

    def test_journal_audit_mobile_filters(self):
        self.browser_size = "390x844"
        action = self.env.ref("flousflow_accounting.acc__action_journal_audit")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_journal_audit_mobile_filters",
            login="admin",
        )

    def test_journal_audit_action_groups_by_entry(self):
        invoice = self.init_invoice(
            "in_invoice",
            invoice_date=fields.Date.to_string(fields.Date.today()),
            amounts=[100.0],
            post=True,
        )
        date_range = self.env["account.journal.audit.report"].get_fiscal_year_range()
        report_data = self.env["account.journal.audit.report"].get_report_data(
            date_range["date_from"], date_range["date_to"], "posted",
        )
        self.assertTrue(
            any(row["journal_id"] == invoice.journal_id.id and row["move_type"] == "in_invoice"
                for row in report_data["journals"]),
            "The posted invoice must appear in the Journal Audit report before the browser tour starts.",
        )
        self.env.ref("base.user_admin").write({
            "company_id": self.env.company.id,
            "company_ids": [Command.set(self.env.company.ids)],
        })
        action = self.env.ref("flousflow_accounting.acc__action_journal_audit")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_journal_audit_entry_group",
            login="admin",
        )
