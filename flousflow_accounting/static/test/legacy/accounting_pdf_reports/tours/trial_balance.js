import { registry } from "@web/core/registry";

async function waitFor(assertion, message) {
    const started = Date.now();
    while (Date.now() - started < 10000) {
        if (assertion()) return;
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(message);
}

registry.category("web_tour.tours").add("ff_trial_balance_controls", {
    steps: () => [
        { trigger: ".ff_tb_period_picker button", run: "click" },
        {
            trigger: ".ff_tb_period_menu.show",
            run() {
                const labels = [...this.anchor.querySelectorAll(".ff_tb_period_option > .dropdown-item")]
                    .map((item) => item.textContent.trim());
                if (labels.join(",") !== "Month,Quarter,Fiscal Year") {
                    throw new Error(`Unexpected Trial Balance periods: ${labels.join(", ")}`);
                }
            },
        },
        { trigger: ".ff_tb_period_option:nth-child(2) .dropdown-item", run: "click" },
        { trigger: ".ff_tb_period_option:nth-child(2) .dropdown-item.active" },
        { trigger: ".ff_tb_period_menu > .dropdown-item", run: "click" },
        { trigger: ".ff_tb_period_menu input[aria-label='Start Date']" },
        { trigger: ".ff_tb_period_picker button", run: "click" },
        {
            trigger: ".ff_trial_balance button",
            run() {
                const button = [...document.querySelectorAll(".ff_trial_balance button")]
                    .find((item) => item.textContent.trim() === "Comparison");
                if (!button) throw new Error("Comparison control is missing.");
                button.click();
            },
        },
        { trigger: ".ff_tb_table thead tr:nth-child(2) th:nth-child(8)", run() {
            if (this.anchor.textContent.trim() !== "Previous Balance") {
                throw new Error("Comparison columns did not appear.");
            }
        } },
        {
            trigger: ".ff_tb_entry_filter",
            run() {
                if (!this.anchor.textContent.includes("Posted Entries")) {
                    throw new Error("Entry-basis filter is missing.");
                }
                this.anchor.click();
            },
        },
        {
            trigger: ".ff_tb_filters .ff_tb_cash_basis input[type='checkbox']",
            async run() {
                this.anchor.click();
                await waitFor(
                    () => document.querySelector(".ff_tb_entry_filter")?.textContent.includes("Cash Basis"),
                    "Cash Basis selection was not reflected in the toolbar."
                );
            },
        },
    ],
});
