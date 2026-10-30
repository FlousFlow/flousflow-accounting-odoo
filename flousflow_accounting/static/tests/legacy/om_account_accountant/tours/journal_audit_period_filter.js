import { registry } from "@web/core/registry";

async function waitFor(assertion, message) {
    const started = Date.now();
    while (Date.now() - started < 10000) {
        if (assertion()) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(message);
}

function periodLabel() {
    return document.querySelector(".ff_journal_audit_period_picker > button")?.innerText.trim() || "";
}

async function fillDateAndWait(input, value) {
    input.value = value;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await new Promise((resolve, reject) => {
        const started = Date.now();
        const check = () => {
            const loading = document.querySelector(".o_ff_journal_audit .fa-spinner.fa-spin");
            if (!loading) {
                resolve();
            } else if (Date.now() - started > 10000) {
                reject(new Error("Journal Audit period reload did not finish."));
            } else {
                setTimeout(check, 50);
            }
        };
        setTimeout(check, 50);
    });
}

registry.category("web_tour.tours").add("ff_journal_audit_period_filter", {
    steps: () => [
        {
            trigger: ".o_ff_journal_audit .ff_journal_audit_control_panel",
            async run() {
                const filters = document.querySelector(".ff_journal_audit_filters");
                const toggle = document.querySelector(".ff_journal_audit_filter_toggle");
                if (window.innerWidth >= 768) {
                    if (!filters || getComputedStyle(filters).display === "none") {
                        throw new Error("Journal Audit filters should be visible on desktop.");
                    }
                    if (toggle && getComputedStyle(toggle).display !== "none") {
                        throw new Error("The filter toggle should be hidden on desktop.");
                    }
                } else {
                    if (!filters || getComputedStyle(filters).display !== "none") {
                        throw new Error("Journal Audit filters should start collapsed on mobile.");
                    }
                    toggle?.click();
                    await waitFor(
                        () => getComputedStyle(filters).display !== "none",
                        "The mobile filter toggle should show Journal Audit filters."
                    );
                }
            },
        },
        {
            trigger: ".o_ff_journal_audit .ff_journal_audit_table",
            run() {
                const zeroPendingJournals = [...document.querySelectorAll(".ff_journal_audit_journal")]
                    .filter((row) => row.querySelector("td:nth-child(2)")?.innerText.trim() === "0");
                if (zeroPendingJournals.some((row) => !row.querySelector(".ff_journal_audit_review"))) {
                    throw new Error("The audit action should remain visible when a journal has no pending reviews.");
                }
            },
        },
        { trigger: ".ff_journal_audit_period_picker > button", run: "click" },
        {
            trigger: ".ff_journal_audit_period_option:nth-child(1) .dropdown-item",
            run: "click",
        },
        {
            trigger: ".ff_journal_audit_period_picker > button",
            async run() {
                await waitFor(
                    () => /January|February|March|April|May|June|July|August|September|October|November|December/i.test(periodLabel()),
                    `Month period was not selected. Current label: ${periodLabel() || "missing"}`
                );
            },
        },
        { trigger: ".ff_journal_audit_period_picker > button", run: "click" },
        {
            trigger: ".ff_journal_audit_period_option:nth-child(2) .dropdown-item",
            run: "click",
        },
        {
            trigger: ".ff_journal_audit_period_picker > button",
            async run() {
                await waitFor(
                    () => /Q[1-4]/.test(periodLabel()),
                    `Quarter period was not selected. Current label: ${periodLabel() || "missing"}`
                );
                window.ffJournalAuditQuarterBefore = periodLabel();
            },
        },
        {
            trigger: ".ff_journal_audit_period_picker > button",
            run: "click",
        },
        {
            trigger: ".ff_journal_audit_period_option:nth-child(2) button[aria-label='Next quarter']",
            run: "click",
        },
        {
            trigger: ".o_ff_journal_audit .ff_journal_audit_table",
            async run() {
                await waitFor(() => {
                    const current = periodLabel();
                    return current && current !== window.ffJournalAuditQuarterBefore;
                }, "Quarter navigation did not change the report period");
            },
        },
        {
            trigger: ".ff_journal_audit_period_option:nth-child(3) .dropdown-item",
            run: "click",
        },
        {
            trigger: ".o_ff_journal_audit .ff_journal_audit_table",
            async run() {
                await waitFor(
                    () => /^\d{4}(?:–\d{4})?$/.test(periodLabel()),
                    `Fiscal year period was not selected. Current label: ${periodLabel() || "missing"}`
                );
            },
        },
        { trigger: ".ff_journal_audit_period_picker > button", run: "click" },
        {
            trigger: ".ff_journal_audit_custom_period input[aria-label='Start Date']",
            run: async function () {
                await fillDateAndWait(this.anchor, "2026-01-10");
            },
        },
        {
            trigger: ".ff_journal_audit_custom_period input[aria-label='End Date']",
            run: async function () {
                await fillDateAndWait(this.anchor, "2026-02-20");
            },
        },
        {
            trigger: ".o_ff_journal_audit .ff_journal_audit_table",
            run() {
                const dates = [...document.querySelectorAll(".ff_journal_audit_custom_period input")].map((input) => input.value);
                if (dates[0] !== "2026-01-10" || dates[1] !== "2026-02-20") {
                    throw new Error(`Custom dates were not applied: ${dates.join(" to ")}`);
                }
            },
        },
        { trigger: ".ff_journal_audit_tax_audit", run: "click" },
        {
            trigger: ".o_list_view",
            async run() {
                if (!document.body.innerText.includes("Taxes Applied")) {
                    throw new Error("The Journal Audit tax action did not open the Taxes Applied list.");
                }
                await waitFor(() => {
                    const groupByText = [...document.querySelectorAll(".o_searchview_facet")]
                        .filter((facet) => facet.querySelector(".o_facet_groupby"))
                        .map((facet) => facet.innerText)
                        .join(" ");
                    return groupByText.includes("Taxes") && groupByText.includes("Account");
                }, "Taxes Applied should be grouped by tax and account.");
            },
        },
    ],
});

registry.category("web_tour.tours").add("ff_journal_audit_mobile_filters", {
    steps: () => [
        {
            trigger: ".o_ff_journal_audit .ff_journal_audit_control_panel",
            async run() {
                if (window.innerWidth >= 768) {
                    throw new Error(`Expected mobile viewport, got ${window.innerWidth}px.`);
                }
                const filters = document.querySelector(".ff_journal_audit_filters");
                const toggle = document.querySelector(".ff_journal_audit_filter_toggle");
                if (!filters || !toggle || getComputedStyle(toggle).display === "none") {
                    throw new Error("The mobile filter toggle should be visible.");
                }
                if (getComputedStyle(filters).display !== "none") {
                    throw new Error("Journal Audit filters should start collapsed on mobile.");
                }
                toggle.click();
                await waitFor(
                    () => getComputedStyle(filters).display !== "none",
                    "The mobile filter toggle should show Journal Audit filters."
                );
                if (toggle.getAttribute("aria-expanded") !== "true") {
                    throw new Error("The mobile filter toggle should report its expanded state.");
                }
            },
        },
        { trigger: ".ff_journal_audit_period_picker > button" },
    ],
});

registry.category("web_tour.tours").add("ff_journal_audit_entry_group", {
    steps: () => [
        {
            trigger: ".ff_journal_audit_journal .ff_journal_audit_review",
            run: "click",
        },
        {
            trigger: ".o_list_view",
            async run() {
                await waitFor(() => {
                    return [...document.querySelectorAll(".o_searchview_facet")].some((facet) =>
                        facet.querySelector(".o_facet_groupby") && facet.innerText.includes("Journal Entry")
                    );
                }, "Journal Audit should open Journal Items grouped by Journal Entry.");
                await waitFor(() => {
                    const columns = [...document.querySelectorAll(".o_list_view thead th")]
                        .map((header) => header.innerText.trim())
                        .filter(Boolean);
                    return JSON.stringify(columns) === JSON.stringify([
                        "Invoice Date", "Account", "Description", "Taxes", "Debit", "Credit",
                    ]);
                }, "Journal Audit drill-down columns should match Enterprise.");
            },
        },
    ],
});
