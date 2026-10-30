# FlousFlow Accounting for Odoo 20

This repository packages the 21 accounting addons from the FlousFlow 20.0 source suite as one Apps-installable addon: `flousflow_accounting`.

The source implementations remain under `flousflow_accounting/legacy/<source_addon>/`. Consolidation changes the Odoo addon topology, resource paths, and XML IDs so the source components can load together under one technical module name. It does not reimplement their business features. See the addon's `SOURCE_LICENSES.md` for the component-by-component license list and `flousflow_accounting/README.md` for installation notes.

## Odoo 20 requirements

- Odoo 20 with the listed dependencies in the module manifest.
- Python package `pypdf`.
- Odoo Enterprise's `spreadsheet_dashboard_account` addon for spreadsheet dashboards. This full package is not compatible with a pure Community installation while those components are included.

Add this repository to `addons_path`, refresh Apps, and install **FlousFlow Accounting**.
