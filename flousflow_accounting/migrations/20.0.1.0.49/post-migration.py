from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    view = env.ref(
        "flousflow_accounting.acc__res_config_settings_view_form",
        raise_if_not_found=False,
    )
    if not view:
        return

    old_variants = (
        "Allow Customer Account credit only at the point of sale assigned to the customer.\n"
        "                                Immediate payment methods remain available at all points of sale.",
        "Allow Customer Account credit only at the point of sale assigned to the customer. Immediate payment methods remain available at all points of sale.",
    )
    new = (
        "السماح بالبيع على الحساب فقط من منفذ البيع المرتبط بالعميل.\n"
        "                                تظل طرق الدفع الفوري متاحة من جميع المنافذ."
    )
    translated = view.with_context(lang="ar_001")
    arch = translated.arch_db
    for old in old_variants:
        if old in arch:
            translated.write({"arch_db": arch.replace(old, new, 1)})
            break
