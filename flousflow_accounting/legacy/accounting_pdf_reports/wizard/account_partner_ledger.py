from odoo import fields, models, api, _
from odoo.exceptions import UserError


class AccountPartnerLedger(models.TransientModel):
    _name = "account.report.partner.ledger"
    _inherit = "account.common.partner.report"
    _description = "Account Partner Ledger"

    amount_currency = fields.Boolean("With Currency",
                                     help="It adds the currency column on "
                                          "report if the currency differs from "
                                          "the company currency.")
    reconciled = fields.Boolean('Reconciled Entries')
    document_type = fields.Selection(
        [
            ('statement', 'Account Statement'),
            ('balance_confirmation', 'Balance Confirmation'),
        ],
        string='Document Type',
        required=True,
        default='statement',
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if (
            'date_to' in fields_list
            and values.get('document_type') == 'balance_confirmation'
            and not values.get('date_to')
        ):
            values['date_to'] = fields.Date.context_today(self)

        if 'result_selection' not in fields_list or self.env.context.get('default_result_selection'):
            return values

        context = self.env.context
        partner_ids = context.get('active_ids') or [context.get('active_id')]
        partner_ids = [partner_id for partner_id in partner_ids if partner_id]
        if context.get('active_model') != 'res.partner' or len(partner_ids) != 1:
            return values

        partner = self.env['res.partner'].browse(partner_ids).exists()
        if not partner:
            return values

        # The Customers and Vendors menus pass this hint through the partner
        # form. It also disambiguates partners that have both roles.
        partner_mode = context.get('res_partner_search_mode')
        if partner_mode == 'supplier' and partner.supplier_rank:
            values['result_selection'] = 'supplier'
        elif partner_mode == 'customer' and partner.customer_rank:
            values['result_selection'] = 'customer'
        elif partner.supplier_rank and not partner.customer_rank:
            values['result_selection'] = 'supplier'
        elif partner.customer_rank:
            # For a dual-role contact, start with receivables. The user can
            # choose Payable Accounts in the wizard before printing instead.
            values['result_selection'] = 'customer'
        return values

    @api.onchange('document_type')
    def _onchange_document_type(self):
        if self.document_type == 'balance_confirmation' and not self.date_to:
            self.date_to = fields.Date.context_today(self)

    def _get_report_data(self, data):
        data = self.pre_print_report(data)
        data['form'].update({'reconciled': self.reconciled,
                             'amount_currency': self.amount_currency,
                             'document_type': self.document_type})
        return data

    def _print_report(self, data):
        if self.document_type == 'balance_confirmation':
            if len(self.partner_ids) != 1:
                raise UserError(_('Select exactly one partner to print a balance confirmation.'))
            if not self.date_to:
                raise UserError(_('Set an end date to calculate the confirmed balance.'))
            if self.target_move != 'posted':
                raise UserError(_('Balance confirmations can include posted entries only.'))
            if self.result_selection == 'customer_supplier':
                partner = self.partner_ids
                is_customer = bool(partner.customer_rank)
                is_supplier = bool(partner.supplier_rank)
                if is_customer != is_supplier:
                    # The interactive ledger's default scope includes both account
                    # types. Resolve it for a single-role partner so Print works
                    # directly from the partner ledger and partner form.
                    self.result_selection = 'customer' if is_customer else 'supplier'
                else:
                    raise UserError(_(
                        'Choose Receivable Accounts or Payable Accounts for a balance '
                        'confirmation. This partner has both or neither role.'
                    ))
            elif self.result_selection not in ('customer', 'supplier'):
                raise UserError(_(
                    'Choose Receivable Accounts or Payable Accounts for a balance confirmation.'
                ))
        data = self._get_report_data(data)
        return self.env.ref('flousflow_accounting.apr__action_report_partnerledger').with_context(
            landscape=True, lang=self.env.user.lang,
        ).\
            report_action(self, data=data)
