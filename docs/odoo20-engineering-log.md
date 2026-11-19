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
- Verification: test and production upgrades completed; both obsolete menus are inactive, the new analytic profitability menu remains active, and a fresh Arabic browser session shows the Executive Summary labels and formulas in Arabic.
- Production backup: `/var/backups/odoo/al_yamen_pre_report_menu_cleanup_20261111.dump`.
- Final branch commit for this change: `ac39fbf` on `20.0`.

## 2026-11-11 - Neutral net-balance confirmations

- Problem: balance confirmations were inferring customer/vendor wording and could reject a dual-role partner even when the partner had valid debit and credit activity.
- Fix: confirmation defaults to the combined receivable/payable scope, sums the partner's net debit-credit balance through the end date, and uses neutral bilingual wording (`Balance Confirmation` / `مصادقة الرصيد`). Customer/vendor terminology is retained only for ordinary ledger scope selection, not in the confirmation document.
- Verification: focused Odoo 20 partner-ledger tests cover mixed customer/vendor moves, neutral Arabic/English output, and combined-scope defaults. Deployment is gated on the test database run and backup-first rollout.
# 2026-11-12 — Sales by salesperson and team report

- Added a native `sale.order` reporting action under Accounting > Reports > Management.
- The report covers confirmed quotations/orders (`sale` and `done`) and supports list, pivot, and graph views with salesperson, sales team, customer, and month grouping.
- Added Arabic translations for the report title, filters, and measures.
- Validation: XML parse, Python compile, `git diff --check`, Odoo 20 test-database module upgrade, and browser verification on `al_yamen_test`.
- Test backup: `/var/backups/odoo/al_yamen_test_pre_salesperson_team_report_20261112.dump`.

## 2026-11-16 — Customer salesperson defaults to payment collector

- Customer payments now inherit `res.partner.user_id` into the accounting payment `salesperson_id` collector when the field is blank.
- The rule runs through the ORM for normal creation, Register Payment, imports, and partner changes; a manually selected collector is preserved and supplier payments remain unchanged.
- Added focused Odoo 20 tests for customer defaulting, manual override, supplier exclusion, and server-side partner changes.
- Extended the standard Register Payment wizard so the collector is visible in invoice payments and is propagated to the created customer payment.

## 2026-11-16 — Internal transfer fees

- Added a configurable company-level expense account for internal bank/cash transfer fees.
- Internal transfers now accept a separate fee amount; the destination receives only the transfer amount, while a separate posted entry debits the configured expense account and credits the source journal liquidity account.
- Added lifecycle handling, validations, and a focused posting test.

## 2026-11-16 — Hide collector on internal transfers

- Internal bank/cash transfers no longer display the customer payment collector field; it remains available on ordinary customer payments only.

## 2026-11-16 — Arabic accounting settings translations

- Added Arabic translations for salesperson credit-limit settings, analytic-account requirements, GCC invoice format, and invoice-total-in-words settings, including their explanatory help text.
- Kept the English source strings unchanged so the settings remain bilingual by user language and upgrade-safe.
- Validation: targeted source inspection and `git diff --check`; the existing `ar_001.po` contains pre-existing duplicate catalog entries, so `msgfmt` still reports those unrelated baseline errors.

## 2026-11-16 — Partner Ledger native control panel

- Replaced the report's bespoke top toolbar with Odoo 20's standard `ControlPanel` component while keeping the existing ledger filters, XLSX export, print action, partner drill-down, and report data service unchanged.
- Updated responsive styling so the standard control-panel actions remain visible on small screens.
- Validation: JavaScript syntax check, XML parse, and `git diff --check`; deployment and browser smoke test pending.
- Follow-up: replaced the report-options menu with Odoo's `Dropdown`/`DropdownItem` components and changed the fiscal-year navigation to a native button group with Odoo icons.
- Follow-up verification found the first icon names were not rendered in the deployed theme; switched the period controls to the supported `arrow_left`/`arrow_right` icons and removed the caret class that collapsed the options button.
## 2026-11-17 - POS credit field visibility

- Problem: `pos_credit_config_id` existed on contacts but was appended to the outer accounting group, so Odoo rendered an unlabeled full-width combobox.
- Evidence: Odoo 20 standard `account.view_partner_property_form` places credit controls in `group[name='credit_limits']`; browser AX tree exposed the field ID without a visible label.
- Change: moved the field into the standard credit-limits group with an explicit label, safe no-create/no-open options, and an Arabic placeholder.
- Validation: XML well-formedness and diff checks passed. Existing translation catalogs contain unrelated historical duplicate msgids, so full `msgfmt --check` remains noisy; the new entries are unique.
- Follow-up: upgrade the addon and verify the Arabic contact form after assets/cache refresh.

# 2026-11-19 — Internal transfer fee posting

- Changed `ff_account_transfer` so outbound transfers with a fee use one direct three-line move: debit the destination journal liquidity account and fee expense, credit the source journal liquidity account for transfer amount plus fee.
- Transfers without a fee retain Odoo's paired payment and Funds in Transit flow. Existing posted transfers are not rewritten.
- Added a focused regression test and bumped the module to `20.0.1.0.55`.

# 2026-11-19 — Transfer form field order

- Moved the internal transfer fee field directly below the amount field to reduce data-entry confusion; the change is limited to the payment form view.
- Bumped the module to `20.0.1.0.56`.

# 2026-11-19 — Transfer fee label visibility

- Corrected the inherited payment view anchor so `transfer_fee` is inserted after the complete amount row, not inside the amount widget. This restores the standard Odoo label/value layout and makes the Arabic fee label visible.
- Bumped the module to `20.0.1.0.57`.

# 2026-11-19 — Explicit transfer fee label

- Added an explicit Arabic label for `transfer_fee` because the inherited field was visible without a label in the resolved Odoo form architecture.
- Bumped the module to `20.0.1.0.58`.

# 2026-11-19 — Remove duplicate transfer fee label

- Removed the explicit label because Odoo's standard group renderer already generates the field label once. This leaves one `مصروف التحويل` label beside the fee value.
- Bumped the module to `20.0.1.0.59`.

# 2026-11-19 — POS credit contact selector

- Fixed the contact POS-credit selector domain. It was using the contact's `company_id`, which is empty for many individual contacts and hid all company POS configurations. Replaced it with Odoo's standard `check_company=True` behavior.
- Bumped the module to `20.0.1.0.60`.

# 2026-11-19 — POS selector company domain

- Added the view domain `company_id in allowed_company_ids` to the contact POS-credit selector. This uses the active Odoo company context and works for contacts whose own `company_id` is empty.
- Bumped the module to `20.0.1.0.61`.

