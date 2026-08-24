# -*- coding: utf-8 -*-
# Part of FlousFlow Accounting
{
    'name': 'FlousFlow Accounting',
    'version': '19.0.36.1.0',
    'category': 'Accounting/Localizations/Account Charts',
    'summary': 'Complete Flous Flow accounting suite — country-based chart of '
               'accounts, financial reports, assets & depreciation, budgets, '
               'follow-up, fiscal years, recurring payments and a dashboard.',
    'description': """
FlousFlow Accounting
====================

A complete, self-contained Flous Flow accounting suite built on the standard
Odoo ``account`` module:

* **Chart of accounts** — neutral FlousFlow template (``flous_generic_coa``)
  that auto-loads by company country, exactly like the standard Odoo accounting
  module. Country localizations reuse Odoo ``l10n_*`` modules (e.g. ``l10n_eg``).
* **Financial reports** — Profit & Loss, Balance Sheet, Trial Balance, Cash
  Flow, General/Partner Ledgers, customer/vendor/account statements, Executive
  Summary, Aged Receivable/Payable, Tax and Journal Audit, with PDF/XLSX export.
* **Internal transfers** — paired transfers between bank and cash journals with
  automatic counterpart payment, full cancellation and journal dashboard
  shortcut (bank/cash "Internal Transfer" action).
* **Multicurrency revaluation** — revaluation wizard with generated gain/loss
  entries and reversal.
* **Assets and deferrals** — assets, deferred expenses and deferred revenues,
  recognition schedules, pause/resume, posting and auditable cancellation.
* **Budgets** — budget lines per account with planned vs actual vs theoretical
  amounts and achievement percentage.
* **Follow-up** — configurable collection levels, overdue partners report and
  reminder processing (email / letter / manual action).
* **Fiscal years and lock dates** — protected fiscal periods and the standard
  Odoo fiscal, tax, sales, purchase and hard lock dates.
* **Recurring payments** — scheduled payments (daily/weekly/monthly/yearly)
  with automatic payment generation.
* **Payment batches & promises** — batch processing of vendor payments and
  "promise to pay" tracking.
* **Bank reconciliation** — guided manual bank statement reconciliation.
* **Tax returns & VAT review** — tax return review, VAT / e-invoicing
  preparation and audit working files with review checklists.
* **Loans** — employee/vendor loan tracking with amortization schedules.
* **Accrual review** — period-end accrual review and posting.
* **Period closing** — controlled checklist, evidence, approval and standard
  Odoo lock-date application.
* **Dashboard** — bank/cash, receivable, payable, YTD income/expense/net profit
  and open/overdue document counters.

All features are original Community code and depend on ``account`` and ``mail``.
""",
    'author': 'Flous Flow',
    'website': 'https://flousflow.com',
    'icon': '/flousflow_accounting/static/description/accounting_icon_v2.png',
    'depends': [
        'account',
        'analytic',
        'hr_expense',
        'mail',
        'mrp_account',
        'point_of_sale',
        'project',
        'purchase_stock',
        'sale_stock',
        'stock_account',
    ],
    'external_dependencies': {'python': ['xlsxwriter']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/followup_mail_template.xml',
        'data/sequence.xml',
        'data/recurring_cron.xml',
        'data/followup_cron.xml',
        'data/financial_report_data.xml',
        'data/legacy_menu_cleanup.xml',
        'views/loan_views.xml',
        'views/working_file_views.xml',
        'views/accrual_review_views.xml',
        'views/period_close_views.xml',
        'views/pos_integration_views.xml',
        'views/bank_reconciliation_views.xml',
        'views/tax_return_views.xml',
        'views/payment_promise_views.xml',
        'views/payment_batch_views.xml',
        'views/payment_transfer_views.xml',
        'views/report_views.xml',
        'views/report_preset_views.xml',
        'views/asset_views.xml',
        'views/account_move_views.xml',
        'views/budget_views.xml',
        'views/followup_views.xml',
        'views/fiscal_year_views.xml',
        'views/lock_date_views.xml',
        'views/recurring_views.xml',
        'views/settings_views.xml',
        'views/dashboard_views.xml',
        'views/revaluation_views.xml',
        'views/financial_report_views.xml',
        'reports/financial_report.xml',
        'reports/followup_letter.xml',
        'views/menu.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
