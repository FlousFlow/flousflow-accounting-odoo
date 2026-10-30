from odoo import _, models
from odoo.exceptions import UserError


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_branch_analytic_distribution(self):
        """Return the analytic distribution dict for this session's POS config,
        or None when no analytic account is configured.

        One pos.session belongs to one pos.config, so all uninvoiced orders in
        the session share the same analytic account.
        """
        account = self.config_id.analytic_account_id
        return {str(account.id): 100.0} if account else None

    def _get_sale_vals(self, key, sale_vals):
        """Inject the branch analytic distribution into POS sales / refund lines.

        Covers both revenue (sign == 1) and revenue reversal (sign == -1):
        the refund is represented by a negative amount on the same line group,
        so assigning the distribution here keeps the branch P&L netted.
        """
        vals = super()._get_sale_vals(key, sale_vals)
        distribution = self._get_branch_analytic_distribution()
        if distribution:
            vals['analytic_distribution'] = distribution
        return vals

    def _get_stock_expense_vals(self, exp_account, amount, amount_converted):
        """Inject the branch analytic distribution into POS COGS / COGS-reversal lines.

        A POS refund produces a negative amount on this same expense group,
        so a full refund nets the branch COGS back to zero.
        """
        vals = super()._get_stock_expense_vals(exp_account, amount, amount_converted)
        distribution = self._get_branch_analytic_distribution()
        if distribution:
            vals['analytic_distribution'] = distribution
        return vals

    def _check_branch_analytic_required(self):
        for record in self:
            if record.company_id.branch_analytic_require_pos and not record.config_id.analytic_account_id:
                raise UserError(_(
                    "An Analytic Account must be configured for the Point of Sale "
                    "'%(pos)s' before closing the session.",
                    pos=record.config_id.name,
                ))

    def _validate_session_accounting(self):
        """Enforce branch configuration before Odoo 20 creates closing moves."""
        self._check_branch_analytic_required()
        return super()._validate_session_accounting()
