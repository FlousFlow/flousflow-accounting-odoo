import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { LazyComponent } from "@web/core/lazy_component";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class WorkingFileSpreadsheetField extends Component {
    static template = "flousflow_accounting.acc__WorkingFileSpreadsheetField";
    static components = { LazyComponent };
    props = useProps(standardFieldProps);

    setup() {
        this.state = proxy({ canEdit: false });
        onWillStart(async () => {
            const canWrite = await user.checkAccessRight("account.working.file", "write");
            const isAccountUser = await user.hasGroup("account.group_account_user");
            const isAccountManager = await user.hasGroup("account.group_account_manager");
            this.state.canEdit =
                !this.props.readonly && canWrite && (isAccountUser || isAccountManager);
        });
    }
}

registry.category("fields").add("ff_working_file_spreadsheet", {
    component: WorkingFileSpreadsheetField,
    supportedTypes: ["text"],
});
