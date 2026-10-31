# Enterprise Reporting Parity Gaps

Reviewed against the Enterprise Reporting menu and live report screens on 2026-10-31. This is an implementation register, not a completion claim.

## Verified in the local Odoo 20 database

`Cashflow Analysis` is already supplied by Odoo's `account` module. The local database has `account.action_account_cashflow_analysis` on `account.bank.statement.line`, with `graph,pivot` views, and the Reporting > Management menu entry. Keep using this native action; do not add a duplicate.

## Missing destinations

| Enterprise destination | Local state | Evidence / distinction |
| --- | --- | --- |
| Executive Summary (`/odoo/executive-summary`) | No matching route or action | The local Annual Report is a user-authored PDF document with editable sections. Its template includes a section named “Executive Summary”, but it is not the interactive report shown in Enterprise. |
| Loan Analysis (`/odoo/loans-analysis`) | No matching action, menu, or loan-analysis model | Enterprise exposes Pivot and List views with Year and Loan dimensions and Principal, Interest, and Payment measures. Local recurring payments and cash forecasting do not provide loan schedules or this analysis. |

## Executive Summary screen contract observed

The screen has Print, date/fiscal-year selection, Comparison, target moves/accrual basis, currency, and a settings control. It groups rows into Cash, Profitability, Balance Sheet, Performance, and Operational indicators. Information popovers expose the following calculations:

- Cash earnings and amount spent filter `account.move.line` by cash or credit-card account type and positive debit or credit respectively; cash surplus aggregates those two rows; bank closing balance uses the cash/credit-card account types.
- Revenue, cost of revenue, gross profit, expenses, and net profit use codes `REV`, `COS`, `GRP`, `EXP`, and `NEP` from the Enterprise Profit and Loss report.
- Net assets use `TA.balance - L.balance` from the Enterprise Balance Sheet report.
- Gross margin is gross profit divided by operating income; net margin is net profit divided by revenue; ROI is net profit divided by assets. The report uses an `ignore_zero_division` subformula.
- Debtor days use `DEB.balance / REV.balance * NDays`; creditor days use `-CRE.balance / (COS.balance + EXP.balance) * NDays`. The observed `NDays` Python engine returned 365.
- Short-term cash forecast uses `DEB.balance + CRE.balance`; current ratio uses `CA.balance / CL.balance` with zero-division protection.

The local source does not contain the Enterprise `account_reports` report definitions referenced by these formulas. The existing local financial-report engine is based on `account.financial.report`; reuse its company/date/posted-entry handling if implementing an equivalent, and verify each row against the source report before release. Do not relabel the manual Annual Report as Executive Summary.

## Next implementation work

1. Implement the interactive Executive Summary using the existing local report engine and the observed formulas, with company, date, target-move, currency, and comparison behavior covered by tests.
2. Locate an existing Odoo 20 loan-analysis source component before deciding whether the Loan Analysis destination can be merged or needs a separately designed equivalent. Do not present recurring payment lines as loan analytics.
3. Compare rendered local screens with Enterprise at desktop and narrow widths after authentication is available in the local browser.
