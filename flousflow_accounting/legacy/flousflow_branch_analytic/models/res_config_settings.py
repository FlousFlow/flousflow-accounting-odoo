from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    branch_analytic_require_pos = fields.Boolean(
        related='company_id.branch_analytic_require_pos',
        readonly=False,
    )
    branch_analytic_require_invoice = fields.Boolean(
        related='company_id.branch_analytic_require_invoice',
        readonly=False,
    )
    branch_analytic_require_sale = fields.Boolean(
        related='company_id.branch_analytic_require_sale',
        readonly=False,
    )
