from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    branch_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        copy=False,
        check_company=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        account_id = self.env.context.get('branch_analytic_account_id')
        if account_id:
            vals_list = [dict(vals, branch_analytic_account_id=account_id) for vals in vals_list]
        return super().create(vals_list)

    def _get_account_move_line_vals(self):
        """Carry the POS branch analytic to Odoo 20 stock valuation lines.

        Odoo 20 creates valuation entries from ``stock.move`` rather than the
        removed POS-session expense hook. The non-valuation line on an outgoing
        POS move is the COGS/stock-output line and is the only line tagged.
        """
        vals_list = super()._get_account_move_line_vals()
        order = self.picking_id.pos_order_id
        account = order.config_id.analytic_account_id if order else False
        account = account or self.branch_analytic_account_id
        if not account:
            return vals_list

        valuation_account = self.product_id._get_product_accounts().get('stock_valuation')
        for vals in vals_list:
            if vals.get('account_id') != valuation_account.id:
                vals['analytic_distribution'] = {str(account.id): 100.0}
        return vals_list
