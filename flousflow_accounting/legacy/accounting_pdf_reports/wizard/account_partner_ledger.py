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

    def _infer_partner_result_selection(self, partner):
        """Infer a single-role scope when the contact ranks are not populated.

        Odoo contacts imported from external systems can have both ranks at
        zero even though their posted ledger lines clearly identify them as a
        customer or a vendor.  Use the posted partner accounts only as a
        fallback; an explicit menu context or a dual-role contact remains
        authoritative.
        """
        MoveLine = self.env['account.move.line'].with_company(self.env.company)
        base_domain = [
            ('partner_id.commercial_partner_id', '=', partner.commercial_partner_id.id),
            ('company_id', '=', self.env.company.id),
        ]
        has_receivable = bool(MoveLine.search(
            base_domain + [('account_id.account_type', '=', 'asset_receivable')],
            limit=1,
        ))
        has_payable = bool(MoveLine.search(
            base_domain + [('account_id.account_type', '=', 'liability_payable')],
            limit=1,
        ))
        if has_payable and not has_receivable:
            return 'supplier'
        if has_receivable and not has_payable:
            return 'customer'
        return False

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if (
            'date_to' in fields_list
            and values.get('document_type') == 'balance_confirmation'
            and not values.get('date_to')
        ):
            values['date_to'] = fields.Date.context_today(self)
        if values.get('document_type') == 'balance_confirmation':
            # The confirmation document is always a net statement, not a
            # customer-only or vendor-only report.
            values['result_selection'] = 'customer_supplier'

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
        else:
            inferred_scope = self._infer_partner_result_selection(partner)
            if inferred_scope:
                values['result_selection'] = inferred_scope
        return values

    @api.onchange('document_type')
    def _onchange_document_type(self):
        if self.document_type == 'balance_confirmation' and not self.date_to:
            self.date_to = fields.Date.context_today(self)
        if self.document_type == 'balance_confirmation':
            self.result_selection = 'customer_supplier'

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
            # A balance confirmation is a statement of the partner's net balance.
            # It must include both receivable and payable lines: payments, refunds,
            # reclassifications, and dual-role partners can legitimately have both.
            # Do not infer the scope from contact ranks or from the direction of a
            # single move.
            self.result_selection = 'customer_supplier'
        data = self._get_report_data(data)
        report_xmlid = (
            'flousflow_accounting.apr__action_report_partnerledger_confirmation'
            if self.document_type == 'balance_confirmation'
            else 'flousflow_accounting.apr__action_report_partnerledger'
        )
        return self.env.ref(report_xmlid).with_context(
            landscape=self.document_type != 'balance_confirmation', lang=self.env.user.lang,
        ).\
            report_action(self, data=data)
