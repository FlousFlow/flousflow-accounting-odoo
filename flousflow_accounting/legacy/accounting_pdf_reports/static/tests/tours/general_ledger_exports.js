import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ff_general_ledger_exports", {
    steps: () => [
        { trigger: ".ff_gl_period_picker button", run: "click" },
        {
            trigger: ".ff_gl_period_menu.show",
            run() {
                const options = [...this.anchor.querySelectorAll(".ff_gl_period_option > .dropdown-item")]
                    .map((item) => item.textContent.trim());
                if (options.join(",") !== "Month,Quarter,Fiscal Year") {
                    throw new Error(`Unexpected General Ledger period options: ${options.join(", ")}`);
                }
            },
        },
        { trigger: ".ff_gl_period_option:nth-child(2) .dropdown-item", run: "click" },
        {
            trigger: ".ff_gl_period_option:nth-child(2) .dropdown-item.active",
            run() {
                const label = document.querySelector(".ff_gl_period_picker button").textContent;
                if (!label.includes("Q")) {
                    throw new Error("Quarter selection was not reflected in the period label.");
                }
            },
        },
        { trigger: ".ff_gl_period_option:nth-child(3) .dropdown-item", run: "click" },
        {
            trigger: ".ff_gl_period_option:nth-child(3) .dropdown-item.active",
            run() {
                const label = document.querySelector(".ff_gl_period_picker button").textContent;
                if (!label.includes("FY")) {
                    throw new Error("Fiscal-year selection was not reflected in the period label.");
                }
            },
        },
        { trigger: ".ff_gl_period_menu > .dropdown-item", run: "click" },
        { trigger: ".ff_gl_period_menu input[aria-label='Start Date']" },
        { trigger: ".ff_gl_period_picker button", run: "click" },
        { trigger: ".ff_gl_settings button", run: "click" },
        {
            trigger: ".ff_gl_settings .dropdown-menu.show",
            run() {
                const options = [...this.anchor.querySelectorAll(".dropdown-item")]
                    .map((item) => item.textContent.trim());
                if (options.join(",") !== "XLSX,CSV") {
                    throw new Error(`Unexpected General Ledger export options: ${options.join(", ")}`);
                }
            },
        },
    ],
});
