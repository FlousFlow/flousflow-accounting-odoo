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
        cls.cash_journal = cls.env["account.journal"].create({
            "name": "POS Credit Restriction Cash",
            "type": "cash",
            "code": "PCRC",
            "company_id": cls.company.id,
            "default_account_id": cls.company_data["default_account_cash"].id,
        })
        receivable = cls.company_data["default_account_receivable"]
        cls.cash_method = cls.env["pos.payment.method"].create({
            "name": "POS Credit Restriction Cash",
            "type": "cash",
            "journal_id": cls.cash_journal.id,
            "receivable_account_id": receivable.id,
            "company_id": cls.company.id,
        })
        cls.credit_method = cls.env["pos.payment.method"].create({
            "name": "POS Credit Restriction Account",
            "type": "pay_later",
            "receivable_account_id": receivable.id,
            "company_id": cls.company.id,
        })
        cls.allowed_pos = cls.env["pos.config"].create({
            "name": "Allowed Credit POS",
            "journal_id": cls.company_data["default_journal_sale"].id,
            "payment_method_ids": [Command.set([cls.cash_method.id, cls.credit_method.id])],
        })
        cls.other_pos = cls.env["pos.config"].create({
            "name": "Other Credit POS",
            "journal_id": cls.company_data["default_journal_sale"].id,
            "payment_method_ids": [Command.set([cls.cash_method.id, cls.credit_method.id])],
        })
        cls.partner_a.pos_credit_config_id = cls.allowed_pos

    def _session(self, config):
        return self.env["pos.session"].create({"config_id": config.id})

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
        self.env["pos.order"]._check_partner_credit_pos(self._order_data(session, self.cash_method), session)

    def test_zero_credit_line_does_not_block_immediate_payment(self):
        session = self._session(self.other_pos)
        order = self._order_data(session, self.cash_method)
        order["payment_ids"].append(
            [0, 0, {"payment_method_id": self.credit_method.id, "amount": 0.0}]
        )
        self.env["pos.order"]._check_partner_credit_pos(order, session)
