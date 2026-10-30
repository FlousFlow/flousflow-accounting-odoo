import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ff_open_items_report", {
    steps: () => [
        {
            trigger: ".ff_open_items_toolbar",
            run() {
                const title = document.querySelector(".ff_open_items_toolbar h2")?.textContent.trim();
                if (title !== "Open Items") {
                    throw new Error(`Unexpected report title: ${title}`);
                }
                const filters = [...document.querySelectorAll(".ff_open_items_filters select")];
                if (filters.length !== 3 || !document.querySelector(".ff_open_items_filters input[type='date']")) {
                    throw new Error("Open Items is missing its date, account, move-state or currency-scale controls.");
                }
                const columns = [...document.querySelectorAll(".ff_open_items_table thead th")]
                    .map((cell) => cell.textContent.trim());
                const expected = [
                    "No Reminder", "Invoice Date", "Due Date", "Journal Item",
                    "Amount", "Amount Currency", "Residual", "Residual Currency",
                ];
                if (JSON.stringify(columns) !== JSON.stringify(expected)) {
                    throw new Error(`Open Items columns differ from Enterprise: ${JSON.stringify(columns)}`);
                }
                document.querySelector(".ff_open_items_toolbar button[aria-label='Report options']").click();
            },
        },
        {
            trigger: ".ff_open_items_toolbar .dropdown-menu.show .dropdown-item",
            run() {
                if (document.querySelector(".ff_open_items_toolbar .dropdown-item")?.textContent.trim() !== "XLSX") {
                    throw new Error("XLSX is missing from the Open Items report options.");
                }
                document.querySelector(".ff_open_items_toolbar .dropdown-item").click();
            },
        },
        {
            trigger: ".ff_open_items_toolbar",
            run() {
                if (!document.querySelector(".ff_open_items_table")) {
                    throw new Error("Open Items was not restored after the XLSX export.");
                }
            },
        },
    ],
});
