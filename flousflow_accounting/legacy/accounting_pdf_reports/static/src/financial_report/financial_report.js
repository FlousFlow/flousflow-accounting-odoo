/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatFloat, formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { serializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class FinancialReport extends Component {
    static template = "accounting_pdf_reports.FinancialReport";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const today = DateTime.now();
        const isProfitLoss = String(this.props.action.context?.report_id) === String(
            this.props.action.context?.profit_loss_report_id
        );
        this.isProfitLoss = isProfitLoss;
        this.state = proxy({
            reportId: this.props.action.context?.report_id,
            printActionXmlid: this.props.action.context?.print_action_xmlid,
            title: "",
            dateFrom: isProfitLoss ? false : "",
            dateTo: isProfitLoss ? false : serializeDate(today),
            periodType: isProfitLoss ? "fiscal_year" : "as_of",
            periodAnchor: serializeDate(today),
            targetMove: "posted",
            cashBasis: false,
            cashBasisDomain: [],
            comparison: false,
            comparisonMode: "previous_period",
            comparisonPeriods: 1,
            comparisonSort: "descending",
            comparisonDateFrom: "",
            comparisonDateTo: "",
            comparisonDisplay: "amount",
            percentageOfRowKey: false,
            comparisonContext: false,
            comparisonContexts: [],
            debitCredit: false,
            scale: "unit",
            loading: true,
            lines: [],
            journals: [],
            journalIds: false,
            expanded: [],
            hideZero: false,
            draftCount: 0,
            dismissedDraftWarning: false,
            currencyId: false,
            companyId: false,
            companyName: "",
            budgetId: false,
            budgets: [],
            budgetSearch: "",
            budgetDialog: false,
            budgetName: "",
            budgetDateFrom: "",
            budgetDateTo: "",
            canEditFinancialBudget: false,
            formulaInfoKey: null,
        });
        onWillStart(() => this.loadReport());
    }

    get visibleLines() {
        const visible = [];
        const parents = [];
        for (const line of this.state.lines) {
            if (this.state.hideZero && this.isZeroDetail(line) && !this.hasNonzeroChildren(line)) {
                continue;
            }
            while (parents.length && parents[parents.length - 1].level >= line.level) {
                parents.pop();
            }
            const hidden = parents.some((parent) =>
                this.hasChildren(parent) && !this.state.expanded.includes(this.expansionKey(parent))
            );
            if (!hidden) {
                visible.push(line);
            }
            if (this.hasChildren(line)) {
                parents.push(line);
            }
        }
        return visible;
    }

    get periodLabel() {
        if (!this.state.dateFrom || !this.state.dateTo) {
            return _t("Fiscal Year");
        }
        const start = DateTime.fromISO(this.state.dateFrom);
        const end = DateTime.fromISO(this.state.dateTo);
        if (this.state.periodType === "month") {
            return `${_t("Month")} ${start.toFormat("LLL yyyy")}`;
        }
        if (this.state.periodType === "quarter") {
            return `${_t("Quarter")} ${start.toFormat("LLL")} – ${end.toFormat("LLL yyyy")}`;
        }
        if (this.state.periodType === "fiscal_year") {
            const years = start.year === end.year ? end.year : `${start.year}–${end.year}`;
            return `${_t("Fiscal Year")} ${years}`;
        }
        return `${start.toLocaleString(DateTime.DATE_MED)} – ${end.toLocaleString(DateTime.DATE_MED)}`;
    }

    get comparisonSourceLabel() {
        if (this.state.comparisonMode === "same_period_last_year") {
            return _t("Same Period Last Year");
        }
        if (this.state.comparisonMode === "custom") {
            return _t("Custom Dates");
        }
        return _t("Previous Period");
    }

    get comparisonBaseLines() {
        return this.state.lines.filter((line) =>
            ["report", "group", "category", "total"].includes(line.type)
        );
    }

    get periodColumns() {
        const columns = [{
            key: "current",
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
            index: -1,
        }];
        if (this.state.comparison && this.state.comparisonMode !== "percentage_of") {
            columns.push(...this.state.comparisonContexts.map((context, index) => ({
                key: `comparison-${index}`,
                date_from: context.date_from,
                date_to: context.date_to,
                index,
            })));
            columns.sort((left, right) => {
                const leftDate = left.date_from || left.date_to || "";
                const rightDate = right.date_from || right.date_to || "";
                const order = leftDate.localeCompare(rightDate);
                return this.state.comparisonSort === "ascending" ? order : -order;
            });
        }
        return columns;
    }

    get percentageOfBaseLine() {
        return this.comparisonBaseLines.find((line) =>
            String(this.formulaInfoKey(line)) === String(this.state.percentageOfRowKey)
        );
    }

    get selectedBudget() {
        return this.state.budgets.find((budget) => budget.id === this.state.budgetId);
    }

    get visibleBudgets() {
        const search = this.state.budgetSearch.trim().toLocaleLowerCase();
        if (!search) {
            return this.state.budgets;
        }
        return this.state.budgets.filter((budget) => budget.name.toLocaleLowerCase().includes(search));
    }

    formatPeriodRange(dateFrom, dateTo, periodType) {
        if (!dateFrom || !dateTo) {
            return _t("Balance");
        }
        const start = DateTime.fromISO(dateFrom);
        const end = DateTime.fromISO(dateTo);
        if (periodType === "month" && start.hasSame(end, "month")) {
            return start.toFormat("LLL yyyy");
        }
        if (periodType === "quarter") {
            return `${start.toFormat("LLL")} – ${end.toFormat("LLL yyyy")}`;
        }
        if (periodType === "fiscal_year" || (start.month === 1 && start.day === 1 &&
                end.month === 12 && end.day === 31)) {
            return start.year === end.year ? String(end.year) : `${start.year}–${end.year}`;
        }
        return `${start.toLocaleString(DateTime.DATE_MED)} – ${end.toLocaleString(DateTime.DATE_MED)}`;
    }

    async selectPeriod(periodType) {
        this.state.periodType = periodType;
        if (periodType === "custom") {
            return;
        }
        const anchor = serializeDate(DateTime.now().startOf("day"));
        this.state.periodAnchor = anchor;
        return this.loadPeriod(periodType, anchor);
    }

    async loadPeriod(periodType, anchor) {
        try {
            const dates = await this.orm.call(
                "report.accounting_pdf_reports.report_financial",
                "get_interactive_period_dates",
                [this.state.reportId, periodType, anchor]
            );
            this.state.dateFrom = dates.date_from;
            this.state.dateTo = dates.date_to;
            return this.loadReport();
        } catch (error) {
            this.notification.add(error.message || _t("The report period could not be loaded."), {
                type: "danger",
            });
        }
    }

    async movePeriod(direction) {
        const units = { month: "months", quarter: "months", fiscal_year: "years" };
        const unit = units[this.state.periodType];
        if (!unit) {
            return;
        }
        const multiplier = this.state.periodType === "quarter" ? 3 : 1;
        const anchor = DateTime.fromISO(this.state.periodAnchor).plus({ [unit]: direction * multiplier });
        this.state.periodAnchor = serializeDate(anchor);
        return this.loadPeriod(this.state.periodType, this.state.periodAnchor);
    }

    onCustomDateChange(field, event) {
        this.state.periodType = "custom";
        this.state[field] = event.target.value;
        if (this.state.dateFrom && this.state.dateTo && this.state.dateFrom > this.state.dateTo) {
            this.notification.add(_t("The start date must be on or before the end date."), {
                type: "warning",
            });
            return;
        }
        return this.loadReport();
    }

    isZeroDetail(line) {
        return ["account", "category"].includes(line.type) &&
            Math.abs(line.balance || 0) < 0.005 &&
            Math.abs(line.debit || 0) < 0.005 &&
            Math.abs(line.credit || 0) < 0.005 &&
            Math.abs(line.balance_cmp || 0) < 0.005;
    }

    hasNonzeroChildren(line) {
        const index = this.state.lines.indexOf(line);
        for (const child of this.state.lines.slice(index + 1)) {
            if (child.level <= line.level) {
                break;
            }
            if (!this.isZeroDetail(child)) {
                return true;
            }
        }
        return false;
    }

    hasChildren(line) {
        if (!["report", "group", "category"].includes(line.type)) {
            return false;
        }
        const index = this.state.lines.indexOf(line);
        return this.state.lines.slice(index + 1).some((item) => item.level > line.level);
    }

    expansionKey(line) {
        return line.row_key || line.report_id;
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.accounting_pdf_reports.report_financial",
                "get_interactive_data",
                [this.state.reportId, this.state.dateFrom || false, this.state.dateTo,
                    this.state.targetMove, this.state.journalIds, this.state.comparison,
                    this.state.debitCredit, null, this.isProfitLoss ? this.state.periodType : false,
                    this.state.comparisonMode, this.state.comparisonDateFrom || false,
                    this.state.comparisonDateTo || false, this.state.comparisonPeriods,
                    null, this.state.budgetId || false, this.state.cashBasis]
            );
            if (this.isProfitLoss && this.state.periodType === "fiscal_year" &&
                    !this.state.dateFrom && !this.state.dateTo) {
                this.state.dateFrom = data.date_from;
                this.state.dateTo = data.date_to;
            }
            this.state.title = data.name;
            this.state.lines = data.lines;
            this.state.comparisonContext = data.comparison_context || false;
            this.state.comparisonContexts = data.comparison_contexts ||
                (data.comparison_context ? [data.comparison_context] : []);
            this.state.expanded = [...data.expanded_report_ids, ...data.expanded_group_keys];
            this.state.journals = data.journals;
            if (this.state.journalIds === false) {
                this.state.journalIds = data.journal_ids;
            }
            this.state.draftCount = data.draft_count;
            this.state.cashBasisDomain = data.cash_basis_domain || [];
            this.state.currencyId = data.currency_id;
            this.state.companyId = data.company_id;
            this.state.companyName = data.company_name;
            this.state.canEditFinancialBudget = data.can_edit_financial_budget;
            if (this.isProfitLoss) {
                this.state.budgets = await this.orm.searchRead(
                    "account.financial.budget",
                    [["company_id", "=", data.company_id]],
                    ["name", "date_from", "date_to"],
                    { order: "date_from desc, name" }
                );
                this.state.budgets = this.state.budgets.map((budget) => ({
                    ...budget,
                    name: budget.name,
                }));
            }
            this.state.dismissedDraftWarning = false;
        } catch (error) {
            this.notification.add(error.message || _t("The report could not be loaded."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async selectBudget(budgetId) {
        this.state.budgetId = Number(budgetId) || false;
        this.state.budgetSearch = "";
        await this.loadReport();
    }

    openBudgetDialog() {
        this.state.budgetName = this.state.budgetSearch.trim();
        this.state.budgetSearch = "";
        this.state.budgetDateFrom = this.state.dateFrom || "";
        this.state.budgetDateTo = this.state.dateTo || "";
        this.state.budgetDialog = true;
    }

    async createFinancialBudget() {
        const { budgetName, budgetDateFrom, budgetDateTo } = this.state;
        if (!budgetName.trim() || !budgetDateFrom || !budgetDateTo || budgetDateFrom > budgetDateTo) {
            this.notification.add(_t("Enter a name and a valid date range for the budget."), {
                type: "warning",
            });
            return;
        }
        try {
            const ids = await this.orm.create("account.financial.budget", [{
                name: budgetName.trim(),
                date_from: budgetDateFrom,
                date_to: budgetDateTo,
                company_id: this.state.companyId,
            }]);
            this.state.budgetId = ids[0];
            this.state.budgetDialog = false;
            await this.loadReport();
            this.notification.add(_t("Budget created. Enter planned amounts in the budget column."), {
                type: "success",
            });
        } catch (error) {
            this.notification.add(error.message || _t("The budget could not be created."), {
                type: "danger",
            });
        }
    }

    async saveBudgetLine(line, event) {
        const amount = Number(event.target.value || 0);
        if (!Number.isFinite(amount) || !this.state.budgetId || !line.account_id) {
            return;
        }
        try {
            const values = {
                budget_id: this.state.budgetId,
                account_id: line.account_id,
                planned_amount: amount,
            };
            if (line.budget_line_id) {
                await this.orm.write("account.financial.budget.line", [line.budget_line_id], values);
            } else {
                await this.orm.create("account.financial.budget.line", [values]);
            }
            await this.loadReport();
        } catch (error) {
            this.notification.add(error.message || _t("The budget amount could not be saved."), {
                type: "danger",
            });
        }
    }

    onDateChange(field, event) {
        this.state[field] = event.target.value;
        return this.loadReport();
    }

    setComparisonMode(mode) {
        this.state.comparisonMode = mode;
        this.state.comparison = mode !== "none";
        if (mode === "percentage_of") {
            return this.state.percentageOfRowKey ? this.loadReport() : undefined;
        }
        if (mode === "custom" && !this.state.comparisonDateFrom) {
            const from = this.state.dateFrom ? DateTime.fromISO(this.state.dateFrom) : false;
            const to = DateTime.fromISO(this.state.dateTo);
            this.state.comparisonDateFrom = from ? serializeDate(from.minus({ years: 1 })) : "";
            this.state.comparisonDateTo = serializeDate(to.minus({ years: 1 }));
        }
        return this.loadReport();
    }

    selectPercentageOfRow(event) {
        this.state.percentageOfRowKey = event.target.value;
        this.state.comparisonMode = "percentage_of";
        this.state.comparison = true;
        return this.loadReport();
    }

    onComparisonPeriodsChange(event) {
        this.state.comparisonPeriods = Math.max(1, Number(event.target.value) || 1);
        return this.loadReport();
    }

    onComparisonDateChange(field, event) {
        this.state[field] = event.target.value;
        if (this.state.comparisonDateFrom && this.state.comparisonDateTo &&
                this.state.comparisonDateFrom > this.state.comparisonDateTo) {
            this.notification.add(_t("The comparison start date must be on or before its end date."), {
                type: "warning",
            });
            return;
        }
        if (this.state.comparisonDateFrom && this.state.comparisonDateTo) {
            return this.loadReport();
        }
    }

    comparisonChange(line) {
        const current = Number(line.balance || 0);
        const previous = Number(line.balance_cmp_list?.[0] ?? line.balance_cmp ?? 0);
        if (this.state.comparisonMode === "percentage_of") {
            const base = Number(this.percentageOfBaseLine?.balance || 0);
            return Math.abs(base) < 0.005 ? _t("N/A") : `${(current / base * 100).toFixed(2)}%`;
        }
        if (this.state.comparisonDisplay === "percentage") {
            return Math.abs(previous) < 0.005 ? (Math.abs(current) < 0.005 ? "0.00%" : _t("N/A"))
                : `${((current - previous) / Math.abs(previous) * 100).toFixed(2)}%`;
        }
        return this.formatAmount(current - previous);
    }

    comparisonAmount(line, index) {
        return Number(line.balance_cmp_list?.[index] ?? (index === 0 ? line.balance_cmp : 0) ?? 0);
    }

    periodColumnAmount(line, column) {
        return column.index < 0 ? Number(line.balance || 0) : this.comparisonAmount(line, column.index);
    }

    onJournalsChange(event) {
        this.state.journalIds = Array.from(event.target.selectedOptions, (option) => Number(option.value));
        return this.loadReport();
    }

    toggleLine(line) {
        const key = this.expansionKey(line);
        this.state.expanded = this.state.expanded.includes(key)
            ? this.state.expanded.filter((id) => id !== key)
            : [...this.state.expanded, key];
    }

    formulaInfoKey(line) {
        return line.row_key || `report-${line.report_id || line.name}`;
    }

    toggleFormulaInfo(line) {
        const key = this.formulaInfoKey(line);
        this.state.formulaInfoKey = this.state.formulaInfoKey === key ? null : key;
    }

    toggleAllLines() {
        const expandable = this.state.lines.filter((line) => this.hasChildren(line));
        const allExpanded = this.areAllLinesExpanded();
        this.state.expanded = allExpanded ? [] : expandable.map((line) => this.expansionKey(line));
    }

    areAllLinesExpanded() {
        const expandable = this.state.lines.filter((line) => this.hasChildren(line));
        return expandable.length > 0 && expandable.every((line) =>
            this.state.expanded.includes(this.expansionKey(line))
        );
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
            currencyId: this.state.currencyId,
            digits: scale.digits,
        })}${scale.suffix}`;
    }

    formatFormulaValue(value) {
        return formatFloat(value || 0, { digits: [69, 2] });
    }

    async openLineDetails(line) {
        const accountIds = line.account_ids || (line.account_id ? [line.account_id] : []);
        if (!accountIds.length) {
            return;
        }
        const action = await this.action.loadAction("account.action_account_moves_all");
        const dateFrom = line.detail_date_from ?? this.state.dateFrom;
        const dateTo = line.detail_date_to ?? this.state.dateTo;
        action.domain = [...(action.domain || []), ["account_id", "in", accountIds], ["date", "<=", dateTo]];
        if (dateFrom) {
            action.domain.push(["date", ">=", dateFrom]);
        }
        action.domain.push(["company_id", "child_of", this.state.companyId]);
        if (Array.isArray(this.state.journalIds)) {
            action.domain.push(["journal_id", "in", this.state.journalIds]);
        }
        if (this.state.cashBasis) {
            action.domain.push(...this.state.cashBasisDomain);
        }
        return this.action.doAction(action);
    }

    async openAccount(accountId) {
        return this.openLineDetails({ account_id: accountId });
    }

    async openPrintOptions() {
        const action = await this.action.loadAction(this.state.printActionXmlid);
        const comparisonContext = this.state.comparisonContext || {};
        const hasPeriodComparison = this.state.comparison && this.state.comparisonMode !== "percentage_of";
        action.context = {
            ...action.context,
            default_date_from: this.state.dateFrom || false,
            default_date_to: this.state.dateTo,
            default_target_move: this.state.targetMove,
            default_cash_basis: this.state.cashBasis,
            default_journal_ids: this.state.journalIds,
            default_enable_filter: hasPeriodComparison,
            default_label_filter: this.comparisonSourceLabel,
            default_filter_cmp: hasPeriodComparison ? "filter_date" : "filter_no",
            default_date_from_cmp: hasPeriodComparison ? comparisonContext.date_from || false : false,
            default_date_to_cmp: hasPeriodComparison ? comparisonContext.date_to || false : false,
            default_debit_credit: this.state.debitCredit,
            default_comparison_period_ranges: hasPeriodComparison
                ? this.state.comparisonContexts.map(({ date_from, date_to }) => ({ date_from, date_to }))
                : [],
            default_comparison_sort: this.state.comparisonSort,
            default_comparison_display: this.state.comparisonDisplay,
            default_comparison_mode: this.state.comparisonMode,
            default_percentage_of_row_key: this.state.percentageOfRowKey || false,
            default_financial_budget_id: this.state.budgetId || false,
        };
        return this.action.doAction(action);
    }

    async exportXlsx() {
        try {
            const comparisonContext = this.state.comparisonContext || {};
            const hasPeriodComparison = this.state.comparison && this.state.comparisonMode !== "percentage_of";
            const wizardIds = await this.orm.create("accounting.report", [{
                account_report_id: this.state.reportId,
                company_id: this.state.companyId,
                date_from: this.state.dateFrom || false,
                date_to: this.state.dateTo,
                journal_ids: [[6, 0, this.state.journalIds || []]],
                target_move: this.state.targetMove,
                cash_basis: this.state.cashBasis,
                enable_filter: hasPeriodComparison,
                label_filter: this.comparisonSourceLabel,
                filter_cmp: hasPeriodComparison ? "filter_date" : "filter_no",
                date_from_cmp: hasPeriodComparison ? comparisonContext.date_from || false : false,
                date_to_cmp: hasPeriodComparison ? comparisonContext.date_to || false : false,
                debit_credit: this.state.debitCredit,
                comparison_period_ranges: hasPeriodComparison
                    ? this.state.comparisonContexts.map(({ date_from, date_to }) => ({ date_from, date_to }))
                    : [],
                comparison_sort: this.state.comparisonSort,
                comparison_display: this.state.comparisonDisplay,
                comparison_mode: this.state.comparisonMode,
                percentage_of_row_key: this.state.percentageOfRowKey || false,
                financial_budget_id: this.state.budgetId || false,
            }]);
            const action = await this.orm.call(
                "accounting.report", "action_export_xlsx", [[wizardIds[0]]]
            );
            return this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || _t("The Excel report could not be exported."), {
                type: "danger",
            });
        }
    }

    async printReport() {
        return this.openPrintOptions();
    }
}

registry.category("actions").add("accounting_pdf_reports.financial_report", FinancialReport);
