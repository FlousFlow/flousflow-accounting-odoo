from odoo import Command
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

FINANCIAL_MENUS = (
    'flousflow_accounting.apr__menu_account_report_bs',
    'flousflow_accounting.apr__menu_account_report_pl',
    'flousflow_accounting.apr__menu_general_ledger',
    'flousflow_accounting.apr__menu_general_balance_report',
    'flousflow_accounting.apr__menu_account_report',
    'flousflow_accounting.apr__menu_print_journal',
    'flousflow_accounting.apr__menu_account_report_annual',
)
PARTNER_MENUS = (
    'flousflow_accounting.apr__menu_interactive_customer_statement',
    'flousflow_accounting.apr__menu_partner_ledger',
    'flousflow_accounting.apr__menu_aged_trial_balance',
    'flousflow_accounting.apr__menu_aged_receivable',
    'flousflow_accounting.apr__menu_aged_payable',
)


@tagged('post_install', '-at_install')
class TestMenuAccess(AccountTestInvoicingCommon):
    """ The report menus show to the users who can run the reports, and only to them. """

    def _user(self, login, group):
        return new_test_user(self.env, login=login, groups=group, company_id=self.env.company.id,
                             company_ids=[Command.set(self.env.company.ids)])

    def _visible(self, user, xmlids):
        visible = self.env['ir.ui.menu'].with_user(user)._visible_menu_ids()
        return {xmlid for xmlid in xmlids if self.env.ref(xmlid).id in visible}

    def _run(self, user, xmlid):
        """Run the report behind a menu as `user`, including interactive actions."""
        action = self.env.ref(xmlid).action
        if action._name == 'ir.actions.client':
            if action.tag == 'flousflow_accounting.apr__aged_partner':
                data = self.env['report.flousflow_accounting.apr__report_agedpartnerbalance'].with_user(user).get_interactive_data(
                    result_selection='customer_supplier',
                )
                return {'type': action._name, 'tag': action.tag, 'data': data}
            if action.tag == 'flousflow_accounting.apr__partner_ledger':
                data = self.env['report.flousflow_accounting.apr__report_partnerledger'].with_user(user).get_interactive_data()
                return {'type': action._name, 'tag': action.tag, 'data': data}
            self.fail(f'No interactive report runner is configured for {action.tag!r}')
        wizard = self.env[action.res_model].with_user(user).with_context(active_model=action.res_model).create({})
        return wizard.check_report()

    def test_auditor_and_administrator_run_the_reports(self):
        self.init_invoice('out_invoice', amounts=[100.0], invoice_date='2025-06-01', post=True)
        for login, group in (('report_auditor', 'account.group_account_readonly'),
                             ('report_admin', 'account.group_account_manager')):
            user = self._user(login, group)
            with self.subTest(group=group):
                self.assertEqual(self._visible(user, FINANCIAL_MENUS + PARTNER_MENUS),
                                 set(FINANCIAL_MENUS + PARTNER_MENUS))
                self.assertEqual(
                    self.env.ref('flousflow_accounting.apr__menu_general_balance_report').action._name,
                    'ir.actions.client',
                )
                # The interactive destination retains the original printable wizard.
                balance_wizard = self.env['account.balance.report'].with_user(user).create({})
                balance_wizard = balance_wizard.with_context(
                    active_model=balance_wizard._name,
                    active_id=balance_wizard.id,
                    active_ids=balance_wizard.ids,
                )
                self.assertEqual(balance_wizard.check_report()['type'], 'ir.actions.report')
                for xmlid in ('flousflow_accounting.apr__menu_general_balance_report',
                              'flousflow_accounting.apr__menu_aged_trial_balance',
                              'flousflow_accounting.apr__menu_partner_ledger'):
                    if xmlid != 'flousflow_accounting.apr__menu_general_balance_report':
                        result = self._run(user, xmlid)
                        self.assertEqual(result['type'], 'ir.actions.client', xmlid)
                        self.assertTrue(result['data'], xmlid)

    def test_invoicing_user_sees_the_partner_reports(self):
        user = self._user('report_billing', 'account.group_account_invoice')
        self.assertEqual(self._visible(user, FINANCIAL_MENUS + PARTNER_MENUS), set(PARTNER_MENUS))
        result = self._run(user, 'flousflow_accounting.apr__menu_aged_trial_balance')
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertIn('rows', result['data'])
