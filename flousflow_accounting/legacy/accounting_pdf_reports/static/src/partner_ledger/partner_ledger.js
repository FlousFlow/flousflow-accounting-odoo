/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { deserializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
const { DateTime } = luxon;
export class PartnerLedger extends Component {
    static template = "accounting_pdf_reports.PartnerLedger";
    props = useProps(standardActionServiceProps);
    setup() {
        this.orm = useService("orm"); this.action = useService("action"); this.notification = useService("notification");
        const today = DateTime.now();
        const context = this.props.action.context || {};
        const initialPartnerIds = context.partner_ids || [];
        const initialPartnerTagIds = context.partner_tag_ids || [];
        this.state = proxy({ anchor: today.toISODate(), periodType: "fiscal_year", dateFrom: "", dateTo: "", customFrom: "", customTo: "", targetMove: "posted", accountScope: "trade", scale: "unit", search: "", partners: [], expandedIds: [], partnerIds: Array.isArray(initialPartnerIds) ? initialPartnerIds : [initialPartnerIds], partnerQuery: "", partnerOptions: [], selectedPartners: [], tags: [], partnerTagIds: Array.isArray(initialPartnerTagIds) ? initialPartnerTagIds : [initialPartnerTagIds], partnerFilterOpen: false, filtersOpen: false, settingsOpen: false, moveActionOpenFor: false, loading: true, companyName: "", currencyId: false, draftCount: 0, dismissedDraftWarning: false });
        onWillStart(async () => {
            try {
                const options = await this.orm.call(
                    "report.accounting_pdf_reports.report_partnerledger", "get_partner_filter_options",
                    [this.state.partnerIds]
                );
                this.state.tags = options.tags;
                this.state.selectedPartners = options.partners;
            } catch (error) {
                this.notification.add(error.message || _t("Partner filters could not be loaded."), { type: "danger" });
            }
            await this.loadReport();
        });
    }
    get periodLabel() { return this.state.periodType === "custom" ? `${this.state.dateFrom} – ${this.state.dateTo}` : `FY ${DateTime.fromISO(this.state.anchor).year}`; }
    get visiblePartners() { const q = this.state.search.trim().toLocaleLowerCase(); return q ? this.state.partners.filter(p => p.name.toLocaleLowerCase().includes(q)) : this.state.partners; }
    get totals() { return this.state.partners.reduce((s,p)=>({debit:s.debit+p.debit,credit:s.credit+p.credit,balance:s.balance+p.balance}),{debit:0,credit:0,balance:0}); }
    async loadReport() {
        this.state.loading = true;
        try {
            const d = await this.orm.call("report.accounting_pdf_reports.report_partnerledger","get_interactive_data",[],{period_type:this.state.periodType,period_anchor:this.state.anchor,custom_date_from:this.state.customFrom,custom_date_to:this.state.customTo,target_move:this.state.targetMove,account_scope:this.state.accountScope,partner_ids:this.state.partnerIds,partner_tag_ids:this.state.partnerTagIds});
            this.state.partners=d.partners; this.state.dateFrom=d.date_from; this.state.dateTo=d.date_to; this.state.companyName=d.company_name; this.state.currencyId=d.currency_id; this.state.companyIds=d.company_ids; this.state.expandedIds=[]; this.state.draftCount=d.draft_count; this.state.dismissedDraftWarning=false;
        } catch(e) { this.notification.add(e.message||_t("The Partner Ledger could not be loaded."),{type:"danger"}); }
        finally { this.state.loading=false; }
    }
    async changeYear(n) { this.state.anchor=DateTime.fromISO(this.state.anchor).plus({years:n}).toISODate(); await this.loadReport(); }
    async toggleCustom() { if(this.state.periodType==="custom"){this.state.periodType="fiscal_year";await this.loadReport();}else{this.state.periodType="custom";this.state.customFrom=this.state.dateFrom;this.state.customTo=this.state.dateTo;} }
    async setDate(field,ev) { this.state[field]=ev.target.value; if(this.state.customFrom&&this.state.customTo&&this.state.customFrom<=this.state.customTo){this.state.periodType="custom";await this.loadReport();} }
    async searchInteractivePartners(event) {
        this.state.partnerQuery = event.target.value;
        if (this.state.partnerQuery.trim().length < 2) {
            this.state.partnerOptions = [];
            return;
        }
        this.state.partnerOptions = await this.orm.call(
            "report.accounting_pdf_reports.report_partnerledger", "search_interactive_partners",
            [this.state.partnerQuery]
        );
    }
    async addPartner(partner) {
        if (!this.state.partnerIds.includes(partner.id)) {
            this.state.partnerIds = [...this.state.partnerIds, partner.id];
            this.state.selectedPartners = [...this.state.selectedPartners, partner];
            await this.loadReport();
        }
        this.state.partnerQuery = "";
        this.state.partnerOptions = [];
    }
    async removePartner(partnerId) {
        this.state.partnerIds = this.state.partnerIds.filter((id) => id !== partnerId);
        this.state.selectedPartners = this.state.selectedPartners.filter((partner) => partner.id !== partnerId);
        await this.loadReport();
    }
    async togglePartnerTag(tagId) {
        const selected = new Set(this.state.partnerTagIds);
        selected.has(tagId) ? selected.delete(tagId) : selected.add(tagId);
        this.state.partnerTagIds = [...selected];
        await this.loadReport();
    }
    async togglePartner(p) {
        if(this.state.expandedIds.includes(p.id)){this.state.expandedIds=this.state.expandedIds.filter(id=>id!==p.id);return;}
        this.state.expandedIds=[...this.state.expandedIds,p.id];
        if(!p.lines.length){try{p.lines=await this.orm.call("report.accounting_pdf_reports.report_partnerledger","get_interactive_partner_lines",[],[p.id,this.state.dateFrom,this.state.dateTo,this.state.targetMove,this.state.accountScope]);}catch(e){this.notification.add(e.message||_t("Partner entries could not be loaded."),{type:"danger"});}}
    }
    formatAmount(v){const s={unit:[1,[69,2],""],rounded:[1,[69,0],""],thousand:[1000,[69,2],"k"],million:[1000000,[69,2],"M"]}[this.state.scale];return `${formatMonetary(v/s[0],{currencyId:this.state.currencyId,digits:s[1]})}${s[2]}`;}
    formatForeignAmount(line){if(!line.currency_id||line.currency_id===this.state.currencyId)return "";const s={unit:[1,[69,2],""],rounded:[1,[69,0],""],thousand:[1000,[69,2],"k"],million:[1000000,[69,2],"M"]}[this.state.scale];return formatMonetary(line.amount_currency/s[0],{currencyId:line.currency_id,digits:s[1]});}
    formatDate(v){return v?deserializeDate(v).toLocaleString(DateTime.DATE_SHORT):"";}
    async openPartner(id){return this.action.doAction({type:"ir.actions.act_window",res_model:"res.partner",res_id:id,views:[[false,"form"]],target:"current"});}
    async openMove(moveId){this.state.moveActionOpenFor=false;return this.action.doAction({type:"ir.actions.act_window",res_model:"account.move",res_id:moveId,views:[[false,"form"]],target:"current"});}
    toggleMoveAction(lineId){this.state.moveActionOpenFor=this.state.moveActionOpenFor===lineId?false:lineId;}
    async openPartnerItems(id) {
        const action = await this.action.loadAction("account.action_account_moves_all");
        const accountTypes = this.state.accountScope === "payable"
            ? ["liability_payable"]
            : this.state.accountScope === "receivable"
                ? ["asset_receivable"]
                : ["asset_receivable", "liability_payable"];
        action.domain = [
            ...(action.domain || []),
            ["company_id", "in", this.state.companyIds],
            ["account_id.account_type", "in", accountTypes],
            ["partner_id.commercial_partner_id", "=", id],
            ["date", ">=", this.state.dateFrom],
            ["date", "<=", this.state.dateTo],
        ];
        const context = { ...(action.context || {}) };
        if (this.state.targetMove === "all") {
            delete context.search_default_posted;
        } else {
            context.search_default_posted = 1;
        }
        action.context = context;
        return this.action.doAction(action);
    }
    async openDraftMoves(){const a=await this.action.loadAction("account.action_account_moves_all");a.domain=[...(a.domain||[]),["company_id","in",this.state.companyIds],["date","<=",this.state.dateTo],["state","=","draft"]];a.context={...a.context,search_default_posted:false};return this.action.doAction(a);}
    async printReport(){if(!this.state.partners.length){this.notification.add(_t("There are no partners to print for the selected filters."),{type:"warning"});return;}const a=await this.action.loadAction("accounting_pdf_reports.action_account_partner_ledger_menu");a.context={...a.context,default_date_from:this.state.dateFrom,default_date_to:this.state.dateTo,default_target_move:this.state.targetMove,default_result_selection:this.state.accountScope==="payable"?"supplier":this.state.accountScope==="receivable"?"customer":"customer_supplier",default_partner_ids:this.state.partners.map(p=>p.id),default_reconciled:true,default_amount_currency:true};return this.action.doAction(a);}
    exportXlsx(){if(!this.visiblePartners.length){this.notification.add(_t("There are no partners to export for the selected filters."),{type:"warning"});return;}const params=new URLSearchParams({period_type:this.state.periodType,period_anchor:this.state.anchor,custom_date_from:this.state.customFrom,custom_date_to:this.state.customTo,target_move:this.state.targetMove,account_scope:this.state.accountScope,partner_ids:this.state.partnerIds.join(","),partner_tag_ids:this.state.partnerTagIds.join(","),search:this.state.search,scale:this.state.scale});this.state.settingsOpen=false;return this.action.doAction({type:"ir.actions.act_url",url:`/accounting_pdf_reports/partner_ledger/export?${params.toString()}`,target:"download"});}
}
registry.category("actions").add("accounting_pdf_reports.partner_ledger",PartnerLedger);
