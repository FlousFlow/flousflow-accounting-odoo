# Odoo 20 Accounting Parity Audit

This document records the Odoo 20 port and a destination-by-destination
comparison with the FlousFlow Enterprise accounting app inspected in the
supplied SaaS session.
The implementation is original Community code; it does not copy Enterprise
source or depend on Enterprise modules. The reference was read live through the
provided Enterprise database API; only menu/action/view/field metadata was read.
The complete 77-destination route/action matrix is in
[`ODOO20_ENTERPRISE_PARITY_MATRIX.md`](ODOO20_ENTERPRISE_PARITY_MATRIX.md).

## Verified in this rollout

- Installed `flousflow_accounting` on the local Odoo 20 database `odoo20`.
- Odoo 20's accounting app root now has the same seven primary sections as the
  Enterprise reference: Dashboard, Customers, Vendors, Accounting, Review,
  Reporting, and Configuration.
- Reuses the standard `account` journal dashboard and accounting engine. The
  module does not create a parallel ledger.
- The module currently owns 66 active accounting menu records. The local
  Accounting tree has 93 action destinations, including standard and FlousFlow
  routes. The latest direct database check found zero journal entries.
- The old duplicate Internal Transfers menu is inactive. The active transfer
  menu and payment workflow belong to this module.
- Added a persistent **Annual Report** workspace under Review > Audit with
  Kanban/list, report title/status/period/company/responsibles, reusable HTML
  templates, workflow buttons, chatter and PDF output. The form can launch the
  existing annual financial-statement wizard for the same period; that wizard
  remains separately available under Reporting > Statement Reports.
- Working Files now supports a Paused state that preserves whether review was
  in Draft or In Review. Its default Kanban selects To Do and Paused filters to
  match the Enterprise queue.
- Aligned **Assets & Liabilities** under Accounting > Accounting, placed
  **Depreciation Schedule** directly under Reporting > Statement Reports, and
  grouped **Working Files** and **Annual Report** under Review > Audit.
- Added the Enterprise **Depreciation Models** destination under Configuration
  > Accounting. It opens fixed-asset category settings with matching
  list/kanban/form views; its underlying Community model remains different.
- Added the missing Community **Account Tags** destination.
- Aligned **Configuration → Accounting → Invoice Reminders** to the Enterprise
  menu route and list/kanban/form view sequence. The destination opens FlousFlow
  reminder levels; Follow-up Settings remains separately accessible.
- Added the Enterprise **Fiscal Report** route as a shortcut to FlousFlow Tax
  Report. It is an internal tax review/report workflow and does not implement
  statutory filing or e-filing.
- Added **Configuration → Accounting → Accounting Reports** on Community's
  standard `account.report` model with explicit list/form/search views. Read
  access follows Odoo's Accounting Readonly group; editing is limited to the
  standard Accounting Manager group. Managers can configure report options,
  grouping, composite sections, lines, columns, and calculation expressions.
- Enabled the Community pivot, list, kanban, form, and graph views on the
  **Analytic Report** action. Enterprise also provides a grid view unavailable
  in the inspected Community source.
- Changed **Loans Analysis** to open FlousFlow loan installment records with
  list/form views, matching Enterprise’s line-based analysis workflow as far
  as the Community loan model allows.
- Repointed the four accrual destinations to native purchase/sale order-line
  lists, using Odoo's own accrual domains, search contexts, and built-in server
  actions that open the native accrual-entry wizard. The separate FlousFlow
  accrual-review screen remains available as an additional menu.
- Added **Review → Inventory → Inventory Valuation**, connected to Odoo 20's
  native stock valuation client action.

## Odoo 20 compatibility changes

- Updated the manifest to `20.0.1.0.0` on the local `20.0` branch.
- Replaced Odoo 19 `ir.model.access`/`ir.rule` records with Odoo 20's unified
  `ir.access` model. Role permissions remain additive; company and saved-filter
  domains remain restrictive.
- Removed the obsolete `report_file` field from report actions.
- Updated the security metadata checks to use Odoo 20's access model.

## Feature coverage

