from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestPosCreditRestriction(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company.pos_credit_restriction_block = True
        cls.cash_journal = cls.company_data["default_journal_cash"]
        cls.other_cash_journal = cls.cash_journal.copy({
            "name": "Other POS Credit Restriction Cash",
            "code": "CRSH2",
        })
        receivable = cls.company_data["default_account_receivable"]
        cls.cash_method = cls.env["pos.payment.method"].sudo().create({
            "name": "POS Credit Restriction Cash",
            "type": "cash",
            "journal_id": cls.cash_journal.id,
            "receivable_account_id": receivable.id,
            "company_id": cls.company.id,
        })
        cls.other_cash_method = cls.env["pos.payment.method"].sudo().create({
            "name": "Other POS Credit Restriction Cash",
            "type": "cash",
            "journal_id": cls.other_cash_journal.id,
            "receivable_account_id": receivable.id,
            "company_id": cls.company.id,
        })
        cls.credit_method = cls.env["pos.payment.method"].sudo().create({
            "name": "POS Credit Restriction Account",
            "type": "pay_later",
            "receivable_account_id": receivable.id,
            "company_id": cls.company.id,
        })
        cls.allowed_pos = cls.env["pos.config"].sudo().create({
            "name": "Allowed Credit POS",
            "journal_id": cls.company_data["default_journal_sale"].id,
            "payment_method_ids": [Command.set([cls.cash_method.id, cls.credit_method.id])],
        })
        cls.other_pos = cls.env["pos.config"].sudo().create({
            "name": "Other Credit POS",
            "journal_id": cls.company_data["default_journal_sale"].id,
            "payment_method_ids": [Command.set([cls.other_cash_method.id, cls.credit_method.id])],
        })
        cls.partner_a.pos_credit_config_id = cls.allowed_pos

    def _session(self, config):
        return self.env["pos.session"].sudo().create({"config_id": config.id})

    def _order_data(self, session, payment_method):
        return {
            "session_id": session.id,
            "partner_id": self.partner_a.id,
            "payment_ids": [[0, 0, {"payment_method_id": payment_method.id, "amount": 10.0}]],
        }

    def test_credit_is_allowed_at_assigned_pos(self):
        session = self._session(self.allowed_pos)
        self.env["pos.order"]._check_partner_credit_pos(
            self._order_data(session, self.credit_method), session
        )

    def test_credit_is_refused_at_other_pos(self):
        session = self._session(self.other_pos)
        with self.assertRaisesRegex(UserError, "not allowed"):
            self.env["pos.order"]._check_partner_credit_pos(self._order_data(session, self.credit_method), session)

    def test_cash_remains_allowed_at_other_pos(self):
        session = self._session(self.other_pos)
        self.env["pos.order"]._check_partner_credit_pos(self._order_data(session, self.other_cash_method), session)

    def test_zero_credit_line_does_not_block_immediate_payment(self):
        session = self._session(self.other_pos)
        order = self._order_data(session, self.other_cash_method)
        order["amount_total"] = 10.0
        order["payment_ids"].append(
            [0, 0, {"payment_method_id": self.credit_method.id, "amount": 0.0}]
        )
        self.env["pos.order"]._check_partner_credit_pos(order, session)

    def test_credit_remains_blocked_when_mixed_with_immediate_payment(self):
        session = self._session(self.other_pos)
        order = self._order_data(session, self.other_cash_method)
        order["amount_total"] = 20.0
        order["payment_ids"].append(
            [0, 0, {"payment_method_id": self.credit_method.id, "amount": 10.0}]
        )
        with self.assertRaisesRegex(UserError, "not allowed"):
            self.env["pos.order"]._check_partner_credit_pos(order, session)

    def test_switching_existing_credit_line_to_cash_allows_order(self):
        session = self._session(self.other_pos)
        order = self.env["pos.order"].sudo().create({
            "session_id": session.id,
            "partner_id": self.partner_a.id,
            "lines": [],
            "payment_ids": [[0, 0, {
                "payment_method_id": self.credit_method.id,
                "amount": 10.0,
            }]],
        })
        update_payload = {
            "id": order.id,
            "session_id": session.id,
            "partner_id": self.partner_a.id,
            "payment_ids": [[1, order.payment_ids.id, {
                "payment_method_id": self.other_cash_method.id,
                "amount": 10.0,
            }]],
        }
        self.env["pos.order"]._check_partner_credit_pos(update_payload, session)

    def test_deleting_existing_credit_line_allows_order(self):
        session = self._session(self.other_pos)
        order = self.env["pos.order"].sudo().create({
            "session_id": session.id,
            "partner_id": self.partner_a.id,
            "lines": [],
            "payment_ids": [[0, 0, {
                "payment_method_id": self.credit_method.id,
                "amount": 10.0,
            }]],
        })
        update_payload = {
            "id": order.id,
            "session_id": session.id,
            "partner_id": self.partner_a.id,
            "payment_ids": [[2, order.payment_ids.id, False]],
        }
        self.env["pos.order"]._check_partner_credit_pos(update_payload, session)
