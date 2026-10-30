from io import BytesIO
from zipfile import ZipFile

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestGeneralLedgerExport(HttpCase):

    def test_csv_and_xlsx_exports(self):
        self.authenticate("admin", "admin")
        base_url = "/accounting_pdf_reports/general_ledger/export"
        common_params = "date_from=2025-02-01&date_to=2025-02-28&target_move=posted&cash_basis=0&scale=unit"

        csv_response = self.url_open(f"{base_url}?export_format=csv&{common_params}")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response.headers["Content-Type"])
        self.assertIn(b"Account Code", csv_response.content)
        self.assertIn(b"Journal", csv_response.content)

        xlsx_response = self.url_open(f"{base_url}?export_format=xlsx&{common_params}")
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn("spreadsheetml.sheet", xlsx_response.headers["Content-Type"])
        with ZipFile(BytesIO(xlsx_response.content)) as workbook:
            workbook_xml = workbook.read("xl/workbook.xml")
        self.assertIn(b"General Ledger", workbook_xml)
        self.assertIn(b"Journal Items", workbook_xml)

    def test_export_menu_is_available_from_interactive_report(self):
        action = self.env.ref("flousflow_accounting.apr__action_interactive_general_ledger")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_general_ledger_exports",
            login="admin",
        )
