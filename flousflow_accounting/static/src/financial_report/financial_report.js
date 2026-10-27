/** @odoo-module **/

import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class FlousflowFinancialReport extends Component {
    static template = "flousflow_accounting.FinancialReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        const context = this.props.action.context || {};
        const reportType = context.default_report_type || "balance_sheet";
        const now = new Date();
        const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
        const isBalanceSheet = reportType === "balance_sheet";
        const initialPreset = ["cash_flow", "trial_balance", "general_ledger"].includes(reportType)
            ? "current_month"
            : "current_year";
        this.state = proxy({
            reportType,
            dateTo: context.default_date_to || today,
            dateFrom: context.default_date_from || (isBalanceSheet ? `${today.slice(0, 4)}-01-01` : today),
            periodPreset: context.default_date_from ? "custom" : initialPreset,
            targetMove: "posted",
            comparisonMode: "none",
            comparisonDate: context.default_comparison_date || today,
            comparisonDisplay: "percentage",
            searchQuery: "",
            loading: false,
            payload: null,
            error: null,
            foldedCodes: [],
        });
        onWillStart(() => this.loadReport());
    }

    async loadReport() {
        if (!this.state.dateTo) {
            return;
        }
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.payload = await this.orm.call(
                "flousflow.account.report",
                "get_interactive_report_data",
                [
                    this.state.reportType,
                    this.state.dateTo,
                    this.state.dateFrom,
                    this.state.targetMove,
                    this.state.comparisonMode,
                ],
                {
                    comparison_date: this.state.comparisonDate,
                    date_filter: this.state.reportType === "balance_sheet" ? "custom" : this.state.periodPreset,
                }
            );
            if (this.state.reportType !== "balance_sheet" && this.state.periodPreset !== "custom") {
                this.state.dateFrom = this.state.payload.date_from;
                this.state.dateTo = this.state.payload.date_to;
            }
        } catch (error) {
            this.state.error = error.data?.message || error.message || "Could not load the report.";
        } finally {
            this.state.loading = false;
        }
    }

    async onDateChange(event) {
        this.state.periodPreset = "custom";
        if (event.target.name === "dateFrom") {
            this.state.dateFrom = event.target.value;
        } else {
            this.state.dateTo = event.target.value;
        }
        await this.loadReport();
    }

    async onPeriodPresetChange(event) {
        this.state.periodPreset = event.target.value;
        await this.loadReport();
    }

    async shiftPeriod(offset) {
        const baseDate = new Date(`${this.state.dateTo}T12:00:00`);
        if (this.state.reportType === "balance_sheet") {
            baseDate.setDate(baseDate.getDate() + offset);
            this.state.dateTo = this.toISODate(baseDate);
        } else if (this.state.periodPreset === "current_month") {
            baseDate.setDate(1);
            baseDate.setMonth(baseDate.getMonth() + offset);
            this.state.dateTo = this.toISODate(new Date(baseDate.getFullYear(), baseDate.getMonth() + 1, 0));
        } else if (this.state.periodPreset === "current_quarter") {
            const quarterStartMonth = Math.floor(baseDate.getMonth() / 3) * 3;
            baseDate.setMonth(quarterStartMonth + (3 * offset), 1);
            this.state.dateTo = this.toISODate(new Date(baseDate.getFullYear(), baseDate.getMonth() + 3, 0));
        } else if (this.state.periodPreset === "current_year") {
            baseDate.setFullYear(baseDate.getFullYear() + offset);
            this.state.dateTo = this.toISODate(baseDate);
        } else {
            const start = new Date(`${this.state.dateFrom}T12:00:00`);
            const days = Math.round((baseDate - start) / 86400000) + 1;
            baseDate.setDate(baseDate.getDate() + (days * offset));
            start.setDate(start.getDate() + (days * offset));
            this.state.dateFrom = this.toISODate(start);
            this.state.dateTo = this.toISODate(baseDate);
        }
        await this.loadReport();
    }

    toISODate(date) {
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    }

    get periodLabel() {
        const start = new Date(`${this.state.dateFrom}T12:00:00`);
        const end = new Date(`${this.state.dateTo}T12:00:00`);
        const locale = document.documentElement.lang || undefined;
        if (this.state.periodPreset === "current_month") {
            return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric" }).format(end);
        }
        if (this.state.periodPreset === "current_quarter") {
            const formatter = new Intl.DateTimeFormat(locale, { month: "short", year: "numeric" });
            return `${formatter.format(start)} – ${formatter.format(end)}`;
        }
        if (this.state.periodPreset === "current_year") {
            const firstYear = start.getFullYear();
            const lastYear = end.getFullYear();
            return firstYear === lastYear ? String(firstYear) : `FY ${firstYear}–${lastYear}`;
        }
        return "";
    }

    async onMoveFilterChange(event) {
        this.state.targetMove = event.target.value;
        await this.loadReport();
    }

    async onComparisonChange(event) {
        this.state.comparisonMode = event.target.value;
        await this.loadReport();
    }

    async onComparisonDateChange(event) {
        this.state.comparisonDate = event.target.value;
        await this.loadReport();
    }

    onComparisonDisplayChange(event) {
        this.state.comparisonDisplay = event.target.value;
    }

    onSearchInput(event) {
        this.state.searchQuery = event.target.value;
    }

    async toggleComparison() {
        this.state.comparisonMode = this.state.comparisonMode === "none" ? "previous_year" : "none";
        await this.loadReport();
    }

    formatAmount(value) {
        const amount = new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(value || 0);
        const symbol = this.state.payload?.currency_symbol || "";
        return this.state.payload?.currency_position === "before"
            ? `${symbol} ${amount}`
            : `${amount} ${symbol}`;
    }

    formatComparison(line) {
        const comparison = line.comparison_balance || 0;
        const difference = (line.balance || 0) - comparison;
        if (this.state.comparisonDisplay === "percentage") {
            const percentage = comparison ? difference / Math.abs(comparison) * 100 : 0;
            return `${new Intl.NumberFormat(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }).format(percentage)}%`;
        }
        return this.formatAmount(difference);
    }

    get visibleLines() {
        let rows = this.state.payload?.lines || [];
        if (this.state.reportType === "general_ledger" && this.state.searchQuery) {
            const query = this.state.searchQuery.toLocaleLowerCase();
            const groups = [];
            let group = [];
            for (const line of rows) {
                if (line.is_section && group.length) {
                    groups.push(group);
                    group = [];
                }
                group.push(line);
            }
            if (group.length) {
                groups.push(group);
            }
            rows = groups
                .filter((accountRows) => accountRows.some((line) =>
                    `${line.code || ""} ${line.name || ""} ${line.partner_name || ""} ${line.move_name || ""}`
                        .toLocaleLowerCase().includes(query)))
                .flat();
        }
        const visible = [];
        const ancestors = [];
        for (const line of rows) {
            while (ancestors.length && ancestors[ancestors.length - 1].level >= line.level) {
                ancestors.pop();
            }
            if (!ancestors.some((ancestor) => this.state.foldedCodes.includes(ancestor.code))) {
                visible.push(line);
            }
            if (line.has_children) {
                ancestors.push(line);
            }
        }
        return visible;
    }

    get hasFoldableLines() {
        return (this.state.payload?.lines || []).some((line) => line.has_children);
    }

    toggleLine(line) {
        this.state.foldedCodes = this.state.foldedCodes.includes(line.code)
            ? this.state.foldedCodes.filter((code) => code !== line.code)
            : [...this.state.foldedCodes, line.code];
    }

    foldAll() {
        this.state.foldedCodes = (this.state.payload?.lines || [])
            .filter((line) => line.has_children)
            .map((line) => line.code);
    }

    unfoldAll() {
        this.state.foldedCodes = [];
    }

    async openLine(line, amountType = null) {
        const lineKey = line.code || line.id;
        if (!lineKey || !line.has_amount || !this.state.payload?.report_id) {
            return;
        }
        try {
            const action = await this.orm.call(
                "flousflow.account.report",
                "get_interactive_drilldown_action",
                [this.state.payload.report_id, lineKey, amountType]
            );
            await this.actionService.doAction(action);
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "warning" });
        }
    }

    async exportReport(format) {
        if (!this.state.payload?.report_id) {
            return;
        }
        try {
            const action = await this.orm.call(
                "flousflow.account.report",
                "get_interactive_export_action",
                [this.state.payload.report_id, format]
            );
            await this.actionService.doAction(action);
        } catch (error) {
            this.notification.add(error.data?.message || error.message, { type: "warning" });
        }
    }
}

registry.category("actions").add(
    "flousflow_accounting.financial_report",
    FlousflowFinancialReport
);
