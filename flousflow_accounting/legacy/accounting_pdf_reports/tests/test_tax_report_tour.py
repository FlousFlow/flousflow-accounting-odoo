from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestTaxReportTour(HttpCase):

    def test_tax_report_comparison_columns_and_period_count(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_tax_report")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_tax_report_comparison",
            login="admin",
        )
