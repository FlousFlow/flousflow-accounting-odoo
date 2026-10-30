# FlousFlow Accounting for Odoo 20

This is one installable Odoo addon containing the source code of the 21 accounting addons listed in `SOURCE_LICENSES.md`. The original Python, XML, report, security, static asset, demo, and test files are retained under `legacy/<source addon>/`; they are loaded through the single `flousflow_accounting` addon. The merge adapts addon paths and XML IDs to avoid collisions while preserving the original implementations.

## Installation

1. Place `flousflow_accounting` on the Odoo 20 addons path.
2. Install the Python dependency `pypdf`.
3. Install the `FlousFlow Accounting` app from Apps or with `-i flousflow_accounting`.

The spreadsheet dashboard features depend on Odoo Enterprise's `spreadsheet_dashboard_account` addon. This package is therefore not installable on a pure Community server with those features included.

## Source and licensing

See `SOURCE_LICENSES.md` for the source component list and original licenses. Original copyright and license headers are preserved in the source files. The consolidated package uses OPL-1 because it includes the OPL-1 `ff_account_transfer` component; this does not relicense source files that retain LGPL-3 notices.
