/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    isCreditMethodAllowed(paymentMethod) {
        if (paymentMethod.type !== "pay_later") {
            return true;
        }
        // Keep the server as the final authority.  Default to enforcing in
        // the UI when an older cached POS payload has not loaded the flag yet.
        if (this.pos.company?.pos_credit_restriction_block === false) {
            return true;
        }
        const partner = this.currentOrder.getPartner();
        const assignedPos = partner?.pos_credit_config_id;
        const assignedPosId =
            assignedPos?.id || (Array.isArray(assignedPos) ? assignedPos[0] : assignedPos);
        return !assignedPosId || Number(assignedPosId) === Number(this.pos.config.id);
    },

    showPaymentMethod(paymentMethod) {
        return super.showPaymentMethod(paymentMethod) && this.isCreditMethodAllowed(paymentMethod);
    },

    async addNewPaymentLine(paymentMethod, args = {}) {
        // A cashier may have added Customer Account before selecting the
        // restricted contact, or before the POS contact cache was refreshed.
        // When they choose an immediate method at the wrong POS, remove that
        // stale credit line first so this order is no longer treated as credit.
        if (
            paymentMethod.type !== "pay_later" &&
            !this.currentOrder.isRefund &&
            !this.isCreditMethodAllowed({ type: "pay_later" })
        ) {
            const staleCreditLines = this.paymentLines.filter(
                (line) => line.payment_method_id.type === "pay_later"
            );
            for (const line of staleCreditLines) {
                this.deletePaymentLine(line.uuid);
            }
            if (staleCreditLines.length) {
                this.notification.add(
                    _t("The previous Customer Account payment was removed. This customer can only use immediate payment at this point of sale."),
                    { type: "warning" }
                );
            }
        }
        return super.addNewPaymentLine(paymentMethod, args);
    },

    get displayedPaymentMethods() {
        return super.displayedPaymentMethods.filter((paymentMethod) =>
            this.isCreditMethodAllowed(paymentMethod)
        );
    },
});
