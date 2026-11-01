from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    languages = env["res.lang"].search([("active", "=", True)]).mapped("code")
    checks = env["account.working.file.check"].search([
        ("tax_return_id", "!=", False),
        ("template_id.scope", "=", "tax_return"),
    ])
    for check in checks:
        template = check.template_id
        source = template.with_context(lang="en_US")
        values = {}
        for language in languages:
            localized_check = check.with_context(lang=language)
            localized_template = template.with_context(lang=language)
            for field_name in ("section", "name", "description"):
                if localized_check[field_name] == source[field_name]:
                    values[field_name] = localized_template[field_name]
            if values:
                localized_check.write(values)
                values = {}
