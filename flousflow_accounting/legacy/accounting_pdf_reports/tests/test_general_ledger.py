from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestGeneralLedger(AccountTestInvoicingCommon):

    def _ledger(self, **vals):
        wizard = self.env['account.report.general.ledger'].create(vals)
        wizard_context = dict(active_model=wizard._name, active_id=wizard.id, active_ids=wizard.ids)
        action = wizard.with_context(**wizard_context).check_report()
        context = dict(wizard_context, **(action.get('context') or {}))
        values = self.env['report.' + action['report_name']].with_context(**context)._get_report_values(
            context.get('active_ids'), action['data'])
        return {account['code']: account for account in values['Accounts']}

    def test_running_balance(self):
        for date, amount in (('2025-01-10', 100.0), ('2025-02-05', 200.0), ('2025-02-20', 50.0)):
            self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount], taxes=[],
                              invoice_date=date, post=True)
        receivable = self.partner_a.property_account_receivable_id

        ledger = self._ledger(date_from='2025-02-01', date_to='2025-02-28', initial_balance=True)
        account = ledger[receivable.code]
        self.assertEqual([line['lname'] for line in account['move_lines']][0], 'Initial Balance')
        # each line carries the balance of the account after it, from the initial balance on
        self.assertEqual([line['balance'] for line in account['move_lines']], [100.0, 300.0, 350.0])
        self.assertEqual((account['debit'], account['credit'], account['balance']), (350.0, 0.0, 350.0))

        ledger = self._ledger(date_from='2025-02-01', date_to='2025-02-28', initial_balance=False)
        self.assertEqual([line['balance'] for line in ledger[receivable.code]['move_lines']], [200.0, 250.0])

    def test_interactive_data_matches_report_engine_and_loads_details_on_demand(self):
        for date, amount in (('2025-01-10', 100.0), ('2025-02-05', 200.0), ('2025-02-20', 50.0)):
            self.init_invoice('out_invoice', partner=self.partner_a, amounts=[amount], taxes=[],
                              invoice_date=date, post=True)
        receivable = self.partner_a.property_account_receivable_id
        report = self.env['report.flousflow_accounting.apr__report_general_ledger']

        summary = report.get_interactive_data('2025-02-01', '2025-02-28')
        account = next(line for line in summary['lines'] if line['account_id'] == receivable.id)
        pdf_engine = self._ledger(date_from='2025-02-01', date_to='2025-02-28',
                                  initial_balance=True)[receivable.code]
        details = report.get_interactive_data(
            '2025-02-01', '2025-02-28', account_ids=[receivable.id]
        )
        detailed_account = next(line for line in details['lines'] if line['account_id'] == receivable.id)
        self.assertEqual((account['debit'], account['credit'], account['balance']),
                         (pdf_engine['debit'], pdf_engine['credit'], pdf_engine['balance']),
                         msg=f"summary={account}; details={detailed_account['move_lines']}")
        self.assertNotIn('move_lines', account)

        self.assertEqual([line['balance'] for line in detailed_account['move_lines']], [100.0, 300.0, 350.0])

    def test_interactive_period_presets(self):
        report = self.env['report.flousflow_accounting.apr__report_general_ledger']
        self.assertEqual(report._get_interactive_period_dates('month', '2025-02-18'),
                         ('2025-02-01', '2025-02-28'))
        self.assertEqual(report._get_interactive_period_dates('quarter', '2025-11-18'),
                         ('2025-10-01', '2025-12-31'))
        fiscal = self.env.company.compute_fiscalyear_dates(fields.Date.from_string('2025-05-15'))
        self.assertEqual(report._get_interactive_period_dates('fiscal_year', '2025-05-15'),
                         (fields.Date.to_string(fiscal['date_from']),
                          fields.Date.to_string(fiscal['date_to'])))
        self.assertEqual(report._get_interactive_period_dates(
            'custom', custom_date_from='2025-02-03', custom_date_to='2025-02-11'
        ), ('2025-02-03', '2025-02-11'))
        with self.assertRaises(ValidationError):
            report._get_interactive_period_dates(
                'custom', custom_date_from='2025-02-12', custom_date_to='2025-02-11'
            )
