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
        if check.name != template.with_context(lang="en_US").name:
            continue
        for language in languages:
            check.with_context(lang=language).write({
                "section": template.with_context(lang=language).section,
                "name": template.with_context(lang=language).name,
                "description": template.with_context(lang=language).description,
            })
