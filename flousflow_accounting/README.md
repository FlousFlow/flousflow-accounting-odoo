# FlousFlow Accounting for Odoo 20

This is one installable Odoo addon containing the source code of the 21 accounting addons listed in `SOURCE_LICENSES.md`. The original Python, XML, report, security, static asset, demo, and test files are retained under `legacy/<source addon>/`; they are loaded through the single `flousflow_accounting` addon. The merge adapts addon paths and XML IDs to avoid collisions while preserving the original implementations.

## Installation

1. Place `flousflow_accounting` on the Odoo 20 addons path.
2. Install the Python dependency `pypdf`.
3. Install the `FlousFlow Accounting` app from Apps or with `-i flousflow_accounting`.

The spreadsheet dashboard features depend on Odoo Enterprise's `spreadsheet_dashboard_account` addon. This package is therefore not installable on a pure Community server with those features included.

## Salesperson commissions

Accounting managers configure commission plans under **Accounting → Reporting → Sales Commissions → Commission Plans**. A plan contains the company, calculation method, minimum achievement, per-salesperson net-sales and collection targets, achievement tiers, general journal, expense account, and payable account.

Accountants create a **Commission Run**, select a plan and any date range, calculate, and review the salesperson results and linked source documents. An accounting manager posts the run through Odoo's standard journal entry workflow.

- Sales are posted customer invoices less posted customer credit notes, using Odoo's invoice salesperson and company-currency untaxed signed amounts.
- Collections are inbound payments or bank statement transactions reconciled to posted customer invoice receivables during the selected period. Credit notes, write-offs, exchange differences, and manual journal entries do not count as cash collections.
- The VAT-inclusive collection value is used for achievement calculations. The commission base excludes VAT by allocating each matched collection to the invoice's untaxed/total ratio.
- The sales-first method checks net sales against the minimum and selects the rate tier by collection achievement. The combined method selects eligibility and tier from net sales plus VAT-inclusive collections against combined targets. The selected rate applies to actual collections excluding VAT.
- Posted runs are locked and overlapping posted periods for the same salesperson are blocked to prevent paying the same commission twice.

Point-of-sale orders without an Odoo customer invoice and salesperson attribution are not included in this first version.

## Source and licensing

See `SOURCE_LICENSES.md` for the source component list and original licenses. Original copyright and license headers are preserved in the source files. The consolidated package uses OPL-1 because it includes the OPL-1 `ff_account_transfer` component; this does not relicense source files that retain LGPL-3 notices.
