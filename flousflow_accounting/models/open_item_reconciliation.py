# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, _
from odoo.exceptions import AccessError, UserError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    def action_flousflow_reconcile_open_items(self):
        """Reconcile selected open items on any reconcilable account natively."""
        if not self.env.user.has_group('account.group_account_user'):
            raise AccessError(_('Only accounting users can reconcile open items.'))
        if len(self) < 2:
            raise UserError(_('Select at least two open items to reconcile.'))

        invalid_lines = self.filtered(lambda line: (
            line.parent_state != 'posted'
            or not line.account_id.reconcile
            or not line.amount_residual
            or line.full_reconcile_id
            or line.company_id not in self.env.companies
        ))
        if invalid_lines:
            raise UserError(_(
                'Only posted, open items on reconcilable accounts in your allowed '
                'companies can be reconciled here.'
            ))

        groups = defaultdict(lambda: self.browse())
        for line in self:
            key = (line.company_id.id, line.account_id.id, line.partner_id.id)
            groups[key] |= line

        if any(len(lines.move_id) < 2 for lines in groups.values()):
            raise UserError(_(
                'Select open items from at least two different journal entries for the same '
                'company, account, and partner.'
            ))

        for lines in groups.values():
            lines.with_company(lines[0].company_id).reconcile()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reconciliation completed'),
                'message': _('%s selected journal items were processed.') % len(self),
                'type': 'success',
                'sticky': False,
            },
        }
