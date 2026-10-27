# FlousFlow Community Accounting

This addon is the FlousFlow-branded distribution layer for the standard Odoo
20 Community `account` module.

The upstream technical name remains `account` deliberately. Renaming that
technical module would break Odoo's native dependencies, XML IDs, migrations,
and integrations. Install `account` first; this addon declares it as a
dependency and provides the FlousFlow product identity for future extensions.

The clean Community baseline was verified in database
`ff_accounting_community20_tmp` with Odoo 20 and `account` version `20.0.1.5`.