| Enterprise area | FlousFlow/Odoo 20 coverage |
|---|---|
| Dashboard, Customers, Vendors | Standard Odoo accounting app surfaces |
| Accounting transactions | Standard journal entries, invoices, payments, journals, and chart of accounts |
| Assets & Liabilities | Assets, asset models/groups, depreciation, and loan schedules |
| Closing | Open-item reconciliation, tax return review, period close, lock dates, and standard secure entries |
| Review and audit | Journal items, audit trail, journal audit, FlousFlow working files, native purchase/sale accrual queues, deferred-asset lists, and currency revaluation |
| Financial reporting | Profit and Loss, Balance Sheet, Cash Flow, Trial Balance, General/Partner Ledgers, statements, aging, tax report, and Executive Summary |
| Other analyses | Standard Invoice Analysis, Cashflow Analysis, and Analytic Report; FlousFlow loan-installment analysis |
| Annual reporting | Persistent report/template management plus a fiscal-year Profit & Loss, Balance Sheet, and Cash Flow wizard with prior-year comparison |
| Configuration | Standard chart, taxes, journals, currencies, fiscal positions, tax groups, analytic setup, plus FlousFlow budgets, asset models, fiscal years, and follow-up setup |

## Destination-by-destination comparison

| Enterprise destination | FlousFlow destination | Screen/action parity |
|---|---|---|
| Accounting app: Dashboard | Dashboard | Same standard journal dashboard and accounting engine. |
| Customers | Customers | Standard customer invoices, credit notes, payments, products, and contacts. |
| Vendors | Vendors | Standard vendor bills, credit notes, payments, products, and contacts. |
| Accounting > Transactions | Accounting > Transactions | Standard journal entries and analytic items, with FlousFlow payment batches, recurring payments, and POS session access. |
| Accounting > Closing > Reconcile | Accounting > Closing > Reconcile | Dedicated selection across reconcilable accounts and native reconciliation; Enterprise matching suggestions remain unavailable. |
| Accounting > Closing > Tax Returns | Accounting > Closing > Tax Returns | FlousFlow tax-return Kanban/Calendar workflow now tracks a filing deadline, internal review-submission date, and tax-lock date; no statutory e-filing integration is claimed. |
| Accounting > Reporting > Statement Reports > Profit and Loss / Balance Sheet / Cash Flow Statement | Same destinations | OWL report screen with date, entry-status, comparison, fold/unfold, amount drill-down, draft-entry warning, and PDF/XLSX actions. Enterprise's cash-basis selector and currency conversion/settings are not implemented yet; local rendered-screen verification is pending a local browser session. |
| Accounting > Closing > Period Closing / Lock Dates | Same destinations | FlousFlow approval checklist plus standard Odoo lock-date configuration. |
| Accounting > Review > Audit > Audit Trail | Same destination | Standard Odoo audit trail action. |
| Accounting > Review > Control > Journal Items | Same destination | Standard all-journal-items action. |
| Accounting > Review > Control > Journal Audit | Same label and route | FlousFlow report form; Enterprise opens the dynamic `account_report` client action. |
| Accounting > Review > Audit > Working Files | Same route after this update | FlousFlow evidence/review model with Kanban/list/form; Enterprise uses `account.return` Kanban/search and filing/audit-cycle fields. |
| Accounting > Review > Audit > Annual Report | Same route after this update | Persistent FlousFlow Kanban/list report workspace with form, HTML template content, status/responsibles, chatter and PDF; links to the existing annual financial-statement wizard. |
| Accounting > Accounting > Assets & Liabilities > Assets / Loans | Same routes | FlousFlow asset/loan models and workflows are different from Enterprise models. |
| Accounting > Reporting > Statement Reports > Depreciation Schedule | Same route after this update | FlousFlow asset schedule list/pivot/graph; Enterprise destination is an `account_report` client action. |
| Accounting > Reporting > Management > Analytic Report | Same route | Same `account.analytic.line` model and matching Community pivot/list/kanban/form/graph views; Enterprise also has `grid`. |
| Accounting > Reporting > Management > Loans Analysis | Same route | Opens FlousFlow loan installment lines in list/form; Enterprise uses its own loan-line model and fields. |
| Accounting > Review > Inventory > Inventory Valuation | Same destination | Native Odoo stock valuation client action. |
| Accounting > Review > Regularization Entries > Unrealized Currencies / Deferred Revenues / Deferred Expenses | Labels/route aligned | Currency revaluation opens a wizard; deferred items open filtered FlousFlow asset lists; Enterprise uses dynamic report actions. |
| Accounting > Review > Purchases > Bills To Receive / Billed Not Received | Native order-line list destinations after this update | Uses Enterprise-equivalent model/domain/context, the same 10 list fields, and native accrual wizard/action. Enterprise `accrual_list_view` client renderer remains edition-specific. |
| Accounting > Review > Sales > Invoices To Be Issued / Invoiced Not Delivered | Native order-line list destinations after this update | Uses the same 13 list fields as the Enterprise snapshot, including unit and total cost mapped to Community `sale_margin`; uses the native accrual wizard/action. Enterprise `accrual_list_view` client renderer and exact cost-compute implementation remain unverified. |
| Accounting > Reporting | Reporting | Standard legal, partner, tax, and management folders plus FlousFlow reports. |
| Accounting > Configuration > Accounting > Account Tags | Added Community tag destination | Uses native `account.account.tag` model and standard tag views; Enterprise wraps this as `account_accountant.account_tag_action`. |
| Accounting > Configuration > Accounting > Invoice Reminders | Same route and list/kanban/form view sequence | FlousFlow reminder levels and actions are available; technical model differs and Enterprise reminder lifecycle is not claimed identical. |
| Accounting > Configuration > Accounting > Accounting Reports | Same route and `account.report` model, list/form; the four list columns and default context match the Enterprise snapshot | Community exposes native definitions, options, sections, columns, report lines, and manager-editable calculation expressions; the Enterprise renderer and interactive report controls remain edition-specific. |
| Accounting > Configuration | Configuration | Standard Odoo configuration plus FlousFlow asset models/groups, fiscal years, budgets, and report templates. |

