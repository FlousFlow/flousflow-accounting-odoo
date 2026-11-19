/** @odoo-module */

import { patch } from "@web/core/utils/patch";
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

    get displayedPaymentMethods() {
        return super.displayedPaymentMethods.filter((paymentMethod) =>
            this.isCreditMethodAllowed(paymentMethod)
        );
    },
});
