from odoo import Command
from lxml import etree
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged


@tagged("post_install", "-at_install")
class TestWorkingFileBalances(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env["account.account"]
        cls.balance_sheet_account = Account.create({
            "code": "199801",
            "name": "Working File Balance Sheet Test",
            "account_type": "asset_current",
        })
        cls.income_account = Account.create({
            "code": "499801",
            "name": "Working File Income Statement Test",
            "account_type": "income",
        })

    def _post_balance_move(self, account, move_date, debit, credit):
        move = self.env["account.move"].create({
            "move_type": "entry",
            "date": move_date,
            "journal_id": self.company_data["default_journal_misc"].id,
            "line_ids": [
                (0, 0, {
                    "name": "Working file balance test",
                    "account_id": account.id,
                    "debit": debit,
                    "credit": credit,
                }),
                (0, 0, {
                    "name": "Working file balance test counterpart",
                    "account_id": self.company_data["default_account_expense"].id,
                    "debit": credit,
                    "credit": debit,
                }),
            ],
        })
        move.action_post()
        return move

    def test_balance_sheet_accounts_include_opening_balance_and_prior_year(self):
        self._post_balance_move(self.balance_sheet_account, "2024-06-01", 120, 0)
        self._post_balance_move(self.balance_sheet_account, "2025-02-01", 40, 0)
        self._post_balance_move(self.balance_sheet_account, "2026-03-01", 60, 0)
        self._post_balance_move(self.balance_sheet_account, "2026-07-01", 90, 0)
        self._post_balance_move(self.balance_sheet_account, "2026-04-01", 0, 10)
        self._post_balance_move(self.balance_sheet_account, "2026-05-01", 20, 0)

        working_file = self.env["account.working.file"].create({
            "name": "Working file balance sheet calculation",
            "date_from": "2026-01-01",
            "date_to": "2026-06-30",
        })
        line = working_file.balance_line_ids.filtered(
            lambda balance: balance.account_id == self.balance_sheet_account
        )

        self.assertEqual(len(line), 1)
        self.assertEqual(line.balance, 230)
        self.assertEqual(line.balance_previous, 160)
        self.assertEqual(line.variation, 70)
        self.assertEqual(line.variation_percent, 43.75)

    def test_income_statement_accounts_use_selected_period_only(self):
        self._post_balance_move(self.income_account, "2025-02-01", 0, 10)
        self._post_balance_move(self.income_account, "2025-07-01", 0, 70)
        self._post_balance_move(self.income_account, "2026-02-01", 0, 30)
        self._post_balance_move(self.income_account, "2026-07-01", 0, 50)

        working_file = self.env["account.working.file"].create({
            "name": "Working file income statement calculation",
            "date_from": "2026-01-01",
            "date_to": "2026-06-30",
        })
        line = working_file.balance_line_ids.filtered(
            lambda balance: balance.account_id == self.income_account
        )

        self.assertEqual(len(line), 1)
        self.assertEqual(line.balance, -30)
        self.assertEqual(line.balance_previous, -10)
        self.assertEqual(line.variation, -20)
        self.assertEqual(line.variation_percent, -200)

    def test_working_file_card_tracks_reviewed_balance_accounts(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file balance review progress",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        line = working_file.balance_line_ids.filtered(
            lambda balance: balance.account_id == self.balance_sheet_account
        )

        self.assertEqual(working_file.balance_reviewed_count, 0)
        self.assertEqual(working_file.balance_line_count, len(working_file.balance_line_ids))
        self.assertEqual(working_file.balance_progress, 0)

        line.write({"state": "reviewed"})

        self.assertEqual(working_file.balance_reviewed_count, 1)
        self.assertAlmostEqual(
            working_file.balance_progress,
            100.0 / working_file.balance_line_count,
        )

    def test_working_file_checks_match_enterprise_review_statuses(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file Enterprise status parity",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        terminal_states = ("reviewed", "supervised", "exception")
        for index, check in enumerate(working_file.check_ids):
            check.write({"state": terminal_states[index % len(terminal_states)]})
            self.assertEqual(check.reviewer_id, self.env.user)
            self.assertTrue(check.reviewed_on)

        self.assertEqual(working_file.reviewed_count, len(working_file.check_ids))
        self.assertEqual(working_file.progress, 100)
        working_file.check_ids[0].write({"state": "pending"})
        self.assertLess(working_file.progress, 100)
        with self.assertRaises(UserError):
            working_file.action_validate()

        working_file.check_ids[0].write({"state": "exception"})
        working_file.action_validate()
        self.assertEqual(working_file.state, "validated")

    def test_only_accounting_managers_can_set_supervised_status(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file supervision permissions",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        accountant = new_test_user(
            self.env,
            login="working_file_supervision_accountant",
            groups="base.group_user,account.group_account_user",
            company_id=working_file.company_id.id,
            company_ids=[Command.set(working_file.company_id.ids)],
        )
        check = working_file.check_ids[:1]

        with self.assertRaises(AccessError):
            check.with_user(accountant).write({"state": "supervised"})
        with self.assertRaises(AccessError):
            self.env["account.working.file.check"].with_user(accountant).create({
                "file_id": working_file.id,
                "section": "Permissions",
                "name": "A supervised check",
                "state": "supervised",
            })

        check.write({"state": "supervised"})
        self.assertEqual(check.state, "supervised")

    def test_working_file_review_stage_allows_pending_checks_but_certification_does_not(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file Reviewed stage",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        pending_check = working_file.check_ids.filtered(
            lambda check: check.state == "pending"
        )[:1]
        self.assertTrue(pending_check)

        working_file.action_mark_reviewed()

        self.assertEqual(working_file.state, "reviewed")
        self.assertEqual(pending_check.state, "pending")
        with self.assertRaises(UserError):
            working_file.action_validate()

        working_file.check_ids.filtered(
            lambda check: check.state == "pending"
        ).write({"state": "reviewed"})
        working_file.action_validate()
        self.assertEqual(working_file.state, "validated")
        working_file.action_reopen()
        self.assertEqual(working_file.state, "in_progress")

    def test_create_syncs_accounts_when_web_form_sends_empty_balance_lines(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file empty balance commands",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "balance_line_ids": [],
        })

        line = working_file.balance_line_ids.filtered(
            lambda balance: balance.account_id == self.balance_sheet_account
        )
        self.assertEqual(len(line), 1)
        self.assertEqual(
            working_file.balance_line_count,
            self.env["account.account"].with_company(working_file.company_id).search_count([
                ("company_ids", "in", working_file.company_id.id),
                ("active", "=", True),
            ]),
        )

    def test_balance_account_link_opens_posted_journal_items_in_review_period(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file journal item drilldown",
            "date_from": "2026-01-01",
            "date_to": "2026-06-30",
        })
        balance = working_file.balance_line_ids.filtered(
            lambda line: line.account_id == self.balance_sheet_account
        )
        in_period_move = self._post_balance_move(
            self.balance_sheet_account, "2026-03-15", 25, 0
        )
        self._post_balance_move(self.balance_sheet_account, "2026-07-01", 35, 0)
        draft_move = self.env["account.move"].create({
            "move_type": "entry",
            "date": "2026-04-15",
            "journal_id": self.company_data["default_journal_misc"].id,
            "line_ids": [
                (0, 0, {
                    "name": "Draft working file drilldown",
                    "account_id": self.balance_sheet_account.id,
                    "debit": 45,
                }),
                (0, 0, {
                    "name": "Draft working file drilldown counterpart",
                    "account_id": self.company_data["default_account_expense"].id,
                    "credit": 45,
                }),
            ],
        })

        action = balance.action_open_journal_items()
        visible_lines = self.env["account.move.line"].search(action["domain"])

        self.assertEqual(action["res_model"], "account.move.line")
        self.assertEqual(action["name"], "Journal Items")
        self.assertEqual(
            set(visible_lines.move_id.ids),
            {in_period_move.id},
        )
        self.assertNotIn(draft_move.id, visible_lines.move_id.ids)

    def test_balance_account_name_uses_journal_items_link_widget(self):
        view = self.env.ref("flousflow_accounting.acc__view_account_working_file_balance_list")
        arch = etree.fromstring(view.arch_db.encode())
        account_field = arch.xpath(".//field[@name='account_name']")[0]

        self.assertEqual(account_field.get("widget"), "ff_working_file_balance_account")

    def test_working_file_opens_on_cycles_before_balances(self):
        view = self.env.ref("flousflow_accounting.acc__view_account_working_file_form")
        arch = etree.fromstring(view.arch_db.encode())
        page_names = [
            page.get("name") for page in arch.xpath(".//notebook/page")
        ]

        self.assertEqual(page_names, ["checks", "balances", "spreadsheet"])
        self.assertEqual(arch.xpath(".//notebook/page")[0].get("string"), "Cycles")

    def test_working_file_check_cards_use_interactive_field_widget(self):
        view = self.env.ref("flousflow_accounting.acc__view_account_working_file_form")
        arch = etree.fromstring(view.arch_db.encode())
        checks_field = arch.xpath(".//field[@name='check_ids']")[0]
        self.assertEqual(checks_field.get("widget"), "ff_working_file_check_cards")
        self.assertEqual(checks_field.get("readonly"), "state == 'validated'")

    def test_working_file_templates_mark_enterprise_evidence_requirements(self):
        template_names = (
            "working_file_check_enterprise_05",
            "working_file_check_enterprise_17",
            "working_file_check_enterprise_21",
            "working_file_check_enterprise_23",
            "working_file_check_enterprise_24",
            "working_file_check_enterprise_33",
            "working_file_check_enterprise_47",
        )
        templates = self.env["account.working.file.template"].browse([
            self.env.ref(f"om_account_accountant.{name}").id for name in template_names
        ])
        self.assertTrue(all(templates.mapped("evidence_required")))

        working_file = self.env["account.working.file"].create({
            "name": "Working file evidence requirement parity",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        evidence_checks = working_file.check_ids.filtered("evidence_required")
        self.assertEqual(len(evidence_checks), len(template_names))
        self.assertSetEqual(
            set(evidence_checks.mapped("template_id").ids),
            set(templates.ids),
        )

    def test_review_check_note_and_evidence_persist_and_evidence_can_be_removed(self):
        working_file = self.env["account.working.file"].create({
            "name": "Working file note and evidence persistence",
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
        })
        check = working_file.check_ids.filtered("evidence_required")[:1]
        self.assertTrue(check)

        note = "Reviewed against supporting bank documentation."
        check.write({"note": note})
        self.env.flush_all()
        check.invalidate_recordset(["note"])
        self.assertEqual(check.note, note)

        attachment = self.env["ir.attachment"].create({
            "name": "working-file-evidence-test.txt",
            "raw": b"Synthetic evidence used by the Working File regression test.",
            "mimetype": "text/plain",
            "res_model": check._name,
            "res_id": check.id,
        })
        check.invalidate_recordset(["evidence_attachment_ids", "evidence_attachment_count"])
        self.assertIn(attachment, check.evidence_attachment_ids)
        self.assertEqual(check.evidence_attachment_count, 1)

        attachment.unlink()
        check.invalidate_recordset(["evidence_attachment_ids", "evidence_attachment_count"])
        self.assertFalse(check.evidence_attachment_ids)
        self.assertEqual(check.evidence_attachment_count, 0)
