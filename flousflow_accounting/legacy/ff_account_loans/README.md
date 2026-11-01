# Loans

This is the FlousFlow Accounting implementation of Odoo's loan workflow, using the current module's license and Odoo 20 APIs.

## User flow

1. Create a loan and enter the principal, total interest, loan date, duration in months, and optional asset group.
2. Build the amortization schedule with **Compute**, import a UTF-8 CSV, or add schedule lines manually. CSV columns are `date,principal,interest`, with ISO dates (`YYYY-MM-DD`).
3. Configure long-term, short-term, and interest expense accounts, the journal, analytic distribution, and optional transfer date.
4. **Confirm** validates the totals and creates future auto-post entries for each payment and short-term reclassification. Odoo's auto-post scheduler posts them on their accounting dates.
5. Use **Close** to close at a date; future posted moves are reversed and future drafts are removed. **Cancel** reverses posted accounting effects and removes generated drafts while retaining the schedule and audit trail.

## Accounting entries

- Installment: debit principal to the short-term account, debit interest to the expense account, credit total payment to the short-term account.
- Current portion: debit the next 12 months of principal to long-term and credit the same amount to short-term; the reversal is scheduled for the next day.
- Analytic distribution is applied to all generated lines. Entries use the loan company, journal, date, and company currency.

## Scope

- The generated schedule uses equal principal and distributes the entered total interest evenly across installments. Imported and manual schedules can use each lender's exact amounts.
- The upload action currently accepts UTF-8 CSV only.
- The feature does not post the initial bank receipt. Record the bank receipt in Odoo's bank journal and transfer the proceeds to the configured long-term liability account as part of the normal accounting workflow.
