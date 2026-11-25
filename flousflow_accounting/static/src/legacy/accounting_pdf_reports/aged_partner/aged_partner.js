/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import "../open_items/open_items";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { deserializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useEffect, useProps } from "@odoo/owl";
const { DateTime } = luxon;

export class AgedPartnerReport extends Component {
    static template = "flousflow_accounting.apr__AgedPartnerReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        this.state = proxy({
            resultSelection: context.default_result_selection || "customer",
            dateFrom: new Date().toISOString().slice(0, 10),
            targetMove: "posted",
            scale: "unit",
            dateBasis: "due_date",
            bucketEnds: [30, 60, 90, 120],
            draftBucketEnd: 30,
            editingBucket: false,
            partnerQuery: "",
            partnerOptions: [],
            partnerIds: [],
            selectedPartners: [],
            rows: [],
            totals: { not_due: 0, buckets: [0, 0, 0, 0, 0], total: 0 },
            currencyId: false,
            expandedIds: [],
            loading: true,
        });
        useEffect(() => {
            if (this.state.editingBucket !== false) {
                const input = document.querySelector(".ff_aged_bucket_inline_input");
                if (!input) {
                    return;
                }
                input.focus();
                input.select();
            }
        });
        onWillStart(() => this.loadReport());
    }

    get title() {
        return this.state.resultSelection === "supplier" ? _t("Aged Payable") : _t("Aged Receivable");
    }

    get bucketLabels() {
        const ends = this.state.bucketEnds;
        return ends.map((end, index) => `${index ? ends[index - 1] + 1 : 1}-${end}`).concat(_t("Older"));
    }

    openBucketEditor(index) {
        this.state.editingBucket = Math.min(index, 3);
        this.state.draftBucketEnd = this.state.bucketEnds[this.state.editingBucket];
    }

    closeBucketEditor() {
        this.state.editingBucket = false;
    }

    onBucketDraftChange(event) {
        this.state.draftBucketEnd = event.target.value;
    }

    onBucketKeydown(event) {
        if (event.key === "Enter") {
            event.preventDefault();
            return this.applyBucketEnds();
        }
        if (event.key === "Escape") {
            event.preventDefault();
            this.closeBucketEditor();
        }
    }

    async applyBucketEnds() {
        const ends = [...this.state.bucketEnds];
        ends[this.state.editingBucket] = Number(this.state.draftBucketEnd);
        if (ends.some((value) => !Number.isInteger(value) || value < 1 || value > 14640)
                || ends.some((value, index) => index && value <= ends[index - 1])) {
            this.notification.add(_t("Enter a valid period end day between 1 and 14640."), { type: "warning" });
            return;
        }
        this.state.bucketEnds = ends;
        this.closeBucketEditor();
        await this.loadReport();
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.flousflow_accounting.apr__report_agedpartnerbalance",
                "get_interactive_data",
                [],
                {
                    result_selection: this.state.resultSelection,
                    date_from: this.state.dateFrom,
                    target_move: this.state.targetMove,
                    bucket_ends: this.state.bucketEnds,
                    partner_ids: this.state.partnerIds,
                    date_basis: this.state.dateBasis,
                }
            );
            this.state.rows = data.rows;
            this.state.totals = data.totals;
            this.state.currencyId = data.currency_id;
            this.state.expandedIds = [];
        } catch (error) {
            this.notification.add(error.message || _t("The aged partner report could not be loaded."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange(field, event) {
        this.state[field] = event.target.value;
        await this.loadReport();
    }

    async searchPartners(event) {
        this.state.partnerQuery = event.target.value;
        if (this.state.partnerQuery.trim().length < 2) {
            this.state.partnerOptions = [];
            return;
        }
        this.state.partnerOptions = await this.orm.call(
            "report.flousflow_accounting.apr__report_agedpartnerbalance",
            "search_interactive_partners",
            [],
            { query: this.state.partnerQuery, result_selection: this.state.resultSelection }
        );
    }

    async addPartner(partner) {
        if (!this.state.partnerIds.includes(partner.id)) {
            this.state.partnerIds = [...this.state.partnerIds, partner.id];
            this.state.selectedPartners = [...this.state.selectedPartners, partner];
            this.state.partnerQuery = "";
            this.state.partnerOptions = [];
            await this.loadReport();
        }
    }

    async removePartner(id) {
        this.state.partnerIds = this.state.partnerIds.filter((partnerId) => partnerId !== id);
        this.state.selectedPartners = this.state.selectedPartners.filter((partner) => partner.id !== id);
        await this.loadReport();
    }

    async togglePartner(row) {
        if (this.state.expandedIds.includes(row.partner_id)) {
            this.state.expandedIds = this.state.expandedIds.filter((id) => id !== row.partner_id);
        } else {
            this.state.expandedIds = [...this.state.expandedIds, row.partner_id];
        }
    }

    openPartner(partnerId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: partnerId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async openOpenItems(partnerId) {
        const action = await this.orm.call(
            "report.flousflow_accounting.apr__report_agedpartnerbalance",
            "get_open_items_action", [partnerId]
        );
        return this.action.doAction(action);
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
        return value ? deserializeDate(value).toLocaleString(DateTime.DATE_MED) : "";
    }

    async openMove(lineId) {
        const action = await this.action.loadAction("account.action_account_moves_all");
        action.domain = [...(action.domain || []), ["id", "=", lineId]];
        return this.action.doAction(action);
    }

    async printReport() {
        try {
            await this.orm.call(
                "report.flousflow_accounting.apr__report_agedpartnerbalance",
                "print_interactive_report",
                [],
                {
                    result_selection: this.state.resultSelection,
                    date_from: this.state.dateFrom,
                    target_move: this.state.targetMove,
                    bucket_ends: this.state.bucketEnds,
                    partner_ids: this.state.partnerIds,
                    date_basis: this.state.dateBasis,
                    scale: this.state.scale,
                }
            ).then((action) => this.action.doAction(action));
        } catch (error) {
            this.notification.add(error.message || _t("The report could not be printed."), { type: "danger" });
        }
    }

    exportXlsx() {
        const params = new URLSearchParams({
            result_selection: this.state.resultSelection,
            date_from: this.state.dateFrom,
            target_move: this.state.targetMove,
            bucket_ends: this.state.bucketEnds.join(","),
            partner_ids: this.state.partnerIds.join(","),
            date_basis: this.state.dateBasis,
            scale: this.state.scale,
        });
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/accounting_pdf_reports/aged_partner/export?${params.toString()}`,
            target: "download",
        });
    }
}

registry.category("actions").add("flousflow_accounting.apr__aged_partner", AgedPartnerReport);
