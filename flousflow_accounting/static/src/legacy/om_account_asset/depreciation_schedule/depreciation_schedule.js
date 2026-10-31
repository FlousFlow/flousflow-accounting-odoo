/** @odoo-module **/

import { Component, onWillStart, useState, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const { DateTime } = luxon;

export class DepreciationSchedule extends Component {
    static template = "flousflow_accounting.ast__DepreciationSchedule";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            dateFrom: "",
            dateTo: "",
            periodType: "fiscal_year",
            periodAnchor: "",
            customDateFrom: "",
            customDateTo: "",
            categoryIds: [],
            categories: [],
            targetMove: "posted",
            scale: "unit",
            hideZero: false,
            data: null,
            loading: true,
            filtersOpen: false,
        });
        onWillStart(async () => {
            try {
                const meta = await this.orm.call("asset.depreciation.schedule", "get_interactive_metadata", []);
                this.state.dateFrom = meta.date_from;
                this.state.dateTo = meta.date_to;
                this.state.periodAnchor = meta.date_from;
                this.state.customDateFrom = meta.date_from;
                this.state.customDateTo = meta.date_to;
                this.state.categories = meta.categories;
                await this.loadReport();
            } catch (error) {
                this.notification.add(error.message || _t("The depreciation schedule could not be loaded."), { type: "danger" });
                this.state.loading = false;
            }
        });
    }

    async loadReport() {
        if (!this.state.dateFrom || !this.state.dateTo) {
            return;
        }
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "asset.depreciation.schedule",
                "get_interactive_data",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    category_ids: this.state.categoryIds,
                    target_move: this.state.targetMove,
                }
            );
        } catch (error) {
            this.notification.add(error.message || _t("The depreciation schedule could not be loaded."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    get periodLabel() {
        const anchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateFrom);
        if (this.state.periodType === "fiscal_year") {
            return anchor.toFormat("yyyy");
        }
        if (this.state.periodType === "month") {
            return anchor.toFormat("LLLL yyyy");
        }
        if (this.state.periodType === "quarter") {
            const start = anchor.startOf("quarter");
            return `${start.toFormat("LLL yyyy")} – ${start.endOf("quarter").toFormat("LLL yyyy")}`;
        }
        return `${this.formatDate(this.state.dateFrom)} – ${this.formatDate(this.state.dateTo)}`;
    }

    async setPeriod(periodType) {
        this.state.periodType = periodType;
        if (periodType === "custom") {
            this.state.customDateFrom = this.state.dateFrom;
            this.state.customDateTo = this.state.dateTo;
            return;
        }
        const anchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateFrom);
        if (periodType === "fiscal_year") {
            const dates = await this.orm.call(
                "asset.depreciation.schedule", "get_interactive_period_dates", [], { anchor_date: anchor.toISODate() }
            );
            this.state.dateFrom = dates.date_from;
            this.state.dateTo = dates.date_to;
        } else {
            this.state.dateFrom = anchor.startOf(periodType).toISODate();
            this.state.dateTo = anchor.endOf(periodType).toISODate();
        }
        this.state.periodAnchor = this.state.dateFrom;
        await this.loadReport();
    }

    async onPeriodTypeClick(periodType, event) {
        event.preventDefault();
        event.stopPropagation();
        await this.setPeriod(periodType);
    }

    async onPeriodNavigationClick(periodType, direction, event) {
        event.preventDefault();
        event.stopPropagation();
        await this.movePeriod(direction, periodType);
    }

    async movePeriod(direction, periodType) {
        const unit = periodType === "fiscal_year" ? "years" : periodType === "quarter" ? "quarters" : "months";
        this.state.periodAnchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateFrom)
            .plus({ [unit]: direction }).toISODate();
        await this.setPeriod(periodType);
    }

    getPeriodOptionLabel(periodType) {
        const anchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateFrom);
        if (periodType === "month") {
            return anchor.toFormat("LLLL yyyy");
        }
        if (periodType === "quarter") {
            const start = anchor.startOf("quarter");
            return `${start.toFormat("LLL yyyy")} – ${start.endOf("quarter").toFormat("LLL yyyy")}`;
        }
        return anchor.toFormat("yyyy");
    }

    async onCustomDateChange(field, event) {
        this.state[field] = event.target.value;
        if (this.state.customDateFrom && this.state.customDateTo && this.state.customDateFrom <= this.state.customDateTo) {
            this.state.dateFrom = this.state.customDateFrom;
            this.state.dateTo = this.state.customDateTo;
            this.state.periodAnchor = this.state.dateFrom;
            await this.loadReport();
        }
    }

    async onCategoryChange(event) {
        this.state.categoryIds = Array.from(event.target.selectedOptions, (option) => Number(option.value));
        await this.loadReport();
    }

    async onTargetMoveChange(targetMove) {
        this.state.targetMove = targetMove;
        await this.loadReport();
    }

    async printReport() {
        try {
            const action = await this.orm.call(
                "asset.depreciation.schedule",
                "action_print_interactive",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    category_ids: this.state.categoryIds,
                    target_move: this.state.targetMove,
                }
            );
            return this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("The depreciation schedule could not be printed."), { type: "danger" });
        }
    }

    formatAmount(value) {
        const data = this.state.data;
        if (!data) {
            return "";
        }
        const scales = {
            unit: [1, data.currency_digits, ""],
            rounded: [1, 0, ""],
            thousand: [1000, data.currency_digits, "k"],
            million: [1000000, data.currency_digits, "M"],
        };
        const [divisor, digits, suffix] = scales[this.state.scale];
        const amount = new Intl.NumberFormat(undefined, {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format((value || 0) / divisor) + suffix;
        return data.currency_position === "before"
            ? `${data.currency_symbol} ${amount}`
            : `${amount} ${data.currency_symbol}`;
    }

    formatDate(value) {
        return value ? DateTime.fromISO(value).toLocaleString(DateTime.DATE_SHORT) : "";
    }

    formatRate(value) {
        return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value || 0)}%`;
    }

    setScale(scale) {
        this.state.scale = scale;
    }

    isZeroRow(row) {
        return [
            "asset_opening", "asset_additions", "asset_disposals", "asset_closing",
            "depreciation_opening", "depreciation_additions", "depreciation_disposals", "depreciation_closing",
            "nbv_opening", "nbv_additions", "nbv_decrease", "nbv_closing",
        ].every((key) => Math.abs(row[key] || 0) < 0.005);
    }

    get groups() {
        const groups = this.state.data?.groups || [];
        return this.state.hideZero
            ? groups.map((group) => ({ ...group, rows: group.rows.filter((row) => !this.isZeroRow(row)) }))
                .filter((group) => group.rows.length)
            : groups;
    }
}

registry.category("actions").add("flousflow_accounting.ast__depreciation_schedule", DepreciationSchedule);
