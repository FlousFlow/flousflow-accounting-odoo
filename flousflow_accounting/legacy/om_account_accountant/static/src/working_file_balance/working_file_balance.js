import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class WorkingFileBalanceAccountField extends Component {
    static template = "om_account_accountant.WorkingFileBalanceAccountField";
    props = useProps(standardFieldProps);

    setup() {
        this.action = useService("action");
    }

    openJournalItems() {
        return this.action.doActionButton({
            type: "object",
            name: "action_open_journal_items",
            resModel: "account.working.file.balance",
            resId: this.props.record.resId,
        });
    }
}

registry.category("fields").add("ff_working_file_balance_account", {
    component: WorkingFileBalanceAccountField,
    supportedTypes: ["char"],
});
