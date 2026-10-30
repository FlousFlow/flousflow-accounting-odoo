/** @odoo-module **/

import { registry } from "@web/core/registry";

function waitFor(assertion, message) {
    return new Promise((resolve, reject) => {
        const started = Date.now();
        const check = () => {
            if (assertion()) {
                resolve();
            } else if (Date.now() - started > 10000) {
                reject(new Error(message));
            } else {
                setTimeout(check, 50);
            }
        };
        check();
    });
}

registry.category("web_tour.tours").add("ff_review_accrual_date_picker", {
    steps: () => [
        {
            trigger: ".ff_review_accrual_as_of input",
            run() {
                const input = document.querySelector(".ff_review_accrual_as_of input");
                const yesterday = new Date();
                yesterday.setDate(yesterday.getDate() - 1);
                window.ffReviewAsOfExpected = [
                    yesterday.getFullYear(),
                    String(yesterday.getMonth() + 1).padStart(2, "0"),
                    String(yesterday.getDate()).padStart(2, "0"),
                ].join("-");
                input.click();
            },
        },
        {
            trigger: ".o_datetime_picker .o_date_item_cell",
            run() {
                const day = window.ffReviewAsOfExpected.slice(-2);
                const cell = [...document.querySelectorAll(".o_datetime_picker .o_date_item_cell")]
                    .find((item) => item.innerText.trim() === day && !item.classList.contains("o_out_of_range"));
                if (!cell) {
                    throw new Error("Could not find yesterday in the date picker.");
                }
                cell.click();
            },
        },
        {
            trigger: ".ff_review_accrual_as_of input",
            async run() {
                await waitFor(
                    () => document.querySelector(".ff_review_accrual_as_of")?.dataset.asOfDate
                        === window.ffReviewAsOfExpected,
                    "The selected as-of date was not applied to the report action."
                );
            },
        },
    ],
});
