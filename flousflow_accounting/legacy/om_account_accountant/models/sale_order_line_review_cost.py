from odoo import api, fields, models
from .review_accrual_read_group import formatted_read_group_with_dynamic_sums


ACCOUNTING_READ_GROUPS = ",".join([
    "account.group_account_readonly",
    "account.group_account_invoice",
    "account.group_account_user",
    "account.group_account_manager",
])


class SaleOrderLineReviewCost(models.Model):
    _inherit = "sale.order.line"

    review_accrual_unit_cost = fields.Monetary(
        string="Unit Cost",
        currency_field="currency_id",
        compute="_compute_review_accrual_unit_cost",
        store=True,
        readonly=False,
        groups=ACCOUNTING_READ_GROUPS,
    )
    review_accrual_delivered_total_cost = fields.Monetary(
        string="Delivered Total Cost",
        currency_field="currency_id",
        compute="_compute_review_accrual_delivered_total_cost",
        groups=ACCOUNTING_READ_GROUPS,
    )
    review_accrual_invoiced_total_cost = fields.Monetary(
        string="Invoiced Total Cost",
        currency_field="currency_id",
        compute="_compute_review_accrual_invoiced_total_cost",
        groups=ACCOUNTING_READ_GROUPS,
    )

    @api.depends("product_id", "company_id", "currency_id", "product_uom_id")
    def _compute_review_accrual_unit_cost(self):
        for line in self:
            line = line.with_company(line.company_id)
            product = line.product_id
            if not product or not line.product_uom_id:
                line.review_accrual_unit_cost = 0.0
                continue
            product_cost = product.uom_id._compute_price(
                product.standard_price, line.product_uom_id
            )
            line.review_accrual_unit_cost = line._convert_to_sol_currency(
                product_cost, product.cost_currency_id
            )

    @api.depends("review_accrual_unit_cost", "qty_delivered_at_date")
    @api.depends_context("accrual_entry_date")
    def _compute_review_accrual_delivered_total_cost(self):
        for line in self:
            line.review_accrual_delivered_total_cost = (
                line.review_accrual_unit_cost * line.qty_delivered_at_date
            )

    @api.depends("review_accrual_unit_cost", "qty_invoiced_at_date")
    @api.depends_context("accrual_entry_date")
    def _compute_review_accrual_invoiced_total_cost(self):
        for line in self:
            line.review_accrual_invoiced_total_cost = (
                line.review_accrual_unit_cost * line.qty_invoiced_at_date
            )

    @api.model
    @api.readonly
    def formatted_read_group(
        self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None,
    ):
        return formatted_read_group_with_dynamic_sums(
            self,
            super().formatted_read_group,
            domain,
            groupby,
            aggregates,
            having,
            offset,
            limit,
            order,
            dynamic_sums={
                "review_accrual_delivered_total_cost:sum",
                "review_accrual_invoiced_total_cost:sum",
                "qty_delivered_at_date:sum",
                "qty_invoiced_at_date:sum",
                "amount_to_invoice_at_date:sum",
            },
        )
