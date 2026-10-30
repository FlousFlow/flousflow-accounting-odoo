from odoo import SUPERUSER_ID, api


EVIDENCE_REQUIRED = {
    "working_file_check_enterprise_05": "Review of Guarantees",
    "working_file_check_enterprise_17": "Subsidiaries and Investments Summary",
    "working_file_check_enterprise_21": "Events of the Period",
    "working_file_check_enterprise_23": "Accounting Process",
    "working_file_check_enterprise_24": "Asset Register",
    "working_file_check_enterprise_33": "Obtain Signed Inventory Valuation",
    "working_file_check_enterprise_47": "Annual General Meeting Minutes on Dividend Distribution",
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {"lang": "en_US"})
    template_ids = set()
    names = []
    for xml_name, check_name in EVIDENCE_REQUIRED.items():
        template = env.ref(
            f"om_account_accountant.{xml_name}", raise_if_not_found=False
        )
        if template:
            template.write({"evidence_required": True})
            template_ids.add(template.id)
        names.append(check_name)

    checks = env["account.working.file.check"].search([
        "|",
        ("template_id", "in", list(template_ids)),
        ("name", "in", names),
    ])
    checks.write({"evidence_required": True})
