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
        # Existing draft orders are synchronized with ORM commands. Rebuild
        # their effective payment lines so changing an existing pay_later line
        # to cash/card (or deleting it) removes the credit exposure before the
        # restriction is evaluated.
        effective_lines = {}
        if self and isinstance(order.get("id"), int):
            existing_order = self.browse(order["id"]).exists()
            for payment in existing_order.payment_ids:
                effective_lines[payment.id] = {
                    "payment_method_id": payment.payment_method_id.id,
                    "amount": payment.amount,
                }

        new_lines = []
        for command in payment_commands:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            operation = command[0]
            if operation == 0 and len(command) >= 3:
                new_lines.append(dict(command[2] or {}))
            elif operation == 1 and len(command) >= 3:
                line = effective_lines.get(command[1])
                if line is not None:
                    line.update(command[2] or {})
            elif operation in (2, 3) and len(command) >= 2:
                effective_lines.pop(command[1], None)
            elif operation == 5:
                effective_lines.clear()
                new_lines.clear()

        payment_lines = [*effective_lines.values(), *new_lines]
        payment_lines = [
            (line.get("payment_method_id"), line.get("amount", 0.0))
            for line in payment_lines
            if line.get("payment_method_id")
            and not self.env.company.currency_id.is_zero(line.get("amount", 0.0))
        ]
        payment_methods = self.env["pos.payment.method"].browse(
            [method_id for method_id, amount in payment_lines if method_id]
        )
        methods_by_id = {method.id: method for method in payment_methods}
        credit_amount = sum(
            amount for method_id, amount in payment_lines
            if methods_by_id.get(method_id) and methods_by_id[method_id].type == "pay_later"
        )
        # Odoo supports split payments. Any positive Customer Account amount is
        # therefore a real credit portion and must be rejected at an unassigned
        # POS; immediate payments do not cancel or mask that credit portion.
        if credit_amount > 0:
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
        if existing_order:
            check_order["id"] = existing_order.id
        self._check_partner_credit_pos(check_order, pos_session)
        return super()._process_order(order, existing_order)
