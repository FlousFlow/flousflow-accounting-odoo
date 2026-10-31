import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("ff_account_dashboard_kpi_reorder", {
    steps: () => [
        {
            trigger: ".o_account_dashboard_kpis > [data-kpi-id='invoices']",
            run: "drag_and_drop(.o_account_dashboard_kpis > [data-kpi-id='receivable'])",
        },
        {
            trigger: ".o_account_dashboard_kpis",
            async run() {
                const started = Date.now();
                let order;
                do {
                    order = [...document.querySelectorAll(".o_account_dashboard_kpis > [data-kpi-id]")]
                        .map((card) => card.dataset.kpiId);
                    if (order.indexOf("invoices") > order.indexOf("receivable")) {
                        const savedOrder = await rpc("/web/dataset/call_kw", {
                            model: "res.users",
                            method: "get_account_dashboard_kpi_order",
                            args: [],
                            kwargs: {},
                        });
                        if (JSON.stringify(savedOrder) === JSON.stringify(order)) {
                            return;
                        }
                    }
                    await new Promise((resolve) => setTimeout(resolve, 100));
                } while (Date.now() - started < 5000);
                throw new Error(`Dashboard KPI order was not visibly reordered and saved: ${order.join(", ")}`);
            },
        },
    ],
});
