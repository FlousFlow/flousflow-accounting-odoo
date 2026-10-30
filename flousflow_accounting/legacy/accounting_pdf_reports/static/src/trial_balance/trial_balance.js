/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";

const { DateTime } = luxon;

export class TrialBalance extends Component {
    static template = "flousflow_accounting.apr__TrialBalance";
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
            search: "",
            targetMove: "posted",
            cashBasis: false,
            displayAccount: "movement",
            comparison: false,
            scale: "unit",
            journals: [],
            journalIds: false,
            filterOpen: false,
            loading: true,
            lines: [],
            totals: {},
            draftCount: 0,
            dismissedDraftWarning: false,
            companyId: false,
            companyName: "",
            currencyId: false,
        });
        onWillStart(() => this.loadReport());
    }

    get periodLabel() {
        if (this.state.periodType === "custom") {
            return `${DateTime.fromISO(this.state.dateFrom).toLocaleString(DateTime.DATE_MED)} – ${DateTime.fromISO(this.state.dateTo).toLocaleString(DateTime.DATE_MED)}`;
        }
        return this.getPeriodOptionLabel(this.state.periodType);
    }

    getPeriodOptionLabel(periodType) {
        const anchor = DateTime.fromISO(this.state.periodAnchor);
        if (periodType === "month") return anchor.toFormat("LLLL yyyy");
        return periodType === "quarter" ? `Q${anchor.quarter} ${anchor.year}` : `FY ${anchor.year}`;
    }

    get periodColumnLabel() {
        if (this.state.periodType !== "custom" && this.state.dateFrom.slice(0, 7) === this.state.dateTo.slice(0, 7)) {
            return DateTime.fromISO(this.state.dateFrom).toFormat("LLLL yyyy");
        }
        const from = DateTime.fromISO(this.state.dateFrom);
        const to = DateTime.fromISO(this.state.dateTo);
        return `${from.toLocaleString(DateTime.DATE_MED)} – ${to.toLocaleString(DateTime.DATE_MED)}`;
    }

    get visibleLines() {
        const query = this.state.search.trim().toLocaleLowerCase();
        return query ? this.state.lines.filter((line) =>
            `${line.code} ${line.name}`.toLocaleLowerCase().includes(query)
        ) : this.state.lines;
    }

    get visibleTotals() {
        return this.visibleLines.reduce((totals, line) => {
            for (const key of ["opening_balance", "debit", "credit", "balance",
                "opening_balance_cmp", "debit_cmp", "credit_cmp", "balance_cmp"]) {
                totals[key] = (totals[key] || 0) + (line[key] || 0);
            }
            return totals;
        }, {});
    }

    async loadReport() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "report.flousflow_accounting.apr__report_trialbalance",
                "get_interactive_data",
                [this.state.periodType, this.state.periodAnchor,
                    this.state.customDateFrom, this.state.customDateTo,
                    this.state.targetMove, this.state.journalIds,
                    this.state.displayAccount, this.state.comparison, this.state.cashBasis]
            );
            this.state.lines = data.lines;
            this.state.totals = data.totals;
            this.state.dateFrom = data.date_from;
            this.state.dateTo = data.date_to;
            this.state.journals = data.journals;
            this.state.journalIds = data.journal_ids;
            this.state.draftCount = data.draft_count;
            this.state.companyId = data.company_id;
            this.state.companyName = data.company_name;
            this.state.currencyId = data.currency_id;
            this.state.dismissedDraftWarning = false;
            if (this.state.periodType !== "custom") {
                this.state.customDateFrom = data.date_from;
                this.state.customDateTo = data.date_to;
            }
        } catch (error) {
            this.notification.add(error.message || _t("The Trial Balance could not be loaded."), {
                type: "danger",
                sticky: true,
            });
            this.state.lines = [];
        } finally {
            this.state.loading = false;
        }
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

    async onCustomDateChange(key, event) {
        this.state[key] = event.target.value;
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

    async applyCustomDateRange() {
        return this.onCustomDateChange("customDateTo", { target: { value: this.state.customDateTo } });
    }

    async onJournalChange(event) {
        this.state.journalIds = Array.from(event.target.selectedOptions, (option) => Number(option.value));
        await this.loadReport();
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

    async openLineDetails(accountId, dateFrom, dateTo) {
        const action = await this.action.loadAction("account.action_account_moves_all");
        action.domain = [...(action.domain || []), ["account_id", "=", accountId],
            ["company_id", "child_of", this.state.companyId], ["date", "<=", dateTo]];
        if (dateFrom) action.domain.push(["date", ">=", dateFrom]);
        if (Array.isArray(this.state.journalIds)) {
            action.domain.push(["journal_id", "in", this.state.journalIds]);
        }
        if (this.state.targetMove === "posted") action.domain.push(["parent_state", "=", "posted"]);
        return this.action.doAction(action);
    }

    async openOpeningBalance(accountId) {
        const cutoff = DateTime.fromISO(this.state.dateFrom).minus({ days: 1 }).toISODate();
        return this.openLineDetails(accountId, false, cutoff);
    }

    async printReport() {
        const action = await this.action.loadAction("flousflow_accounting.apr__action_account_balance_menu");
        action.context = {
            ...action.context,
            default_date_from: this.state.dateFrom,
            default_date_to: this.state.dateTo,
            default_target_move: this.state.targetMove,
            default_journal_ids: this.state.journalIds,
            default_display_account: this.state.displayAccount,
            default_cash_basis: this.state.cashBasis,
        };
        return this.action.doAction(action);
    }
}

registry.category("actions").add("flousflow_accounting.apr__trial_balance", TrialBalance);
