/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    isCreditMethodAllowed(paymentMethod) {
        if (paymentMethod.type !== "pay_later") {
            return true;
        }
        if (!this.pos.company.pos_credit_restriction_block) {
            return true;
        }
        const partner = this.currentOrder.getPartner();
        const assignedPos = partner?.pos_credit_config_id;
        return !assignedPos || assignedPos.id === this.pos.config.id;
    },

    showPaymentMethod(paymentMethod) {
        return super.showPaymentMethod(paymentMethod) && this.isCreditMethodAllowed(paymentMethod);
    },
});
