# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
from odoo import models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def install_l10n_modules(self):
        """Complete Odoo's country-localization flow with a neutral fallback.

        Standard Odoo installs and loads a country chart when one exists. It
        deliberately leaves ``generic_coa`` unloaded; for those companies we
        schedule the self-contained FlousFlow generic chart instead.
        """
        fallback_company_ids = [
            company.id
            for company in self
            if (
                company.country_id
                and not company.chart_template
                and self.env['account.chart.template']
                ._flousflow_template_for_company(company) == 'flous_generic_coa'
            )
        ]
        result = super().install_l10n_modules()
        if not result or not fallback_company_ids:
            return result

        env = self.env
        env.flush_all()
        env.transaction.reset()
        for company_id in fallback_company_ids:
            company = env['res.company'].browse(company_id)
            if company.exists() and not company.chart_template:
                @env.cr.precommit.add
                def load_flousflow_fallback(company_id=company_id):
                    current_company = env['res.company'].browse(company_id)
                    if current_company.exists() and not current_company.chart_template:
                        env['account.chart.template'].try_loading(
                            'flous_generic_coa', current_company)
        return result
