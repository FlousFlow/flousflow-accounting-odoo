# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo.tests.common import TransactionCase


class TestDashboard(TransactionCase):

    def test_dashboard_defaults(self):
        dashboard = self.env['flousflow.account.dashboard'].create({})
        self.assertTrue(dashboard)
        # Fields must be populated (at least company_id)
        self.assertTrue(dashboard.company_id)
        # net profit should be a number
        self.assertIsInstance(dashboard.net_profit, float)

    def test_dashboard_refresh(self):
        dashboard = self.env['flousflow.account.dashboard'].create({})
        dashboard.action_refresh()
        self.assertTrue(dashboard.company_id)
