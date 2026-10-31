from odoo import _, fields, models


class AccountTaxReturnCreateWizard(models.TransientModel):
    _name = 'account.tax.return.create.wizard'
    _description = 'Create Tax Return'

    return_type = fields.Selection(
        selection=[
            ('annual_corporate_tax', 'Annual Closing: Corporate Tax'),
            ('tax', 'Tax Return'),
        ],
        string='Return Type',
        required=True,
        default='annual_corporate_tax',
    )
    date_from = fields.Date(
        string='Start Date',
        required=True,
        default=lambda self: self.env['account.tax.return']._default_period_dates()['date_from'],
    )
    date_to = fields.Date(
        string='End Date',
        required=True,
        default=lambda self: self.env['account.tax.return']._default_period_dates()['date_to'],
    )

    def action_create_return(self):
        self.ensure_one()
        self.env['account.tax.return'].create({
            'return_type': self.return_type,
            'date_from': self.date_from,
            'date_to': self.date_to,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}
