# -*- coding: utf-8 -*-
import csv
import io

from odoo import fields, models, _, Command
from odoo.exceptions import UserError


class LoanScheduleUpload(models.TransientModel):
    _name = 'flousflow.account.loan.upload'
    _description = 'Import Loan Amortization Schedule'

    loan_id = fields.Many2one('flousflow.account.loan', required=True, readonly=True)
    file_data = fields.Binary(required=True, string='CSV File')
    file_name = fields.Char(required=True)

    def action_import(self):
        self.ensure_one()
        loan = self.loan_id
        if loan.state != 'draft':
            raise UserError(_('A schedule can only be imported for a draft loan.'))
        if not self.file_name.lower().endswith('.csv'):
            raise UserError(_('Upload a CSV file with date, principal, and interest columns.'))
        try:
            # Odoo 20 exposes Binary fields as decoded BinaryValue objects in the ORM.
            content = bytes(self.file_data).decode('utf-8-sig')
            rows = list(csv.reader(io.StringIO(content)))
        except (ValueError, UnicodeDecodeError) as error:
            raise UserError(_('The CSV file could not be read as UTF-8.')) from error
        lines = []
        for row_number, row in enumerate(rows, 1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if row_number == 1 and row[0].strip().lower() in ('date', 'payment date', 'maturity date'):
                continue
            if len(row) < 3:
                raise UserError(_('Row %s must contain date, principal, and interest.', row_number))
            try:
                date = fields.Date.to_date(row[0].strip())
                principal = float(row[1].strip())
                interest = float(row[2].strip())
            except (TypeError, ValueError) as error:
                raise UserError(_('Row %s contains an invalid date or amount.', row_number)) from error
            if not date or principal < 0 or interest < 0:
                raise UserError(_('Row %s must contain a valid date and non-negative amounts.', row_number))
            lines.append({'sequence': len(lines) + 1, 'date': date,
                          'principal_amount': principal, 'interest_amount': interest})
        if not lines:
            raise UserError(_('The CSV file does not contain any schedule lines.'))
        if len({line['date'] for line in lines}) != len(lines):
            raise UserError(_('Each schedule line must have a unique date.'))
        loan.line_ids.unlink()
        loan.write({
            'duration': len(lines),
            'amount_borrowed': sum(line['principal_amount'] for line in lines),
            'interest': sum(line['interest_amount'] for line in lines),
            'line_ids': [Command.create(line) for line in lines],
        })
        return {'type': 'ir.actions.act_window', 'res_model': loan._name, 'res_id': loan.id,
                'view_mode': 'form', 'target': 'current'}
