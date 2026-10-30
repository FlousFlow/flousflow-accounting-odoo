/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { deserializeDate } from "@web/core/l10n/dates";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class GeneralLedger extends Component {
    static template = "flousflow_accounting.apr__GeneralLedger";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        const today = DateTime.now();
        this.state = proxy({
            periodType: "month",
            periodAnchor: today.toISODate(),
            periodPickerOpen: false,
            dateFrom: "",
            dateTo: "",
            customDateFrom: "",
            customDateTo: "",
            customDateError: "",
            targetMove: "posted",
            cashBasis: false,
            scale: "unit",
            search: "",
            loading: true,
            lines: [],
            expandedIds: [],
            dismissedDraftWarning: false,
            settingsOpen: false,
            draftCount: 0,
            currencyId: false,
            companyName: "",
        });
        onWillStart(() => this.loadReport());
    }

    get periodLabel() {
        if (this.state.periodType === "custom") {
            return `${DateTime.fromISO(this.state.dateFrom).toLocaleString(DateTime.DATE_MED)} – ${DateTime.fromISO(this.state.dateTo).toLocaleString(DateTime.DATE_MED)}`;
        }
        const anchor = DateTime.fromISO(this.state.periodAnchor);
        if (this.state.periodType === "month") {
            return anchor.toFormat("LLLL yyyy");
        }
        return this.state.periodType === "quarter" ? `Q${anchor.quarter} ${anchor.year}` : `FY ${anchor.year}`;
    }

    getPeriodOptionLabel(periodType) {
        const anchor = DateTime.fromISO(this.state.periodAnchor);
        if (periodType === "month") {
            return anchor.toFormat("LLLL yyyy");
        }
        return periodType === "quarter" ? `Q${anchor.quarter} ${anchor.year}` : `FY ${anchor.year}`;
    }

    get visibleLines() {
        const query = this.state.search.trim().toLocaleLowerCase();
        if (!query) {
            return this.state.lines;
        }
        return this.state.lines.filter((line) =>
            `${line.code} ${line.name}`.toLocaleLowerCase().includes(query)
        );
    }

    get allVisibleExpanded() {
        return this.visibleLines.length > 0 && this.visibleLines.every(
            (line) => this.state.expandedIds.includes(line.account_id)
        );
    }

    get totals() {
        return this.state.lines.reduce((result, line) => ({
            debit: result.debit + line.debit,
            credit: result.credit + line.credit,
            balance: result.balance + line.balance,
        }), { debit: 0, credit: 0, balance: 0 });
    }

    async loadReport(accountIds = false) {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.flousflow_accounting.apr__report_general_ledger",
                "get_interactive_data",
                [false, false, this.state.targetMove, this.state.cashBasis, accountIds || [],
                    this.state.periodType, this.state.periodAnchor,
                    this.state.customDateFrom, this.state.customDateTo]
            );
            if (accountIds) {
                const selected = new Set(accountIds);
                this.state.lines = this.state.lines.map((line) => {
                    const details = data.lines.find((item) => item.account_id === line.account_id);
                    return selected.has(line.account_id) && details ? { ...line, move_lines: details.move_lines } : line;
                });
            } else {
                this.state.lines = data.lines;
                this.state.expandedIds = [];
                this.state.dismissedDraftWarning = false;
            }
            this.state.draftCount = data.draft_count;
            this.state.currencyId = data.currency_id;
            this.state.companyName = data.company_name;
            this.state.companyId = data.company_id;
            this.state.companyIds = data.company_ids;
            this.state.journalIds = data.journal_ids;
            this.state.dateFrom = data.date_from || "";
            this.state.dateTo = data.date_to || "";
            if (this.state.periodType !== "custom") {
                this.state.customDateFrom = data.date_from || "";
                this.state.customDateTo = data.date_to || "";
            }
        } catch (error) {
            this.notification.add(error.message || _t("The General Ledger could not be loaded."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async applyFilters() {
        await this.loadReport();
    }

    togglePeriodPicker() {
        this.state.periodPickerOpen = !this.state.periodPickerOpen;
    }

    async setPeriodType(periodType) {
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
        if (!unit) return;
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
                ? _t("Enter valid start and end dates.") : "";
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

    async toggleAccount(line) {
        const expanded = this.state.expandedIds.includes(line.account_id);
        if (expanded) {
            this.state.expandedIds = this.state.expandedIds.filter((id) => id !== line.account_id);
            return;
        }
        this.state.expandedIds = [...this.state.expandedIds, line.account_id];
        if (!line.move_lines) {
            await this.loadReport([line.account_id]);
        }
    }

    async toggleAll() {
        if (this.allVisibleExpanded) {
            this.state.expandedIds = this.state.expandedIds.filter(
                (id) => !this.visibleLines.some((line) => line.account_id === id)
            );
            return;
        }
        const ids = this.visibleLines.map((line) => line.account_id);
        this.state.expandedIds = [...new Set([...this.state.expandedIds, ...ids])];
        const missing = ids.filter((id) => !this.state.lines.find(
            (line) => line.account_id === id && line.move_lines
        ));
        if (missing.length) {
            await this.loadReport(missing);
        }
    }

    formatAmount(value) {
        const scales = {
            unit: { divisor: 1, digits: [69, 2], suffix: "" },
            rounded: { divisor: 1, digits: [69, 0], suffix: "" },
            thousand: { divisor: 1000, digits: [69, 2], suffix: "k" },
            million: { divisor: 1000000, digits: [69, 2], suffix: "M" },
        };
        const scale = scales[this.state.scale];
        return `${formatMonetary(value / scale.divisor, {
            currencyId: this.state.currencyId,
            digits: scale.digits,
        })}${scale.suffix}`;
    }

    formatDate(value) {
        if (!value) {
            return _t("Initial Balance");
        }
        return deserializeDate(value).toLocaleString(DateTime.DATE_SHORT);
    }

    async openJournalItems(accountId = false, drafts = false) {
        const { dateFrom, dateTo } = this.state;
        const action = await this.action.loadAction("account.action_account_moves_all");
        action.domain = [...(action.domain || []), ["company_id", "in", this.state.companyIds]];
        if (accountId) {
            action.domain.push(["account_id", "=", accountId]);
        }
        action.domain.push(["date", "<=", dateTo]);
        if (dateFrom && !drafts) {
            action.domain.push(["date", ">=", dateFrom]);
        }
        if (drafts) {
            action.domain.push(["parent_state", "=", "draft"]);
        }
        return this.action.doAction(action);
    }

    async printReport() {
        const { dateFrom, dateTo } = this.state;
        const action = await this.action.loadAction("flousflow_accounting.apr__action_account_general_ledger_menu");
        action.context = {
            ...action.context,
            default_date_from: dateFrom,
            default_date_to: dateTo,
            default_target_move: this.state.targetMove,
            default_journal_ids: this.state.journalIds,
            default_sortby: "sort_date",
            default_display_account: "movement",
            default_initial_balance: true,
        };
        return this.action.doAction(action);
    }

    exportReport(exportFormat) {
        const { dateFrom, dateTo } = this.state;
        const params = new URLSearchParams({
            export_format: exportFormat,
            date_from: dateFrom || "",
            date_to: dateTo,
            target_move: this.state.targetMove,
            cash_basis: this.state.cashBasis ? "1" : "0",
            scale: this.state.scale,
            search: this.state.search,
        });
        this.state.settingsOpen = false;
        return this.action.doAction({
            type: "ir.actions.act_url",
            url: `/accounting_pdf_reports/general_ledger/export?${params.toString()}`,
            target: "download",
        });
    }
}

registry.category("actions").add("flousflow_accounting.apr__general_ledger", GeneralLedger);
