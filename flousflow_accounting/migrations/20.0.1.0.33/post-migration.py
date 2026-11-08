from odoo import SUPERUSER_ID, api

from odoo.addons.flousflow_accounting.hooks import hide_legacy_duplicate_menus


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    hide_legacy_duplicate_menus(env)
