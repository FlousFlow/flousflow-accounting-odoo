from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        check_company=True,
        copy=False,
        help='Branch / profit center analytic account applied to invoice product lines and their COGS.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if (
                vals.get('move_type') in ('out_invoice', 'out_refund')
                and not vals.get('analytic_account_id')
                and vals.get('partner_id')
            ):
                partner = self.env['res.partner'].browse(vals['partner_id']).with_company(
                    vals.get('company_id') or self.env.company.id
                )
                if partner.analytic_account_id:
                    vals['analytic_account_id'] = partner.analytic_account_id.id
        moves = super().create(vals_list)
        moves.filtered('analytic_account_id')._apply_branch_analytic_distribution()
        return moves

    @api.onchange('partner_id')
    def _onchange_partner_analytic_account(self):
        for move in self:
            if (
                move.move_type in ('out_invoice', 'out_refund')
                and move.partner_id
                and not move.analytic_account_id
            ):
                move.analytic_account_id = move.partner_id.with_company(
                    move.company_id
                ).analytic_account_id
                move._apply_branch_analytic_distribution()

    @api.onchange('analytic_account_id')
    def _onchange_branch_analytic_account_id(self):
        if not self.analytic_account_id:
            return
        self._apply_branch_analytic_distribution()

    def _get_branch_analytic_distribution(self):
        return {str(self.analytic_account_id.id): 100.0} if self.analytic_account_id else None

    def _apply_branch_analytic_distribution(self):
        """Apply the header analytic account (100%) to commercial invoice lines.

        Only 'product' lines are updated. Tax lines, payment-term lines,
        receivable lines, sections and notes are left untouched. An empty
        header never modifies existing line-level distributions.
        """
        distribution = self._get_branch_analytic_distribution()
        if not distribution:
            return
        for line in self.line_ids.filtered(lambda l: l.display_type == 'product'):
            line.analytic_distribution = distribution

    def _check_branch_analytic_required(self):
        for move in self:
            if (
                move.company_id.branch_analytic_require_invoice
                and move.move_type in ('out_invoice', 'out_refund')
                and not move.analytic_account_id
            ):
                raise UserError(_(
                    "Please select an Analytic Account before posting this customer invoice."
                ))

    def _post(self, soft=True):
        self._check_branch_analytic_required()
        return super()._post(soft=soft)
