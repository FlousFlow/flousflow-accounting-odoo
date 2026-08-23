# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FlousflowAccountPeriodClose(models.Model):
    _inherit = 'flousflow.account.period.close'

    open_pos_session_count = fields.Integer(
        string='Open POS Sessions', compute='_compute_open_pos_session_count')

    def _open_pos_session_domain(self):
        self.ensure_one()
        if not self.company_id or not self.date_end:
            return [('id', '=', 0)]
        next_date = fields.Date.to_date(self.date_end) + timedelta(days=1)
        return [
            ('company_id', '=', self.company_id.id),
            ('state', '!=', 'closed'),
            ('start_at', '<', fields.Datetime.to_string(next_date)),
        ]

    @api.depends('company_id', 'date_end')
    def _compute_open_pos_session_count(self):
        # Closing control must also work for accounting managers who do not
        # operate the POS.  Elevation is restricted to a count on the current
        # close company/date domain and never exposes session records.
        Session = self.env['pos.session'].sudo()
        for close in self:
            close.open_pos_session_count = (
                Session.search_count(close._open_pos_session_domain())
                if close.company_id and close.date_end else 0
            )

    def _check_no_open_pos_sessions(self):
        for close in self:
            count = self.env['pos.session'].sudo().search_count(
                close._open_pos_session_domain())
            if count:
                raise UserError(_(
                    'There are %(count)s Point of Sale sessions opened on or '
                    'before %(date)s that are not closed and posted.',
                    count=count, date=close.date_end,
                ))

    def action_submit(self):
        self._check_no_open_pos_sessions()
        return super().action_submit()

    def action_close(self):
        self._check_no_open_pos_sessions()
        return super().action_close()

    def action_open_pos_sessions(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'point_of_sale.action_pos_session')
        action['domain'] = self._open_pos_session_domain()
        action['context'] = {
            'search_default_open_sessions': 1,
            'allowed_company_ids': self.company_id.ids,
        }
        return action
