from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestBranchAnalytic(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        plan = cls.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            plan = cls.env['account.analytic.plan'].create({'name': 'Branches'})
        cls.plan = plan
        cls.cairo = cls.env['account.analytic.account'].create({
            'name': 'Cairo Branch',
            'plan_id': plan.id,
        })
        cls.giza = cls.env['account.analytic.account'].create({
            'name': 'Giza Branch',
            'plan_id': plan.id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Test Customer'})

    @classmethod
    def _get_account(cls):
        account = cls.env['account.account'].search(
            [('company_ids', 'in', cls.env.company.ids)], limit=1, order='id')
        if not account:
            account = cls.env['account.account'].create({
                'name': 'Test Account',
                'code': 'TST9999',
                'account_type': 'asset_current',
                'company_ids': [Command.link(cls.env.company.id)],
            })
        return account

    @classmethod
    def _get_journal(cls):
        journal = cls.env['account.journal'].search([], limit=1, order='id')
        if not journal:
            journal = cls.env['account.journal'].create({
                'name': 'Test Journal',
                'code': 'TSTJ',
                'type': 'general',
            })
        return journal

    @classmethod
    def _get_pos_config(cls, analytic=None):
        return cls.env['pos.config'].create({
            'name': 'Test POS',
            'analytic_account_id': analytic.id if analytic else False,
        })

    @classmethod
    def _get_pos_session(cls, config):
        return cls.env['pos.session'].create({'config_id': config.id})

    # ------------------------------------------------------------------
    # POS configuration
    # ------------------------------------------------------------------
    def test_pos_config_analytic_account(self):
        config = self._get_pos_config(self.cairo)
        self.assertEqual(config.analytic_account_id, self.cairo)

    # ------------------------------------------------------------------
    # POS generated invoice
    # ------------------------------------------------------------------
    def test_pos_invoice_vals_get_analytic(self):
        config = self._get_pos_config(self.cairo)
        session = self._get_pos_session(config)
        order = self.env['pos.order'].create({
            'session_id': session.id,
            'partner_id': self.partner.id,
            'amount_tax': 0.0,
            'amount_total': 0.0,
            'amount_paid': 0.0,
            'amount_return': 0.0,
        })
        vals = order._prepare_invoice_vals()
        self.assertEqual(vals.get('analytic_account_id'), self.cairo.id)

    # ------------------------------------------------------------------
    # Account move header + propagation
    # ------------------------------------------------------------------
    def test_account_move_apply_distribution(self):
        account = self._get_account()
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Product A',
                    'quantity': 1,
                    'price_unit': 100,
                    'account_id': account.id,
                    'display_type': 'product',
                }),
                Command.create({
                    'name': 'Section note',
                    'display_type': 'line_note',
                }),
            ],
        })
        move.analytic_account_id = self.cairo
        move._apply_branch_analytic_distribution()

        product_line = move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        note_line = move.line_ids.filtered(lambda l: l.display_type == 'line_note')
        self.assertEqual(product_line.analytic_distribution, {str(self.cairo.id): 100.0})
        self.assertFalse(note_line.analytic_distribution)

    def test_account_move_apply_distribution_changes_account(self):
        account = self._get_account()
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Product A',
                    'quantity': 1,
                    'price_unit': 100,
                    'account_id': account.id,
                    'display_type': 'product',
                }),
            ],
        })
        move.analytic_account_id = self.cairo
        move._apply_branch_analytic_distribution()
        move.analytic_account_id = self.giza
        move._apply_branch_analytic_distribution()
        self.assertEqual(
            move.invoice_line_ids.analytic_distribution,
            {str(self.giza.id): 100.0},
        )

    def test_account_move_empty_header_preserves_existing_distribution(self):
        account = self._get_account()
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [
                Command.create({
                    'name': 'Product A',
                    'quantity': 1,
                    'price_unit': 100,
                    'account_id': account.id,
                    'display_type': 'product',
                    'analytic_distribution': {str(self.cairo.id): 100.0},
                }),
            ],
        })
        move._apply_branch_analytic_distribution()
        self.assertEqual(
            move.invoice_line_ids.analytic_distribution,
            {str(self.cairo.id): 100.0},
        )

    # ------------------------------------------------------------------
    # Mandatory enforcement (invoice)
    # ------------------------------------------------------------------
    def _make_out_invoice(self, analytic=None):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'analytic_account_id': analytic.id if analytic else False,
        })

    def test_invoice_requires_analytic_when_enabled(self):
        self.company.branch_analytic_require_invoice = True
        move = self._make_out_invoice()
        with self.assertRaises(UserError):
            move._check_branch_analytic_required()

    def test_invoice_ok_when_analytic_set(self):
        self.company.branch_analytic_require_invoice = True
        move = self._make_out_invoice(self.cairo)
        move._check_branch_analytic_required()

    def test_invoice_not_required_when_disabled(self):
        self.company.branch_analytic_require_invoice = False
        move = self._make_out_invoice()
        move._check_branch_analytic_required()

    def test_entry_move_not_affected(self):
        self.company.branch_analytic_require_invoice = True
        move = self.env['account.move'].create({'move_type': 'entry'})
        move._check_branch_analytic_required()

    # ------------------------------------------------------------------
    # Mandatory enforcement (POS)
    # ------------------------------------------------------------------
    def test_pos_requires_analytic_when_enabled(self):
        self.company.branch_analytic_require_pos = True
        config = self._get_pos_config()
        session = self._get_pos_session(config)
        with self.assertRaises(UserError):
            session._check_branch_analytic_required()

    def test_pos_ok_when_analytic_set(self):
        self.company.branch_analytic_require_pos = True
        config = self._get_pos_config(self.cairo)
        session = self._get_pos_session(config)
        session._check_branch_analytic_required()
