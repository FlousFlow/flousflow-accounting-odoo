import { registry } from "@web/core/registry";

async function waitForPeriodHeaders(expected) {
    const started = Date.now();
    while (Date.now() - started < 15000) {
        const headers = document.querySelectorAll(".ff_tax_table thead tr:first-child th[colspan='2']");
        if (headers.length === expected) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    const actual = document.querySelectorAll(".ff_tax_table thead tr:first-child th[colspan='2']").length;
    throw new Error(`Expected ${expected} tax report period columns, found ${actual}.`);
}

async function waitForTaxReport() {
    const started = Date.now();
    while (Date.now() - started < 15000) {
        if (document.querySelector(".ff_tax_table") && !document.querySelector(".ff_tax_report .fa-spinner")) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error("The selected tax report grouping did not finish loading.");
}

registry.category("web_tour.tours").add("ff_tax_report_comparison", {
    steps: () => [
        {
            trigger: ".ff_tax_report .ff_tax_table",
            run() {
                if (document.querySelectorAll(".ff_tax_table thead tr:first-child th[colspan='2']").length) {
                    throw new Error("The report starts with comparison columns enabled.");
                }
            },
        },
        {
            trigger: ".ff_tax_comparison .dropdown-toggle",
            run: "click",
        },
        {
            trigger: ".ff_tax_comparison .dropdown-menu.show",
            run() {
                const option = [...document.querySelectorAll(".ff_tax_comparison .dropdown-menu.show .dropdown-item")]
                    .find((item) => item.textContent.trim() === "Previous Period");
                if (!option) {
                    throw new Error("The Previous Period comparison option is missing.");
                }
                option.click();
            },
        },
        {
            trigger: ".ff_tax_table thead tr:first-child",
            async run() {
                await waitForPeriodHeaders(2);
                const menu = document.querySelector(".ff_tax_comparison .dropdown-toggle");
                menu.click();
                const started = Date.now();
                let input;
                while (Date.now() - started < 5000) {
                    input = document.querySelector(".ff_tax_comparison input[type='number']");
                    if (input) {
                        break;
                    }
                    await new Promise((resolve) => setTimeout(resolve, 50));
                }
                if (!input) {
                    throw new Error("The previous-period count control is missing.");
                }
                input.value = "2";
                input.dispatchEvent(new Event("change", { bubbles: true }));
                await waitForPeriodHeaders(3);
            },
        },
        {
            trigger: ".ff_tax_table",
            async run() {
                const selector = document.querySelector(".ff_tax_report select[aria-label='Report']");
                if (!selector) {
                    throw new Error("The tax report grouping selector is missing.");
                }
                selector.value = "account_tax";
                selector.dispatchEvent(new Event("change", { bubbles: true }));
                await waitForTaxReport();
                if (selector.value !== "account_tax") {
                    throw new Error("The Account > Tax grouping was not selected.");
                }
                selector.value = "tax_account";
                selector.dispatchEvent(new Event("change", { bubbles: true }));
                await waitForTaxReport();
                if (selector.value !== "tax_account") {
                    throw new Error("The Tax > Account grouping was not selected.");
                }
            },
        },
    ],
});
