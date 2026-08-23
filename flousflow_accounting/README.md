# FlousFlow Accounting

A complete, self-contained Flous Flow accounting suite. The chart of accounts
and taxes load automatically based on the **company's country**, using the
standard `account.chart.template` engine — exactly like standard Odoo.

## Features

| Area | What it provides |
|---|---|
| Chart of accounts | Country-based chart/tax auto-load (`flous_generic_coa` fallback) |
| Financial reports | P&L, cumulative Balance Sheet with fiscal-year earnings, Trial Balance with opening/closing, Cash Flow, General/Partner Ledgers, detailed Customer/Vendor/Account Statements with opening and running balances, Executive Summary, historically accurate Aged Receivable/Payable, Tax and Journal Audit, period comparison, journal/account/partner and entry-state filters, drill-down, PDF and XLSX export |
| Assets & deferrals | Asset models and hierarchical groups, straight-line/declining/hybrid depreciation, constant-period or daily prorata, analytic distribution, manual or automatic creation from posted vendor-bill lines, deferred expenses/revenues, multi-currency posting, auditable modifications, partial/full disposal, sale and disposal reversal, plus list/pivot/graph depreciation schedules |
| Budgets | Company-isolated financial and analytic budget lines, controlled approval states, period boundaries, planned vs actual vs theoretical and sign-aware overrun detection |
| Follow-up | Configurable collection levels, actual overdue residual, overdue partners report, manual or opt-in scheduled reminder processing, repeat intervals, printable letters, immutable processing history and responsible-user activities |
| Fiscal years & locks | Fiscal years plus standard fiscal, tax, sales, purchase and hard lock dates |
| Recurring payments | Scoped, idempotent schedules plus a concurrency-safe daily cron that creates and posts standard Odoo payments with live payment states |
| Payment batches | Groups draft standard payments by company, journal, currency and direction; separates accountant submission from manager approval and posts only through the standard payment flow |
| Internal transfers | Paired bank↔cash transfers: one action creates the two standard Odoo payments linked through `paired_internal_transfer_payment_id`, with automatic destination account, safe cancellation of both legs and a one-click shortcut on every bank/cash journal dashboard |
| Revaluation | Multicurrency revaluation wizard: computes and posts unrealized gain/loss entries per currency and period and creates reversal entries when requested |
| Loans | Annuity, fixed-principal and interest-only schedules; disbursement, principal/interest posting, multi-currency amounts, reversals and pivot/graph analysis |
| Audit working files | Evidence attachments, linked accounts and entries, owners/reviewers, chatter and immutable manager approval |
| Accrual review | Goods received not billed and goods delivered not invoiced, valued in company currency with source-order drill-down |
| Period closing | Month/quarter/year close checklist, draft-entry gate, reviewer approval, audit evidence and controlled application of standard Odoo lock dates |
| Dashboard | Bank/cash, receivable, payable, YTD P&L and open/overdue counters |

All features are original Community code. The logistics accrual review uses the
standard `purchase_stock`, `sale_stock` and `stock_account` modules. Online bank
synchronization is intentionally excluded.

## How the chart behaves

| Scenario | What happens |
|---|---|
| Fresh install, company has a country with a localization template | The country chart/taxes load automatically (e.g. Odoo `l10n_*` or a Flous localization) |
| Fresh install, no country / no country localization | The **FlousFlow generic chart** (`flous_generic_coa`) loads |
| Existing database with a chart already configured | Nothing is touched (chart_template is respected) |

## What the generic chart ships

* `flous_generic_coa` — neutral chart of accounts:
  * 46 accounts (receivable, payable, income, expense, fixed assets, equity…)
  * standard journals (Sales INV, Purchases BILL, Misc MISC, Bank…)
  * 15% sale/purchase taxes + 0% exports/imports taxes
  * Domestic & Foreign Trade fiscal positions
* Country-independent by design (no forced fiscal country — the company's own
  country drives behavior).

## Install

```bash
docker exec odoo_clean_web odoo --db_host=db --db_user=odoo --db_password=odoo \
  -i flousflow_accounting -d <db> --stop-after-init
```

After install, the chart can be changed anytime in
**Settings → Accounting → Chart of Accounts** (standard flow).

## Manual bank reconciliation

