from odoo.tests import HttpCase, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestInteractiveTrialBalance(AccountTestInvoicingCommon):

    def test_interactive_trial_balance_reconciles_period_and_opening(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-01-10', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[200.0], taxes=[],
                          invoice_date='2025-02-05', post=True)
        report = self.env['report.flousflow_accounting.apr__report_trialbalance']
        result = report.get_interactive_data(
            'custom', '2025-02-01', '2025-02-01', '2025-02-28', 'posted', False, 'all', True, False
        )
        receivable = self.partner_a.property_account_receivable_id
        line = next(item for item in result['lines'] if item['account_id'] == receivable.id)
        self.assertEqual(line['opening_balance'], 100.0)
        self.assertEqual(line['debit'], 200.0)
        self.assertEqual(line['credit'], 0.0)
        self.assertEqual(line['balance'], 300.0)
        self.assertEqual(line['debit_cmp'], 100.0)
        self.assertEqual(line['balance_cmp'], 100.0)
        self.assertAlmostEqual(result['totals']['debit'], result['totals']['credit'])
        self.assertAlmostEqual(result['totals']['balance'], 0.0)
        cash_basis_result = report.get_interactive_data(
            'custom', '2025-02-01', '2025-02-01', '2025-02-28', 'posted', False, 'all', False, True
        )
        self.assertTrue(cash_basis_result['cash_basis'])

        wizard = self.env['account.balance.report'].create({'cash_basis': True})
        used_context = wizard._build_contexts({'form': {
            'journal_ids': wizard.journal_ids.ids,
            'target_move': 'posted',
            'date_from': False,
            'date_to': False,
            'company_id': [self.env.company.id],
        }})
        self.assertTrue(used_context['tax_exigible'])


@tagged('post_install', '-at_install')
class TestInteractiveTrialBalanceTour(HttpCase):

    def test_trial_balance_period_comparison_and_filters(self):
        action = self.env.ref('flousflow_accounting.apr__action_interactive_trial_balance')
        self.start_tour(
            f'/odoo/action-{action.id}',
            'ff_trial_balance_controls',
            login='admin',
        )
