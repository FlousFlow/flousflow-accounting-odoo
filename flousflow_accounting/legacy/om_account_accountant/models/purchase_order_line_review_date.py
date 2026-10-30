from odoo import api, fields, models
from .review_accrual_read_group import formatted_read_group_with_dynamic_sums


class PurchaseOrderLineReviewDate(models.Model):
    _inherit = "purchase.order.line"

    @api.model
    def _get_accrual_line_ids(self, mode=False, date=False, extra_domain=None):
        date = date or fields.Date.to_date(self.env.context.get("accrual_entry_date"))
        return super()._get_accrual_line_ids(mode, date, extra_domain)

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
                "qty_received_at_date:sum",
                "qty_invoiced_at_date:sum",
                "amount_to_invoice_at_date:sum",
            },
        )
