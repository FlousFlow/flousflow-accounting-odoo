from io import BytesIO
from zipfile import ZipFile

from odoo.tests import tagged
from odoo.exceptions import ValidationError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBalanceSheet(AccountTestInvoicingCommon):

    def _balance_sheet(self, date_to):
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0')
        balances = self.env['report.flousflow_accounting.apr__report_financial'].with_context(
            date_from=False, date_to=date_to, state='posted', strict_range=False,
            company_id=self.env.company.id,
        )._compute_report_balance(report.children_ids)
        return {line.name: balances[line.id]['balance'] for line in report.children_ids}

    def _printed(self, date_to):
        """ :return: {name: amount} as the report prints them, the sign of each line applied """
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0')
        lines = self.env['report.flousflow_accounting.apr__report_financial'].with_context(
            date_from=False, date_to=date_to, state='posted', strict_range=False,
            company_id=self.env.company.id,
        ).get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'date_from': False, 'date_to': date_to, 'state': 'posted',
                             'strict_range': False, 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })
        return {line['name']: line['balance'] for line in lines if line.get('type') == 'report'}

    def test_balance_sheet_balances_with_current_year_earnings_postings(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)
        retained_earnings = self.env['account.account'].create({
            'code': 'RETEARN', 'name': 'Retained Earnings', 'account_type': 'equity',
        })
        # e.g. the transfer of the earnings of 2025, or an opening balance difference
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2026-01-01',
            'line_ids': [
                (0, 0, {'name': 'transfer', 'balance': 1000.0,
                        'account_id': self.env.company.get_unaffected_earnings_account().id}),
                (0, 0, {'name': 'transfer', 'balance': -1000.0, 'account_id': retained_earnings.id}),
            ],
        }).action_post()

        for date_to in ('2025-12-31', '2026-12-31'):
            with self.subTest(date_to=date_to):
                lines = self._balance_sheet(date_to)
                self.assertAlmostEqual(sum(lines.values()), 0.0)
                self.assertAlmostEqual(lines['Assets'], 1000.0)

    def test_prepayments_are_assets(self):
        prepayments = self.env['account.account'].create({
            'code': 'PREPAID', 'name': 'Prepaid Rent', 'account_type': 'asset_prepayments',
        })
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-06-01',
            'line_ids': [
                (0, 0, {'name': 'rent', 'balance': 600.0, 'account_id': prepayments.id}),
                (0, 0, {'name': 'rent', 'balance': -600.0,
                        'account_id': self.company_data['default_account_payable'].id}),
            ],
        }).action_post()
        lines = self._balance_sheet('2025-12-31')
        self.assertAlmostEqual(lines['Assets'], 600.0)
        self.assertAlmostEqual(sum(lines.values()), 0.0)

    def test_the_sections_are_named_apart(self):
        """ Up to 1.x a Liability sat inside a Liability, and the equity was counted among the liabilities. """
        names = [line.name for line in self.env.ref(
            'flousflow_accounting.apr__account_financial_report_balancesheet0').children_ids]
        self.assertEqual(names, ['Assets', 'Liabilities and Equity'])
        sections = [line.name for line in self.env.ref(
            'flousflow_accounting.apr__account_financial_report_liabilitysum0').children_ids]
        self.assertEqual(sections, ['Liabilities', 'Equity'])
        equity = [line.name for line in self.env.ref(
            'flousflow_accounting.apr__account_financial_report_equity0').children_ids]
        self.assertEqual(equity, ['Capital and Reserves', 'Profit (Loss) to report'],
                         'the profit of the period belongs to the owners')

    def test_interactive_xlsx_export_preserves_comparison_period(self):
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0')
        interactive_data = self.env['report.flousflow_accounting.apr__report_financial'].get_interactive_data(
            report.id, '2026-01-01', '2026-06-30', 'posted', [], True, False,
            comparison_mode='same_period_last_year',
        )
        comparison_context = interactive_data['comparison_context']
        self.assertEqual(comparison_context['date_from'], '2025-01-01')
        self.assertEqual(comparison_context['date_to'], '2025-06-30')

        wizard = self.env['accounting.report'].create({
            'account_report_id': report.id,
            'date_from': '2026-01-01',
            'date_to': '2026-06-30',
            'journal_ids': [(6, 0, self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
            'enable_filter': True,
            'filter_cmp': 'filter_date',
            'date_from_cmp': comparison_context['date_from'],
            'date_to_cmp': comparison_context['date_to'],
            'target_move': 'posted',
        })
        action = wizard.action_export_xlsx()

        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertEqual(wizard.xlsx_filename, 'Balance Sheet.xlsx')
        self.assertTrue(wizard.xlsx_file)

    def test_interactive_xlsx_export_preserves_all_comparison_periods_and_order(self):
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0')
        wizard = self.env['accounting.report'].create({
            'account_report_id': report.id,
            'date_to': '2026-06-30',
            'journal_ids': [(6, 0, self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
            'target_move': 'posted',
            'enable_filter': True,
            'filter_cmp': 'filter_date',
            'comparison_period_ranges': [
                {'date_from': '2025-01-01', 'date_to': '2025-06-30'},
                {'date_from': '2024-01-01', 'date_to': '2024-06-30'},
            ],
            'comparison_sort': 'ascending',
        })
        form = wizard.read([
            'date_from', 'date_to', 'journal_ids', 'target_move', 'company_id',
            'account_report_id', 'date_from_cmp', 'date_to_cmp', 'filter_cmp',
            'enable_filter', 'label_filter', 'debit_credit',
            'comparison_period_ranges', 'comparison_sort', 'comparison_display',
        ])[0]
        form['used_context'] = {'lang': self.env.lang}
        export_data = wizard._prepare_export_data(
            form, wizard._get_interactive_report_data(form),
        )

        self.assertEqual([column['index'] for column in export_data['period_columns']], [1, 0, -1])
        self.assertFalse(export_data['show_comparison_change'])
        report_action = self.env.ref('flousflow_accounting.apr__action_report_financial')
        rendered_html, report_type = report_action.with_context(
            active_model='accounting.report', active_id=wizard.id,
        )._render_qweb_html(
            report_action.report_name, [wizard.id], {'form': form},
        )
        self.assertEqual(report_type, 'html')
        rendered_html = rendered_html.decode()
        for column in export_data['period_columns']:
            self.assertIn(column['label'], rendered_html)

        action = wizard.action_export_xlsx()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        with ZipFile(BytesIO(bytes(wizard.xlsx_file))) as workbook:
            shared_strings = workbook.read('xl/sharedStrings.xml').decode()
        for column in export_data['period_columns']:
            self.assertIn(column['label'], shared_strings)

    def test_percentage_of_selection_is_preserved_in_pdf_and_xlsx(self):
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')
        wizard = self.env['accounting.report'].create({
            'account_report_id': report.id,
            'company_id': self.env.company.id,
            'date_from': '2025-01-01',
            'date_to': '2025-12-31',
            'journal_ids': [(6, 0, self.env['account.journal'].search([
                ('company_id', 'child_of', self.env.company.id),
            ]).ids)],
            'target_move': 'posted',
        })
        form = wizard.read([
            'date_from', 'date_to', 'journal_ids', 'target_move', 'company_id',
            'account_report_id', 'enable_filter', 'debit_credit', 'comparison_mode',
            'percentage_of_row_key', 'comparison_display', 'comparison_sort',
        ])[0]
        form['used_context'] = {'lang': self.env.lang}
        interactive_data = wizard._get_interactive_report_data(form)
        base_line = next(line for line in interactive_data['lines']
                         if line.get('type') in {'report', 'group', 'category', 'total'}
                         and line.get('show_amount', True))
        form['comparison_mode'] = 'percentage_of'
        form['percentage_of_row_key'] = base_line.get('row_key') or (
            f"report-{base_line.get('report_id') or base_line.get('name')}"
        )
        wizard.write({
            'comparison_mode': form['comparison_mode'],
            'percentage_of_row_key': form['percentage_of_row_key'],
        })
        export_data = wizard._prepare_export_data(
            form, interactive_data,
        )
        base_line = next(line for line in export_data['lines']
                         if (line.get('row_key') or f"report-{line.get('report_id') or line.get('name')}")
                         == form['percentage_of_row_key'])
        expected_header = f"Percentage of {base_line['name']}"
        self.assertEqual(export_data['comparison_change_label'], expected_header)
        self.assertEqual(base_line['comparison_change'], '100.00%')

        report_action = self.env.ref('flousflow_accounting.apr__action_report_financial')
        rendered_html, report_type = report_action.with_context(
            active_model='accounting.report', active_id=wizard.id,
        )._render_qweb_html(report_action.report_name, [wizard.id], {'form': form})
        self.assertEqual(report_type, 'html')
        self.assertIn(expected_header, rendered_html.decode())
        self.assertIn('100.00%', rendered_html.decode())

        action = wizard.action_export_xlsx()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        with ZipFile(BytesIO(bytes(wizard.xlsx_file))) as workbook:
            shared_strings = workbook.read('xl/sharedStrings.xml').decode()
        self.assertIn(expected_header, shared_strings)
        self.assertIn('100.00%', shared_strings)

    def test_percentage_of_zero_base_matches_interactive_n_a_behavior(self):
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')
        wizard = self.env['accounting.report'].create({'account_report_id': report.id})
        export_data = wizard._prepare_export_data({
            'account_report_id': (report.id, report.display_name),
            'comparison_mode': 'percentage_of',
            'percentage_of_row_key': 'base-line',
            'enable_filter': False,
        }, {
            'lines': [
                {'name': 'Base', 'type': 'report', 'row_key': 'base-line', 'balance': 0.0},
                {'name': 'Nonzero', 'type': 'category', 'row_key': 'nonzero-line', 'balance': 25.0},
                {'name': 'Zero', 'type': 'category', 'row_key': 'zero-line', 'balance': 0.0},
            ],
        })
        self.assertEqual(export_data['lines'][1]['comparison_change'], 'N/A')
        self.assertEqual(export_data['lines'][2]['comparison_change'], '0.00%')

    def test_the_equity_is_not_among_the_liabilities(self):
        equity_types = self.env.ref('flousflow_accounting.apr__account_financial_report_equity_accounts0')\
            .account_type_ids.mapped('type')
        liability_types = self.env.ref('flousflow_accounting.apr__account_financial_report_liability0')\
            .account_type_ids.mapped('type')
        self.assertEqual(set(equity_types), {'equity', 'equity_unaffected'})
        self.assertFalse(set(equity_types) & set(liability_types), 'nothing is counted on both sides')
        self.assertIn('liability_credit_card', liability_types,
                      'a credit card is money owed: without it the balance sheet does not balance')

    def test_what_is_owed_prints_positive(self):
        """ A balance sheet is read with the liabilities and the equity positive, facing the assets. """
        self.init_invoice('out_invoice', amounts=[1000.0], invoice_date='2025-06-01', taxes=[], post=True)
        printed = self._printed('2025-12-31')
        self.assertGreater(printed['Assets'], 0.0)
        self.assertGreater(printed['Liabilities and Equity'], 0.0,
                           'what the company owes and what belongs to its owners, printed positive')
        self.assertAlmostEqual(printed['Assets'], printed['Liabilities and Equity'],
                               msg='the two sides of the balance sheet face each other')
        self.assertAlmostEqual(printed['Equity'], 1000.0, msg='the profit of the period is in the equity')
        self.assertAlmostEqual(printed['Profit (Loss) to report'], 1000.0)
        self.assertAlmostEqual(printed['Capital and Reserves'], 0.0)

    def test_a_credit_card_balances(self):
        """ The credit card accounts belong to the liabilities: the report balances with one in use. """
        credit_card = self.env['account.account'].create({
            'code': 'CCARD', 'name': 'Company Card', 'account_type': 'liability_credit_card',
        })
        expense = self.env['account.account'].create({
            'code': 'CCEXP', 'name': 'Card Expense', 'account_type': 'expense',
        })
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-06-01',
            'line_ids': [
                (0, 0, {'name': 'card', 'balance': 250.0, 'account_id': expense.id}),
                (0, 0, {'name': 'card', 'balance': -250.0, 'account_id': credit_card.id}),
            ],
        }).action_post()
        lines = self._balance_sheet('2025-12-31')
        self.assertAlmostEqual(sum(lines.values()), 0.0)

    def test_the_lines_carry_their_level(self):
        """ The sections are indented by their depth in the report, the title of the report is not printed. """
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0')
        lines = self.env['report.flousflow_accounting.apr__report_financial'].get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'state': 'posted', 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })
        levels = {line['name']: line['level'] for line in lines if line['type'] == 'report'}
        self.assertEqual(levels, {
            'Balance Sheet': 0,
            'Assets': 1,
            'Liabilities and Equity': 1,
            'Liabilities': 2,
            'Equity': 2,
            'Capital and Reserves': 3,
            'Profit (Loss) to report': 3,
        })
        self.env.ref('flousflow_accounting.apr__account_financial_report_equity0').style_overwrite = '1'
        lines = self.env['report.flousflow_accounting.apr__report_financial'].get_account_lines({
            'account_report_id': (report.id, report.name),
            'used_context': {'state': 'posted', 'company_id': self.env.company.id},
            'enable_filter': False,
            'debit_credit': False,
        })
        self.assertEqual(next(line['level'] for line in lines if line['name'] == 'Equity'), 1,
                         'a style chosen on the line wins over its depth')

    def test_interactive_report_returns_the_same_financial_report_lines(self):
        self.init_invoice('out_invoice', amounts=[420.0], invoice_date='2025-06-01', taxes=[], post=True)
        report = self.env['report.flousflow_accounting.apr__report_financial']
        result = report.get_interactive_data(
            self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0').id,
            False, '2025-12-31', 'posted', self.env['account.journal'].search([
                ('company_id', '=', self.env.company.id),
            ]).ids, False, True,
        )
        self.assertEqual(result['name'], 'Balance Sheet')
        self.assertEqual(result['date_to'], '2025-12-31')
        self.assertTrue(result['lines'])
        self.assertTrue(all('formula_info' in item for item in result['lines']))
        total_assets = next(item for item in result['lines'] if item['name'] == 'Total ASSETS')
        self.assertEqual(total_assets['formula_info']['engine'], 'Aggregate Other Formulas')
        self.assertEqual(total_assets['formula_info']['formula'], 'CA.balance + FA.balance + PNCA.balance')
        self.assertNotIn('Balance Sheet', [item['name'] for item in result['lines']])
        self.assertNotIn('Liabilities and Equity', [item['name'] for item in result['lines']])
        self.assertIn('LIABILITIES', [item['name'] for item in result['lines']])
        self.assertIn('Current Assets', [item['name'] for item in result['lines']])
        self.assertIn('Current Liabilities', [item['name'] for item in result['lines']])
        self.assertNotIn('Other Current Assets', [item['name'] for item in result['lines']])
        self.assertNotIn('Other Current Liabilities', [item['name'] for item in result['lines']])
        self.assertEqual(
            [item['name'] for item in result['lines'] if item.get('account_type') == 'asset_current'],
            ['Current Assets'],
        )
        self.assertEqual(
            [item['name'] for item in result['lines'] if item.get('account_type') == 'liability_current'],
            ['Current Liabilities'],
        )
        self.assertIn('Bank and Cash Accounts', [item['name'] for item in result['lines']])
        self.assertIn('Receivables', [item['name'] for item in result['lines']])
        line_names = [item['name'] for item in result['lines']]
        self.assertLess(line_names.index('Bank and Cash Accounts'), line_names.index('Receivables'))
        self.assertIn('EQUITY (& EARNINGS)', line_names)
        self.assertIn('Capital', line_names)
        self.assertNotIn('Equity', [item['name'] for item in result['lines']
                                    if item.get('row_key', '').startswith('equity-accounts-')])
        self.assertIn('Current Year Unallocated Earnings', line_names)
        self.assertIn('Previous Years Earnings', line_names)
        self.assertIn('LIABILITIES + EQUITY', line_names)
        self.assertAlmostEqual(next(item for item in result['lines']
                                    if item['name'] == 'Total Current Assets')['balance'], 420.0)
        self.assertAlmostEqual(next(item for item in result['lines']
                                    if item['name'] == 'Total ASSETS')['balance'], 420.0)
        self.assertAlmostEqual(next(item for item in result['lines']
                                    if item['name'] == 'Current Year Unallocated Earnings')['balance'], 420.0)
        self.assertAlmostEqual(next(item for item in result['lines']
                                    if item['name'] == 'LIABILITIES + EQUITY')['balance'], 420.0)
        receivable = self.partner_a.property_account_receivable_id
        line = next(item for item in result['lines'] if item.get('account_id') == receivable.id)
        self.assertAlmostEqual(line['balance'], 420.0)
        self.assertIn('debit', line)
        self.assertIn('credit', line)

    def test_profit_and_loss_revenue_formula_metadata_uses_negative_sum(self):
        invoice = self.init_invoice('out_invoice', amounts=[420.0], invoice_date='2025-06-10',
                                    taxes=[], post=True)
        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')
        result = self.env['report.flousflow_accounting.apr__report_financial'].get_interactive_data(
            report.id, '2025-06-01', '2025-06-30', 'posted',
            self.env['account.journal'].search([('company_id', '=', self.env.company.id)]).ids,
            False, False,
        )
        lines = result['lines']
        by_name = {line['name']: line for line in lines}
        self.assertEqual(
            [line['name'] for line in lines],
            [
                'Revenue', 'Cost of Revenue', 'Gross Profit', 'Operating Expenses',
                'Operating Income (or Loss)', 'Other Income', 'Other Expenses',
                'Net Income', 'Distributions and Withdrawals',
            ],
        )
        self.assertFalse(any(line.get('type') == 'report' for line in lines))
        revenue = by_name['Revenue']
        self.assertEqual(revenue['type'], 'category')
        self.assertIn(invoice.invoice_line_ids.account_id.id, revenue['account_ids'])
        self.assertAlmostEqual(revenue['balance'], 420.0)
        self.assertAlmostEqual(by_name['Gross Profit']['balance'], 420.0)
        self.assertAlmostEqual(by_name['Operating Income (or Loss)']['balance'], 420.0)
        self.assertAlmostEqual(by_name['Net Income']['balance'], 420.0)
        self.assertEqual(revenue['formula_info']['engine'], 'Odoo Domain')
        self.assertEqual(revenue['formula_info']['label'], 'balance')
        self.assertEqual(revenue['formula_info']['formula'], "[('account_id.account_type', '=', 'income')]")
        self.assertEqual(revenue['formula_info']['subformula'], '-sum')
        self.assertEqual(by_name['Gross Profit']['formula_info']['engine'], 'Aggregate Other Formulas')
        self.assertEqual(by_name['Gross Profit']['formula_info']['formula'], 'REV.balance - COS.balance')
        self.assertEqual(
            by_name['Operating Income (or Loss)']['formula_info']['formula'],
            'REV.balance - COS.balance - EXP.balance',
        )
        self.assertEqual(
            by_name['Other Expenses']['formula_info']['formula'],
            "[('account_id.account_type', 'in', ('expense_depreciation', 'expense_other'))]",
        )
        self.assertEqual(by_name['Other Expenses']['formula_info']['subformula'], 'sum')
        self.assertEqual(
            by_name['Net Income']['formula_info']['formula'],
            'REV.balance + OIN.balance - COS.balance - EXP.balance - OEXP.balance',
        )

    def test_profit_and_loss_summary_uses_enterprise_category_formulas(self):
        direct_cost = self.env['account.account'].create({
            'code': '992001', 'name': 'P&L Direct Cost', 'account_type': 'expense_direct_cost',
        })
        operating_expense = self.env['account.account'].create({
            'code': '992002', 'name': 'P&L Operating Expense', 'account_type': 'expense',
        })
        other_income = self.env['account.account'].create({
            'code': '992003', 'name': 'P&L Other Income', 'account_type': 'income_other',
        })
        depreciation = self.env['account.account'].create({
            'code': '992004', 'name': 'P&L Depreciation', 'account_type': 'expense_depreciation',
        })
        other_expense = self.env['account.account'].create({
            'code': '992005', 'name': 'P&L Other Expense', 'account_type': 'expense_other',
        })
        self.env['account.move'].create({
            'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2025-06-15',
            'line_ids': [
                (0, 0, {'name': 'Direct cost', 'account_id': direct_cost.id, 'balance': 100.0}),
                (0, 0, {'name': 'Operating expense', 'account_id': operating_expense.id,
                        'balance': 50.0}),
                (0, 0, {'name': 'Other income', 'account_id': other_income.id, 'balance': -25.0}),
                (0, 0, {'name': 'Depreciation', 'account_id': depreciation.id, 'balance': 10.0}),
                (0, 0, {'name': 'Other expense', 'account_id': other_expense.id, 'balance': 5.0}),
                (0, 0, {'name': 'Balancing payable',
                        'account_id': self.company_data['default_account_payable'].id,
                        'balance': -140.0}),
            ],
        }).action_post()
        self.init_invoice('out_invoice', amounts=[420.0], invoice_date='2025-06-10',
                          taxes=[], post=True)

        report = self.env.ref('flousflow_accounting.apr__account_financial_report_profitandloss0')
        result = self.env['report.flousflow_accounting.apr__report_financial'].get_interactive_data(
            report.id, '2025-06-01', '2025-06-30', 'posted',
            self.env['account.journal'].search([('company_id', '=', self.env.company.id)]).ids,
            False, False,
        )
        lines = {line['name']: line for line in result['lines']}
        expected = {
            'Revenue': 420.0,
            'Cost of Revenue': 100.0,
            'Gross Profit': 320.0,
            'Operating Expenses': 50.0,
            'Operating Income (or Loss)': 270.0,
            'Other Income': 25.0,
            'Other Expenses': 15.0,
            'Net Income': 280.0,
        }
        for name, amount in expected.items():
            with self.subTest(name=name):
                self.assertAlmostEqual(lines[name]['balance'], amount)

    def test_the_sections_keep_their_order(self):
        """ The sections without a sequence print in the order they were created (Assets before the
        liabilities, Income before Expense), not in the order the database happens to return them. """
        for xmlid in ('flousflow_accounting.apr__account_financial_report_balancesheet0',
                      'flousflow_accounting.apr__account_financial_report_profitandloss0'):
            report = self.env.ref(xmlid)
            sections = report.children_ids.sorted(lambda section: (section.sequence, section.id))
            # an update writes the row anew at the end of the table, where a scan finds it last
            # (the ORM skips a write of the same value: the update is made in SQL)
            self.env.cr.execute("UPDATE account_financial_report SET name = name WHERE id = %s", [sections[0].id])
            printed = report._get_children_by_order().filtered(lambda line: line.parent_id == report)
            # the ids, in order: two recordsets compare equal whatever their order
            self.assertEqual(printed.ids, sections.ids, xmlid)

    def test_a_section_cannot_depend_on_itself(self):
        """ A loop in the sections would make the report recurse forever """
        balance_sheet = self.env.ref('flousflow_accounting.apr__account_financial_report_balancesheet0')
        assets = self.env.ref('flousflow_accounting.apr__account_financial_report_assets0')
        with self.assertRaises(ValidationError):
            balance_sheet.parent_id = assets
        with self.assertRaises(ValidationError):
            assets.write({'type': 'account_report', 'account_report_id': balance_sheet.id})
        value = self.env['account.financial.report'].create({
            'name': 'Value', 'type': 'account_report', 'account_report_id': assets.id})
        with self.assertRaises(ValidationError):
            value.account_report_id = value
        # a View that sums a Report Value of itself
        view = self.env['account.financial.report'].create({'name': 'View', 'type': 'sum'})
        with self.assertRaises(ValidationError):
            value.write({'parent_id': view.id, 'account_report_id': view.id})
        # what the standard reports do stays allowed
        value.write({'parent_id': view.id, 'account_report_id': balance_sheet.id})
