Accounting Suite for Odoo 20 Community
======================================

The suite adds accounting reports, reconciliation, cash-management tools,
assets, budgets, customer follow-up, currency tools, and dashboards to Odoo 20
Community Edition.

Installation
============

Add this repository and the standard Odoo 20 Community addon paths to
``addons_path``, restart Odoo, update the Apps list, then install
``om_account_accountant``.

Requirements
============

* Odoo 20.0 Community Edition.
* An Odoo-compatible ``wkhtmltopdf`` build with patched Qt for on-premise PDF
  rendering.
* Tesseract and Poppler on the Odoo host for local vendor-bill OCR.

Licensing
=========

Each addon has its own license in its manifest. The root suite is LGPL-3;
``ff_account_transfer`` is OPL-1. Preserve upstream attribution notices when
redistributing components.
