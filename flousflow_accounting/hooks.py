# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting


def post_init_hook(env):
    """Auto-load a safe chart of accounts for every unconfigured company.

    Country-specific Odoo localizations remain authoritative. Branches inherit
    their parent chart, and only companies without a standard localization use
    the FlousFlow generic chart.
    """
    chart_template = env['account.chart.template']
    for company in env['res.company'].search([]):
        if company.chart_template or company._existing_accounting():
            # Never replace configured accounting or touch existing entries.
            continue
        template_code = chart_template._flousflow_template_for_company(company)
        chart_template.try_loading(template_code, company)
