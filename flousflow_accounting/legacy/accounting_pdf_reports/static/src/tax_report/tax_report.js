/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

export class TaxReport extends Component {
    static template = "flousflow_accounting.apr__TaxReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            dateFrom: "",
            dateTo: "",
            targetMove: "posted",
            reportView: "general",
            comparisonMode: "none",
            comparisonPeriods: 1,
            comparisonDateFrom: "",
            comparisonDateTo: "",
            comparisonSort: "descending",
            scale: "unit",
            companyName: "",
            currencyId: false,
            currencySymbol: "",
            groups: [],
            totals: {},
            periods: [],
            draftCount: 0,
            dismissedWarning: false,
            settingsOpen: false,
            loading: true,
        });
        onWillStart(async () => {
            try {
                const metadata = await this.orm.call(
                    "report.flousflow_accounting.apr__report_tax", "get_interactive_metadata", []
                );
                this.state.dateFrom = metadata.date_from;
                this.state.dateTo = metadata.date_to;
                this.state.companyName = metadata.company_name;
                this.state.currencyId = metadata.currency_id;
                this.state.currencySymbol = metadata.currency_symbol;
                await this.loadReport();
            } catch (error) {
                this.notification.add(error.message || _t("Tax report options could not be loaded."), { type: "danger" });
                this.state.loading = false;
            }
        });
    }

    get visibleGroups() {
        const labels = {
            sale: _t("Sales"),
            purchase: _t("Purchases"),
            withholding: _t("Withholding"),
        };
        return Object.entries(labels).map(([key, label]) => {
            const linesByTax = new Map();
            for (const period of this.state.periods) {
                for (const line of period.groups?.[key] || []) {
                    if (!linesByTax.has(line.tax_id)) {
                        linesByTax.set(line.tax_id, line);
                    }
                }
            }
            return { key, label, lines: [...linesByTax.values()] };
        }).filter((group) => group.lines.length);
    }

    get visibleGroupedGroups() {
        const labels = {
            sale: _t("Sales"),
            purchase: _t("Purchases"),
            withholding: _t("Withholding"),
        };
        const view = this.state.reportView;
        return Object.entries(labels).map(([key, label]) => {
            const parents = new Map();
            for (const period of this.state.periods) {
                for (const parent of period.grouped_lines?.[view]?.[key] || []) {
                    const parentId = view === "account_tax" ? parent.account_id : parent.tax_id;
                    if (!parents.has(parentId)) {
                        parents.set(parentId, {
                            id: parentId,
                            label: view === "account_tax" ? parent.account_label : parent.name,
                            children: new Map(),
                        });
                    }
                    const target = parents.get(parentId);
                    const children = view === "account_tax" ? parent.lines : parent.accounts;
                    for (const child of children || []) {
                        const childId = view === "account_tax" ? child.tax_id : child.account_id;
                        if (!target.children.has(childId)) {
                            target.children.set(childId, {
                                id: childId,
                                label: view === "account_tax" ? child.name : child.account_label,
                            });
                        }
                    }
                }
            }
            const items = [...parents.values()].map((parent) => ({
                ...parent,
                children: [...parent.children.values()].sort((a, b) => a.label.localeCompare(b.label)),
            })).sort((a, b) => a.label.localeCompare(b.label));
            return { key, label, items };
        }).filter((group) => group.items.length);
    }

    get scaleOptions() {
        const symbol = this.state.currencySymbol;
        return [
            { value: "unit", label: symbol ? `In .${symbol}` : _t("In unit currency") },
            { value: "rounded", label: symbol ? `In ${symbol}` : _t("In whole units") },
            { value: "thousand", label: symbol ? `In k${symbol}` : _t("In thousands") },
            { value: "million", label: symbol ? `In M${symbol}` : _t("In millions") },
        ];
    }

    get periodColumns() {
        return this.state.periods.map((period, index) => ({
            ...period,
            key: period.current ? "current" : `comparison-${index}`,
            label: this.formatPeriod(period.date_from, period.date_to),
        }));
    }

    get amountColumnCount() {
        return 1 + this.periodColumns.length * 2;
    }

    formatPeriod(dateFrom, dateTo) {
        if (!dateFrom || !dateTo) {
            return dateFrom || dateTo || "";
        }
        const start = new Date(`${dateFrom}T00:00:00`);
        const end = new Date(`${dateTo}T00:00:00`);
        const lastDay = new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate();
        if (start.getDate() === 1 && end.getDate() === lastDay &&
                start.getMonth() === end.getMonth() && start.getFullYear() === end.getFullYear()) {
            return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(start);
        }
        return `${dateFrom} – ${dateTo}`;
    }

    periodAmount(groupKey, taxId, period, field) {
        const lines = period.groups?.[groupKey] || [];
        const line = lines.find((item) => item.tax_id === taxId);
        return this.formatAmount(line?.[field] || 0);
    }

    periodTotal(groupKey, period, field) {
        return this.formatAmount(period.totals?.[groupKey]?.[field] || 0);
    }

    formatAmount(amount) {
        const scales = {
            unit: [1, [69, 2], ""],
            rounded: [1, [69, 0], ""],
            thousand: [1000, [69, 2], "k"],
            million: [1000000, [69, 2], "M"],
        };
        const [divisor, digits, suffix] = scales[this.state.scale];
        return `${formatMonetary((amount || 0) / divisor, { currencyId: this.state.currencyId, digits })}${suffix}`;
    }

    async loadReport() {
        if (!this.state.dateFrom || !this.state.dateTo || this.state.dateFrom > this.state.dateTo) {
            this.notification.add(_t("Choose a valid reporting period."), { type: "warning" });
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.flousflow_accounting.apr__report_tax", "get_interactive_data", [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    target_move: this.state.targetMove,
                    comparison_mode: this.state.comparisonMode,
                    comparison_periods: this.state.comparisonPeriods,
                    comparison_date_from: this.state.comparisonDateFrom,
                    comparison_date_to: this.state.comparisonDateTo,
                    comparison_sort: this.state.comparisonSort,
                    report_view: this.state.reportView,
                }
            );
            this.state.groups = data.groups;
            this.state.totals = data.totals;
            this.state.draftCount = data.draft_count;
            this.state.periods = data.periods;
            this.state.dismissedWarning = false;
        } catch (error) {
            this.notification.add(error.message || _t("The Tax Report could not be loaded."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async setComparisonMode(mode) {
        this.state.comparisonMode = mode;
        if (mode === "custom" && !this.state.comparisonDateFrom) {
            const start = new Date(`${this.state.dateFrom}T00:00:00`);
            const end = new Date(`${this.state.dateTo}T00:00:00`);
            start.setFullYear(start.getFullYear() - 1);
            end.setFullYear(end.getFullYear() - 1);
            const asDate = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
            this.state.comparisonDateFrom = asDate(start);
            this.state.comparisonDateTo = asDate(end);
        }
        if (mode !== "custom" || (this.state.comparisonDateFrom && this.state.comparisonDateTo)) {
            await this.loadReport();
        }
    }

    async setReportView(view) {
        this.state.reportView = view;
        await this.loadReport();
    }

    groupedAmount(groupKey, parentId, childId, period, field) {
        const lines = period.grouped_lines?.[this.state.reportView]?.[groupKey] || [];
        if (this.state.reportView === "account_tax") {
            const account = lines.find((item) => item.account_id === parentId);
            return this.formatAmount(account?.lines?.find((item) => item.tax_id === childId)?.[field] || 0);
        }
        const tax = lines.find((item) => item.tax_id === parentId);
        return this.formatAmount(tax?.accounts?.find((item) => item.account_id === childId)?.[field] || 0);
    }

    async openJournalItems(taxId, accountId, period) {
        const action = await this.action.loadAction("account.action_account_moves_all_a");
        const states = this.state.targetMove === "all" ? ["posted", "draft"] : ["posted"];
        action.domain = [
            ["display_type", "not in", ["line_section", "line_subsection", "line_note"]],
            ["date", ">=", period.date_from],
            ["date", "<=", period.date_to],
            ["parent_state", "in", states],
            "|",
            ["tax_ids", "in", [taxId]],
            ["tax_line_id", "=", taxId],
        ];
        if (accountId) {
            action.domain.unshift(["account_id", "=", accountId]);
        }
        action.context = { ...action.context };
        if (this.state.targetMove === "all") {
            delete action.context.search_default_posted;
        }
        action.context = { ...action.context, search_default_group_by_move: 1 };
        return this.action.doAction(action);
    }

    async updateComparison(field, event) {
        this.state[field] = event.target.value;
        if (field === "comparisonPeriods") {
            this.state.comparisonPeriods = Math.max(1, Math.min(12, Number(event.target.value) || 1));
        }
        if (this.state.comparisonMode === "custom" &&
                (!this.state.comparisonDateFrom || !this.state.comparisonDateTo ||
                    this.state.comparisonDateFrom > this.state.comparisonDateTo)) {
            return;
        }
        await this.loadReport();
    }

    async printReport() {
        const action = await this.action.loadAction("flousflow_accounting.apr__action_account_tax_report");
        action.context = {
            ...action.context,
            default_period: "custom",
            default_date_from: this.state.dateFrom,
            default_date_to: this.state.dateTo,
            default_target_move: this.state.targetMove,
        };
        return this.action.doAction(action);
    }

    exportXlsx() {
        const params = new URLSearchParams({
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
            target_move: this.state.targetMove,
            scale: this.state.scale,
            comparison_mode: this.state.comparisonMode,
            comparison_periods: this.state.comparisonPeriods,
            comparison_date_from: this.state.comparisonDateFrom,
            comparison_date_to: this.state.comparisonDateTo,
            comparison_sort: this.state.comparisonSort,
            report_view: this.state.reportView,
        });
        this.state.settingsOpen = false;
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/accounting_pdf_reports/tax_report/export?${params.toString()}`,
            target: "download",
        });
    }
}

registry.category("actions").add("flousflow_accounting.apr__tax_report", TaxReport);
