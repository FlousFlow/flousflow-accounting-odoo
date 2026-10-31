from pathlib import Path

import polib

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    language = 'ar_001'
    if not env['res.lang'].search([('code', '=', language), ('active', '=', True)], limit=1):
        return

    po_path = Path(__file__).parents[2] / 'i18n' / f'{language}.po'
    po = polib.pofile(str(po_path))
    for entry in po:
        if not entry.msgstr:
            continue
        for reference, _line in entry.occurrences:
            prefix = 'model:ir.ui.menu,name:flousflow_accounting.'
            if not reference.startswith(prefix):
                continue
            menu = env.ref(reference[len('model:ir.ui.menu,name:'):], raise_if_not_found=False)
            if menu:
                menu.with_context(lang=language).write({'name': entry.msgstr})