The two accounting apps cannot be byte-for-byte identical: this build targets
Odoo 20 Community, while the reference is Odoo Enterprise. The comparison
matches user-facing destinations and equivalent workflows where Community
APIs support them; it records different implementation behavior in the gap
table below.

## Requirement-by-requirement gap analysis

| Enterprise requirement | Standard Odoo 20 support | Actual gap in this module | Implemented route |
|---|---|---|---|
| Accounting > Closing > Reconcile | `account.move.line.reconcile()` and reconciliation models provide the ledger operation; Community has no Enterprise open-item board at `/odoo/reconcile`. | No direct screen to select open receivable/payable entries. Bank-statement reconciliation is a separate workflow. | Added a Closing > Reconcile list grouped by account and partner. It validates posted/open receivable or payable lines, scopes by company/account/partner, requires entries from at least two moves, then delegates to Odoo's reconcile method. |
| Closing > Tax Returns | Localization tax tags and standard Tax Reports are available; submission task boards depend on the installed app/localization. | FlousFlow's tax return review was previously located under Reporting and opened only list/form views. | Moved Tax Returns to Closing and added Kanban and Calendar views while preserving the existing preparation, review, approval, and tax-lock workflow. It is an internal review workflow, not an electronic filing integration. |
| Review > Inventory > Inventory Valuation | Odoo 20 provides `account.action_report_stock_valuation`. | The Community action existed but had no Accounting Review menu entry. | Added the native report at Review > Inventory > Inventory Valuation; no alternate valuation calculation is introduced. |
| Review > Purchases / Sales accrual queues | Standard Odoo has the accrued-order adjustment wizard and order/invoice data. | The four review-only queues were grouped under Inventory instead of the Enterprise Purchases and Sales folders. | Split the queues under Review > Purchases and Review > Sales; their amounts remain non-posting review information. |
| Periodic tax reports and localized filing | Odoo reports tax grids; `l10n_*` modules supply statutory definitions and country rules. | A generic addon cannot claim complete country-specific returns or electronic filing. | Keep statutory reporting on the standard localization reports; use FlousFlow's tax review and evidence workflow for internal control. |

## View, model, and field-level differences verified

The Enterprise metadata snapshot included 103 active Accounting menu records,
77 action destinations, 114 linked views, and `fields_get` metadata for 16
Enterprise-facing models. The FlousFlow module adds its own functionality; menu
count is therefore not a meaningful parity score. The important differences are:

