from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestDashboardPartnerParity(AccountTestInvoicingCommon):

    def test_dashboard_kpis_use_the_available_report_actions(self):
        cards = {
            card["id"]: card
            for card in self.env["account.journal"].get_account_dashboard_kpis()
        }

        self.assertSetEqual(
            set(cards),
            {"invoices", "expenses", "receivable", "payable", "invoice_layout"},
        )
        self.assertEqual(
            cards["invoices"]["action_id"],
            self.env.ref("account.action_account_invoice_report_all").id,
        )
        self.assertEqual(
            cards["expenses"]["action_id"],
            self.env.ref("flousflow_accounting.apr__action_interactive_profit_and_loss").id,
        )
        self.assertEqual(
            cards["receivable"]["action_id"],
            self.env.ref("flousflow_accounting.apr__action_interactive_aged_receivable").id,
        )
        self.assertEqual(
            cards["payable"]["action_id"],
            self.env.ref("flousflow_accounting.apr__action_interactive_aged_payable").id,
        )

    def test_dashboard_kpi_order_is_saved_for_the_current_user(self):
        requested_order = ["payable", "cash", "invoice_layout", "invoices", "expenses", "receivable"]

        self.env["res.users"].save_account_dashboard_kpi_order(requested_order)

        self.assertEqual(self.env["res.users"].get_account_dashboard_kpi_order(), requested_order)

    def test_einvoicing_onboarding_label_is_translated_in_arabic(self):
        sales_journal = self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", self.env.company.id)],
            limit=1,
        )

        action_data = sales_journal.with_context(lang="ar_001")._get_onboarding_action_data()

        self.assertEqual(action_data["title"], "تفعيل الفوترة الإلكترونية")

    def test_partner_open_items_button_uses_current_company_residuals(self):
        invoice = self.init_invoice(
            "in_invoice", amounts=[125.0], taxes=[], invoice_date="2026-01-15", post=True,
        )
        partner = invoice.partner_id

        self.assertGreater(partner.open_items_count, 0)
        self.assertNotEqual(partner.open_items_balance, 0.0)

        action = partner.action_open_accounting_items()
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(action["tag"], "flousflow_accounting.apr__open_items")
        self.assertEqual(action["context"]["default_partner_ids"], [partner.commercial_partner_id.id])

        partner_view = self.env.ref("flousflow_accounting.acc__view_partner_property_form")
        self.assertIn("action_open_accounting_items", partner_view.arch_db)
        self.assertIn("account.group_account_readonly", partner_view.arch_db)
        self.assertIn("account.group_account_manager", partner_view.arch_db)


@tagged("post_install", "-at_install")
class TestDashboardKpiReorderTour(HttpCase):

    def test_dashboard_kpi_reorder_is_applied_and_saved(self):
        user = self.env.ref("base.user_admin")
        user.account_dashboard_kpi_order = "[]"
        self.start_tour(
            "/odoo/accounting",
            "ff_account_dashboard_kpi_reorder",
            login=user.login,
        )
