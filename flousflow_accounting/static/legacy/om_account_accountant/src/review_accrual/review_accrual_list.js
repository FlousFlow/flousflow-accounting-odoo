/** @odoo-module **/

import { DateTimeInput } from "@web/core/datetime/datetime_input";
import { serializeDate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

const { DateTime } = luxon;

export class ReviewAccrualListController extends ListController {
    static components = {
        ...ListController.components,
        DateTimeInput,
    };

    setup() {
        super.setup();
        const date = this.props.context.accrual_entry_date;
        this.reviewAsOfDate = date ? DateTime.fromISO(date) : DateTime.now();
    }

    async onReviewAsOfDateApply(date) {
        if (!date) {
            return;
        }
        const action = await this.actionService.loadAction(this.env.config.actionId);
        await this.actionService.doAction(action, {
            additionalContext: {
                accrual_entry_date: serializeDate(date),
            },
        });
    }
}

registry.category("views").add("review_accrual_list", {
    ...listView,
    Controller: ReviewAccrualListController,
    buttonTemplate: "flousflow_accounting.acc__ReviewAccrualList.Buttons",
});
