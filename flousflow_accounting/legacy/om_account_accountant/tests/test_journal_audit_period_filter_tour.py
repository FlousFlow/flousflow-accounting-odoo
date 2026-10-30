from odoo import fields
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
        self.init_invoice(
            "in_invoice",
            invoice_date=fields.Date.to_string(fields.Date.today()),
            amounts=[100.0],
            post=True,
        )
        action = self.env.ref("flousflow_accounting.acc__action_journal_audit")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_journal_audit_entry_group",
            login="admin",
        )
