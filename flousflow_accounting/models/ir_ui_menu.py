# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _flousflow_hide_legacy_account_roots(self):
        """Hide known legacy roots that duplicate this suite's features."""
        legacy_xml_ids = (
            'om_account_followup.menu_finance_followup',
            'recurring_accruals.menu_recurring_accruals_root',
            # Merged into this suite: internal transfers are now provided by
            # flousflow_accounting (flousflow_menu_account_payments_transfer).
            'ff_account_transfer.menu_action_account_payments_transfer',
        )
        menus = self.browse()
        for xml_id in legacy_xml_ids:
            menu = self.env.ref(xml_id, raise_if_not_found=False)
            if menu and menu._name == 'ir.ui.menu':
                menus |= menu
        menus.write({'active': False})
        # Disable the legacy form inheritance that adds the same internal
        # transfer fields on account.payment (now defined by this suite), so
        # the fields are not rendered twice on the payment form.
        legacy_views = (
            'ff_account_transfer.view_account_payment_form_inherit_transfer',
            'ff_account_transfer.account_journal_dashboard_kanban_view_inherit',
        )
        for xml_id in legacy_views:
            view = self.env.ref(xml_id, raise_if_not_found=False)
            if view and view._name == 'ir.ui.view':
                view.active = False
        return True
