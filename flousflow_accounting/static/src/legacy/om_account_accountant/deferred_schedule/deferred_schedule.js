/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class DeferredScheduleReport extends Component {
    static template = "flousflow_accounting.acc__DeferredScheduleReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const params = this.props.action.params || {};
        const defaultMonth = DateTime.now().minus({ months: 1 }).startOf("month");
        this.state = proxy({
            reportType: params.report_type || "expense",
            period: defaultMonth.toFormat("yyyy-MM"),
            periodType: "month",
            periodAnchor: defaultMonth.toISODate(),
            periodPickerOpen: false,
            dateFrom: "",
            dateTo: "",
            customDateFrom: "",
            customDateTo: "",
            customDateError: "",
            groupBy: "account",
            targetMove: "posted",
            comparisonPeriods: 0,
            comparisonMode: "percentage",
            sortOrder: "desc",
            hideZero: false,
            unfoldAll: false,
            expandedRows: [],
            scale: 1,
            optionsOpen: false,
            settingsOpen: false,
            search: "",
            journals: [],
            journalIds: [],
            journalPickerOpen: false,
            loading: true,
            currencyId: false,
            periods: [],
            rows: [],
        });
        onWillStart(() => this.loadReport());
    }

    get title() {
        return this.state.reportType === "expense" ? _t("Deferred Expenses") : _t("Deferred Revenues");
    }

    get periodLabel() {
        if (this.state.periodType === "custom") {
            return `${DateTime.fromISO(this.state.dateFrom).toLocaleString(DateTime.DATE_MED)} – ${DateTime.fromISO(this.state.dateTo).toLocaleString(DateTime.DATE_MED)}`;
        }
        return this.getPeriodOptionLabel(this.state.periodType);
    }

    getPeriodOptionLabel(periodType) {
        const anchor = DateTime.fromISO(this.state.periodAnchor);
        if (periodType === "month") {
            return anchor.toFormat("LLLL yyyy");
        }
        if (periodType === "quarter") {
            return `Q${anchor.quarter} ${anchor.year}`;
        }
        return `FY ${anchor.year}`;
    }

    get totals() {
        return this.visibleRows.reduce((result, row) => ({
            entries: result.entries + row.entries,
            amount: result.amount + row.amount,
        }), { entries: 0, amount: 0 });
    }

    get visibleRows() {
        const search = this.state.search.trim().toLocaleLowerCase();
        if (!search) {
            return this.state.rows;
        }
        return this.state.rows.filter((row) => row.name.toLocaleLowerCase().includes(search));
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "account.deferred.schedule.report",
                "get_report_data",
                [this.state.reportType, this.state.period, this.state.groupBy,
                    this.state.targetMove, this.state.comparisonPeriods > 0, this.state.hideZero,
                    this.state.journalIds, this.state.comparisonPeriods,
                    this.state.comparisonMode, this.state.sortOrder, this.state.periodType,
                    this.state.periodAnchor, this.state.customDateFrom, this.state.customDateTo]
            );
            this.state.currencyId = data.currency_id;
            this.state.rows = data.rows;
            this.state.expandedRows = this.state.unfoldAll ? data.rows.map((row) => row.key) : [];
            this.state.journals = data.journals;
            this.state.periods = data.periods;
            this.state.period = data.periods[0].key;
            this.state.periodAnchor = data.period_anchor;
            this.state.dateFrom = data.date_from;
            this.state.dateTo = data.date_to;
            if (this.state.periodType !== "custom") {
                this.state.customDateFrom = data.date_from;
                this.state.customDateTo = data.date_to;
            }
        } catch (error) {
            this.notification.add(error.message || _t("The deferred report could not be loaded."), {
                type: "danger",
                sticky: true,
            });
            this.state.rows = [];
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange(key, value) {
        this.state[key] = value;
        await this.loadReport();
    }

    isExpanded(row) {
        return this.state.expandedRows.includes(row.key);
    }

    rowToggleLabel(row) {
        return this.isExpanded(row) ? _t("Collapse row") : _t("Expand row");
    }

    toggleRow(row) {
        const expanded = new Set(this.state.expandedRows);
        if (expanded.has(row.key)) {
            expanded.delete(row.key);
        } else {
            expanded.add(row.key);
        }
        this.state.expandedRows = [...expanded];
        this.state.unfoldAll = this.state.rows.length > 0
            && this.state.rows.every((item) => expanded.has(item.key));
    }

    toggleUnfoldAll(ev) {
        this.state.unfoldAll = ev.target.checked;
        this.state.expandedRows = ev.target.checked ? this.state.rows.map((row) => row.key) : [];
    }

    togglePeriodPicker() {
        this.state.periodPickerOpen = !this.state.periodPickerOpen;
    }

    async setPeriodType(periodType) {
        if (!["month", "quarter", "fiscal_year", "custom"].includes(periodType)) {
            return;
        }
        this.state.periodType = periodType;
        this.state.periodPickerOpen = true;
        if (periodType === "custom") {
            this.state.customDateFrom = this.state.dateFrom;
            this.state.customDateTo = this.state.dateTo;
            await this.applyCustomDateRange();
        } else {
            await this.loadReport();
        }
    }

    async navigatePeriod(periodType, offset) {
        const unit = { month: "months", quarter: "quarters", fiscal_year: "years" }[periodType];
        if (!unit) {
            return;
        }
        this.state.periodType = periodType;
        this.state.periodAnchor = DateTime.fromISO(this.state.periodAnchor).plus({ [unit]: offset }).toISODate();
        await this.loadReport();
    }

    async onCustomDateChange(key, ev) {
        this.state[key] = ev.target.value;
        await this.applyCustomDateRange();
    }

    async applyCustomDateRange() {
        const from = DateTime.fromISO(this.state.customDateFrom);
        const to = DateTime.fromISO(this.state.customDateTo);
        if (!from.isValid || !to.isValid) {
            this.state.customDateError = this.state.customDateFrom && this.state.customDateTo
                ? _t("Enter valid start and end dates.")
                : "";
            return;
        }
        if (from > to) {
            this.state.customDateError = _t("The start date must be on or before the end date.");
            return;
        }
        this.state.customDateError = "";
        this.state.periodType = "custom";
        this.state.periodAnchor = from.toISODate();
        await this.loadReport();
    }

    onScaleChange(ev) {
        this.state.scale = Number(ev.target.value) || 1;
    }

    async onComparisonToggle(ev) {
        await this.onFilterChange(
            "comparisonPeriods",
            ev.target.value === "previous" ? Math.max(this.state.comparisonPeriods, 1) : 0
        );
    }

    async onComparisonPeriodCount(ev) {
        await this.onFilterChange("comparisonPeriods", Number(ev.target.value) || 1);
    }

    async onComparisonOptionChange(key, ev) {
        await this.onFilterChange(key, ev.target.value);
    }

    comparisonValue(row, periodKey) {
        return row.comparison_values[periodKey];
    }

    totalComparisonValue(periodKey) {
        if (this.state.comparisonMode === "percentage") {
            const comparedAmount = this.visibleRows.reduce(
                (total, row) => total + row.period_values[periodKey], 0
            );
            if (comparedAmount === 0) {
                return this.totals.amount === 0 ? 0 : null;
            }
            return ((this.totals.amount - comparedAmount) / Math.abs(comparedAmount)) * 100;
        }
        return this.visibleRows.reduce(
            (total, row) => total + row.comparison_values[periodKey], 0
        );
    }

    formatComparison(value) {
        if (value === null || value === undefined) {
            return "—";
        }
        if (this.state.comparisonMode === "percentage") {
            return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)}%`;
        }
        return this.formatAmount(value);
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    toggleJournalPicker() {
        this.state.journalPickerOpen = !this.state.journalPickerOpen;
    }

    isJournalSelected(journalId) {
        return this.state.journalIds.includes(journalId);
    }

    async onJournalToggle(journalId, ev) {
        const ids = new Set(this.state.journalIds);
        if (ev.target.checked) {
            ids.add(journalId);
        } else {
            ids.delete(journalId);
        }
        this.state.journalIds = [...ids];
        await this.loadReport();
    }

    toggleSettings() {
        this.state.settingsOpen = !this.state.settingsOpen;
    }

    toggleOptions() {
        this.state.optionsOpen = !this.state.optionsOpen;
    }

    exportXlsx() {
        this.state.settingsOpen = false;
        const params = new URLSearchParams({
            report_type: this.state.reportType,
            period: this.state.period,
            period_type: this.state.periodType,
            period_anchor: this.state.periodAnchor,
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
            group_by: this.state.groupBy,
            target_move: this.state.targetMove,
            compare_previous: this.state.comparisonPeriods > 0 ? "1" : "0",
            comparison_periods: String(this.state.comparisonPeriods),
            comparison_mode: this.state.comparisonMode,
            sort_order: this.state.sortOrder,
            hide_zero: this.state.hideZero ? "1" : "0",
            scale: String(this.state.scale),
            journal_ids: this.state.journalIds.join(","),
        });
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/om_account_accountant/deferred_schedule/xlsx?${params.toString()}`,
            target: "download",
        });
    }

    formatAmount(value) {
        return formatMonetary((value || 0) / this.state.scale, { currencyId: this.state.currencyId });
    }

    async openGroup(row, period = this.state.periods[0]) {
        try {
            const domain = await this.orm.call(
                "account.deferred.schedule.report",
                "get_group_move_domain",
                [this.state.reportType, period.date_from, this.state.groupBy,
                    row.group_id, this.state.targetMove, row.group_model, this.state.journalIds,
                    period.date_to]
            );
            return this.action.doAction({
                type: "ir.actions.act_window",
                name: this.title,
                res_model: "account.move",
                views: [[false, "list"], [false, "form"]],
                domain,
                target: "current",
            });
        } catch (error) {
            this.notification.add(error.message || _t("The selected schedule entries could not be opened."), {
                type: "danger",
            });
        }
    }

    printReport() {
        window.print();
    }
}

registry.category("actions").add("flousflow_accounting.acc__deferred_schedule", DeferredScheduleReport);
