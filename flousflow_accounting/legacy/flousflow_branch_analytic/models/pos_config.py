from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        check_company=True,
        help='Branch / profit center analytic account applied to POS sales, refunds and COGS.',
    )
