def pre_init_hook(env):
    from .legacy import accounting_pdf_reports
    accounting_pdf_reports._pre_init_clean_m2m_models(env)

def post_init_hook(env):
    from .legacy import om_account_followup
    om_account_followup.post_init_hook(env)
