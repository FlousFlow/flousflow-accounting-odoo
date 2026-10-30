"""Branch analytic propagation for sales, POS, and inventory valuation."""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResCompany(models.Model):
    _inherit = 'res.company'

    branch_analytic_require_pos = fields.Boolean(
        string='Require Analytic Account on POS', default=False,
        help='Prevent closing a POS session whose configuration has no Analytic Account.',
    )
    branch_analytic_require_invoice = fields.Boolean(
        string='Require Analytic Account on Customer Invoices', default=False,
        help='Prevent posting a customer invoice or credit note without an Analytic Account.',
    )
    branch_analytic_require_sale = fields.Boolean(
        string='Require Analytic Account on Sales Orders', default=False,
        help='Prevent confirming a sales order without an Analytic Account.',
    )


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    branch_analytic_require_pos = fields.Boolean(related='company_id.branch_analytic_require_pos', readonly=False)
    branch_analytic_require_invoice = fields.Boolean(related='company_id.branch_analytic_require_invoice', readonly=False)
    branch_analytic_require_sale = fields.Boolean(related='company_id.branch_analytic_require_sale', readonly=False)


class PosConfig(models.Model):
    _inherit = 'pos.config'

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', check_company=True,
        help='Branch / profit center analytic account applied to POS sales, refunds and COGS.',
    )


class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _prepare_account_move_line_data(self, aggregate=True):
        lines = super()._prepare_account_move_line_data(aggregate=aggregate)
        account = self[:1].config_id.analytic_account_id
        if account:
            for line_data in lines:
                vals = line_data.get('account.move.line', {})
                if vals.get('display_type') == 'product':
                    vals['analytic_distribution'] = {str(account.id): 100.0}
        return lines

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        account = self.config_id.analytic_account_id
        if account:
            vals['analytic_account_id'] = account.id
        return vals


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_branch_analytic_distribution(self):
        account = self.config_id.analytic_account_id
        return {str(account.id): 100.0} if account else None

    def _get_sale_vals(self, key, sale_vals):
        vals = super()._get_sale_vals(key, sale_vals)
        distribution = self._get_branch_analytic_distribution()
        if distribution:
            vals['analytic_distribution'] = distribution
        return vals

    def _get_stock_expense_vals(self, exp_account, amount, amount_converted):
        vals = super()._get_stock_expense_vals(exp_account, amount, amount_converted)
        distribution = self._get_branch_analytic_distribution()
        if distribution:
            vals['analytic_distribution'] = distribution
        return vals

    def _check_branch_analytic_required(self):
        for session in self:
            if session.company_id.branch_analytic_require_pos and not session.config_id.analytic_account_id:
                raise UserError(_(
                    "An Analytic Account must be configured for the Point of Sale '%(pos)s' before closing the session.",
                    pos=session.config_id.name,
                ))

    def _validate_session_accounting(self):
        self._check_branch_analytic_required()
        return super()._validate_session_accounting()


class AccountMove(models.Model):
    _inherit = 'account.move'

    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', check_company=True,
        copy=False,
        help='Branch / profit center analytic account applied to invoice product lines and their COGS.',
    )

    @api.onchange('analytic_account_id')
    def _onchange_branch_analytic_account_id(self):
        self._apply_branch_analytic_distribution()

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._apply_branch_analytic_distribution()
        return moves

    def write(self, vals):
        result = super().write(vals)
        if 'analytic_account_id' in vals:
            self._apply_branch_analytic_distribution()
        return result

    def _apply_branch_analytic_distribution(self):
        for move in self:
            if move.analytic_account_id:
                distribution = {str(move.analytic_account_id.id): 100.0}
                move.line_ids.filtered(lambda line: line.display_type == 'product').analytic_distribution = distribution

    def _check_branch_analytic_required(self):
        for move in self:
            if (move.company_id.branch_analytic_require_invoice
                    and move.move_type in ('out_invoice', 'out_refund')
                    and not move.analytic_account_id):
                raise UserError(_(
                    'Please select an Analytic Account before posting this customer invoice.'
                ))

    def _post(self, soft=True):
        self._check_branch_analytic_required()
        self._apply_branch_analytic_distribution()
        return super()._post(soft=soft)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.onchange('analytic_account_id')
    def _onchange_branch_analytic_account_id(self):
        self._apply_branch_analytic_distribution()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        orders._apply_branch_analytic_distribution()
        return orders

    def write(self, vals):
        result = super().write(vals)
        if 'analytic_account_id' in vals:
            self._apply_branch_analytic_distribution()
        return result

    def _apply_branch_analytic_distribution(self):
        for order in self:
            if order.analytic_account_id:
                distribution = {str(order.analytic_account_id.id): 100.0}
                order.order_line.filtered(lambda line: not line.display_type).analytic_distribution = distribution

    def _check_branch_analytic_required(self):
        for order in self:
            if order.company_id.branch_analytic_require_sale and not order.analytic_account_id:
                raise UserError(_('Please select an Analytic Account before confirming this sales order.'))

    def action_confirm(self):
        self._check_branch_analytic_required()
        self._apply_branch_analytic_distribution()
        return super().action_confirm()


class StockMove(models.Model):
    _inherit = 'stock.move'

    branch_analytic_account_id = fields.Many2one('account.analytic.account', copy=False, check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        account_id = self.env.context.get('branch_analytic_account_id')
        if account_id:
            vals_list = [dict(vals, branch_analytic_account_id=account_id) for vals in vals_list]
        return super().create(vals_list)

    def _get_account_move_line_vals(self):
        vals_list = super()._get_account_move_line_vals()
        for move in self:
            order = move.picking_id.pos_order_id
            account = (order.config_id.analytic_account_id if order else False) or move.branch_analytic_account_id
            if not account:
                continue
            valuation_account = move.product_id._get_product_accounts().get('stock_valuation')
            for vals in vals_list:
                if vals.get('account_id') != valuation_account.id:
                    vals['analytic_distribution'] = {str(account.id): 100.0}
        return vals_list


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def _create_picking_from_pos_order_lines(self, location_dest_id, lines, picking_type, partner=False):
        account = lines[:1].order_id.session_id.config_id.analytic_account_id
        picking_model = self.with_context(branch_analytic_account_id=account.id if account else False)
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
