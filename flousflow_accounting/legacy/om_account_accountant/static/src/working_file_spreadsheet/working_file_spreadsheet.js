import { Model } from "@odoo/o-spreadsheet";
import { Component, markRaw, onWillStart, onWillUnmount, proxy, t, useProps } from "@odoo/owl";
import { OdooDataProvider } from "@spreadsheet/data_sources/odoo_data_provider";
import { SpreadsheetComponent } from "@spreadsheet/actions/spreadsheet_component";
import { createDefaultCurrency } from "@spreadsheet/currency/helpers";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class WorkingFileSpreadsheetEditor extends Component {
    static template = "om_account_accountant.WorkingFileSpreadsheetEditor";
    static components = { SpreadsheetComponent };
    props = useProps({
        recordId: t.number(),
        canEdit: t.boolean(),
        embedded: t.boolean().optional(false),
        onBack: t.function().optional(),
    });

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            loading: true,
            name: "",
            status: "",
            error: false,
        });
        this.saveTimer = undefined;
        this.saveInProgress = false;
        this.saveAgain = false;
        this.hasUnsavedChanges = false;
        this.model = undefined;

        onWillStart(() => this.loadSpreadsheet());
        onWillUnmount(() => this.dispose());
    }

    async loadSpreadsheet() {
        try {
            const [record] = await this.orm.read(
                "account.working.file",
                [this.props.recordId],
                ["name", "company_id"]
            );
            const snapshot = await this.orm.call(
                "account.working.file",
                "get_working_file_spreadsheet_snapshot",
                [[this.props.recordId]]
            );
            const currency = await this.orm.call(
                "res.currency",
                "get_company_currency_for_spreadsheet",
                [record.company_id[0]]
            );
            const dataProvider = markRaw(new OdooDataProvider(this.env));
            const config = {
                mode: this.props.canEdit ? undefined : "readonly",
                custom: {
                    env: this.env,
                    orm: this.orm,
                    odooDataProvider: dataProvider,
                },
                defaultCurrency: createDefaultCurrency(currency),
            };
            this.model = markRaw(new Model(snapshot, config, []));
            dataProvider.addEventListener("data-source-updated", () => {
                this.model.dispatch("EVALUATE_CELLS");
            });
            this.model.on("update", this, this.onSpreadsheetUpdate);
            this.state.name = record.name;
            this.state.status = this.props.canEdit ? "saved" : "readonly";
        } catch (error) {
            this.state.error = true;
            this.state.status = "error";
            this.notification.add(_t("Could not load this working file spreadsheet."), {
                type: "danger",
            });
            throw error;
        } finally {
            this.state.loading = false;
        }
    }

    onSpreadsheetUpdate() {
        if (!this.props.canEdit) {
            return;
        }
        this.hasUnsavedChanges = true;
        this.state.status = "dirty";
        this.state.error = false;
        if (this.saveInProgress) {
            this.saveAgain = true;
        }
        clearTimeout(this.saveTimer);
        this.saveTimer = setTimeout(() => this.saveSpreadsheet(), 800);
    }

    async saveSpreadsheet() {
        if (!this.props.canEdit || !this.model || !this.hasUnsavedChanges) {
            return;
        }
        if (this.saveInProgress) {
            this.saveAgain = true;
            return;
        }

        this.saveInProgress = true;
        this.state.status = "saving";
        try {
            do {
                this.saveAgain = false;
                const snapshot = this.model.exportData();
                const serializedSnapshot = JSON.stringify(snapshot);
                await this.orm.write("account.working.file", [this.props.recordId], {
                    spreadsheet_data: serializedSnapshot,
                });
                this.hasUnsavedChanges =
                    serializedSnapshot !== JSON.stringify(this.model.exportData());
                if (this.hasUnsavedChanges) {
                    this.saveAgain = true;
                }
            } while (this.saveAgain);
            this.state.status = "saved";
        } catch (error) {
            this.state.error = true;
            this.state.status = "error";
            this.notification.add(
                _t("Spreadsheet changes could not be saved. Reopen the file if it has been validated."),
                { type: "danger" }
            );
        } finally {
            this.saveInProgress = false;
        }
    }

    retrySave() {
        this.state.error = false;
        this.hasUnsavedChanges = true;
        return this.saveSpreadsheet();
    }

    async goBack() {
        clearTimeout(this.saveTimer);
        if (this.hasUnsavedChanges) {
            await this.saveSpreadsheet();
        }
        if (this.state.error || this.hasUnsavedChanges) {
            return;
        }
        return this.props.onBack?.();
    }

    dispose() {
        clearTimeout(this.saveTimer);
        if (this.model) {
            this.model.off("update", this, this.onSpreadsheetUpdate);
            if (this.hasUnsavedChanges) {
                this.saveSpreadsheet();
            }
        }
    }
}

class WorkingFileSpreadsheet extends Component {
    static template = "om_account_accountant.WorkingFileSpreadsheet";
    static components = { WorkingFileSpreadsheetEditor };
    props = useProps(standardActionServiceProps);

    setup() {
        this.actionService = useService("action");
        this.recordId = this.props.action.params.record_id;
        this.canEdit = Boolean(this.props.action.params.can_edit);
    }

    returnToWorkingFile() {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Working File"),
            res_model: "account.working.file",
            res_id: this.recordId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("lazy_components").add(
    "om_account_accountant.WorkingFileSpreadsheet",
    WorkingFileSpreadsheet
);
registry.category("lazy_components").add(
    "om_account_accountant.WorkingFileSpreadsheetEmbedded",
    WorkingFileSpreadsheetEditor
);
