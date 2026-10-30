from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    open_items_balance = fields.Monetary(
        string='Open Items', compute='_compute_open_items_summary', compute_sudo=True,
        currency_field='company_currency_id',
    )
    open_items_count = fields.Integer(compute='_compute_open_items_summary', compute_sudo=True)
    company_currency_id = fields.Many2one(
        'res.currency', compute='_compute_company_currency',
    )

    @api.depends_context('company')
    def _compute_company_currency(self):
        for partner in self:
            partner.company_currency_id = self.env.company.currency_id

    @api.depends_context('company')
    def _compute_open_items_summary(self):
        for partner in self:
            partner.open_items_balance = 0.0
            partner.open_items_count = 0
        if not self:
            return

        commercial_ids = self.commercial_partner_id.ids
        grouped = self.env['account.move.line'].sudo()._read_group(
            [
                ('partner_id', 'child_of', commercial_ids),
                ('company_id', '=', self.env.company.id),
                ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
                ('parent_state', '=', 'posted'),
                ('amount_residual', '!=', 0),
            ],
            ['partner_id'],
            ['amount_residual:sum', '__count'],
        )
        values_by_commercial = {}
        for partner, amount, count in grouped:
            commercial = partner.commercial_partner_id
            balance, line_count = values_by_commercial.get(commercial.id, (0.0, 0))
            values_by_commercial[commercial.id] = (balance + amount, line_count + count)
        for partner in self:
            partner.open_items_balance, partner.open_items_count = values_by_commercial.get(
                partner.commercial_partner_id.id, (0.0, 0)
            )

    def action_open_accounting_items(self):
        self.ensure_one()
        return self.env['report.flousflow_accounting.apr__report_agedpartnerbalance'].get_open_items_action(
            self.commercial_partner_id.id
        )

    def action_open_partner_ledger(self):
        self.ensure_one()
        action = self.env.ref('flousflow_accounting.apr__action_interactive_partner_ledger').read()[0]
        action['context'] = {
            **self.env.context,
            'partner_ids': [self.commercial_partner_id.id],
        }
        return action
