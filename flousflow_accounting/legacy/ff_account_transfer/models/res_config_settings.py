from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    internal_transfer_fee_account_id = fields.Many2one(
        related='company_id.transfer_fee_account_id',
        string='Internal Transfer Fee Expense Account',
        readonly=False,
    )
