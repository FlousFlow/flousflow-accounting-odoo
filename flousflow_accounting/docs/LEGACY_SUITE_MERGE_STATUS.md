# Legacy Accounting Suite Merge Status

The Odoo 20 branch publishes one standalone addon: `flousflow_accounting`.
The former `flousflow-om-account-accountant-odoo20` repository contains 21
separately installable addons. The feature names below are mapped to the
FlousFlow implementation; a similar feature label does not mean its data model
or every workflow is identical.

| Legacy addon | Current FlousFlow status |
|---|---|
| `om_account_accountant` | No separate legacy root is included. The standalone dashboard, financial reports, payment, and review workflows are implemented in FlousFlow models and views. |
| `accounting_pdf_reports` | FlousFlow has its own PDF and XLSX financial report engine; legacy report templates and layouts are not copied. |
| `om_account_asset` | FlousFlow asset and deferral models are implemented independently; legacy model and record compatibility is not claimed. |
| `om_account_budget` | FlousFlow financial and analytic budgets are implemented independently. |
| `om_fiscal_year` | FlousFlow fiscal-year and lock-date workflows are implemented independently. |
| `om_recurring_payments` | FlousFlow recurring payments are implemented independently using standard Odoo payments. |
| `om_account_followup` | FlousFlow collection levels, reminders, letters, and history are implemented independently. |
| `om_account_reconcile` | FlousFlow provides explicit open-item reconciliation through Odoo's reconciliation engine; legacy automatic matching UI is not included. |
| `om_currency_rate_update` | Not merged. Automatic rate providers and scheduled rate updates are absent. |
| `om_account_daily_reports` | Not merged. Dedicated Cash Book, Day Book, and Bank Book reports are absent. |
| `om_account_cash_forecast` | Not merged. Weekly/monthly forecast modeling and manual expected cash items are absent. |
| `om_account_check_printing` | Not merged. Configurable cheque layouts and calibration printing are absent. |
| `om_currency_revaluation` | FlousFlow has its own revaluation wizard and reversal workflow. |
| `om_account_bank_statement_import` | Not merged. The extra CAMT/MT940/OFX/QIF/CSV/Excel import mappings are absent. Native Odoo statement import remains separate. |
| `om_account_bill_ocr` | Not merged. Vendor bill OCR/extraction is absent. |
| `om_spreadsheet_account` | Not merged. Odoo Spreadsheet accounting dashboards are absent. |
| `om_spreadsheet_account_asset` | Not merged. Spreadsheet asset dashboards are absent. |
| `om_spreadsheet_account_budget` | Not merged. Spreadsheet budget dashboards are absent. |
| `om_spreadsheet_account_followup` | Not merged. Spreadsheet follow-up/cash dashboards are absent. |
| `ff_account_transfer` | Internal transfers are implemented natively in `flousflow_accounting`; the separate OPL-1 addon is not copied into this LGPL-3 addon. |
| `flousflow_branch_analytic` | Integrated into `flousflow_accounting`: branch account fields on POS configuration and customer invoices, sale-line propagation using Odoo's native sale-order analytic field, optional per-company enforcement, and POS revenue/COGS propagation. |

The independently implemented rows above represent workflow coverage, not a
code merge or a guarantee of identical fields, views, stored records, or user
experience. The rows marked **Not merged** are outstanding work. They should
be implemented and verified inside this addon before describing the legacy
suite's full feature set as included.
