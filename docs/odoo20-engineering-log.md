# Odoo 20 Engineering Log

## 2026-11-08 — Client-action registry repair

- Module: `flousflow_accounting`, deployed version `20.0.1.0.48`.
- Problem: report actions such as `flousflow_accounting.apr__open_items` and `flousflow_accounting.apr__partner_ledger` were missing from the browser actions registry.
- Evidence: a fresh debug bundle contained the report modules, but the module loader stopped on a duplicate `om_bank_reconciliation` registry key from the merged addon and the upstream reconciliation addon.
- Fix: register the merged reconciliation component under `flousflow_accounting.om_bank_reconciliation`; keep the report action loading imports in place.
- Verification: both `tabark` and `tabark_training` are installed and healthy; the fresh browser runtime reports the partner-ledger and open-items action keys present, and the Partner Ledger UI opens successfully.
- Commit: `548f3a2` on branch `20.0`.

## 2026-11-08 — Partner Ledger native theme alignment

- Problem: the interactive Partner Ledger toolbar and table used hard-coded light colors, which conflicted with the active Odoo dark/RTL theme and made controls low-contrast.
- Fix: replaced hard-coded backgrounds, borders, and partner-row colors with Odoo theme variables and retained the existing responsive breakpoints.
- Verification: after upgrading both databases, the live training page rendered the Partner Ledger controls and table; computed styles showed transparent/theme-backed surfaces, readable `rgb(235, 235, 235)` text, and a 1176px responsive viewport without overflow in the container.
## 2026-11-08 - Accounting report views aligned with native Odoo theme

- Normalized report toolbar, content, table, alert, and popover surfaces across customer statement, financial report, cash flow, open items, general ledger, trial balance, aged partner, tax report, and executive summary.
- Replaced hard-coded light backgrounds/text colors with Odoo theme variables and changed Open Items report actions to the native icon-link treatment.
- Preserved existing report behavior and responsive breakpoints; the change is visual/semantic only.

## 2026-11-11 - Partner analytic defaults and customer COGS propagation

- Module: `flousflow_accounting`, branch `20.0`.
- Added a company-dependent analytic account on `res.partner`; customer invoices default the header analytic account and retain draft-time manual override.
- Reused the native analytic distribution and stock-accounting path; outgoing stock moves use the sale order/header analytic on the non-stock-valuation COGS line while the stock valuation line remains untagged.
- Verification: XML/Python checks, Odoo 20 upgrade, partner/invoice ORM smoke test, existing branch-analytic test tag, service health, and HTTP checks on `al_yamen_test` and `al_yamen`.
- Commit: `e8cc03e` on branch `20.0`.

## 2026-11-11 - Partner analytic field visibility

- Problem: the partner analytic field was present in the form architecture but was inserted into a hidden accounting subsection and had no visible label.
- Fix: place the field in the visible Accounting > General group and add a translatable label while keeping the field company-dependent and optional.
- Verification: fresh test-browser reload exposed `analytic_account_id` on the contact Accounting tab; the test database was upgraded successfully.
- Commit: `08568c5` plus the follow-up label/log change on branch `20.0`.

## 2026-11-11 - Analytic profitability report

- Added a native accounting report wizard beside Odoo's analytic-items report.
- Filters: period, posted-only scope, analytic plan, and multiple analytic accounts.
- Summary: revenue, COGS, operating expenses, other income/expenses, net profit, margin, movement count, PDF print, and drill-down to analytic movements.
- Accounting rule: balance-sheet analytic lines remain auditable but are excluded from P&L totals; only income and expense account types affect profitability.
- Verification: Odoo 20 test upgrade, ORM summary (200 revenue - 120 COGS = 80 net / 40%), Arabic UI flow, movement drill-down, and QWeb PDF (`%PDF`) render.
- Test backup: `/var/backups/odoo/al_yamen_test_pre_analytic_translation_20261111.dump`.
- Latest branch commit: `925c836` on `20.0`; production deployment remains pending until final approval after test review.

## 2026-11-11 - Report navigation cleanup and Arabic labels

- Hid the obsolete `Financial Report` shortcut and the standard legacy `Analytic Report` shortcut from the user-facing report menus without removing their internal engines, because the Executive Summary and existing tests still use the financial report service.
- Kept `Analytic Profitability` and added explicit Arabic menu/action translation references (`الربحية التحليلية`).
- Added missing Arabic labels for the Executive Summary KPI groups, filters, and profitability cards.
- Verification target: upgrade both test and production databases, confirm menu visibility and Arabic labels in a fresh browser session, then re-run the Executive Summary and analytic profitability smoke flows.
