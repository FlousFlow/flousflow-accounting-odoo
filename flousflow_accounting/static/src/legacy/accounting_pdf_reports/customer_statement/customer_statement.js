/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { deserializeDate, serializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class CustomerStatement extends Component {
    static template = "flousflow_accounting.apr__CustomerStatement";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const today = DateTime.now();
        const previousMonth = today.minus({ months: 1 });
        this.state = proxy({
            title: _t("Customer / Vendor Statement"),
            periodType: "month",
            periodAnchor: serializeDate(previousMonth),
            dateFrom: "",
            dateTo: "",
            customDateFrom: serializeDate(previousMonth.startOf("month")),
            customDateTo: serializeDate(previousMonth.endOf("month")),
            periodOpen: false,
            filterOpen: false,
            partnerFilterOpen: false,
            infoOpenFor: false,
            targetMove: "posted",
            accountScopes: ["receivable", "payable"],
            partnerSearch: "",
            partnerOptions: [],
            selectedPartners: [],
            tags: [],
            selectedTagIds: [],
            moveActionOpenFor: false,
            moreOpen: false,
            settingsOpen: false,
            scale: "unit",
            loading: true,
            partners: [],
            expandedPartnerIds: [],
            lineCount: 0,
            draftCount: 0,
            companyName: "",
            currencyId: false,
        });
        onWillStart(async () => {
            this.state.tags = await this.orm.call(
                "report.flousflow_accounting.apr__customer_statement_data", "get_partner_tags", []
            );
            await this.searchPartners();
            await this.loadReport();
        });
    }

    get periodLabel() {
        if (!this.state.dateFrom || !this.state.dateTo) return _t("Period");
        if (this.state.periodType === "month") return DateTime.fromISO(this.state.dateFrom).toFormat("LLLL yyyy");
        if (this.state.periodType === "quarter") {
            const start = DateTime.fromISO(this.state.dateFrom);
            return `Q${start.quarter} ${start.year}`;
        }
        if (this.state.periodType === "fiscal_year") return DateTime.fromISO(this.state.dateFrom).toFormat("yyyy");
        return `${DateTime.fromISO(this.state.dateFrom).toLocaleString(DateTime.DATE_MED)} – ${DateTime.fromISO(this.state.dateTo).toLocaleString(DateTime.DATE_MED)}`;
    }

    getPeriodOptionLabel(periodType) {
        const anchor = DateTime.fromISO(this.state.periodAnchor);
        if (periodType === "month") return anchor.toFormat("LLL yyyy");
        if (periodType === "quarter") return `Q${anchor.quarter} ${anchor.year}`;
        return anchor.toFormat("yyyy");
    }

    get accountScopeLabel() {
        const standard = ["receivable", "payable"];
        if (standard.every((scope) => this.state.accountScopes.includes(scope)) &&
                this.state.accountScopes.length === standard.length) {
            return _t("Trade Partners");
        }
        const labels = {
            receivable: _t("Receivable"),
            non_trade_receivable: _t("Non-trade Receivable"),
            payable: _t("Payable"),
            non_trade_payable: _t("Non-trade Payable"),
        };
        return this.state.accountScopes.map((scope) => labels[scope]).join(", ");
    }

    get accountScopeOptions() {
        return [
            ["receivable", _t("Trade Receivable")],
            ["non_trade_receivable", _t("Non-trade Receivable")],
            ["payable", _t("Trade Payable")],
            ["non_trade_payable", _t("Non-trade Payable")],
        ];
    }

    get reportTitle() {
        const hasReceivable = this.state.accountScopes.some((scope) => scope.includes("receivable"));
        const hasPayable = this.state.accountScopes.some((scope) => scope.includes("payable"));
        // The Enterprise Customer Statement keeps its customer heading for the
        // combined trade-partner scope; only a payable-only report is a vendor statement.
        if (hasReceivable) return _t("Customer Statement");
        if (hasPayable && !hasReceivable) return _t("Vendor Statement");
        return _t("Customer / Vendor Statement");
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.flousflow_accounting.apr__customer_statement_data", "get_interactive_data", [], {
                    period_type: this.state.periodType,
                    period_anchor: this.state.periodAnchor,
                    custom_date_from: this.state.customDateFrom,
                    custom_date_to: this.state.customDateTo,
                    account_scopes: this.state.accountScopes,
                    partner_ids: this.state.selectedPartners.map((partner) => partner.id),
                    partner_tag_ids: this.state.selectedTagIds,
                    target_move: this.state.targetMove,
                }
            );
            this.state.dateFrom = data.date_from;
            this.state.dateTo = data.date_to;
            this.state.partners = data.partners;
            this.state.lineCount = data.line_count;
            this.state.draftCount = data.draft_count;
            this.state.companyName = data.company_name;
            this.state.currencyId = data.currency_id;
        } catch (error) {
            this.notification.add(error.message || _t("The statement could not be loaded."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async setPeriod(periodType) {
        if (periodType === "custom") {
            if (this.state.periodType !== "custom") {
                this.state.customDateFrom = this.state.dateFrom;
                this.state.customDateTo = this.state.dateTo;
            }
            this.state.periodType = "custom";
            return;
        }
        this.state.periodType = periodType;
        if (!this.state.periodAnchor) {
            this.state.periodAnchor = serializeDate(DateTime.now());
        }
        await this.loadReport();
    }

    async movePeriod(periodType, direction) {
        const unit = { month: "months", quarter: "months", fiscal_year: "years" }[periodType];
        const factor = periodType === "quarter" ? 3 : 1;
        this.state.periodType = periodType;
        this.state.periodAnchor = serializeDate(
            DateTime.fromISO(this.state.periodAnchor).plus({ [unit]: direction * factor })
        );
        await this.loadReport();
    }

    async setCustomDate(field, event) {
        this.state[field] = event.target.value;
        if (this.state.customDateFrom && this.state.customDateTo &&
                this.state.customDateFrom > this.state.customDateTo) {
            this.notification.add(_t("The start date must be on or before the end date."), { type: "warning" });
            return;
        }
        this.state.periodType = "custom";
        await this.loadReport();
    }

    toggleAccountScope(scope) {
        const selected = new Set(this.state.accountScopes);
        selected.has(scope) ? selected.delete(scope) : selected.add(scope);
        if (!selected.size) {
            this.notification.add(_t("Select at least one account scope."), { type: "warning" });
            return;
        }
        this.state.accountScopes = [...selected];
        this.loadReport();
    }

    async searchPartners() {
        this.state.partnerOptions = await this.orm.call(
            "report.flousflow_accounting.apr__customer_statement_data", "search_partners",
            [this.state.partnerSearch]
        );
    }

    async addPartner(partner) {
        if (!this.state.selectedPartners.some((item) => item.id === partner.id)) {
            this.state.selectedPartners.push(partner);
            await this.loadReport();
        }
        this.state.partnerSearch = "";
        await this.searchPartners();
    }

    async removePartner(partnerId) {
        this.state.selectedPartners = this.state.selectedPartners.filter((partner) => partner.id !== partnerId);
        await this.loadReport();
    }

    async toggleTag(tagId) {
        const selected = new Set(this.state.selectedTagIds);
        selected.has(tagId) ? selected.delete(tagId) : selected.add(tagId);
        this.state.selectedTagIds = [...selected];
        await this.loadReport();
    }

    async setTargetMove(targetMove) {
        this.state.targetMove = targetMove;
        await this.loadReport();
    }

    formatAmount(value) {
        const scales = {
            unit: { divisor: 1, digits: [69, 2], suffix: "" },
            rounded: { divisor: 1, digits: [69, 0], suffix: "" },
            thousand: { divisor: 1000, digits: [69, 2], suffix: "k" },
            million: { divisor: 1000000, digits: [69, 2], suffix: "M" },
        };
        const scale = scales[this.state.scale];
        return `${formatMonetary((value || 0) / scale.divisor, {
            currencyId: this.state.currencyId, digits: scale.digits,
        })}${scale.suffix}`;
    }

    formatDate(value) {
        return value ? deserializeDate(value).toLocaleString(DateTime.DATE_SHORT) : "";
    }

    formatForeignAmount(line) {
        if (!line.currency_id || line.currency_id === this.state.currencyId) {
            return "";
        }
        return formatMonetary(line.amount_currency || 0, { currencyId: line.currency_id });
    }

    isPartnerExpanded(partnerId) {
        return this.state.expandedPartnerIds.includes(partnerId);
    }

    togglePartner(partnerId) {
        const expanded = new Set(this.state.expandedPartnerIds);
        expanded.has(partnerId) ? expanded.delete(partnerId) : expanded.add(partnerId);
        this.state.expandedPartnerIds = [...expanded];
    }

    toggleInfo(target) {
        this.state.infoOpenFor = this.state.infoOpenFor === target ? false : target;
    }

    get statementInfoRows() {
        return [
            {
                label: "_currency_amount_currency",
                formula: "_report_engine_partner_ledger_report",
                subFormula: "_currency_amount_currency",
                value: "1",
            },
            {
                label: "amount",
                formula: "_report_engine_partner_ledger_report",
                subFormula: "amount",
                value: this.formatAmount(this.totalAmount),
            },
            { label: "amount_currency", formula: "_report_engine_partner_ledger_report", subFormula: "amount_currency", value: "" },
            { label: "date_maturity", formula: "_report_engine_partner_ledger_report", subFormula: "date_maturity", value: "" },
            { label: "invoice_date", formula: "_report_engine_partner_ledger_report", subFormula: "invoice_date", value: "" },
        ];
    }

    get totalAmount() {
        return this.state.partners.reduce((total, partner) => total + partner.amount, 0);
    }

    openPartner(partnerId) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "res.partner", res_id: partnerId,
            views: [[false, "form"]], target: "current" });
    }

    openPartnerJournalItems(partner) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Journal Items"),
            res_model: "account.move.line",
            views: [[false, "list"], [false, "form"]],
            domain: [["id", "in", partner.lines.map((line) => line.id)]],
            target: "current",
        });
    }

    openMove(moveId) {
        this.state.moveActionOpenFor = false;
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "account.move", res_id: moveId,
            views: [[false, "form"]], target: "current" });
    }

    toggleMoveAction(lineId) {
        this.state.moveActionOpenFor = this.state.moveActionOpenFor === lineId ? false : lineId;
    }

    getReportFilters() {
        return {
            period_type: this.state.periodType,
            period_anchor: this.state.periodAnchor,
            custom_date_from: this.state.customDateFrom,
            custom_date_to: this.state.customDateTo,
            account_scopes: this.state.accountScopes,
            partner_ids: this.state.selectedPartners.map((partner) => partner.id),
            partner_tag_ids: this.state.selectedTagIds,
            target_move: this.state.targetMove,
            scale: this.state.scale,
        };
    }

    exportXlsx() {
        const params = new URLSearchParams({
            period_type: this.state.periodType,
            period_anchor: this.state.periodAnchor,
            custom_date_from: this.state.customDateFrom,
            custom_date_to: this.state.customDateTo,
            account_scopes: this.state.accountScopes.join(","),
            partner_ids: this.state.selectedPartners.map((partner) => partner.id).join(","),
            partner_tag_ids: this.state.selectedTagIds.join(","),
            target_move: this.state.targetMove,
            scale: this.state.scale,
        });
        this.state.settingsOpen = false;
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/accounting_pdf_reports/customer_statement/export?${params.toString()}`,
            target: "download",
        });
    }

    async printReport() {
        try {
            const action = await this.orm.call(
                "report.flousflow_accounting.apr__customer_statement_data",
                "get_print_action", [this.getReportFilters()]
            );
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("The statement could not be printed."), { type: "danger" });
        }
    }

    async sendReport() {
        this.state.moreOpen = false;
        try {
            const action = await this.orm.call(
                "report.flousflow_accounting.apr__customer_statement_data",
                "get_send_action", [this.getReportFilters()]
            );
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("The statement could not be prepared for sending."), { type: "danger" });
        }
    }
}

registry.category("actions").add("flousflow_accounting.apr__customer_statement", CustomerStatement);
