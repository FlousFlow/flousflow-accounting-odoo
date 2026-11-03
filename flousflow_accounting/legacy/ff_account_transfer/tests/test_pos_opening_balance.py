from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPosOpeningBalanceIncludesTransfers(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref('point_of_sale.group_pos_manager')
        company = cls.company
        cash_account = cls.env['account.account'].create({
            'name': 'POS Transfer Cash Test',
            'code': 'TSTCASH',
            'account_type': 'asset_cash',
        })
        cls.cash_journal = cls.env['account.journal'].create({
            'name': 'POS Transfer Cash Test',
            'type': 'cash',
            'code': 'TSTC',
            'company_id': company.id,
            'default_account_id': cash_account.id,
        })
        receivable = (
            company.account_default_pos_receivable_account_id
            or cls.company_data['default_account_receivable']
        )
        if not company.account_default_pos_receivable_account_id:
            company.account_default_pos_receivable_account_id = receivable
        cls.cash_method = cls.env['pos.payment.method'].create({
            'name': 'POS Transfer Cash Test',
            'type': 'cash',
            'journal_id': cls.cash_journal.id,
            'receivable_account_id': receivable.id,
            'company_id': company.id,
        })
        cls.config = cls.env['pos.config'].create({
            'name': 'POS Transfer Balance Test',
            'journal_id': cls.company_data['default_journal_sale'].id,
            'payment_method_ids': [(6, 0, cls.cash_method.ids)],
        })

    def test_cash_transfer_updates_next_pos_opening_balance_once(self):
        config = self.config
        cash_method = self.cash_method
        cash_journal = self.cash_journal
        source_method_line = cash_journal.outbound_payment_method_line_ids[:1]
        destination_journal = self.company_data['default_journal_bank']

        self.assertTrue(source_method_line)
        self.assertTrue(self.env.company.transfer_account_id)

        first_session = self.env['pos.session'].create({
            'config_id': config.id,
        })
        first_session._handle_cash_statement_entries({str(cash_method.id): 500.0})
        self.assertAlmostEqual(first_session.bank_statement_id.balance_end_real, 500.0)
        first_session.write({'state': 'closed'})

        transfer = self.env['account.payment'].with_context(force_payment_move=True).create({
            'amount': 500.0,
            'payment_type': 'outbound',
            'journal_id': cash_journal.id,
            'destination_journal_id': destination_journal.id,
            'payment_method_line_id': source_method_line.id,
            'currency_id': config.currency_id.id,
            'is_internal_transfer': True,
        })
        transfer.action_post()
        self.assertTrue(
            transfer.move_id and transfer.move_id.state == 'posted',
            f'Transfer state={transfer.state}, paired state={transfer.paired_internal_transfer_payment_id.state}',
        )

        self.assertAlmostEqual(config._get_opening_balance(), 0.0)

        next_session = self.env['pos.session'].create({
            'config_id': config.id,
        })
        next_session._handle_cash_statement_entries({str(cash_method.id): 0.0})
        self.assertAlmostEqual(next_session.bank_statement_id.balance_start, 0.0)
        self.assertAlmostEqual(config._get_opening_balance(), 0.0)

        next_session._handle_cash_statement_entries({str(cash_method.id): 100.0})
        self.assertAlmostEqual(next_session.bank_statement_id.balance_end_real, 100.0)
        next_session.write({'state': 'closed'})
        cash_journal.invalidate_recordset(['current_statement_balance'])
        statement_snapshot = [
            (s.id, s.date, s.balance_end_real, s.pos_session_id.state)
            for s in self.env['account.bank.statement'].search([
                ('journal_id', '=', cash_journal.id),
            ])
        ]
        opening = config._get_opening_balance()
        self.assertAlmostEqual(
            opening,
            100.0,
            msg=(
                f"opening={opening}, "
                f"journal={cash_journal.current_statement_balance}, "
                f"statements={statement_snapshot!r}"
            ),
        )
