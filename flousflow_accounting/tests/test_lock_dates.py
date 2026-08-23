# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase


class TestLockDates(TransactionCase):

    def test_apply_updates_standard_company_lock_dates(self):
        wizard = self.env['flousflow.account.lock.date'].create({
            'company_id': self.env.company.id,
            'fiscalyear_lock_date': '2025-12-31',
            'tax_lock_date': '2025-11-30',
            'sale_lock_date': '2025-10-31',
            'purchase_lock_date': '2025-09-30',
        })
        wizard.action_apply()
        company = self.env.company
        self.assertEqual(str(company.fiscalyear_lock_date), '2025-12-31')
        self.assertEqual(str(company.tax_lock_date), '2025-11-30')
        self.assertEqual(str(company.sale_lock_date), '2025-10-31')
        self.assertEqual(str(company.purchase_lock_date), '2025-09-30')
