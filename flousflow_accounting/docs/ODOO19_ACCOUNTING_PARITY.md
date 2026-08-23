# Odoo 19 Accounting Parity Workbench

This document records clean-room behavioral comparison against an authorized
Odoo 19 SaaS database. It contains no Enterprise source code.

## Reference snapshot

- Reference edition: Odoo SaaS 19, `account` 19.0.1.4 and `accountant` 19.0.1.1.
- Inspection method: authenticated read-only JSON-2 metadata and aggregate
  queries. No reference records were created, changed, or deleted.
- Installed asset population at the snapshot: 80 running assets, all using
  straight-line depreciation with constant periods.

## Side-by-side scenarios

| Scenario | Odoo 19 SaaS reference | FlousFlow result | Automated proof |
|---|---|---|---|
| Accounting navigation | Dashboard, Customers, Vendors, Accounting, Review, Reporting, Configuration | Same primary navigation and aligned Assets & Liabilities / Review / Configuration placement | XML upgrade plus browser smoke |
| Asset list | Assets action excludes models and child assets | Asset action is restricted to fixed assets | action/view test |
| Asset models | Separate Asset Models action | Asset Models backed by reusable category/template records | model-default test |
| Asset groups | Hierarchical company-owned groups | Hierarchical company-owned groups with parent-company constraint | security and model test |
| Methods | Straight Line, Declining, Declining then Straight Line | All three methods | depreciation engine test |
| Prorata | None, Constant Periods, Based on Days per Period | Same three choices; legacy boolean remains migration-compatible | daily-prorata test |
| Analytic allocation | Asset exposes analytic distribution | Analytic distribution is copied from the source bill line and applied to the depreciation expense line | ORM field/entry assertions |
| Depreciation schedule | Review > Inventory > Depreciation Schedule | List, pivot, and graph schedule views | action/view test |
| Posted history | Posted depreciation entries remain auditable | Posted entries are never deleted; modifications rebuild future lines only | modification/reversal tests |
| Disposal | Asset disposal and sale workflow | Full/partial disposal, invoice-backed sale, gain/loss and reversal | disposal tests |
| Loans | Loan contracts, amortization and loan analysis | Annuity, fixed-principal and interest-only schedules; disbursement, installment posting, reversals and analysis views | schedule/accounting/cancellation tests |
| Audit working files | Evidence, ownership, review and approval | Company-isolated working files with attachments, linked entries, immutable approval and chatter | workflow/security tests |
| Purchase/Sales accrual review | Goods received not billed and goods delivered not invoiced | Date-based logistics-versus-invoice review with source drill-down and company-currency valuation | receipt-without-bill test |
| Period closing | Lock dates plus review controls | Month/quarter/year checklist, evidence links, draft-entry gate, assigned manager approval and standard soft/hard lock application. Approval and close both reject managers outside the close company. | workflow/permission/immutability tests |
| Interactive reporting | Filtering, comparison, folding, saved filters, drill-down and exports | Standard month/quarter/year/custom periods, previous-period/year comparison, expanded/collapsed details, private reusable filters with a management screen, posted/all entries, journal/account/partner filters, journal-item drill-down, PDF and XLSX. Presets are enforced as personal records at ORM level, including API/import paths. | report engine, preset, security and display-mode tests |
| Report review annotations | Report notes, comparison columns and fold/unfold review controls | Persistent wizard notes printed in PDF/XLSX, comparison amount, variance and variance percentage, plus explicit Fold All / Unfold All actions | report annotation and comparison tests |
| Report navigation | Each report opens and refreshes in its matching report surface | Every report action has an explicit form view; customer/vendor statements retain the dedicated statement view after refresh | action/view regression tests |
| General ledger | Account opening, dated journal-item detail, running balance and account total | Same server-driven detail with entry/reference/partner/journal/currency drill-down in UI, PDF and XLSX | detailed ledger and filter tests |
| Partner ledger | Partner opening, receivable/payable journal-item details, running and closing balances | Same detailed partner ledger with entry/account/journal/currency drill-down in UI, PDF and XLSX | opening/detail/total ledger test |
| Cash flow | Opening cash, operating/investing/financing movements, net change and closing cash | Same reconciled cash bridge using posted cash-account movements; standard cash-flow account tags take precedence over account-type fallback | cash-flow tag classification and balance tests |
| Tax report | Tax amount with taxable base and journal-item drill-down | Tax-grouped base, debit, credit and net tax with PDF/UI output and drill-down | posted invoice tax-base test |
| Manual bank statements | Available from Accounting without requiring an online provider | Standard Community bank-statement action promoted under Accounting; online feeds remain excluded | navigation/action test |
| Manual bank reconciliation | Suggested customer/vendor matches, partial and multi-document allocation, undo | Original server-driven workbench over standard statement lines and `reconcile()`; deterministic matching, stale-data checks, company isolation, manager-only undo | exact/partial/vendor/multi-invoice/undo/security tests |
| Community independence | Proprietary report client is optional to the accounting business flow | No `account_reports`, `account_accountant`, or `web_enterprise` dependency/import; all report menus use original FlousFlow window actions | manifest/source/menu independence gate |
| Country localization | Company country selects its standard Odoo localization and tax setup | Every unconfigured company uses the visible country template when available (for example `l10n_eg`), otherwise the neutral FlousFlow chart; branches retain the parent chart and existing accounting is never replaced | template-selection tests plus isolated Egyptian-company creation gate |
| Tax return review | Localization grids, review and tax-period closing | Posted localization tax tags are snapshotted, draft tax entries block review, manager approval is separated, and closing applies the standard tax lock without fabricating statutory forms or journal entries | tax-grid, draft-gate, immutability and lock-date tests |
| Promise to pay | Collection commitment history and outcomes | Company-isolated promises linked optionally to an open receivable, with responsible collector and kept/broken/cancelled audit trail; no ledger mutation | lifecycle, validation and no-entry tests |
| Point of Sale accounting | Closed sessions post standard journal entries; open sessions are not final accounting | Built into the single FlousFlow Accounting application: period close blocks unposted sessions and the General Ledger reads the standard POS entry without duplicate posting | POS session/ledger, single-menu and period-close tests |
| Standard app integration | Expenses, inventory, manufacturing, POS and projects feed the standard accounting and analytic ledgers | Single installable accounting application depends on the official integration modules and reads their posted `account.move` / analytic output once, without parallel posting | dependency, link-field, single-menu and no-duplicate-ledger tests |
| Payment batches | Group standard payments with preparation and manager approval before posting | Company/journal/currency/direction validation, submit/approve/post separation, manager-only posting, standard `account.payment.action_post()` and no parallel journal entry | payment-batch workflow, permission and accounting-path tests |

## Remaining intentional or configuration-dependent differences

| Area | Current status | Reason / next boundary |
|---|---|---|
| Online bank feeds | Excluded | Explicit project boundary; manual bank statements and reconciliation models remain available |
| Proprietary report client | Not required | Original server-driven FlousFlow UI provides business results, filters, exports and drill-down without copying or loading proprietary client code |
| Country tax grids and statutory declarations | Localization-dependent | Install and configure the matching standard `l10n_*` module; the generic chart cannot claim country-specific statutory parity |
| Multi-company consolidation | Not claimed | Per-company reports are isolated and accurate; elimination entries and consolidation mappings require a separate controlled design |

## Explicit integration boundary

Online bank synchronization is intentionally excluded. The module does not
store provider credentials, call aggregation APIs, or claim live bank feeds.

OCR is an external extraction service rather than an accounting calculation.
Evidence ingestion and document attachments are handled by Audit Working Files;
automatic OCR requires a separately selected provider and credentials. No fake
OCR result or hidden external dependency is presented as complete.

The report UI is an original server-driven implementation. It covers the
business outcomes above, but does not copy Enterprise web-client source code.
