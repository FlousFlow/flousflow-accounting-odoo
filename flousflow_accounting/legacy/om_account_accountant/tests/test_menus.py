from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged

# where each menu of the accounting apps stands: daily work, reports, settings
PARENTS = {
    'account.menu_action_account_moves_all': 'account.account_transactions_menu',
    'flousflow_accounting.rec__menu_bank_reconciliation': 'flousflow_accounting.rec__menu_reconciliation',
    'flousflow_accounting.rec__menu_open_items_reconciliation': 'flousflow_accounting.rec__menu_reconciliation',
    'flousflow_accounting.rec__menu_move_line_match': 'flousflow_accounting.rec__menu_reconciliation',
    'flousflow_accounting.rec__menu_reconciliation': 'account.menu_finance_entries',
    'flousflow_accounting.acc__menu_review_bank_rec_to_review': 'flousflow_accounting.rec__menu_reconciliation',
    'flousflow_accounting.ast__menu_action_account_asset_asset_form': 'account.menu_finance_entries',
    'flousflow_accounting.bgt__menu_account_budget': 'account.menu_finance_entries',
    'flousflow_accounting.rcp__menu_recurring_payment': 'account.menu_finance_entries',
    'flousflow_accounting.csh__menu_cash_forecast_item': 'account.menu_finance_entries',
    'flousflow_accounting.fyi__menu_action_change_lock_date': 'account.account_closing_menu',
    'flousflow_accounting.apr__menu_account_report_bs': 'account.account_reports_legal_statements_menu',
    'flousflow_accounting.apr__menu_account_report_pl': 'account.account_reports_legal_statements_menu',
    'flousflow_accounting.apr__menu_account_report_cash_flow': 'account.account_reports_legal_statements_menu',
    'flousflow_accounting.apr__menu_general_ledger': 'flousflow_accounting.apr__menu_finance_reporting_ledgers',
    'flousflow_accounting.apr__menu_general_balance_report': 'flousflow_accounting.apr__menu_finance_reporting_ledgers',
    'flousflow_accounting.apr__menu_finance_reporting_ledgers': 'account.menu_finance_reports',
    'flousflow_accounting.apr__menu_finance_entries_accounting_ledgers': 'account.menu_finance_entries',
    'flousflow_accounting.apr__menu_partner_ledger': 'account.account_reports_partners_reports_menu',
    'flousflow_accounting.apr__menu_aged_trial_balance': 'account.account_reports_partners_reports_menu',
    'flousflow_accounting.apr__menu_account_report': 'account.account_reports_taxes_and_fiscal_menu',
    'flousflow_accounting.apr__menu_account_reports': 'account.account_account_menu',
    'flousflow_accounting.ast__menu_asset_depreciation_schedule': 'account.account_reports_legal_statements_menu',
    'flousflow_accounting.chk__menu_check_format': 'account.account_invoicing_menu',
    'flousflow_accounting.fol__om_account_followup_menu': 'account.account_invoicing_menu',
    'flousflow_accounting.ast__menu_action_account_asset_asset_list_normal_purchase':
        'flousflow_accounting.acc__menu_account_management_config',
    'flousflow_accounting.bgt__menu_account_budget_position': 'flousflow_accounting.acc__menu_account_management_config',
    'flousflow_accounting.rcp__menu_recurring_template': 'flousflow_accounting.acc__menu_account_management_config',
    'flousflow_accounting.fyi__menu_account_period_closing_task': 'flousflow_accounting.acc__menu_account_management_config',
}
# the folders replaced by the ones of the account module, or holding a single menu
REMOVED = (
    'flousflow_accounting.apr__menu_finance_legal_statement',
    'flousflow_accounting.apr__menu_finance_partner_reports',
    'flousflow_accounting.apr__menu_finance_reports_settings',
    'flousflow_accounting.ast__menu_finance_entries_assets',
    'flousflow_accounting.fol__om_account_followup_main_menu',
    'flousflow_accounting.rcp__menu_recurring_payments',
    'flousflow_accounting.acc__menu_account_templates',
)


