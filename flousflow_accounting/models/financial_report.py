# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FlousflowAccountReportTemplate(models.Model):
    _name = 'flousflow.account.report.template'
    _description = 'FlousFlow Financial Report Template'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(string='Code', required=True, help="Unique technical code.")
    company_id = fields.Many2one(
        'res.company', string='Company',
        help="Leave empty for a template shared across all companies.")
    line_ids = fields.One2many(
        'flousflow.account.report.template.line', 'template_id',
        string='Lines')

    _code_uniq = models.Constraint(
        'unique (code)', 'The template code must be unique.')

    # ------------------------------------------------------------------
    # Report engine
    # ------------------------------------------------------------------
    def _compute_lines(
            self, company, date_from, date_to,
            extra_domain=None, target_move='posted'):
        """Return a flat, ordered list of dicts describing the computed report:
        {'name', 'code', 'amount', 'level', 'is_total', 'is_section'}."""
        self.ensure_one()
        by_code = {line.code: line for line in self.line_ids if line.code}
        amounts = {}
        visiting = set()

        def amount_of(line):
            if line.id in amounts:
                return amounts[line.id]
            if line.id in visiting:
                raise ValidationError(
                    _('Circular reference in report template line "%s".') % line.name)
            visiting.add(line.id)
            if line.is_section:
                value = 0.0
            elif line.formula:
                value = self._eval_formula(line.formula, by_code, amount_of)
            elif line.account_ids or line.account_types:
                value = self._leaf_amount(
                    line, company, date_from, date_to,
                    extra_domain=extra_domain, target_move=target_move)
            else:
                value = sum(amount_of(child) for child in line.child_line_ids)
            visiting.discard(line.id)
            amounts[line.id] = value
            return value

        for line in self.line_ids:
            amount_of(line)

        result = []
        roots = self.line_ids.filtered(lambda l: not l.parent_id)
        self._flatten(roots, 0, amounts, result)
        return result

    def _eval_formula(self, formula, by_code, amount_of):
        total = 0.0
        for token in (formula or '').split():
            if not token:
                continue
            sign = 1.0
            name = token
            if name[0] == '-':
                sign = -1.0
                name = name[1:]
            elif name[0] == '+':
                name = name[1:]
            ref = by_code.get(name)
            if ref is not None:
                total += sign * amount_of(ref)
        return total

    def _leaf_amount(
            self, line, company, date_from, date_to,
            extra_domain=None, target_move='posted'):
        domain = [
            ('company_id', '=', company.id),
            ('date', '<=', date_to),
        ]
        if target_move == 'posted':
            domain.append(('parent_state', '=', 'posted'))
        domain += list(extra_domain or [])
        scoped_date_from = date_from
        if line.date_scope == 'to_date':
            scoped_date_from = False
        elif line.date_scope == 'fiscal_year':
            scoped_date_from = company.compute_fiscalyear_dates(date_to)['date_from']
        if scoped_date_from:
            domain.append(('date', '>=', scoped_date_from))
        if line.account_ids:
            domain += [('account_id', 'in', line.account_ids.ids)]
        else:
            types = [t.strip() for t in (line.account_types or '').split(',') if t.strip()]
            domain += [('account_id.account_type', 'in', types)]
        groups = self.env['account.move.line']._read_group(
            domain, aggregates=['debit:sum', 'credit:sum'])
        debit, credit = (groups[0] if groups else (0.0, 0.0))
        amount = (debit or 0.0) - (credit or 0.0)
        if line.sign == 'reversed':
            amount = -amount
        return amount

    def _flatten(self, lines, level, amounts, result):
        for line in lines.sorted('sequence'):
            amount = amounts.get(line.id, 0.0)
            is_total = bool(line.formula) or (
                not line.account_ids and not line.account_types
                and line.child_line_ids and not line.is_section)
            if not line.hide_in_report:
                result.append({
                    'name': line.name,
                    'code': line.code,
                    'amount': 0.0 if line.is_section else amount,
                    'level': level,
                    'is_total': is_total,
                    'is_section': line.is_section,
                })
            child_level = level if line.hide_in_report else level + 1
            self._flatten(line.child_line_ids, child_level, amounts, result)


class FlousflowAccountReportTemplateLine(models.Model):
    _name = 'flousflow.account.report.template.line'
    _description = 'FlousFlow Financial Report Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'flousflow.account.report.template', string='Template',
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='template_id.company_id', store=True)
    parent_id = fields.Many2one(
        'flousflow.account.report.template.line', string='Parent',
        ondelete='cascade', index=True)
    child_line_ids = fields.One2many(
        'flousflow.account.report.template.line', 'parent_id',
        string='Children')
    sequence = fields.Integer(string='Sequence', default=10)
    name = fields.Char(string='Label', required=True)
    code = fields.Char(string='Code', help="Unique code used by formulas.")
    sign = fields.Selection(
        [('normal', 'Normal (Debit)'), ('reversed', 'Reversed (Credit)')],
        string='Sign', default='normal',
        help="Reversed is used for income, liabilities and equity.")
    account_ids = fields.Many2many(
        'account.account', 'flousflow_report_line_account_rel',
        'line_id', 'account_id', string='Accounts')
    account_types = fields.Char(
        string='Account Types',
        help="Comma-separated account types (e.g. income,expense_direct_cost). "
             "Used when Accounts is empty, so the template works with any chart.")
    formula = fields.Char(
        string='Formula',
        help="Sum/subtract other line codes, e.g. 'total_revenue -total_expenses'.")
    date_scope = fields.Selection(
        [('report', 'Report Period'), ('to_date', 'As of Date'),
         ('fiscal_year', 'Current Fiscal Year')],
        string='Date Scope', default='report', required=True)
    hide_in_report = fields.Boolean(
        string='Calculation Only',
        help='Use this line in formulas without displaying it in the report.')
    is_section = fields.Boolean(string='Section Header')

    @api.constrains('code')
    def _check_code_unique(self):
        for line in self:
            if line.code and line.template_id:
                dup = line.template_id.line_ids.filtered(
                    lambda l: l.id != line.id and l.code == line.code)
                if dup:
                    raise ValidationError(
                        _('The code must be unique within a template.'))
