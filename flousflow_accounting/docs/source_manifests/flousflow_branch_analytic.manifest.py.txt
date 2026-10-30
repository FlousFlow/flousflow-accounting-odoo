{
    'name': 'Branch Analytics',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'sequence': 10,
    'summary': 'Track branch / profit-center P&L by assigning an analytic account to POS, sales orders and customer invoices.',
    'description': """
Branch Analytic Accounting
==========================

Turn Odoo **Analytic Accounting** into a branch / profit-center tracking system.

Assign a single branch (analytic account) to a Point of Sale configuration, a
sales order or a customer invoice, and Odoo automatically posts the revenue and
the cost of goods sold (COGS) onto that same branch, so the Accounting -> Reports
analytic P&L shows Revenue - COGS = Gross Profit per branch.

Only P&L lines are tagged. Receivable, cash, bank, tax and stock-valuation
(balance-sheet) lines are never polluted.

Key features
============

* **Point of Sale** — new *Analytic Account* field on each POS configuration.
* **POS session closing** — sales, refunds, COGS and COGS reversals automatically
  receive the POS analytic account. Balance-sheet lines are left untouched.
* **Customer invoices & credit notes** — new *Analytic Account* header that is
  propagated to the invoice product lines (100%); native ``stock_account`` then
  copies it onto the COGS lines automatically. Credit notes reverse on the same
  branch.
* **POS-generated invoices** — inherit the analytic account from the POS
  configuration (header + lines), no manual selection required.
* **Sales orders** — new *Analytic Account* header that is propagated to the
  sale order lines, and from there natively to the invoice and COGS.
* **Optional enforcement** — require an analytic account before closing a POS
  session, posting a customer invoice, or confirming a sales order.

No core files are modified. Everything is done through standard inheritance and
native Odoo accounting / analytic / stock_account flows.

Configuration
=============

1. Create the branch analytic accounts (Accounting -> Configuration -> Analytic
   Accounts), optionally under a dedicated analytic plan.
2. Assign an analytic account on each Point of Sale configuration
   (Point of Sale -> Configuration -> Point of Sale -> *Analytic Accounting* tab).
3. Optionally enable the enforcement toggles in
   Settings -> Accounting -> *Analytics*.
""",
    'author': 'Flous Flow',
    'website': 'https://flousflow.com',
    'license': 'LGPL-3',
    'depends': ['point_of_sale', 'pos_stock', 'stock_account', 'sale'],
    'data': [
        'views/pos_config_views.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