Use **Accounting → Accounting → Bank Reconciliation** or select a transaction
from **Bank Statements** and run **Reconcile Bank Transaction** from Actions.
The workbench ranks posted open entries by company, partner, reference, amount,
and date, and supports customer receipts, vendor payments, partial payments,
and one transaction matched against multiple invoices. Validation delegates to
Odoo's standard `account.move.line.reconcile()` engine; no parallel ledger is
created. Only Accounting Managers can undo a completed match. Online bank feeds
and bank credential storage remain intentionally excluded.

## Tax return review and collections

**Reporting → Tax Return Reviews** snapshots posted localization tax tags for a
company and period, blocks submission while tax entries remain in draft,
separates preparation from manager approval, and applies only Odoo's standard
tax lock date when closed. It never invents statutory grids for an unsupported
country and never creates a tax closing journal entry.

**Follow-up → Promises to Pay** records customer commitments with amount, due
date, responsible collector, optional open receivable item, and kept/broken/
cancelled outcomes. A promise is collection evidence, not a payment; only the
standard `account.payment` flow affects the ledger.

## Egyptian companies

Egypt works out of the box through the standard Odoo Egyptian localization:

```bash
docker exec odoo_clean_web odoo --db_host=db --db_user=odoo --db_password=odoo \
  -i l10n_eg -d <db> --stop-after-init
```

When `l10n_eg` is installed, the `post_init_hook` loads the Egyptian chart of
accounts and taxes (14% VAT, zero rated, exempt, stamp tax, schedule taxes,
withholding taxes, ETA codes and the VAT return report) automatically for a
company whose country is Egypt. `l10n_eg` also auto-installs on `account` when
the company country is Egypt.

## Adding a country localization

Two ways, both using the standard Odoo mechanism:

1. **Reuse an Odoo localization** — install the matching `l10n_*` module; the
   `post_init_hook` picks it automatically by country.
2. **Ship a Flous localization** — create a `template_flous_<cc>.py` with
   `@template('flous_<cc>', ...)` functions (note the `template_` file prefix,
   which Odoo requires for discovery) and the CSVs under
   `data/template/account.*-flous_<cc>.csv`.

## Tests

```bash
docker exec odoo_clean_web odoo --db_host=db --db_user=odoo --db_password=odoo \
  --test-enable -u flousflow_accounting -d test --stop-after-init
```

## Internal transfers

**Accounting → Accounting → Internal Transfers** lists every transfer with its
journal, payment method, partner, amount and status. To move money between a bank
and a cash journal: open the **Bank** or **Cash** journal dashboard and click
**Internal Transfer** (or create a payment with the **Internal Transfer** flag),
choose the destination journal and post. The module automatically creates the
paired receiving payment with the opposite direction and links both through the
standard Odoo `paired_internal_transfer_payment_id` field, so cancelling or
resetting either leg keeps both in sync. The transfer uses the company's
configured transfer account.

## Notes

* Existing companies with a configured chart are never overwritten.
* Posted recognition is never deleted on cancellation. The module creates and
  links a posted reversal entry so the accounting audit trail remains intact.
* Foreign-currency disposal uses the historical company-currency acquisition
  value. Asset sales use a posted customer-invoice line on the configured
  clearing account; taxes and customer reconciliation therefore remain in the
  standard Odoo invoice flow. Reversing a disposal does not cancel that invoice.
* Asset schedule modifications preserve posted depreciation entries and rebuild
  only future lines. Partial disposals proportionally reduce gross and salvage
  values and retain a separate reversible disposal-history record.
* The parity workbench and verified reference/local scenario matrix are tracked
  in `docs/ODOO19_ACCOUNTING_PARITY.md`.
* Period closing does not create accounting entries. It verifies that required
  review tasks are signed off and no draft entries remain, then applies Odoo's
  standard fiscal, tax, sales and purchase lock dates. Hard lock is optional
  and deliberately requires an Accounting Manager.
* This is a clean-room implementation built on public Odoo Community APIs. It
  does not contain or redistribute Odoo Enterprise proprietary source code.
* An automated Community-independence gate rejects proprietary module
  dependencies/imports and verifies that every accounting report menu opens an
  original FlousFlow window action. This protects future upgrades from silently
  reintroducing an Enterprise client dependency.
* Bank matching is revalidated at confirmation time. Reconciled, draft,
  cross-company, stale, or over-allocated candidates are rejected before any
  accounting mutation.
