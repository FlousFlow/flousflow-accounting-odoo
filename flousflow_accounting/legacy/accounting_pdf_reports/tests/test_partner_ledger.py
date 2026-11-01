from odoo.tests import tagged
from odoo import fields

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPartnerLedger(AccountTestInvoicingCommon):

    def _ledger(self, **vals):
        wizard = self.env['account.report.partner.ledger'].create(vals)
        data = wizard.with_context(active_model=wizard._name, active_id=wizard.id).check_report()['data']
        return self.env['report.flousflow_accounting.apr__report_partnerledger']._get_report_values(None, data)

    def test_partner_ledger(self):
        for partner, amounts in ((self.partner_a, [100.0, 40.0]), (self.partner_b, [250.0])):
            for date, amount in zip(('2025-06-01', '2025-07-01'), amounts):
                self.init_invoice('out_invoice', partner=partner, amounts=[amount], taxes=[],
                                  invoice_date=date, post=True)
        self.init_invoice('out_refund', partner=self.partner_a, amounts=[30.0], taxes=[],
                          invoice_date='2025-08-01', post=True)

        values = self._ledger(result_selection='customer')
        data, docs = values['data'], values['docs']
        self.assertEqual({partner.id for partner in docs}, {self.partner_a.id, self.partner_b.id})

        sum_partner, lines = values['sum_partner'], values['lines']
        self.assertEqual(sum_partner(data, self.partner_a, 'debit'), 140.0)
        self.assertEqual(sum_partner(data, self.partner_a, 'credit'), 30.0)
        self.assertEqual(sum_partner(data, self.partner_a, 'debit - credit'), 110.0)
        self.assertEqual(sum_partner(data, self.partner_b, 'debit - credit'), 250.0)
        self.assertIsNone(sum_partner(data, self.partner_a, 'balance'))

        rows = lines(data, self.partner_a)
        self.assertEqual([row['debit'] - row['credit'] for row in rows], [100.0, 40.0, -30.0])
        self.assertEqual([row['progress'] for row in rows], [100.0, 140.0, 110.0])
        # the payment terms of partner b split its invoice in two installments
        self.assertEqual(sum(row['debit'] - row['credit'] for row in lines(data, self.partner_b)), 250.0)

        # the methods for one partner give the same
        report = self.env['report.flousflow_accounting.apr__report_partnerledger']
        self.assertEqual(report._sum_partner(data, self.partner_a, 'debit - credit'), 110.0)
        self.assertEqual([row['progress'] for row in report._lines(data, self.partner_a)], [100.0, 140.0, 110.0])

    def test_partner_ledger_of_selected_partners(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2025-06-01', post=True)
        partner_c = self.env['res.partner'].create({'name': 'Partner without entries'})

        values = self._ledger(result_selection='customer', partner_ids=[(6, 0, partner_c.ids)])
        self.assertEqual(values['docs'], [partner_c])
        self.assertEqual(values['sum_partner'](values['data'], partner_c, 'debit - credit'), 0.0)
        self.assertEqual(values['lines'](values['data'], partner_c), [])

    def test_balance_confirmation_uses_cumulative_balance_through_end_date(self):
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
                          invoice_date='2024-12-01', post=True)
        self.init_invoice('out_invoice', partner=self.partner_a, amounts=[40.0], taxes=[],
                          invoice_date='2025-07-01', post=True)
        self.init_invoice('out_refund', partner=self.partner_a, amounts=[30.0], taxes=[],
                          invoice_date='2025-08-01', post=True)

        wizard = self.env['account.report.partner.ledger'].create({
            'result_selection': 'customer',
            'partner_ids': [(6, 0, self.partner_a.ids)],
            'date_from': '2025-06-01',
            'date_to': '2025-12-31',
            'target_move': 'posted',
            'document_type': 'balance_confirmation',
        })
        data = wizard.with_context(
            active_model=wizard._name, active_id=wizard.id,
        ).check_report()['data']
        values = self.env['report.flousflow_accounting.apr__report_partnerledger']._get_report_values(
            None, data,
        )

        self.assertEqual(data['form']['document_type'], 'balance_confirmation')
        self.assertEqual(values['confirmation_closing_balance'](self.partner_a), 110.0)

        html, report_type = self.env['ir.actions.report']._render_qweb_html(
            'flousflow_accounting.apr__report_partnerledger',
            wizard.ids,
            data=data,
        )
        self.assertEqual(report_type, 'html')
        for english_text in (
            'Balance Confirmation Request', 'Period:', 'Target Moves:', 'Partners:',
            'Receivable Accounts', 'Dear', 'We request that you review the closing balance',
            'Closing balance as of', 'A positive amount means the partner owes the company',
            'I agree with this balance.', 'I disagree with this balance',
            'This document requests balance confirmation.',
        ):
            self.assertIn(english_text.encode(), html)
        self.assertIn(b'110.00', html)

        arabic_wizard = wizard.with_context(lang='ar_001', active_model=wizard._name, active_id=wizard.id)
        arabic_data = arabic_wizard.check_report()['data']
        arabic_html, _ = self.env['ir.actions.report'].with_context(lang='ar_001')._render_qweb_html(
            'flousflow_accounting.apr__report_partnerledger',
            wizard.ids,
            data=arabic_data,
        )
        for arabic_text in (
            'طلب مصادقة الرصيد', 'الفترة:', 'الحركات المستهدفة:', 'الشركاء:',
            'حسابات القبض', 'السادة', 'نرجو مراجعة الرصيد الختامي أدناه',
            'الرصيد الختامي في', 'الرصيد الموجب يعني أن على الشريك مبلغًا للشركة',
            'أوافق على هذا الرصيد.', 'لا أوافق على هذا الرصيد؛ يرجى التواصل معي.',
            'هذا المستند لطلب مصادقة الرصيد',
        ):
            self.assertIn(arabic_text.encode(), arabic_html)
        for english_text in (
            'Balance Confirmation Request', 'Period:', 'Target Moves:', 'Partners:',
            'Receivable Accounts', 'Dear', 'We request that you review',
            'Closing balance as of', 'A positive amount means', 'I agree with this balance.',
            'I disagree with this balance', 'This document requests balance confirmation.',
        ):
            self.assertNotIn(english_text.encode(), arabic_html)

    def test_balance_confirmation_keeps_customer_and_vendor_balances_separate(self):
        partner = self.partner_a
        partner.write({'customer_rank': 1, 'supplier_rank': 1})
        self.init_invoice(
            'out_invoice', partner=partner, amounts=[100.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        self.init_invoice(
            'in_invoice', partner=partner, amounts=[70.0], taxes=[],
            invoice_date='2025-06-02', post=True,
        )

        LedgerWizard = self.env['account.report.partner.ledger']
        customer_defaults = LedgerWizard.with_context(
            active_model='res.partner', active_ids=partner.ids,
            res_partner_search_mode='customer',
        ).default_get(['result_selection'])
        vendor_defaults = LedgerWizard.with_context(
            active_model='res.partner', active_ids=partner.ids,
            res_partner_search_mode='supplier',
        ).default_get(['result_selection'])
        contact_defaults = LedgerWizard.with_context(
            active_model='res.partner', active_ids=partner.ids,
        ).default_get(['result_selection'])
        confirmation_defaults = LedgerWizard.with_context(
            default_document_type='balance_confirmation',
        ).default_get(['document_type', 'date_to'])
        self.assertEqual(customer_defaults['result_selection'], 'customer')
        self.assertEqual(vendor_defaults['result_selection'], 'supplier')
        self.assertEqual(contact_defaults['result_selection'], 'customer')
        self.assertEqual(confirmation_defaults['date_to'], fields.Date.context_today(LedgerWizard))

        confirmation_wizard = LedgerWizard.new({'document_type': 'balance_confirmation'})
        confirmation_wizard._onchange_document_type()
        self.assertEqual(confirmation_wizard.date_to, fields.Date.context_today(LedgerWizard))

        customer_values = self._ledger(
            result_selection='customer', partner_ids=[(6, 0, partner.ids)],
            date_to='2025-12-31', target_move='posted',
            document_type='balance_confirmation',
        )
        vendor_values = self._ledger(
            result_selection='supplier', partner_ids=[(6, 0, partner.ids)],
            date_to='2025-12-31', target_move='posted',
            document_type='balance_confirmation',
        )

        self.assertEqual(customer_values['confirmation_closing_balance'](partner), 100.0)
        self.assertEqual(vendor_values['confirmation_closing_balance'](partner), -70.0)

    def test_interactive_lines_show_journal_entry_and_account_code(self):
        move = self.init_invoice(
            'out_invoice', partner=self.partner_a, amounts=[100.0], taxes=[],
            invoice_date='2025-06-01', post=True,
        )
        rows = self.env['report.flousflow_accounting.apr__report_partnerledger'].get_interactive_partner_lines(
            self.partner_a.id, '2025-01-01', '2025-12-31', 'posted', 'receivable'
        )
        row = next(row for row in rows if row['move_id'] == move.id)
        receivable_line = move.line_ids.filtered(
            lambda line: line.account_id.account_type == 'asset_receivable'
        )[:1]

        self.assertEqual(row['label'], move.name)
        self.assertEqual(row['journal'], move.journal_id.name)
        self.assertEqual(row['account'], receivable_line.account_id.code)
        self.assertEqual(row['move_id'], move.id)