@tagged('post_install', '-at_install')
class TestMenus(TransactionCase):

    def test_menus_are_arranged(self):
        for xmlid, parent in PARENTS.items():
            with self.subTest(menu=xmlid):
                self.assertEqual(self.env.ref(xmlid).parent_id, self.env.ref(parent))
        for xmlid in REMOVED:
            self.assertFalse(self.env.ref(xmlid, raise_if_not_found=False), xmlid)

    def test_account_settings_tab_uses_accounting_suite_icon(self):
        settings_view = self.env['res.config.settings'].get_view(
            view_id=self.env.ref('account.res_config_settings_view_form').id,
        )
        self.assertIn(
            'logo="/flousflow_accounting/static/legacy/om_account_accountant/description/icon.png"',
            settings_view['arch'],
        )
        self.assertEqual(
            self.env.ref('account.menu_finance').web_icon,
            'flousflow_accounting,static/legacy/om_account_accountant/description/icon.png',
        )

    def test_reconciliation_menu_has_no_duplicate_actions(self):
        reconciliation = self.env.ref('flousflow_accounting.rec__menu_reconciliation')
        duplicate_menu_xmlids = (
            'flousflow_accounting.acc__menu_review_reconciliation',
            'flousflow_accounting.acc__menu_review_bank_reconciliation',
            'flousflow_accounting.acc__menu_review_open_items',
            'flousflow_accounting.acc__menu_review_match_journal_items',
        )
        for xmlid in duplicate_menu_xmlids:
            with self.subTest(menu=xmlid):
                self.assertFalse(self.env.ref(xmlid).active)

        transaction_queue = self.env.ref('flousflow_accounting.acc__menu_review_bank_rec_to_review')
        self.assertEqual(transaction_queue.parent_id, reconciliation)
        visible_children = reconciliation.child_id.filtered('active')
        expected_children = {
            self.env.ref('flousflow_accounting.rec__menu_bank_reconciliation').id,
            self.env.ref('flousflow_accounting.rec__menu_open_items_reconciliation').id,
            self.env.ref('flousflow_accounting.rec__menu_move_line_match').id,
            transaction_queue.id,
        }
        self.assertTrue(expected_children.issubset(set(visible_children.ids)))

    def test_review_control_matches_enterprise_menu(self):
        control_menu = self.env.ref('account.account_audit_control_menu')
        actual = control_menu.child_id.filtered('active').sorted(
            key=lambda menu: (menu.sequence, menu.id)
        )
        expected = [
            self.env.ref('flousflow_accounting.acc__menu_review_journal_items'),
            self.env.ref('account.account_audit_trail_menu'),
            self.env.ref('flousflow_accounting.acc__menu_review_journal_audit'),
        ]
        self.assertEqual(actual.ids, [menu.id for menu in expected])
        self.assertEqual(
            self.env.ref('flousflow_accounting.acc__menu_review_moves_to_review').parent_id,
            self.env.ref('flousflow_accounting.acc__menu_review_work_queues'),
        )
        work_queues = self.env.ref('flousflow_accounting.acc__menu_review_work_queues')
        self.assertEqual(
            work_queues.child_id.filtered('active').sorted(key=lambda menu: (menu.sequence, menu.id)),
            self.env['ir.ui.menu'].browse([
                self.env.ref('flousflow_accounting.acc__menu_review_moves_to_review').id,
                self.env.ref('flousflow_accounting.acc__menu_review_moves_unposted').id,
            ]),
        )
        journal_items_action = self.env.ref('flousflow_accounting.acc__menu_review_journal_items').action
        self.assertEqual(journal_items_action, self.env.ref('account.action_account_moves_all'))
        self.assertEqual(journal_items_action.res_model, 'account.move.line')

    def test_review_menu_tree_matches_enterprise_destinations(self):
        expected_tree = {
            'account.account_audit_menu': [
                'account.account_audit_control_menu',
                'flousflow_accounting.acc__menu_review_audit',
                'flousflow_accounting.acc__menu_review_inventory',
                'flousflow_accounting.acc__menu_review_regularization',
                'flousflow_accounting.acc__menu_review_purchases',
                'flousflow_accounting.acc__menu_review_sales',
            ],
            'flousflow_accounting.acc__menu_review_audit': [
                'flousflow_accounting.acc__menu_review_working_files',
                'flousflow_accounting.apr__menu_account_report_annual',
            ],
            'flousflow_accounting.acc__menu_review_inventory': [
                'flousflow_accounting.acc__menu_review_inventory_valuation',
            ],
            'flousflow_accounting.acc__menu_review_regularization': [
                'flousflow_accounting.acc__menu_review_unrealized_currencies',
                'flousflow_accounting.acc__menu_review_deferred_revenues',
                'flousflow_accounting.acc__menu_review_deferred_expenses',
            ],
            'flousflow_accounting.acc__menu_review_purchases': [
                'flousflow_accounting.acc__menu_review_bill_to_receive',
                'flousflow_accounting.acc__menu_review_billed_not_received',
            ],
            'flousflow_accounting.acc__menu_review_sales': [
                'flousflow_accounting.acc__menu_review_invoice_to_be_issued',
                'flousflow_accounting.acc__menu_review_invoiced_not_delivered',
            ],
        }
        for parent_xmlid, child_xmlids in expected_tree.items():
            with self.subTest(menu=parent_xmlid):
                actual = self.env.ref(parent_xmlid).child_id.filtered('active').sorted(
                    key=lambda menu: (menu.sequence, menu.id)
                )
                expected_ids = [self.env.ref(xmlid).id for xmlid in child_xmlids]
                self.assertEqual(actual.ids, expected_ids)
        self.assertTrue(self.env.ref('flousflow_accounting.acc__menu_review_inventory').active)

    def test_no_two_menus_share_a_place(self):
        """ Menus with the same sequence under the same parent come in no given order. """
        roots = self.env.ref('account.menu_finance')
        menus = self.env['ir.ui.menu'].search([('id', 'child_of', roots.ids)])
        ours = self.env['ir.model.data'].search([
            ('model', '=', 'ir.ui.menu'), ('res_id', 'in', menus.ids), ('module', '!=', 'account'),
        ])
        for menu in self.env['ir.ui.menu'].browse(ours.mapped('res_id')):
            clashes = menu.parent_id.child_id.filtered(lambda other: other != menu and other.sequence == menu.sequence)
            self.assertFalse(clashes, '%s shares its place with %s' % (menu.complete_name, clashes.mapped('name')))

    def test_accountant_sees_the_daily_work(self):
        accountant = new_test_user(
            self.env, login='menu_accountant', groups='account.group_account_user',
            company_id=self.env.company.id, company_ids=[Command.set(self.env.company.ids)])
        visible = self.env['ir.ui.menu'].with_user(accountant)._visible_menu_ids()
        for xmlid in ('flousflow_accounting.rec__menu_bank_reconciliation',
                      'flousflow_accounting.rec__menu_open_items_reconciliation',
                      'flousflow_accounting.rec__menu_move_line_match',
                      'flousflow_accounting.bgt__menu_account_budget',
                      'flousflow_accounting.rcp__menu_recurring_payment',
                      'flousflow_accounting.csh__menu_cash_forecast_item',
                      'flousflow_accounting.apr__menu_action_account_moves_ledger_general',
                      'flousflow_accounting.apr__menu_account_report_bs',
                      'flousflow_accounting.apr__menu_account_report'):
            self.assertIn(self.env.ref(xmlid).id, visible, xmlid)
        self.assertIn(self.env.ref('flousflow_accounting.acc__menu_review_journal_items').id, visible)
