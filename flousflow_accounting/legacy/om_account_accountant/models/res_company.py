from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    credit_limit_block = fields.Boolean(
        string='Block Over the Credit Limit',
        help="Refuse to post a customer invoice that brings the customer over its credit limit. The users "
             "allowed to override the credit limit can still post it, and the override is logged on the invoice.")
    credit_limit_scope = fields.Selection(
        selection=[
            ('global', 'One limit for all customers'),
            ('partner', 'Individual limit per contact'),
        ],
        string='Credit Limit Scope',
        default='global',
        required=True,
        help='Choose whether the company default applies to every customer or each contact can use a specific limit.',
    )
