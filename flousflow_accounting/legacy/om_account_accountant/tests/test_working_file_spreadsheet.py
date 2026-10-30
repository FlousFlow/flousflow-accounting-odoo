import json

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestWorkingFileSpreadsheet(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.WorkingFile = cls.env["account.working.file"]
        cls.working_file = cls.WorkingFile.create({
            "name": "Spreadsheet persistence test",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })

    def test_spreadsheet_snapshot_has_valid_empty_workbook_and_round_trips(self):
        snapshot = self.working_file.get_working_file_spreadsheet_snapshot()
        self.assertEqual(len(snapshot["sheets"]), 1)
        self.assertTrue(snapshot["sheets"][0]["name"])

        snapshot["revisionId"] = "test-revision"
        self.working_file.write({"spreadsheet_data": json.dumps(snapshot)})
        self.assertEqual(
            self.working_file.get_working_file_spreadsheet_snapshot(), snapshot
        )

    def test_spreadsheet_action_has_readonly_state_and_record_context(self):
        action = self.working_file.action_open_spreadsheet()
        self.assertEqual(action["tag"], "flousflow_accounting.acc__working_file_spreadsheet")
        self.assertEqual(action["params"]["record_id"], self.working_file.id)
        self.assertTrue(action["params"]["can_edit"])

        auditor = new_test_user(
            self.env,
            login="working_file_spreadsheet_auditor",
            groups="account.group_account_readonly",
            company_id=self.working_file.company_id.id,
            company_ids=[Command.set(self.working_file.company_id.ids)],
        )
        auditor_action = self.working_file.with_user(auditor).action_open_spreadsheet()
        self.assertFalse(auditor_action["params"]["can_edit"])

        self.working_file.check_ids.write({"state": "reviewed"})
        self.working_file.action_validate()
        action = self.working_file.action_open_spreadsheet()
        self.assertFalse(action["params"]["can_edit"])
        with self.assertRaises(UserError):
            self.working_file.write({"spreadsheet_data": json.dumps({"sheets": []})})


@tagged("post_install", "-at_install")
class TestWorkingFileSpreadsheetTour(HttpCase):
    def test_spreadsheet_is_embedded_in_the_working_file(self):
        working_file = self.env["account.working.file"].create({
            "name": "Embedded spreadsheet tour",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        action = self.env.ref("flousflow_accounting.acc__action_account_working_file")
        self.start_tour(
            f"/odoo/action-{action.id}/{working_file.id}",
            "ff_working_file_spreadsheet_embedded",
            login="admin",
        )
