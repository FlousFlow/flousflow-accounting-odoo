from datetime import date

from freezegun import freeze_time
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDeferredSchedulePeriods(TransactionCase):

    def setUp(self):
        super().setUp()
        self.report = self.env["account.deferred.schedule.report"]

    def test_month_and_quarter_ranges_and_previous_periods(self):
        month_ranges = self.report._get_period_ranges(
            "month", period_anchor="2026-10-28", comparison_periods=1
        )
        self.assertEqual(
            [(item["date_from"], item["date_to"]) for item in month_ranges],
            [("2026-10-01", "2026-10-31"), ("2026-09-01", "2026-09-30")],
        )

        quarter_ranges = self.report._get_period_ranges(
            "quarter", period_anchor="2026-10-28", comparison_periods=1
        )
        self.assertEqual(
            [(item["label"], item["date_from"], item["date_to"]) for item in quarter_ranges],
            [("Q4 2026", "2026-10-01", "2026-12-31"), ("Q3 2026", "2026-07-01", "2026-09-30")],
        )

    def test_fiscal_year_ranges_use_company_settings(self):
        self.env.company.write({"fiscalyear_last_day": 30, "fiscalyear_last_month": "6"})

        ranges = self.report._get_period_ranges(
            "fiscal_year", period_anchor="2026-10-28", comparison_periods=1
        )

        self.assertEqual(
            [(item["date_from"], item["date_to"]) for item in ranges],
            [("2026-07-01", "2027-06-30"), ("2025-07-01", "2026-06-30")],
        )

    def test_custom_range_compares_with_an_equal_length_prior_range(self):
        ranges = self.report._get_period_ranges(
            "custom", date_from="2026-09-10", date_to="2026-09-19", comparison_periods=2
        )

        self.assertEqual(
            [(item["date_from"], item["date_to"]) for item in ranges],
            [
                ("2026-09-10", "2026-09-19"),
                ("2026-08-31", "2026-09-09"),
                ("2026-08-21", "2026-08-30"),
            ],
        )

    def test_invalid_custom_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.report._get_period_ranges(
                "custom", date_from="2026-09-20", date_to="2026-09-10"
            )


@tagged("post_install", "-at_install")
class TestDeferredSchedulePeriodsTour(HttpCase):

    def test_deferred_schedule_period_picker(self):
        action = self.env.ref("flousflow_accounting.acc__action_deferred_expense_report")
        self.start_tour(
            f"/odoo/action-{action.id}",
            "ff_deferred_schedule_periods",
            login="admin",
        )


@tagged("post_install", "-at_install")
class TestDeferredScheduleReportValues(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        account_model = cls.env["account.account"]
        cls.asset_account = account_model.create({
            "code": "151100",
            "name": "Period Test Equipment",
            "account_type": "asset_fixed",
        })
        cls.accumulated_account = account_model.create({
            "code": "151900",
            "name": "Period Test Accumulated Depreciation",
            "account_type": "asset_fixed",
        })
        cls.expense_account = account_model.create({
            "code": "681100",
            "name": "Period Test Depreciation Expense",
            "account_type": "expense_depreciation",
        })
        cls.category = cls.env["account.asset.category"].create({
            "name": "Period Test Equipment",
            "type": "purchase",
            "journal_id": cls.company_data["default_journal_misc"].id,
            "account_asset_id": cls.asset_account.id,
            "account_depreciation_id": cls.accumulated_account.id,
            "account_depreciation_expense_id": cls.expense_account.id,
            "method_number": 12,
            "method_period": 1,
            "date_first_depreciation": "last_day_period",
            "open_asset": True,
        })

    def test_quarter_report_and_custom_drilldown_use_selected_dates(self):
        asset = self.env["account.asset.asset"].create({
            "name": "Period Test Laptop",
            "category_id": self.category.id,
            "value": 1200.0,
            "date": date(2025, 1, 1),
            "method": "linear",
            "method_time": "number",
            "method_number": 12,
            "method_period": 1,
            "date_first_depreciation": "last_day_period",
        })
        with freeze_time("2025-04-15"):
            asset.validate()

        report = self.env["account.deferred.schedule.report"]
        quarter = report.get_report_data(
            "expense", "2025-03", comparison_periods=1,
            period_type="quarter", period_anchor="2025-03-15",
        )
        self.assertEqual(
            (quarter["date_from"], quarter["date_to"]),
            ("2025-01-01", "2025-03-31"),
        )
        self.assertEqual(len(quarter["rows"]), 1)
        self.assertEqual(quarter["rows"][0]["amount"], 300.0)
        self.assertEqual(quarter["rows"][0]["entries"], 3)
        self.assertEqual(quarter["rows"][0]["comparison_values"][quarter["periods"][1]["key"]], 300.0)
        self.assertEqual(len(quarter["rows"][0]["details"]), 1)
        detail = quarter["rows"][0]["details"][0]
        self.assertEqual(detail["asset_id"], asset.id)
        self.assertEqual(detail["entries"], 3)
        self.assertEqual(detail["amount"], quarter["rows"][0]["amount"])
        self.assertEqual(detail["comparison_values"][quarter["periods"][1]["key"]], 300.0)

        group_domain = report.get_group_move_domain(
            "expense", "2025-02-01", "account", self.expense_account.id,
            "posted", self.env["account.account"]._name, [], "2025-02-28",
        )
        matching_moves = self.env["account.move"].search(group_domain)
        self.assertEqual(matching_moves.mapped("date"), [date(2025, 2, 28)])
