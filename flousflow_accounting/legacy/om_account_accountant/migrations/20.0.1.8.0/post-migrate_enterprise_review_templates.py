from odoo import SUPERUSER_ID, api


LEGACY_TEMPLATE_XMLIDS = (
    "working_file_check_treasury",
    "working_file_check_receivables",
    "working_file_check_revenue",
    "working_file_check_fixed_assets",
    "working_file_check_inventory",
    "working_file_check_payables",
    "working_file_check_accruals",
    "working_file_check_equity",
    "working_file_check_expenses",
)


def migrate(cr, version):
    """Replace generic starter checks without deleting their records."""
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    legacy_templates = env["account.working.file.template"]
    for xmlid in LEGACY_TEMPLATE_XMLIDS:
        template = env.ref(f"om_account_accountant.{xmlid}", raise_if_not_found=False)
        if template and template.active:
            legacy_templates |= template
    if legacy_templates:
        legacy_templates.write({"active": False})
