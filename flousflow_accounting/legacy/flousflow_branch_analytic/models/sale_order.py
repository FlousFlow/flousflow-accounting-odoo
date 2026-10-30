from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        check_company=True,
        copy=False,
        help='Branch / profit center analytic account applied to sale order lines and their invoices/COGS.',
    )

    @api.onchange('analytic_account_id')
    def _onchange_branch_analytic_account_id(self):
        if not self.analytic_account_id:
            return
        self._apply_branch_analytic_distribution()

    def _apply_branch_analytic_distribution(self):
        """Apply the header analytic account (100%) to commercial sale order lines.

        Only real product lines (no display_type) are updated; sections and notes
        are left untouched. An empty header never modifies existing line-level
        distributions, which are then propagated natively to invoice and COGS.
        """
        distribution = {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else None
        if not distribution:
            return
        for line in self.order_line.filtered(lambda l: not l.display_type):
            line.analytic_distribution = distribution

    def _check_branch_analytic_required(self):
        for order in self:
            if order.company_id.branch_analytic_require_sale and not order.analytic_account_id:
                raise UserError(_(
                    "Please select an Analytic Account before confirming this sales order."
                ))

    def action_confirm(self):
        self._check_branch_analytic_required()
        return super().action_confirm()
