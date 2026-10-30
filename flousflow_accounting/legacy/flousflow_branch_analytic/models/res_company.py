from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    branch_analytic_require_pos = fields.Boolean(
        string='Require Analytic Account on POS',
        default=False,
        help='Prevent closing a POS session whose configuration has no Analytic Account.',
    )
    branch_analytic_require_invoice = fields.Boolean(
        string='Require Analytic Account on Customer Invoices',
        default=False,
        help='Prevent posting a customer invoice or credit note without an Analytic Account.',
    )
    branch_analytic_require_sale = fields.Boolean(
        string='Require Analytic Account on Sales Orders',
        default=False,
        help='Prevent confirming a sales order without an Analytic Account.',
    )
