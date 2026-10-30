from odoo import api, fields, models, _
from odoo.tools.misc import get_lang


class AccountCommonReport(models.TransientModel):
    _name = "account.common.report"
    _description = "Account Common Report"

    company_id = fields.Many2one('res.company', string='Company', required=True, readonly=True,
                                 default=lambda self: self.env.company)
    journal_ids = fields.Many2many(
        comodel_name='account.journal',
        string='Journals',
        required=True,
        # 'child_of': the journals of the company and of the branches it consolidates
        default=lambda self: self.env['account.journal'].search([('company_id', 'child_of', self.env.company.id)]),
        domain="[('company_id', 'child_of', company_id)]",
    )
    date_from = fields.Date(string='Start Date')
    date_to = fields.Date(string='End Date')
    target_move = fields.Selection([('posted', 'All Posted Entries'),
                                    ('all', 'All Entries'),
                                    ], string='Target Moves', required=True, default='posted')
    customer_statement_partner_id = fields.Many2one('res.partner', readonly=True)
    customer_statement_filters = fields.Json(readonly=True)
    draft_entry_count = fields.Integer(
        string='Draft Entries',
        compute='_compute_draft_entry_count',
        help='Number of draft journal entries matching the selected company, journals and period.',
    )

    @api.depends('company_id', 'journal_ids', 'date_from', 'date_to')
    def _compute_draft_entry_count(self):
        """Mirror Enterprise's draft-entry warning without changing report scope.

        The warning is informational: reports still use ``target_move`` exactly as
        selected by the user.  The company and journal filters are applied so the
        message points to entries that can affect the current report.
        """
        Move = self.env['account.move']
        for report in self:
            domain = [
                ('state', '=', 'draft'),
                ('company_id', 'child_of', report.company_id.id),
            ]
            if report.journal_ids:
                domain.append(('journal_id', 'in', report.journal_ids.ids))
            if report.date_from:
                domain.append(('date', '>=', report.date_from))
            if report.date_to:
                domain.append(('date', '<=', report.date_to))
            report.draft_entry_count = Move.search_count(domain)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            self.journal_ids = self.env['account.journal'].search(
                [('company_id', 'child_of', self.company_id.id)])
        else:
            self.journal_ids = self.env['account.journal'].search([])

    def _build_contexts(self, data):
        result = {}
        result['journal_ids'] = 'journal_ids' in data['form'] and data['form']['journal_ids'] or False
        result['state'] = 'target_move' in data['form'] and data['form']['target_move'] or ''
        result['date_from'] = data['form']['date_from'] or False
        result['date_to'] = data['form']['date_to'] or False
        result['strict_range'] = True if result['date_from'] else False
        result['company_id'] = data['form']['company_id'][0] or False
        return result

    def _print_report(self, data):
        raise NotImplementedError()

    def check_report(self):
        self.ensure_one()
        data = {}
        data['ids'] = self.env.context.get('active_ids', [])
        data['model'] = self.env.context.get('active_model', 'ir.ui.menu')
        data['form'] = self.read(['date_from', 'date_to', 'journal_ids', 'target_move', 'company_id'])[0]
        used_context = self._build_contexts(data)
        data['form']['used_context'] = dict(used_context, lang=get_lang(self.env).code)
        return self.with_context(discard_logo_check=True)._print_report(data)
