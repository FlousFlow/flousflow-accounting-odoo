/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class ExecutiveSummary extends Component {
    static template = "flousflow_accounting.apr__ExecutiveSummary";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            dateFrom: "",
            dateTo: "",
            targetMove: "posted",
            cashBasis: false,
            comparison: false,
            loading: true,
            companyName: "",
            currencyId: false,
            groups: [],
            comparisonGroups: [],
        });
        onWillStart(async () => {
            try {
                const data = await this.fetchData(false, false);
                if (data) {
                    this.applyData(data);
                }
            } catch (error) {
                this.notification.add(error.message || _t("Executive Summary could not be loaded."), { type: "danger" });
            } finally {
                this.state.loading = false;
            }
        });
    }

    async fetchData(dateFrom = this.state.dateFrom, dateTo = this.state.dateTo) {
        return this.orm.call(
            "report.flousflow_accounting.apr__report_financial",
            "get_executive_summary_data",
            [dateFrom || false, dateTo || false, this.state.targetMove, this.state.cashBasis],
        );
    }

    applyData(data) {
        this.state.dateFrom = data.date_from;
        this.state.dateTo = data.date_to;
        this.state.companyName = data.company_name;
        this.state.currencyId = data.currency_id;
        this.state.groups = data.groups;
    }

    async reload() {
        if (this.state.dateFrom && this.state.dateTo && this.state.dateFrom > this.state.dateTo) {
            this.notification.add(_t("The start date must be on or before the end date."), { type: "warning" });
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.fetchData();
            this.applyData(data);
            this.state.comparisonGroups = [];
            if (this.state.comparison) {
                const from = DateTime.fromISO(data.date_from);
                const to = DateTime.fromISO(data.date_to);
                const previousTo = from.minus({ days: 1 });
                const length = Math.max(Math.round(to.diff(from, "days").days), 0);
                const previousFrom = previousTo.minus({ days: length });
                const previous = await this.fetchData(previousFrom.toISODate(), previousTo.toISODate());
                this.state.comparisonGroups = previous.groups;
            }
        } catch (error) {
            this.notification.add(error.message || _t("Executive Summary could not be loaded."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onDateFromChange(event) {
        this.state.dateFrom = event.target.value;
        await this.reload();
    }

    async onDateToChange(event) {
        this.state.dateTo = event.target.value;
        await this.reload();
    }

    async onTargetMoveChange(event) {
        this.state.targetMove = event.target.value;
        await this.reload();
    }

    async onComparisonChange(event) {
        this.state.comparison = event.target.checked;
        await this.reload();
    }

    async onAccountingBasisChange(event) {
        this.state.cashBasis = event.target.value === "cash";
        await this.reload();
    }

    getComparisonValue(groupKey, itemKey) {
        const group = this.state.comparisonGroups.find((item) => item.key === groupKey);
        return group?.items.find((item) => item.key === itemKey)?.value;
    }

    formatComparison(groupKey, item) {
        return this.formatValue({ ...item, value: this.getComparisonValue(groupKey, item.key) || 0 });
    }

    formatValue(item) {
        if (item.unit === "percent") {
            return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(item.value || 0)}%`;
        }
        if (item.unit === "days") {
            return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(item.value || 0);
        }
        if (item.unit === "ratio") {
            return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(item.value || 0);
        }
        return formatMonetary(item.value || 0, { currencyId: this.state.currencyId });
    }

    print() {
        window.print();
    }
}

registry.category("actions").add("flousflow_accounting.apr__executive_summary", ExecutiveSummary);
