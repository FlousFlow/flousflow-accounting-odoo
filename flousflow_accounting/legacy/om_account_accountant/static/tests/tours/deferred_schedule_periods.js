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
    return document.querySelector(".ff_deferred_period")?.innerText.trim() || "";
}

async function fillDateAndWait(input, value) {
    input.value = value;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    await waitFor(
        () => !document.querySelector(".o_ff_deferred_schedule .fa-spinner.fa-spin"),
        "Deferred schedule period reload did not finish."
    );
}

registry.category("web_tour.tours").add("ff_deferred_schedule_periods", {
    steps: () => [
        {
            trigger: ".o_ff_deferred_schedule .ff_deferred_title",
            run() {
                const title = document.querySelector(".o_ff_deferred_schedule .ff_deferred_title");
                if (title.parentElement.innerText.trim() !== title.innerText.trim()) {
                    throw new Error("Deferred Schedule should show only the report title in its header.");
                }
            },
        },
        { trigger: ".ff_deferred_options button", run: "click" },
        { trigger: ".ff_deferred_unfold_all", run: "click" },
        {
            trigger: ".ff_deferred_unfold_all",
            run() {
                if (!this.anchor.checked) {
                    throw new Error("Unfold All did not stay enabled.");
                }
            },
        },
        { trigger: ".ff_deferred_unfold_all", run: "click" },
        {
            trigger: ".ff_deferred_unfold_all",
            run() {
                if (this.anchor.checked) {
                    throw new Error("Unfold All did not stay disabled.");
                }
            },
        },
        { trigger: ".o_ff_deferred_schedule .ff_deferred_period", run: "click" },
        {
            trigger: ".ff_deferred_period_option:nth-child(2) .dropdown-item",
            run: "click",
        },
        {
            trigger: ".o_ff_deferred_schedule .ff_deferred_period",
            async run() {
                await waitFor(() => /Q[1-4]/.test(periodLabel()), "Quarter selection did not update the report.");
            },
        },
        {
            trigger: ".ff_deferred_period_option:nth-child(3) .dropdown-item",
            run: "click",
        },
        {
            trigger: ".o_ff_deferred_schedule .ff_deferred_period",
            async run() {
                await waitFor(() => periodLabel().startsWith("FY "), "Fiscal year selection did not update the report.");
            },
        },
        { trigger: ".ff_deferred_period", run: "click" },
        { trigger: ".ff_deferred_period_menu .dropdown-item:last-of-type", run: "click" },
        {
            trigger: ".ff_deferred_custom_period input[aria-label='Start Date']",
            run: async function () {
                await fillDateAndWait(this.anchor, "2026-09-10");
            },
        },
        {
            trigger: ".ff_deferred_custom_period input[aria-label='End Date']",
            run: async function () {
                await fillDateAndWait(this.anchor, "2026-09-19");
            },
        },
        {
            trigger: ".o_ff_deferred_schedule .ff_deferred_period",
            run() {
                const dates = [...document.querySelectorAll(".ff_deferred_custom_period input")]
                    .map((input) => input.value);
                if (dates[0] !== "2026-09-10" || dates[1] !== "2026-09-19") {
                    throw new Error(`Custom deferred dates were not applied: ${dates.join(" to ")}`);
                }
            },
        },
    ],
});
