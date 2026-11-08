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
