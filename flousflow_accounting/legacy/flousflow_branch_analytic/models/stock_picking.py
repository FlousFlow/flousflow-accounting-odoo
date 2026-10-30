from odoo import api, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def _create_picking_from_pos_order_lines(self, location_dest_id, lines, picking_type, partner=False):
        account = lines[:1].order_id.session_id.config_id.analytic_account_id
        picking_model = self.with_context(
            branch_analytic_account_id=account.id if account else False,
        )
        return super(StockPicking, picking_model)._create_picking_from_pos_order_lines(
            location_dest_id, lines, picking_type, partner,
        )

    def _create_move_from_pos_order_lines(self, lines):
        result = super()._create_move_from_pos_order_lines(lines)
        account_id = self.env.context.get('branch_analytic_account_id')
        if account_id:
            self.move_ids.write({'branch_analytic_account_id': account_id})
        return result

    def write(self, vals):
        result = super().write(vals)
        if vals.get('pos_session_id'):
            for picking in self:
                account = picking.pos_session_id.config_id.analytic_account_id
                if account:
                    picking.move_ids.write({'branch_analytic_account_id': account.id})
        return result
