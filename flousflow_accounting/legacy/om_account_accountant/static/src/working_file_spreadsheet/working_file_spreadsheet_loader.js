import { Component, useProps } from "@odoo/owl";
import { LazyComponent } from "@web/core/lazy_component";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class WorkingFileSpreadsheetLoader extends Component {
    static template = "om_account_accountant.WorkingFileSpreadsheetLoader";
    static components = { LazyComponent };

    props = useProps(standardActionServiceProps);
}

registry.category("actions").add(
    "om_account_accountant.working_file_spreadsheet",
    WorkingFileSpreadsheetLoader
);
