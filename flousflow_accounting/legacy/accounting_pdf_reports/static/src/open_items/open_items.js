/** @odoo-module **/
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { deserializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
const { DateTime } = luxon;

export class OpenItemsReport extends Component {
    static template = "flousflow_accounting.apr__OpenItemsReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        this.state = proxy({
            dateFrom: new Date().toISOString().slice(0, 10),
            resultSelection: context.default_result_selection || "trade",
            targetMove: "posted",
            scale: "unit",
            partnerQuery: "",
            partnerOptions: [],
            partnerIds: context.default_partner_ids || [],
            selectedPartners: [],
            rows: [],
            totals: { amount: 0, residual: 0 },
            currencyId: false,
            canEditReminder: false,
            canSendReminder: false,
            settingsOpen: false,
            unpostedCount: 0,
            expandedIds: [],
            loading: true,
        });
        onWillStart(() => this.loadReport());
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.flousflow_accounting.apr__report_agedpartnerbalance",
                "get_open_items_data", [], {
                    date_from: this.state.dateFrom,
                    result_selection: this.state.resultSelection,
                    target_move: this.state.targetMove,
                    partner_ids: this.state.partnerIds,
                }
            );
            this.state.rows = data.rows;
            this.state.totals = data.totals;
            this.state.currencyId = data.currency_id;
            this.state.canEditReminder = data.can_edit_reminder;
            this.state.canSendReminder = data.can_send_reminder;
            this.state.unpostedCount = data.unposted_count;
            this.state.selectedPartners = data.selected_partners;
            this.state.expandedIds = data.rows.map((row) => row.partner_id);
        } catch (error) {
            this.notification.add(error.message || _t("Open Items could not be loaded."), { type: "danger" });
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
            "search_open_items_partners", [], {
                query: this.state.partnerQuery,
                result_selection: this.state.resultSelection,
            }
        );
    }

    async addPartner(partner) {
        if (!this.state.partnerIds.includes(partner.id)) {
            this.state.partnerIds = [...this.state.partnerIds, partner.id];
            this.state.partnerQuery = "";
            this.state.partnerOptions = [];
            await this.loadReport();
        }
    }

    async removePartner(id) {
        this.state.partnerIds = this.state.partnerIds.filter((partnerId) => partnerId !== id);
        await this.loadReport();
    }

    togglePartner(row) {
        this.state.expandedIds = this.state.expandedIds.includes(row.partner_id)
            ? this.state.expandedIds.filter((id) => id !== row.partner_id)
            : [...this.state.expandedIds, row.partner_id];
    }

    async openPartner(partnerId) {
        const action = await this.orm.call(
            "report.flousflow_accounting.apr__report_agedpartnerbalance",
            "get_open_items_partner_action", [partnerId]
        );
        return this.action.doAction(action);
    }

    async openJournalItems(row) {
        const action = await this.orm.call(
            "report.flousflow_accounting.apr__report_agedpartnerbalance",
            "get_open_items_journal_action", [row.lines.map((line) => line.id)]
        );
        return this.action.doAction(action);
    }

    async sendReminder(row) {
        try {
            const action = await this.orm.call(
                "report.flousflow_accounting.apr__report_agedpartnerbalance",
                "get_open_items_reminder_action", [row.partner_id]
            );
            return this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("The reminder could not be opened."), { type: "danger" });
        }
    }

    async toggleNoReminder(line, event) {
        const value = event.target.checked;
        try {
            await this.orm.call(
                "report.flousflow_accounting.apr__report_agedpartnerbalance",
                "set_open_items_no_reminder", [[line.id], value]
            );
            line.no_reminder = value;
        } catch (error) {
            event.target.checked = !value;
            this.notification.add(error.message || _t("The reminder setting could not be updated."), { type: "danger" });
        }
    }

    async openMove(line) {
        const action = await this.action.loadAction("account.action_account_moves_all");
        action.domain = [...(action.domain || []), ["id", "=", line.id]];
        return this.action.doAction(action);
    }

    formatAmount(value, currencyId = this.state.currencyId) {
        const scales = {
            unit: { divisor: 1, digits: [69, 2], suffix: "" },
            rounded: { divisor: 1, digits: [69, 0], suffix: "" },
            thousand: { divisor: 1000, digits: [69, 2], suffix: "k" },
            million: { divisor: 1000000, digits: [69, 2], suffix: "M" },
        };
        const scale = scales[this.state.scale];
        return `${formatMonetary((value || 0) / scale.divisor, {
            currencyId, digits: scale.digits,
        })}${scale.suffix}`;
    }

    formatDate(value) {
        return value ? deserializeDate(value).toLocaleString(DateTime.DATE_MED) : "";
    }

    async printReport() {
        try {
            const action = await this.orm.call(
                "report.flousflow_accounting.apr__report_agedpartnerbalance",
                "print_open_items", [], {
                    date_from: this.state.dateFrom,
                    result_selection: this.state.resultSelection,
                    target_move: this.state.targetMove,
                    partner_ids: this.state.partnerIds,
                }
            );
            return this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("Open Items could not be printed."), { type: "danger" });
        }
    }

    exportXlsx() {
        const params = new URLSearchParams({
            date_from: this.state.dateFrom,
            result_selection: this.state.resultSelection,
            target_move: this.state.targetMove,
            partner_ids: this.state.partnerIds.join(","),
            scale: this.state.scale,
        });
        this.state.settingsOpen = false;
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/accounting_pdf_reports/open_items/export?${params.toString()}`,
            target: "download",
        });
    }
}

registry.category("actions").add("flousflow_accounting.apr__open_items", OpenItemsReport);
