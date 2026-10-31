import { patch } from "@web/core/utils/patch";
import { AccountDashboardKpis } from "@account/components/account_dashboard_kpis/account_dashboard_kpis";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(AccountDashboardKpis.prototype, {
    setup(...args) {
        super.setup(...args);
        this.notification = useService("notification");
    },

    async loadCards(...args) {
        await super.loadCards(...args);
        const order = await this.orm.call("res.users", "get_account_dashboard_kpi_order", []);
        if (order.length) {
            const positions = new Map(order.map((id, index) => [id, index]));
            const originalPositions = new Map(this.state.cards.map((card, index) => [card.id, index]));
            this.state.cards.sort((left, right) => {
                const leftPosition = positions.get(left.id) ?? order.length + originalPositions.get(left.id);
                const rightPosition = positions.get(right.id) ?? order.length + originalPositions.get(right.id);
                return leftPosition - rightPosition;
            });
        }
    },

    onKpiDragStart(event) {
        event.stopPropagation();
        const card = event.target.closest("[data-kpi-id]");
        if (!card) {
            event.preventDefault();
            return;
        }
        this.draggedKpiId = card.dataset.kpiId;
        if (event.dataTransfer) {
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", this.draggedKpiId);
        }
    },

    onKpiDragOver(event) {
        event.stopPropagation();
        if (this.draggedKpiId) {
            event.preventDefault();
            if (event.dataTransfer) {
                event.dataTransfer.dropEffect = "move";
            }
        }
    },

    onKpiDragBoundary(event) {
        event.stopPropagation();
    },

    async onKpiDrop(event) {
        event.preventDefault();
        event.stopPropagation();
        const target = event.target.closest("[data-kpi-id]");
        const sourceId = this.draggedKpiId || event.dataTransfer?.getData("text/plain");
        this.draggedKpiId = null;
        if (!target || !sourceId || sourceId === target.dataset.kpiId) {
            return;
        }
        const cards = [...this.state.cards];
        const sourceIndex = cards.findIndex((card) => card.id === sourceId);
        const targetIndex = cards.findIndex((card) => card.id === target.dataset.kpiId);
        if (sourceIndex < 0 || targetIndex < 0) {
            return;
        }
        const [moved] = cards.splice(sourceIndex, 1);
        cards.splice(targetIndex, 0, moved);
        const previousCards = this.state.cards;
        this.state.cards = cards;
        this.ignoreKpiClickUntil = Date.now() + 500;
        try {
            await this.orm.call("res.users", "save_account_dashboard_kpi_order", [
                cards.map((card) => card.id),
            ]);
        } catch (error) {
            this.state.cards = previousCards;
            this.notification.add(error.message || _t("The dashboard tile order could not be saved."), {
                type: "danger",
            });
        }
    },

    onClickCard(card) {
        if (this.ignoreKpiClickUntil > Date.now()) {
            this.ignoreKpiClickUntil = 0;
            return;
        }
        return super.onClickCard(card);
    },
});
