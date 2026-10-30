from odoo import fields, models

CHECK_FORMAT_LAYOUT = 'flousflow_accounting.chk__action_report_check'


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_check_printing_layout = fields.Selection(
        selection_add=[(CHECK_FORMAT_LAYOUT, 'Configurable Cheque Format')],
        ondelete={CHECK_FORMAT_LAYOUT: 'set default'},
    )
