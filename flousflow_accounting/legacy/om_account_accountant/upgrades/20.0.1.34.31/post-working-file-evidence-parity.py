from odoo import SUPERUSER_ID, api


TEMPLATES_WITHOUT_ENTERPRISE_UPLOAD = (
    "working_file_check_enterprise_23",
    "working_file_check_enterprise_24",
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"lang": "en_US"})
    templates = env["account.working.file.template"]
    checks = env["account.working.file.check"]

    for xml_name in TEMPLATES_WITHOUT_ENTERPRISE_UPLOAD:
        template = env.ref(
            f"om_account_accountant.{xml_name}", raise_if_not_found=False
        )
        if not template:
            continue

        template.write({"evidence_required": False})

        # New checks keep template_id. Older working-file rows were copied
        # without that link, so also match the exact template name, section,
        # and sequence to avoid changing unrelated/custom checks.
        linked_checks = checks.search([
            ("template_id", "=", template.id),
            ("evidence_required", "=", True),
        ])
        legacy_checks = checks.search([
            ("template_id", "=", False),
            ("name", "=", template.name),
            ("section", "=", template.section),
            ("sequence", "=", template.sequence),
            ("evidence_required", "=", True),
        ])
        (linked_checks | legacy_checks).write({"evidence_required": False})
