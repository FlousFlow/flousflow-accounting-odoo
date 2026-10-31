import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ff_executive_summary", {
    steps: () => [
        {
            trigger: ".ff_es_group",
            run() {
                const groups = [...document.querySelectorAll(".ff_es_group h3")].map((node) => node.textContent.trim());
                for (const expected of ["Cash", "Profitability", "Balance Sheet", "Performance", "Operational"]) {
                    if (!groups.includes(expected)) {
                        throw new Error(`Executive Summary is missing ${expected}.`);
                    }
                }
                const cards = [...document.querySelectorAll(".ff_es_card")];
                if (cards.length < 15 || cards.some((card) => !card.querySelector(".fa-info-circle"))) {
                    throw new Error("Executive Summary KPI cards or formula details are missing.");
                }
            },
        },
        {
            trigger: ".ff_es_check input[type='checkbox']",
            run() {
                const comparison = [...document.querySelectorAll(".ff_es_check")]
                    .find((label) => label.textContent.includes("Comparison"));
                comparison.querySelector("input").click();
            },
        },
        {
            trigger: ".ff_es_compare",
            run() {
                if (![...document.querySelectorAll(".ff_es_compare")].some((node) => node.textContent.includes("Previous period"))) {
                    throw new Error("Comparison values did not appear after enabling comparison.");
                }
            },
        },
    ],
});
