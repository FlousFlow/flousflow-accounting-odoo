# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import models, _
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    def _flousflow_template_for_company(self, company):
        """Return the standard country chart, or our neutral fallback.

        Branches intentionally keep the root company's chart, matching Odoo's
        standard multi-company behavior. Independent companies use the first
        visible template matching their country. A country without a standard
        localization receives the FlousFlow generic chart.
        """
        if company.parent_id and company.parent_id.chart_template:
            return company.parent_id.chart_template
        if company.country_id:
            mapping = self._get_chart_template_mapping()
            guessed = self._guess_chart_template(company.country_id)
            if mapping.get(guessed, {}).get('country_id') == company.country_id.id:
                return guessed
        return 'flous_generic_coa'

    @template('flous_generic_coa')
    def _get_flous_generic_coa_template_data(self):
        """Data for the neutral FlousFlow chart of accounts template.

        Mirrors the standard Odoo ``generic_coa`` structure but stays
        country-independent: no fiscal country is forced, so the company's own
        country drives localization behavior.
        """
        return {
            'name': _("FlousFlow Generic Chart of Accounts"),
            'country': None,
            'property_account_receivable_id': 'flous_receivable',
            'property_account_payable_id': 'flous_payable',
        }

    @template('flous_generic_coa', 'res.company')
    def _get_flous_generic_coa_res_company(self):
        """Values written on the company when the template is loaded.

        ``account_fiscal_country_id`` follows the standard Odoo ``generic_coa``
        behaviour: Odoo 19 requires every tax to carry a country, computed from
        the company's fiscal country. The standard generic template defaults it
        to the United States; the company can change its own country afterwards
        and the taxes recompute accordingly.
        """
        return {
            self.env.company.id: {
                'anglo_saxon_accounting': True,
                'account_fiscal_country_id': 'base.us',
                'bank_account_code_prefix': '1014',
                'cash_account_code_prefix': '1015',
                'transfer_account_code_prefix': '1017',
                'account_default_pos_receivable_account_id': 'flous_pos_receivable',
                'income_currency_exchange_account_id': 'flous_income_currency_exchange',
                'expense_currency_exchange_account_id': 'flous_expense_currency_exchange',
                'default_cash_difference_income_account_id': 'flous_cash_diff_income',
                'default_cash_difference_expense_account_id': 'flous_cash_diff_expense',
                'account_journal_early_pay_discount_loss_account_id': 'flous_cash_discount_loss',
                'account_journal_early_pay_discount_gain_account_id': 'flous_cash_discount_gain',
                'expense_account_id': 'flous_expense',
                'income_account_id': 'flous_income',
                'account_stock_journal_id': 'inventory_valuation',
                'account_stock_valuation_id': 'flous_stock_valuation',
                'account_production_wip_account_id': 'flous_wip',
                'account_production_wip_overhead_account_id': 'flous_cost_of_production',
            },
        }

    @template('flous_generic_coa', 'account.account')
    def _get_flous_generic_coa_account_account(self):
        """Extra per-account data (stock variation link)."""
        return {
            'flous_stock_valuation': {
                'account_stock_variation_id': 'flous_stock_variation',
            },
        }
