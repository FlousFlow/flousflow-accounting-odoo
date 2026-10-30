Accounting Suite for Odoo 20 Community
======================================

Install the suite to add accounting reports and workflows to Odoo 20 Community.
It combines financial statements, ledgers, reconciliation, cash management,
assets, budgets, follow-up, currency tools, and accounting dashboards.

Requirements
============

* Odoo 20.0 Community Edition.
* This repository and the standard Odoo 20 addons in ``addons_path``.
* For on-premise PDF rendering, an Odoo-compatible ``wkhtmltopdf`` build with
  patched Qt.
* For vendor-bill OCR, Tesseract and Poppler installed on the Odoo host.

Installation
============

1. Add this repository and Odoo 20's standard addon paths to ``addons_path``.
2. Restart Odoo and update the Apps list.
3. Install **Accounting Suite** (technical name ``om_account_accountant``).

The root addon installs its accounting dependencies from this repository and
standard Odoo 20.0 Community addons. A clean installation was verified on Odoo
20.0; see the repository README for the verification database name.

Included workflows
==================

* Financial statements, ledgers, aged balances, tax reports, open items, and
  customer or supplier statements.
* Bank and cash reconciliation, statement imports, internal transfers, and
  daily accounting books.
* Assets and depreciation, budgets, recurring entries, and fiscal-year controls.
* Customer follow-up, cash forecasting, currency updates, and revaluation.
* Vendor-bill data extraction, accounting dashboards, and working-file review.

Data handling
=============

Vendor-bill OCR processes documents on the Odoo host. Currency-rate updates
contact the provider selected by the administrator when configured.

Licensing and attribution
=========================

The root addon is LGPL-3. The original accounting suite and several included
components contain work by Odoo Mates and Odoo S.A.; their attributions and
license notices are retained. FlousFlow maintains this Odoo 20 suite. Addons in
this repository have separate manifests and licenses. In particular,
``ff_account_transfer`` is OPL-1. Review the license of each component before
redistributing or modifying it.

Support
=======

Contact ``support@flousflow.com``.
