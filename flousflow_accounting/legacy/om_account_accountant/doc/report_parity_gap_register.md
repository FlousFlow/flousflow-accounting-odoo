# Enterprise Reporting Parity Gaps

Reviewed against the Enterprise Reporting menu and live report screens on 2026-10-31. This is an implementation register, not a completion claim.

## Verified in the local Odoo 20 database

`Cashflow Analysis` is already supplied by Odoo's `account` module. The local database has `account.action_account_cashflow_analysis` on `account.bank.statement.line`, with `graph,pivot` views, and the Reporting > Management menu entry. Keep using this native action; do not add a duplicate.

## Report destinations and gaps

| Enterprise destination | Local state | Evidence / distinction |
| --- | --- | --- |
| Customer Statement (`/odoo/customer-statement`) | Available locally as `apr__action_interactive_customer_statement` | Date, account scope, partner, posted-entry, currency-scale, print and send flows are present. Arabic labels now resolve in the web client; the empty-state total is hidden and the table fits an 890px viewport. The local database currently has zero `account.move` records, while Enterprise FY 2026 shows Gemini Furniture and Ready Mat totaling -$10,031.50. Populated-screen parity cannot be confirmed until the local comparison database has accounting entries. Backend tests cover filters, signs, access, PDF and e-mail actions. |
| Executive Summary (`/odoo/executive-summary`) | Implemented as `apr__action_executive_summary` over the existing financial-report engine | Includes Cash, Profitability, Balance Sheet, Performance, and Operational groups; date range, posted/all moves, accrual/cash basis, comparison with the previous period, and reporting-currency conversion. Backend tests cover posted values, zero denominators, the fixed 365-day formula, currency conversion, invalid dates, and unknown currencies. A headless browser tour covers KPI groups and comparison. Live visual parity against the Enterprise page is still unverified. |
| Loans (`/odoo/loans`) and Loan Analysis (`/odoo/loans-analysis`) | Implemented in `ff_account_loans`: loan form/list/kanban, editable/importable/calculable amortization schedule, accounting settings, auto-post payment/reclassification moves, and Pivot/Graph/List analysis | Follows Odoo's documented schedule and accounting-entry flow. Verify on the populated local database, run the loan transaction tests, and compare the visible form and analysis against Enterprise before claiming full parity. |

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

1. Compare the rendered Executive Summary against the Enterprise screen at desktop and narrow widths, then close remaining presentation and filter gaps (including its settings controls and comparison modes).
2. Compare the new loan form, imported/manual/generated schedules, confirmation and early-close flow, and Loan Analysis dimensions/measures against Enterprise. The local implementation follows the published Odoo loan accounting contract; it is not copied Enterprise source.
3. Repeat the Customer Statement comparison with populated local accounting data, including expanded lines and print/send output.
4. Continue the broader Enterprise-vs-local screen/action audit; this register is a focused report audit, not proof that every Accounting screen is at parity.
