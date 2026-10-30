# -*- coding: utf-8 -*-

{
    'name': 'Internal Transfers',
    'version': '20.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Paired internal transfers between bank and cash journals',
    'description': """
Flous Flow Internal Account Transfers
=====================================

Create paired, traceable internal transfers between bank and cash journals.
Each transfer posts both legs, keeps the source and destination linked, and
keeps the journal dashboard balance aligned with the posted ledger entries.

Features
--------
* Bank-to-bank, bank-to-cash, and cash-to-bank transfers.
* Automatic paired payment creation and synchronization.
* Safe cancellation and draft restoration of both legs.
* Dashboard balance based on posted liquidity and outstanding accounts.
* Multi-company journal validation through standard Odoo accounting rules.
""",
    'images': ['static/description/banner.png', 'static/description/icon.png'],
    'author': 'Flous Flow / Mohamed Gamal',
    'license': 'OPL-1',
    'depends': ['account'],
    'data': [
        'views/account_payment_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
