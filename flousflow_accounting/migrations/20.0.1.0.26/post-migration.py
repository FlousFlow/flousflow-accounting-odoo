from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    templates = env["account.working.file.template"].search([
        ("active", "=", True), ("scope", "=", "tax_return"),
    ])
    if not templates:
        return

    for tax_return in env["account.tax.return"].search([("check_ids", "=", False)]):
        tax_return.check_ids = [fields.Command.create({
            "sequence": template.sequence,
            "section": template.section,
            "name": template.name,
            "description": template.description,
            "template_id": template.id,
            "evidence_required": template.evidence_required,
        }) for template in templates]
