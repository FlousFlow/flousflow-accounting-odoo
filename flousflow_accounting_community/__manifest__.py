# Part of FlousFlow Accounting.
{
    'name': 'FlousFlow Community Accounting',
    'version': '20.0.1.0.0',
    'summary': 'FlousFlow-branded Odoo 20 Community Accounting foundation',
    'description': """
FlousFlow Community Accounting
==============================
Branded distribution layer for the standard Odoo 20 Community ``account``
module.  The upstream technical module remains ``account`` so Odoo's native
dependencies, XML IDs, migrations, and accounting integrations stay intact.
Future FlousFlow customizations should inherit the Community models and views
from this module.
    """,
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',
    'author': 'FlousFlow',
    'website': 'https://flousflow.com',
    'depends': ['account'],
    'data': [],
    'application': True,
    'installable': True,
}
