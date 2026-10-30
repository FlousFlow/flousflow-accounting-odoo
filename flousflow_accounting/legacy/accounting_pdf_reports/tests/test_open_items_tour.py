from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestOpenItemsTour(HttpCase):

    def test_open_items_report_filters_columns_and_xlsx_export(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_open_items")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_open_items_report",
            login="admin",
        )
