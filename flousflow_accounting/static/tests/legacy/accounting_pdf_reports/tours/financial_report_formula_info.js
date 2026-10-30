import { registry } from "@web/core/registry";

async function waitForFormula(expected, message) {
    const started = Date.now();
    while (Date.now() - started < 10000) {
        const formula = document.querySelector(".ff_fr_formula_popover .ff_fr_formula_row code")?.textContent.trim();
        if (formula === expected) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    const actual = document.querySelector(".ff_fr_formula_popover .ff_fr_formula_row code")?.textContent.trim();
    throw new Error(`${message}: ${actual}`);
}

registry.category("web_tour.tours").add("ff_balance_sheet_formula_info", {
    steps: () => [
        {
            trigger: ".ff_fr_table tbody tr",
            run() {
                const rows = [...document.querySelectorAll(".ff_fr_table tbody tr")].filter((row) =>
                    row.querySelector(".ff_fr_info_button")
                );
                if (!rows.length || rows.some((row) => !row.querySelector(".ff_fr_info_button i[data-icon='info']"))) {
                    throw new Error("The Balance Sheet info icon is missing from one or more report rows.");
                }
                const currentAssetsRow = [...document.querySelectorAll(".ff_fr_table tbody tr.ff_fr_group")]
                    .find((row) => row.textContent.includes("Current Assets"));
                if (!currentAssetsRow) {
                    throw new Error("The Current Assets report group is missing.");
                }
                currentAssetsRow.querySelector(".ff_fr_info_button").click();
            },
        },
        {
            trigger: ".ff_fr_formula_popover[role='dialog']",
            run() {
                const popover = document.querySelector(".ff_fr_formula_popover");
                const values = Object.fromEntries([...popover.querySelectorAll(".ff_fr_formula_row")].map((row) => [
                    row.querySelector("span")?.innerText.trim(),
                    row.querySelector("strong, code")?.innerText.trim(),
                ]));
                for (const label of ["Engine", "Label", "Formula", "Value"]) {
                    if (!values[label]) {
                        throw new Error(`Formula details are missing ${label}.`);
                    }
                }
                if (values.Engine !== "Aggregate Other Formulas" || values.Label !== "balance") {
                    throw new Error(`Current Assets formula metadata differs from Enterprise: ${JSON.stringify(values)}`);
                }
                if (values.Formula !== "BA.balance + REC.balance + CAS.balance + PRE.balance") {
                    throw new Error(`Current Assets formula differs from Enterprise: ${values.Formula}`);
                }
                if (!/^-?[\d,]+\.\d{2}$/.test(values.Value)) {
                    throw new Error(`Current Assets formula value is not an unscaled two-decimal amount: ${values.Value}`);
                }
            },
        },
        {
            trigger: ".ff_fr_toolbar .ff_fr_title button[aria-label='Report actions']",
            run: "click",
        },
        {
            trigger: ".ff_fr_toolbar .dropdown-menu .dropdown-item",
            run: "click",
        },
        {
            trigger: ".ff_fr_table",
            run() {
                if (!document.querySelector(".ff_fr_toolbar .ff_fr_title button[aria-label='Report actions']")) {
                    throw new Error("The financial report output menu was not restored after XLSX export.");
                }
            },
        },
    ],
});


registry.category("web_tour.tours").add("ff_balance_sheet_total_assets_formula", {
    steps: () => [
        {
            trigger: ".ff_fr_table tbody tr.ff_fr_total",
            run() {
                const totalAssetsRow = [...document.querySelectorAll(".ff_fr_table tbody tr.ff_fr_total")]
                    .find((row) => row.textContent.includes("Total ASSETS"));
                if (!totalAssetsRow) {
                    throw new Error("The Total ASSETS report row is missing.");
                }
                totalAssetsRow.querySelector(".ff_fr_info_button").click();
            },
        },
        {
            trigger: ".ff_fr_formula_popover[role='dialog']",
            run() {
                const formula = document.querySelector(".ff_fr_formula_popover .ff_fr_formula_row code")?.textContent.trim();
                if (formula !== "CA.balance + FA.balance + PNCA.balance") {
                    throw new Error("Total ASSETS formula differs from Enterprise: " + formula);
                }
            },
        },
    ],
});


registry.category("web_tour.tours").add("ff_profit_and_loss_revenue_formula_info", {
    steps: () => [
        {
            trigger: ".ff_fr_table tbody tr",
            run() {
                const revenueRow = [...document.querySelectorAll(".ff_fr_table tbody tr")]
                    .find((row) => row.classList.contains("ff_fr_account") &&
                        row.querySelector(".ff_fr_info_button") &&
                        row.querySelector("td")?.innerText.trim() === "Revenue");
                if (!revenueRow) {
                    throw new Error("The Revenue row with formula details is missing.");
                }
                revenueRow.querySelector(".ff_fr_info_button").click();
            },
        },
        {
            trigger: ".ff_fr_formula_popover[role='dialog']",
            run() {
                const popover = document.querySelector(".ff_fr_formula_popover");
                const values = Object.fromEntries([...popover.querySelectorAll(".ff_fr_formula_row")].map((row) => [
                    row.querySelector("span")?.innerText.trim(),
                    row.querySelector("strong, code")?.innerText.trim(),
                ]));
                if (values.Engine !== "Odoo Domain" || values.Label !== "balance" ||
                        values.Formula !== "[('account_id.account_type', '=', 'income')]" ||
                        values.Subformula !== "-sum") {
                    throw new Error(`Revenue formula metadata differs from Enterprise: ${JSON.stringify(values)}`);
                }
            },
        },
    ],
});


registry.category("web_tour.tours").add("ff_profit_and_loss_enterprise_summary", {
    steps: () => [
        {
            trigger: ".ff_fr_table tbody tr",
            run() {
                const rows = [...document.querySelectorAll(".ff_fr_table tbody tr")];
                const labels = rows.map((row) => row.querySelector("td")?.textContent.trim());
                const expected = [
                    "Revenue", "Cost of Revenue", "Gross Profit", "Operating Expenses",
                    "Operating Income (or Loss)", "Other Income", "Other Expenses",
                    "Net Income", "Distributions and Withdrawals",
                ];
                if (JSON.stringify(labels) !== JSON.stringify(expected)) {
                    throw new Error(`P&L rows differ from Enterprise: ${JSON.stringify(labels)}`);
                }
                if (rows.some((row) => ["Income", "Expense"].includes(row.querySelector("td")?.textContent.trim()))) {
                    throw new Error("Legacy Income/Expense wrappers are still displayed.");
                }
                for (const label of ["Gross Profit", "Operating Income (or Loss)", "Net Income"]) {
                    const row = rows.find((item) => item.querySelector("td")?.textContent.trim() === label);
                    if (!row?.classList.contains("ff_fr_total")) {
                        throw new Error(`${label} is not styled as a total row.`);
                    }
                }
                rows.find((row) => row.querySelector("td")?.textContent.trim() === "Gross Profit")
                    .querySelector(".ff_fr_info_button").click();
            },
        },
        {
            trigger: ".ff_fr_formula_popover[role='dialog']",
            run() {
                const formula = document.querySelector(".ff_fr_formula_popover .ff_fr_formula_row code")?.textContent.trim();
                if (formula !== "REV.balance - COS.balance") {
                    throw new Error("Gross Profit formula differs from Enterprise: " + formula);
                }
                const grossProfitRow = [...document.querySelectorAll(".ff_fr_table tbody tr")]
                    .find((row) => row.querySelector("td")?.textContent.trim() === "Gross Profit");
                grossProfitRow.querySelector(".ff_fr_info_button").click();
            },
        },
        {
            trigger: ".ff_fr_table tbody tr.ff_fr_total",
            run() {
                const netIncomeRow = [...document.querySelectorAll(".ff_fr_table tbody tr")]
                    .find((row) => row.querySelector("td")?.textContent.trim() === "Net Income");
                if (!netIncomeRow) {
                    throw new Error("Net Income summary row is missing.");
                }
                netIncomeRow.querySelector(".ff_fr_info_button").click();
            },
        },
        {
            trigger: ".ff_fr_formula_popover[role='dialog']",
            async run() {
                await waitForFormula(
                    "REV.balance + OIN.balance - COS.balance - EXP.balance - OEXP.balance",
                    "Net Income formula differs from Enterprise",
                );
            },
        },
    ],
});