| Area | Enterprise model and views | FlousFlow / Community model and views | Result |
|---|---|---|---|
| Accrual queues | `purchase.order.line` / `sale.order.line`, list/search, accrual list renderer, native accrued-order wizard | Same Community line models, matching purchase/sales list columns, native order-line list and wizard | Route/model/columns/workflow aligned; Enterprise-specific client renderer remains different. |
| Working Files | `account.return`, Kanban/search; return type, filing/deadline/status, tax-unit, cycle/check fields | `flousflow.account.working.file`, list/form/search; owner/reviewer, evidence, approval workflow | Similar purpose, different data model, field set, and screen. |
| Annual Report | `audit.report`, Kanban/list; title, status, date range, company, responsible users, Knowledge template article | `flousflow.account.annual.report`, Kanban/list/form; title, status, period, company, responsible users, HTML template, chatter and PDF; financial statements open in a separate wizard | Screen fields and list workflows are closer; model differs. Enterprise Knowledge article editor/pages and template lifecycle are not in Community. |
| Assets / depreciation | Enterprise `account.asset` with list/form and Enterprise depreciation report client action | `flousflow.account.asset` and depreciation-line list/pivot/graph | Similar accounting workflow, not model- or view-identical; Enterprise asset engine absent in checked Community source. |
| Loans / Loans Analysis | `account.loan` list/form; `account.loan.line` pivot/list/form | `flousflow.account.loan` list/form/pivot/graph; `flousflow.account.loan.line` pivot/list/form analysis destination | Analysis now matches view order, yearly pivot axes/measures, Current default, and loan-date/asset-group filters. Local asset group is an optional classification; exact Enterprise theoretical-balance formula is unverified. |
| Analytic Report | `account.analytic.line`, pivot/list/kanban/form/graph/grid | Same Community model with pivot/list/kanban/form/graph | All matching Community views are enabled; the Enterprise grid view has no Community counterpart in the checked source. |
| Reconciliation | `account.move.line`, Enterprise reconciliation list class, action button and extended search/columns | `account.move.line` list and FlousFlow explicit-selection reconcile operation | Native ledger operation; Enterprise-assisted match UI remains a gap. |
| Accounting reports | Enterprise dynamic `account_report` client actions and `account.report` list/form configuration | FlousFlow report transient forms for business output; Community `account.report` configuration list/form added | Configuration destination is aligned by model and view sequence; report rendering/options/export remain different. |
| Tax returns | Enterprise `account.return` dynamic return workflow, return types, authority submission and localization integrations | `flousflow.account.tax.return` Kanban/calendar/list/form; localization grids, internal review/approval, filing deadline and tax lock | Community model/action and return types are absent. Local review submission date is not proof of authority filing; deadline calculation and return lifecycle remain different. |
| Lock dates | Enterprise `account.change.lock.date` wizard | `flousflow.account.lock.date` with extended lock controls | Same destination intent, different wizard model. |
| Secure Entries | Enterprise `account.secure.entries.wizard` | Native Community wizard reused | Closest direct Community equivalent. |
| Loans and budgets setup | Enterprise loan/budget models and richer record views | FlousFlow-specific loan and budget models | Functional coverage is not record-level or field-level identity. |

The four Enterprise accrual models expose 74 purchase-line and 123 sale-line
fields in the remote metadata; this is the full underlying order-line model,
not a guarantee that every field appears in either list. Enterprise `account.return`
has 81 fields, `audit.report` 15, `account.asset` 85, `account.loan` 60, and
`account.loan.line` 24. Those Enterprise-only model fields cannot be copied as a
claim of Community parity; local equivalent models were inspected separately.

## Remaining differences

- Online bank feeds and provider synchronization are not implemented. Manual
  bank statements and reconciliation remain available.
- OCR bill extraction is not implemented.
- The module provides tax review and uses localization tax tags, but statutory
  declarations depend on the installed country localization.
- Multi-company consolidation and elimination entries are not claimed.
- The open-item reconciliation screen supports explicit selection and standard
  reconciliation, but does not reproduce Enterprise's automatic suggestions,
  matching-score UI, or reconciliation assistant. Standard reconciliation may
  create exchange-difference or cash-basis tax moves according to company
  settings; the addon does not create those moves itself.
- Enterprise-only tax units, horizontal report groups, and accounting checks
  do not have direct Community equivalents in this module.
