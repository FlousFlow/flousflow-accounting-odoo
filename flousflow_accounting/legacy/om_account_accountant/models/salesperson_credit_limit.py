from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount


class SalespersonCreditLimit(models.Model):
    _name = "salesperson.credit.limit"
    _description = "Salesperson Credit Limit"
    _rec_name = "name"
    _order = "company_id, salesperson_id"

    name = fields.Char(compute="_compute_name", store=True)
    salesperson_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        required=True,
        index=True,
        domain=[("share", "=", False)],
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company, index=True
    )
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    credit_limit = fields.Monetary(
        string="Credit Limit",
        currency_field="currency_id",
        required=True,
        default=0.0,
        help="Maximum open credit exposure this salesperson may confirm. Zero means no limit.",
    )
    active = fields.Boolean(default=True)
    used_credit = fields.Monetary(
        string="Used Credit", currency_field="currency_id", compute="_compute_credit_usage", compute_sudo=True
    )
    available_credit = fields.Monetary(
        string="Available Credit", currency_field="currency_id", compute="_compute_credit_usage", compute_sudo=True
    )
    utilization_percent = fields.Float(string="Utilization", compute="_compute_credit_usage", compute_sudo=True)

    _salesperson_company_unique = models.Constraint(
        "unique(salesperson_id, company_id)",
        "A salesperson can have only one credit limit per company.",
    )
    _credit_limit_non_negative = models.Constraint(
        "CHECK(credit_limit >= 0)",
        "The credit limit cannot be negative.",
    )

    @api.depends("salesperson_id", "company_id")
    def _compute_name(self):
        for record in self:
            record.name = record.salesperson_id.display_name or _("New")

    @api.depends("credit_limit", "salesperson_id", "company_id", "active")
    def _compute_credit_usage(self):
        for record in self:
            usage = self._get_salesperson_credit_usage(record.salesperson_id, record.company_id) if record.active else 0.0
            record.used_credit = usage
            record.available_credit = max(record.credit_limit - usage, 0.0) if record.credit_limit else 0.0
            record.utilization_percent = (usage / record.credit_limit * 100.0) if record.credit_limit else 0.0

    @api.model
    def _get_salesperson_credit_usage(self, salesperson, company):
        """Return open exposure in the company's currency.

        Posted receivables use the accounting residual, while confirmed sales orders
        reserve only their not-yet-invoiced balance. This avoids double counting.
        """
        if not salesperson or not company:
            return 0.0
        Move = self.env["account.move"].sudo().with_company(company)
        moves = Move.search(
            [
                ("company_id", "=", company.id),
                ("invoice_user_id", "=", salesperson.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
                ("state", "=", "posted"),
            ]
        )
        usage = sum(moves.mapped("amount_residual_signed"))
        orders = self.env["sale.order"].sudo().with_company(company).search(
            [
                ("company_id", "=", company.id),
                ("user_id", "=", salesperson.id),
                ("state", "in", ("sale", "done")),
                ("invoice_status", "!=", "invoiced"),
            ]
        )
        today = fields.Date.context_today(self)
        for order in orders:
            usage += order.currency_id._convert(
                order.amount_to_invoice,
                company.currency_id,
                company,
                order.date_order.date() if order.date_order else today,
            )
        return max(usage, 0.0)

    @api.constrains("salesperson_id", "company_id")
    def _check_salesperson_company(self):
        for record in self:
            if record.salesperson_id.share:
                raise ValidationError(_("A portal user cannot be assigned as a salesperson credit owner."))


class ResCompany(models.Model):
    _inherit = "res.company"

    salesperson_credit_limit_block = fields.Boolean(
        string="Enforce Salesperson Credit Limits",
        help="Refuse confirming sales orders when the salesperson's open exposure exceeds their configured limit.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    salesperson_credit_limit_block = fields.Boolean(
        related="company_id.salesperson_credit_limit_block", readonly=False
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _check_salesperson_credit_limit(self):
        if not self:
            return
        limits = self.env["salesperson.credit.limit"].sudo().search(
            [
                ("company_id", "in", self.mapped("company_id").ids),
                ("salesperson_id", "in", self.mapped("user_id").ids),
                ("active", "=", True),
            ]
        )
        limits_by_key = {(limit.company_id.id, limit.salesperson_id.id): limit for limit in limits}
        additions = defaultdict(float)
        can_override = self.env.user.has_group("sales_team.group_sale_manager") or self.env.user.has_group(
            "account.group_account_manager"
        )
        for order in self:
            if not order.company_id.salesperson_credit_limit_block or not order.user_id:
                continue
            limit = limits_by_key.get((order.company_id.id, order.user_id.id))
            if not limit or not limit.credit_limit:
                continue
            key = (order.company_id.id, order.user_id.id)
            used = self.env["salesperson.credit.limit"]._get_salesperson_credit_usage(
                order.user_id, order.company_id
            )
            current = used + additions[key]
            order_amount = order.currency_id._convert(
                order.amount_total,
                order.company_id.currency_id,
                order.company_id,
                order.date_order.date() if order.date_order else fields.Date.context_today(order),
            )
            projected = current + order_amount
            if projected <= limit.credit_limit:
                additions[key] += order_amount
                continue
            message = _(
                "Salesperson %(salesperson)s cannot confirm this order.\n"
                "Credit limit: %(limit)s\n"
                "Already used: %(used)s\n"
                "This order: %(order)s\n"
                "Projected exposure: %(projected)s\n"
                "Available before this order: %(available)s",
                salesperson=order.user_id.display_name,
                limit=format_amount(self.env, limit.credit_limit, order.company_id.currency_id),
                used=format_amount(self.env, current, order.company_id.currency_id),
                order=format_amount(self.env, order_amount, order.company_id.currency_id),
                projected=format_amount(self.env, projected, order.company_id.currency_id),
                available=format_amount(
                    self.env, max(limit.credit_limit - current, 0.0), order.company_id.currency_id
                ),
            )
            if not can_override:
                raise UserError(message)
            order.message_post(body=_(
                "Credit limit override used by %(user)s.\n%(message)s",
                user=self.env.user.display_name,
                message=message,
            ))
            additions[key] += order_amount

    def action_confirm(self):
        self._check_salesperson_credit_limit()
        return super().action_confirm()
