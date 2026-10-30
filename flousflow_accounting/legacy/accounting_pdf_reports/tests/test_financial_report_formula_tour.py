from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestFinancialReportFormulaTour(HttpCase):

    def test_balance_sheet_formula_details_are_visible(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_balance_sheet")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_balance_sheet_formula_info",
            login="admin",
        )


    def test_total_assets_formula_details_are_visible(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_balance_sheet")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_balance_sheet_total_assets_formula",
            login="admin",
        )

    def test_profit_and_loss_revenue_formula_details_are_visible(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_profit_and_loss")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_profit_and_loss_revenue_formula_info",
            login="admin",
        )

    def test_profit_and_loss_enterprise_summary_rows_and_formulas_are_visible(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_profit_and_loss")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_profit_and_loss_enterprise_summary",
            login="admin",
        )
