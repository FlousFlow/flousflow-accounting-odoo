/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { deserializeDate, serializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class CashFlowReport extends Component {
    static template = "accounting_pdf_reports.CashFlowReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({
            periodType: "month",
            periodAnchor: "",
            dateFrom: "",
            dateTo: "",
            customDateFrom: "",
            customDateTo: "",
            targetMove: "posted",
            scale: "unit",
            hideZero: false,
            filtersOpen: false,
            journalFilterEnabled: false,
            journalIds: [],
            journals: [],
            companyId: false,
            companyName: "",
            currencyId: false,
            opening: 0,
            netChange: 0,
            closing: 0,
            sections: [],
            expandedKeys: [],
            loading: true,
        });
        onWillStart(async () => {
            await this.loadMetadata();
            await this.loadReport();
        });
    }

    async loadMetadata() {
        try {
            const data = await this.orm.call(
                "report.accounting_pdf_reports.report_cash_flow",
                "get_interactive_metadata",
                []
            );
            this.state.companyId = data.company_id;
            this.state.companyName = data.company_name;
            this.state.currencyId = data.currency_id;
            this.state.journals = data.journals;
            this.state.journalIds = data.journals.map((journal) => journal.id);
            this.state.dateFrom = data.default_date_from;
            this.state.dateTo = data.default_date_to;
            this.state.periodAnchor = data.default_date_from;
            this.state.customDateFrom = data.default_date_from;
            this.state.customDateTo = data.default_date_to;
        } catch (error) {
            this.notification.add(error.message || _t("Cash flow report options could not be loaded."), { type: "danger" });
        }
    }

    get periodLabel() {
        if (!this.state.dateFrom || !this.state.dateTo) {
            return _t("Select a period");
        }
        const start = DateTime.fromISO(this.state.dateFrom);
        const end = DateTime.fromISO(this.state.dateTo);
        if (this.state.periodType === "month") {
            return start.toFormat("LLL yyyy");
        }
        if (this.state.periodType === "quarter") {
            return `${start.toFormat("LLL")} – ${end.toFormat("LLL yyyy")}`;
        }
        if (this.state.periodType === "fiscal_year") {
            return start.year === end.year ? `${_t("Fiscal Year")} ${start.year}` : `${start.year}–${end.year}`;
        }
        return `${start.toLocaleString(DateTime.DATE_MED)} – ${end.toLocaleString(DateTime.DATE_MED)}`;
    }

    get visibleSections() {
        const sectionNames = {
            operating: _t("Cash Flows from Operating Activities"),
            investing: _t("Cash Flows from Investing and Extraordinary Activities"),
            financing: _t("Cash Flows from Financing Activities"),
            unclassified: _t("Cash Flows from Unclassified Activities"),
        };
        const labels = {
            operating: [
                ["receivable", _t("Payments received from customers")],
                ["income", _t("Operating income")],
                ["payable", _t("Payments made to suppliers")],
                ["expense", _t("Operating expenses")],
            ],
            investing: [["income", _t("Income")], ["expense", _t("Expenses")]],
            financing: [["income", _t("Income")], ["expense", _t("Expenses")]],
            unclassified: [["income", _t("Income")], ["expense", _t("Expenses")]],
        };
        return this.state.sections.map((section) => {
            const lines = labels[section.activity] || [];
            const groupedLines = lines.map(([key, name]) => {
                const sourceLines = section.activity === "operating"
                    ? section.lines.filter((line) => key === "expense"
                        ? !["receivable", "income", "payable"].includes(line.key)
                        : line.key === key)
                    : section.lines.filter((line) => key === "income"
                        ? line.amount > 0
                        : line.amount < 0);
                return {
                    key,
                    name,
                    amount: sourceLines.reduce((total, line) => total + line.amount, 0),
                    line_ids: [...new Set(sourceLines.flatMap((line) => line.line_ids || []))],
                    accounts: sourceLines.flatMap((line) => line.accounts || []),
                };
            });
            return {
                ...section,
                name: sectionNames[section.activity] || section.name,
                lines: this.state.hideZero
                    ? groupedLines.filter((line) => !this.isZero(line.amount))
                    : groupedLines,
            };
        });
    }

    isZero(value) {
        return Math.abs(value || 0) < 0.005;
    }

    async loadReport() {
        if (!this.state.dateFrom || !this.state.dateTo) {
            return;
        }
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.accounting_pdf_reports.report_cash_flow",
                "get_interactive_data",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    target_move: this.state.targetMove,
                    journal_ids: this.state.journalIds,
                    journal_filter_enabled: this.state.journalFilterEnabled,
                }
            );
            this.state.opening = data.opening;
            this.state.netChange = data.net_change;
            this.state.closing = data.closing;
            this.state.sections = data.sections;
            this.state.currencyId = data.currency_id;
            this.state.companyName = data.company_name;
            this.state.expandedKeys = [];
        } catch (error) {
            this.notification.add(error.message || _t("The cash flow report could not be loaded."), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async setPeriod(periodType) {
        this.state.periodType = periodType;
        const anchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateTo);
        if (periodType === "custom") {
            this.state.customDateFrom = this.state.dateFrom;
            this.state.customDateTo = this.state.dateTo;
            return;
        }
        if (periodType === "fiscal_year") {
            const dates = await this.orm.call(
                "report.accounting_pdf_reports.report_cash_flow",
                "get_interactive_period_dates",
                [],
                { anchor_date: anchor.toISODate() }
            );
            this.state.dateFrom = dates.date_from;
            this.state.dateTo = dates.date_to;
        } else {
            this.state.dateFrom = serializeDate(anchor.startOf(periodType));
            this.state.dateTo = serializeDate(anchor.endOf(periodType));
        }
        this.state.periodAnchor = this.state.dateFrom;
        await this.loadReport();
    }

    getPeriodOptionLabel(periodType) {
        const anchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateFrom);
        if (periodType === "month") {
            return anchor.toFormat("LLLL yyyy");
        }
        if (periodType === "quarter") {
            const start = anchor.startOf("quarter");
            const end = anchor.endOf("quarter");
            return `${start.toFormat("LLL yyyy")} – ${end.toFormat("LLL yyyy")}`;
        }
        if (periodType === "fiscal_year") {
            return `${anchor.year}`;
        }
        return `${DateTime.fromISO(this.state.customDateFrom).toLocaleString(DateTime.DATE_MED)} – ${DateTime.fromISO(this.state.customDateTo).toLocaleString(DateTime.DATE_MED)}`;
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

    async movePeriod(direction, periodType = this.state.periodType) {
        this.state.periodType = periodType;
        const unit = periodType === "fiscal_year" ? "years" : periodType === "quarter" ? "quarters" : "months";
        this.state.periodAnchor = DateTime.fromISO(this.state.periodAnchor || this.state.dateFrom)
            .plus({ [unit]: direction }).toISODate();
        if (this.state.periodType === "fiscal_year") {
            const dates = await this.orm.call(
                "report.accounting_pdf_reports.report_cash_flow",
                "get_interactive_period_dates",
                [],
                { anchor_date: this.state.periodAnchor }
            );
            this.state.dateFrom = dates.date_from;
            this.state.dateTo = dates.date_to;
        } else {
            const anchor = DateTime.fromISO(this.state.periodAnchor);
            this.state.dateFrom = serializeDate(anchor.startOf(unit));
            this.state.dateTo = serializeDate(anchor.endOf(unit));
        }
        await this.loadReport();
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

    async onJournalsChange(event) {
        this.state.journalIds = Array.from(event.target.selectedOptions, (option) => Number(option.value));
        await this.loadReport();
    }

    setScale(scale) {
        this.state.scale = scale;
    }

    async toggleJournalFilter() {
        this.state.journalFilterEnabled = !this.state.journalFilterEnabled;
        if (this.state.journalFilterEnabled && !this.state.journalIds.length) {
            this.state.journalIds = this.state.journals.map((journal) => journal.id);
        }
        await this.loadReport();
    }

    toggleFilters() {
        this.state.filtersOpen = !this.state.filtersOpen;
    }

    async onTargetMoveChange(targetMove) {
        this.state.targetMove = targetMove;
        await this.loadReport();
    }

    toggleLine(section, line) {
        const key = `${section.activity}:${line.key}`;
        this.state.expandedKeys = this.state.expandedKeys.includes(key)
            ? this.state.expandedKeys.filter((value) => value !== key)
            : [...this.state.expandedKeys, key];
    }

    isExpanded(section, line) {
        return this.state.expandedKeys.includes(`${section.activity}:${line.key}`);
    }

    formatAmount(value) {
        const scales = {
            unit: [1, [69, 2], ""],
            rounded: [1, [69, 0], ""],
            thousand: [1000, [69, 2], "k"],
            million: [1000000, [69, 2], "M"],
        };
        const [divisor, digits, suffix] = scales[this.state.scale];
        return `${formatMonetary((value || 0) / divisor, { currencyId: this.state.currencyId, digits, noSymbol: true })}${suffix}`;
    }

    async openJournalItems(lineIds) {
        if (!lineIds?.length) {
            return;
        }
        const action = await this.action.loadAction("account.action_account_moves_all");
        action.domain = [...(action.domain || []), ["id", "in", lineIds]];
        action.context = { ...action.context, search_default_posted: false };
        return this.action.doAction(action);
    }

    async printReport() {
        if (this.state.journalFilterEnabled && !this.state.journalIds.length) {
            this.notification.add(_t("Select at least one journal before printing."), { type: "warning" });
            return;
        }
        try {
            const action = await this.orm.call(
                "report.accounting_pdf_reports.report_cash_flow",
                "print_interactive_report",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    target_move: this.state.targetMove,
                    journal_ids: this.state.journalIds,
                    journal_filter_enabled: this.state.journalFilterEnabled,
                    display_detail: "accounts",
                }
            );
            return this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("The cash flow report could not be printed."), { type: "danger" });
        }
    }

    exportXlsx() {
        if (this.state.journalFilterEnabled && !this.state.journalIds.length) {
            this.notification.add(_t("Select at least one journal before exporting."), { type: "warning" });
            return;
        }
        const params = new URLSearchParams({
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
            target_move: this.state.targetMove,
            journal_ids: this.state.journalIds.join(","),
            journal_filter_enabled: this.state.journalFilterEnabled ? "1" : "0",
            scale: this.state.scale,
        });
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/accounting_pdf_reports/cash_flow/export?${params.toString()}`,
            target: "download",
        });
    }
}

registry.category("actions").add("accounting_pdf_reports.cash_flow", CashFlowReport);
