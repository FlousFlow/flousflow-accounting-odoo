LEGACY_MENU_XMLIDS = (
    # Menus duplicated by the bundled FlousFlow accounting reports.
    "accounting_pdf_reports.menu_finance_audit_reports",
    "accounting_pdf_reports.menu_finance_entries_accounting_ledgers",
    "accounting_pdf_reports.menu_action_account_moves_ledger_general",
    "accounting_pdf_reports.menu_action_account_moves_ledger_partner",
    "accounting_pdf_reports.menu_account_reports",
    "accounting_pdf_reports.menu_partner_ledger",
    "accounting_pdf_reports.menu_general_ledger",
    "accounting_pdf_reports.menu_general_balance_report",
    "accounting_pdf_reports.menu_account_report_bs",
    "accounting_pdf_reports.menu_account_report_pl",
    "accounting_pdf_reports.menu_account_report",
    "accounting_pdf_reports.menu_aged_trial_balance",
    "accounting_pdf_reports.menu_aged_receivable",
    "accounting_pdf_reports.menu_aged_payable",
    "accounting_pdf_reports.menu_print_journal",
    "accounting_pdf_reports.menu_account_report_cash_flow",
    "accounting_pdf_reports.menu_account_report_annual",
    "om_account_daily_reports.menu_finance_daily_reports",
    "om_account_daily_reports.menu_daybook",
    "om_account_daily_reports.menu_cashbook",
    "om_account_daily_reports.menu_bankbook",
    "om_account_followup.menu_finance_followup",
    "om_account_followup.om_account_followup_print_menu",
    "om_account_followup.om_account_followup_menu",
    "om_account_followup.om_account_followup_s",
    "om_account_followup.menu_sale_followup",
    "om_account_followup.menu_action_followup_stat_follow",
    "om_account_accountant.menu_finance_entries_accounting_journals",
    "om_account_accountant.menu_action_account_moves_journal_sales",
    "om_account_accountant.menu_action_account_moves_journal_purchase",
    "om_account_accountant.menu_action_account_moves_journal_bank_cash",
    "om_account_accountant.menu_action_account_moves_journal_misc",
    "om_account_accountant.menu_account_management_config",
    "om_account_accountant.menu_review_journal_audit",
    "om_account_accountant.menu_review_moves_to_review",
    "om_account_accountant.menu_review_moves_unposted",
    "om_account_accountant.menu_review_reconciliation",
    "om_account_accountant.menu_review_bank_reconciliation",
    "om_account_accountant.menu_review_open_items",
    "om_account_accountant.menu_review_match_journal_items",
    "om_account_accountant.menu_review_bank_rec_to_review",
    "om_account_accountant.menu_review_regularization",
    "om_account_accountant.menu_review_unrealized_currencies",
    "om_account_accountant.menu_account_tag",
    "om_account_accountant.menu_accounting_bank_and_cash",
    "om_account_accountant.menu_accounting_statement_bank",
    "om_account_accountant.menu_accounting_statement_cash",
    "om_account_accountant.menu_account_payment_method",
)

LEGACY_PARTNER_ACTION_XMLIDS = (
    "accounting_pdf_reports.action_partner_report_partnerledger",
    "om_account_followup.action_report_customer_statement",
    "om_account_followup.action_report_vendor_statement",
)


def hide_legacy_duplicate_menus(env):
    """Hide standalone legacy menus duplicated by this consolidated module."""
    for xmlid in LEGACY_MENU_XMLIDS:
        menu = env.ref(xmlid, raise_if_not_found=False)
        if menu and menu.active:
            menu.write({"active": False})

    for xmlid in LEGACY_PARTNER_ACTION_XMLIDS:
        action = env.ref(xmlid, raise_if_not_found=False)
        if action and action.binding_model_id:
            action.write({"binding_model_id": False})


def pre_init_hook(env):
    from .legacy import accounting_pdf_reports
    accounting_pdf_reports._pre_init_clean_m2m_models(env)

def post_init_hook(env):
    from .legacy import om_account_followup
    om_account_followup.post_init_hook(env)
    hide_legacy_duplicate_menus(env)
