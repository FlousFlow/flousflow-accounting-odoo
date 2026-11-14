from collections import defaultdict

from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import formatLang

# the documents that add to what a customer owes
CREDIT_LIMIT_TYPES = ('out_invoice', 'out_receipt')


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_effective_credit_limit(self, partner, company):
        """Return the effective limit, allowing an explicit contact limit to override the default."""
        if company.credit_limit_scope == 'global' and not partner.use_partner_credit_limit:
            return company.account_credit_limit
        return partner.credit_limit

    def _build_credit_warning_message(self, record, current_amount=0.0, exclude_current=False, exclude_amount=0.0):
        if record.company_id.credit_limit_scope != 'global':
            return super()._build_credit_warning_message(
                record,
                current_amount=current_amount,
                exclude_current=exclude_current,
                exclude_amount=exclude_amount,
            )
        partner_id = record.partner_id.commercial_partner_id
        credit_to_invoice = partner_id.credit_to_invoice - exclude_amount
        total_credit = partner_id.credit + credit_to_invoice + current_amount
        credit_limit = self._get_effective_credit_limit(partner_id, record.company_id)
        if not credit_limit or total_credit <= credit_limit:
            return ''
        msg = _(
            '%(partner_name)s has reached its credit limit of: %(credit_limit)s',
            partner_name=partner_id.name,
            credit_limit=formatLang(self.env, credit_limit, currency_obj=record.company_id.currency_id),
        )
        total_credit_formatted = formatLang(self.env, total_credit, currency_obj=record.company_id.currency_id)
        if credit_to_invoice > 0 and current_amount > 0:
            detail = _('Total amount due (including sales orders and this document): %(total_credit)s', total_credit=total_credit_formatted)
        elif credit_to_invoice > 0:
            detail = _('Total amount due (including sales orders): %(total_credit)s', total_credit=total_credit_formatted)
        elif current_amount > 0:
            detail = _('Total amount due (including this document): %(total_credit)s', total_credit=total_credit_formatted)
        else:
            detail = _('Total amount due: %(total_credit)s', total_credit=total_credit_formatted)
        return msg + '\n' + detail

    @api.model
    def _get_invoice_in_payment_state(self):
        return 'in_payment'

    def _check_credit_limit(self):
        """ A customer invoice going over the credit limit of the customer is refused, unless the user is
        allowed to override it: the override is then logged on the invoice. """
        can_override = self.env.user.has_group('flousflow_accounting.acc__group_credit_limit_override')
        # the invoices posted together add up: the customer owes them all at the end
        posted_together = defaultdict(float)
        for move in self:
            company = move.company_id
            if move.move_type not in CREDIT_LIMIT_TYPES or move.state != 'draft' \
                    or not company.credit_limit_block or not company.account_use_credit_limit:
                continue
            move = move.with_company(company)
            partner = move.partner_id.commercial_partner_id
            if not partner:
                continue
            # what the customer owes is read again: the invoices posted since are part of it
            partner.invalidate_recordset(['credit', 'credit_to_invoice'])
            current_amount = move.amount_total_signed + posted_together[partner]
            posted_together[partner] += move.amount_total_signed
            warning = move._build_credit_warning_message(
                move,
                current_amount=current_amount,
                exclude_amount=move._get_partner_credit_warning_exclude_amount(),
            )
            if not warning:
                continue
            if not can_override:
                raise UserError(_(
                    '%(warning)s\n\nThis invoice cannot be posted: ask an accounting manager to post it, or '
                    'collect what the customer owes first.', warning=warning,
                ))
            move.message_post(body=_('Posted over the credit limit of the customer.\n%(warning)s',
                                     warning=warning))

    def _post(self, soft=True):
        self._check_credit_limit()
        return super()._post(soft)
