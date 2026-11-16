from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    transfer_fee_account_id = fields.Many2one(
        'account.account',
        string='Internal Transfer Fee Expense Account',
        check_company=True,
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost')), ('deprecated', '=', False)]",
        help='Expense account used for bank fees entered on internal transfers.',
    )