- Enterprise-only configuration menus also include Tax Units, Horizontal Groups, Checks, Fiscal Categories, Depreciation Models, Return Types, and online synchronization; these models/actions are not available in the inspected local Community addon source. The local database also contains the legacy `ff_account_transfer` module, but
  its available source manifest is still `19.0.1.0.0`, so Odoo 20 skips that
  add-on. FlousFlow Accounting now supplies the transfer workflow and hides
  the legacy duplicate menu/views; the standalone legacy add-on still needs a
  separate Odoo 20 port if it must remain independently installed.

## Reconciliation accounting boundary

| Accounting event | Behavior |
|---|---|
| Trigger and source | An Accounting User selects posted, open `account.move.line` records from any reconcilable account from at least two journal entries for the same company, account, and partner, then chooses **Reconcile Selected**. |
| Debit/credit and journal | The addon does not create or edit `account.move` lines. Odoo's `account.move.line.reconcile()` links the existing debit and credit items. The native engine may create exchange-difference or cash-basis tax moves when company configuration requires them. |
| Posting date, taxes, currency, analytics | Reconciliation date, exchange handling, and cash-basis tax effects follow Odoo's standard reconciliation logic and company setup. No tax, analytic, or journal values are constructed by the addon. |
| Reversal and cancellation | Posted source entries remain unchanged. Users can undo matching through Odoo's standard unreconcile action; native reversal/cash-basis handling applies. The addon adds no separate reversal path. |
| Company and permission boundary | The action requires the Accounting User group, validates every selected line and allowed company, and partitions the native call by company/account/partner. It supports general reconcilable accounts as well as receivable/payable accounts. Existing Odoo access rules still apply. |

## Validation boundary

The Odoo 20 module upgrade and full test run completed on the local `odoo20`
database after the Accounting Reports, asset-list, and loan-view alignments:
229 tests total,
including 183 post-install tests, with zero failures and zero errors. The suite
includes Depreciation Models route/view coverage, Annual Report company
isolation, and Working Files pause/resume and direct-status-write protection.
Database checks confirmed the module is installed;
the Accounting Reports action resolves to `account.report` with list/form
views and an explicit search view. The final database check reported zero
`account_move` records, with 66 active menus owned by the module.
The live `get_views` result for its form contains the report-line expression
editor and the Community report options, grouping, and composite-section
controls. After the interactive statement, trial-balance, and general-ledger viewers were added, the focused report
suite passed 49 post-install tests with zero failures/errors. Odoo's backend JS
bundle includes the registered client action and its OWL template; the SCSS
bundle compiles with zero errors. The local browser opened to its login page,
so a live rendered-screen check of the new viewer remains outstanding.
The exact Enterprise route/action comparison and current local destinations
are in the linked parity matrix. Against 77 Enterprise action destinations, the
current matrix reports 40 same-model/view-sequence matches, 2 same-model grid
gaps, 10 technical-model differences, 15 action-type differences, 6 missing
Enterprise routes, no remaining view-sequence differences, and 1 matching
client-action tag. The route-level scope comparison has 41 exact domain/context matches and
1 difference among matching-model actions; the other 35 have no comparable
window-action scope. A separate table maps all 17 Enterprise dynamic report
actions to their local route, action, and report intent.

The full run includes the Loans Analysis Current filter, Assets view sequence,
tax-return review, Working Files, reconciliation, and Annual Report changes.
The complete `TestLoans` class then passed all 7 tests with zero failures and
errors. A live registry export confirmed the action's resolved order is
`pivot,list,form` and its context contains only `search_default_current`.

A subsequent focused Odoo test passed for the Working Files To Do/Paused
filters, action context, loaded search view, and pause/resume state restoration.

After adding tax-return deadline/submission/lock tracking and search fields,
the `TestTaxReturnReview` class passed all 6 tests with zero failures and
errors. Module upgrade and view loading also completed successfully.

A database and filestore backup were created immediately before the latest
upgrade at `work/backups/odoo20-before-fiscal-report-route-20261027.dump`
and `work/backups/odoo20-filestore-before-fiscal-report-route-20261027.tar.gz`.
The inspected Enterprise source provided 103 active menu records, 77 actions,
114 linked views, and 16 model field snapshots. This inspection was read-only
and did not retrieve accounting business records. XML/view registry loading
and the Odoo test suite were verified; browser UI rendering was not verified in
this pass. Arabic translation entries are included and syntax-checked, but the
local test database has only `en_US` active, so Arabic runtime rendering remains
unverified.
