# Odoo 20 Engineering Log

## 2026-11-25 — Salesperson commission plans and runs

- Module/version: `flousflow_accounting` 20.0.1.0.77.
- Requirement: configurable sales-first or combined sales/collection commission methods; user-selected date range; net sales after credit notes; payout on collected amount excluding VAT.
- Evidence: Odoo 20 account move exposes stored `invoice_user_id`, `amount_untaxed_signed`, and `amount_total_signed`; payment reconciliation exposes `account.partial.reconcile` debit/credit lines, `amount`, `max_date`, and payment/bank-statement origin fields.
- Design: added plan targets per salesperson, configurable thresholds, a reviewable commission run with source documents, and a standard `account.move` journal entry using configured company accounts and journal.
- Guardrails: company-scoped access, portal salesperson rejection, accounting-manager posting, immutable posted runs, and an advisory lock plus overlapping-period check against double payment.
- Data scope: posted customer invoices and credit notes; inbound Odoo payments and posted bank-statement transactions reconciled against customer invoice receivables. VAT exclusion is proportional to the invoice untaxed-to-total ratio.
- Boundaries: POS orders without invoice salesperson attribution are excluded. No automated tests or live database upgrade were run in this implementation turn.
- Upgrade follow-up: the first staging upgrade exposed a CSV header mismatch (`model_id` instead of Odoo 20's `model_id/id`) before applying the module update. Corrected the access CSV and removed unsupported One2many ordering metadata; staging DB remained at 20.0.1.0.74 and the service recovered.
- Upgrade follow-up: the next staging pass loaded access and sequence data, then rejected legacy search-group attributes. Removed those attributes and assigned the informational alert an appropriate accessibility role; staging DB remained unchanged and service recovered.
