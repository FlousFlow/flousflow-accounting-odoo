from odoo import SUPERUSER_ID, api


TEMPLATES_WITH_ENTERPRISE_UPLOAD = (
    "working_file_check_enterprise_23",
    "working_file_check_enterprise_24",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"lang": "en_US"})
    templates = env["account.working.file.template"]
    checks = env["account.working.file.check"]

    for xml_name in TEMPLATES_WITH_ENTERPRISE_UPLOAD:
        template = env.ref(
            f"om_account_accountant.{xml_name}", raise_if_not_found=False
        )
        if not template:
            continue

        template.write({"evidence_required": True})
        linked_checks = checks.search([
            ("template_id", "=", template.id),
        ])
        legacy_checks = checks.search([
            ("template_id", "=", False),
            ("name", "=", template.name),
            ("section", "=", template.section),
        ])
        (linked_checks | legacy_checks).write({"evidence_required": True})
