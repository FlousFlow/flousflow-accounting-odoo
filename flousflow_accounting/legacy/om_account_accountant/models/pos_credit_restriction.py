from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = "res.company"

    pos_credit_restriction_block = fields.Boolean(
        string="Restrict POS credit by point of sale",
        help=(
            "When enabled, a customer's Customer Account payment is allowed only "
            "from the point of sale assigned on the customer's contact. "
            "Cash and other immediate payment methods remain available everywhere."
        ),
    )

    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        return fields_to_load + ["pos_credit_restriction_block"]


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_credit_restriction_block = fields.Boolean(
        related="company_id.pos_credit_restriction_block", readonly=False
    )


class ResPartner(models.Model):
    _inherit = "res.partner"

    pos_credit_config_id = fields.Many2one(
        "pos.config",
        string="Credit Point of Sale",
        help=(
            "This customer may use Customer Account credit only at this point of sale. "
            "Leave empty when the restriction is not applicable to this contact."
        ),
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        return fields_to_load + ["pos_credit_config_id"]

    @api.constrains("pos_credit_config_id")
    def _check_pos_credit_company(self):
        allowed_companies = self.env.companies
        for partner in self:
            pos_config = partner.pos_credit_config_id
            if pos_config.company_id and pos_config.company_id not in allowed_companies:
                raise UserError(_(
                    "The allowed credit point of sale must belong to one of your active companies."
                ))


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _check_partner_credit_pos(self, order, pos_session):
        """Reject only Customer Account payments at an unassigned POS.

        This runs server-side while the POS order is being synced, so changing the
        browser or POS JavaScript cannot bypass the restriction. Cash/card payments
        are intentionally unaffected.
        """
        if not pos_session or not pos_session.company_id.pos_credit_restriction_block:
            return
        partner_id = order.get("partner_id")
        if not partner_id:
            return
        partner = self.env["res.partner"].browse(partner_id).exists()
        if not partner or not partner.pos_credit_config_id:
            return
        current_pos = pos_session.config_id
        if partner.pos_credit_config_id == current_pos:
            return

        payment_commands = order.get("payment_ids") or []
        payment_lines = []
        for command in payment_commands:
            if isinstance(command, (list, tuple)) and len(command) >= 3 and command[0] == 0:
                vals = command[2] or {}
                # The POS can keep a zero-valued Customer Account line in the
                # payload after the cashier switches to cash/card.  A zero
                # line is not a credit sale and must not block the order.
                amount = vals.get("amount")
                if amount is not None and not self.env.company.currency_id.is_zero(amount):
                    payment_lines.append((vals.get("payment_method_id"), amount))
        payment_methods = self.env["pos.payment.method"].browse(
            [method_id for method_id, amount in payment_lines if method_id]
        )
        methods_by_id = {method.id: method for method in payment_methods}
        credit_amount = sum(
            amount for method_id, amount in payment_lines
            if methods_by_id.get(method_id) and methods_by_id[method_id].type == "pay_later"
        )
        immediate_amount = sum(
            amount for method_id, amount in payment_lines
            if methods_by_id.get(method_id) and methods_by_id[method_id].type != "pay_later"
        )
        order_total = order.get("amount_total")
        # A POS order can retain a stale Customer Account line after the cashier
        # switches to cash/card. If immediate payment covers the full order,
        # treat that stale line as inactive; partial credit remains blocked.
        fully_paid_immediately = (
            order_total is not None
            and immediate_amount >= order_total
            and self.env.company.currency_id.is_zero(order_total - immediate_amount)
        )
        if credit_amount > 0 and not fully_paid_immediately:
            raise UserError(
                _(
                    "Customer %(customer)s is assigned to %(assigned_pos)s for credit sales. "
                    "Customer Account credit is not allowed at %(current_pos)s. "
                    "Use an immediate payment method or process the credit sale from the assigned point of sale.",
                    customer=partner.display_name,
                    assigned_pos=partner.pos_credit_config_id.display_name,
                    current_pos=current_pos.display_name,
                )
            )

    def _process_order(self, order, existing_order):
        pos_session = self.env["pos.session"].browse(order.get("session_id")).exists()
        check_order = dict(order)
        if not check_order.get("partner_id") and existing_order:
            check_order["partner_id"] = existing_order.partner_id.id
        self._check_partner_credit_pos(check_order, pos_session)
        return super()._process_order(order, existing_order)
