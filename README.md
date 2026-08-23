# FlousFlow Accounting for Odoo 19

A complete, self-contained accounting suite for **Odoo 19 Community**, built on
the standard `account` module. All features are original Community code.

## Module: `flousflow_accounting`

The module lives in the [`flousflow_accounting/`](flousflow_accounting/) folder —
add this repository to your `addons_path` and it works directly.

### Features

* **Chart of accounts** — country-based chart/tax auto-load using the standard
  `account.chart.template` engine (`flous_generic_coa` fallback, `l10n_eg`
  support out of the box).
* **Financial reports** — Profit & Loss, Balance Sheet, Trial Balance, Cash
  Flow, General/Partner Ledgers, Customer/Vendor/Account Statements, Executive
  Summary, Aged Receivable/Payable, Tax & Journal Audit — with drill-down,
  filters, PDF and XLSX export.
* **Internal transfers** — paired bank ↔ cash transfers with automatic
  counterpart payment and safe cancellation.
* **Multicurrency revaluation** — revaluation wizard with posted gain/loss
  entries and reversal.
* **Assets & depreciation** — models, groups, straight-line/declining/hybrid
  depreciation, prorata, deferred expenses/revenues, disposals and reversals.
* **Budgets** — financial and analytic budget lines, approval states, planned
  vs actual vs theoretical with overrun detection.
* **Follow-up** — collection levels, overdue report, scheduled reminders and
  printable letters.
* **Fiscal years & lock dates** — fiscal periods plus fiscal/tax/sales/
  purchase/hard lock dates.
* **Recurring payments** — scoped, idempotent schedules with a concurrency-safe
  cron that posts standard Odoo payments.
* **Payment batches & promises** — batch vendor payments with approval flow and
  "promise to pay" tracking.
* **Bank reconciliation** — guided manual reconciliation workbench.
* **Tax returns & VAT review** — tax return review and audit working files.
* **Loans** — annuity/fixed-principal/interest-only schedules.
* **Accrual review** — goods received not billed / delivered not invoiced.
* **Period closing** — month/quarter/year close checklist with approval and
  controlled lock-date application.
* **Dashboard** — bank/cash, receivable, payable, YTD P&L and counters.

### Install

```bash
odoo -i flousflow_accounting -d <db> --stop-after-init
```

The chart of accounts loads automatically based on the company's country.

### Documentation

* [`flousflow_accounting/README.md`](flousflow_accounting/README.md) — full
  feature and behaviour reference.
* [`flousflow_accounting/docs/ODOO19_ACCOUNTING_PARITY.md`](flousflow_accounting/docs/ODOO19_ACCOUNTING_PARITY.md)
  — Odoo 19 parity workbench and verified scenario matrix.

## License

LGPL-3. Author: Flous Flow — https://flousflow.com
