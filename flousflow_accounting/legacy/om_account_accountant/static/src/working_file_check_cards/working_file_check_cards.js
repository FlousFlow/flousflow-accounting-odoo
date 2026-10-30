import { Component, onWillStart, onWillUnmount, onWillUpdateProps, proxy, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { FileInput } from "@web/core/file_input/file_input";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const CHECK_MODEL = "account.working.file.check";
const ATTACHMENT_MODEL = "ir.attachment";
const CHECK_FIELDS = [
    "section",
    "name",
    "description",
    "state",
    "note",
    "evidence_filename",
    "evidence_required",
];

export class WorkingFileCheckCards extends Component {
    static template = "om_account_accountant.WorkingFileCheckCards";
    static components = { Dropdown, DropdownItem, FileInput };
    props = useProps(standardFieldProps);

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            sections: [],
            canWrite: false,
            canSupervise: false,
            loading: true,
        });
        this.isAccountUser = false;
        this.isAccountManager = false;
        this.hasWriteAccess = false;
        this.noteTimers = new Map();

        onWillStart(async () => {
            const [hasWriteAccess, isAccountUser, isAccountManager] = await Promise.all([
                user.checkAccessRight(CHECK_MODEL, "write"),
                user.hasGroup("account.group_account_user"),
                user.hasGroup("account.group_account_manager"),
            ]);
            this.isAccountUser = isAccountUser;
            this.isAccountManager = isAccountManager;
            this.hasWriteAccess = hasWriteAccess;
            this.state.canWrite =
                !this.props.readonly && hasWriteAccess && (isAccountUser || isAccountManager);
            this.state.canSupervise = isAccountManager;
            await this.loadChecks();
        });
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.readonly !== this.props.readonly) {
                this.state.canWrite =
                    !nextProps.readonly && this.hasWriteAccess &&
                    (this.isAccountUser || this.isAccountManager);
            }
            if (nextProps.record.resId !== this.props.record.resId) {
                await this.loadChecks(nextProps.record.resId);
            }
        });
        onWillUnmount(() => {
            for (const timer of this.noteTimers.values()) {
                clearTimeout(timer);
            }
            this.noteTimers.clear();
        });
    }

    get statusOptions() {
        return [
            { value: "pending", label: _t("Pending Review"), decoration: "info" },
            { value: "reviewed", label: _t("Reviewed"), decoration: "success" },
            { value: "supervised", label: _t("Supervised"), decoration: "success" },
            { value: "exception", label: _t("Exception"), decoration: "danger" },
        ];
    }

    get addNotesLabel() {
        return _t("Add notes...");
    }

    get loadingLabel() {
        return _t("Loading review checks…");
    }

    get emptyLabel() {
        return _t("No review checks are available.");
    }

    get reviewStatusLabel() {
        return _t("Review status");
    }

    get notesLabel() {
        return _t("Review notes");
    }

    get uploadFileLabel() {
        return _t("Upload File");
    }

    get removeFileLabel() {
        return _t("Remove file");
    }

    getEditableStatusOptions() {
        return this.statusOptions.filter(
            (option) => option.value !== "supervised" || this.state.canSupervise
        );
    }

    getStatusLabel(value) {
        return this.statusOptions.find((option) => option.value === value)?.label || value;
    }

    getStatusButtonClass(value) {
        const decoration = this.statusOptions.find((option) => option.value === value)?.decoration;
        return decoration ? `btn-outline-${decoration}` : "btn-outline-secondary";
    }

    getStatusItemClass(option) {
        return `text-bg-${option.decoration}`;
    }

    async loadChecks(recordId = this.props.record.resId) {
        this.state.loading = true;
        try {
            const checks = recordId
                ? await this.orm.call(CHECK_MODEL, "search_read", [
                      [["file_id", "=", recordId]],
                  ], { fields: ["id", ...CHECK_FIELDS], order: "sequence,id" })
                : [];
            const ids = checks.map((check) => check.id);
            const attachments = ids.length
                ? await this.orm.call(ATTACHMENT_MODEL, "search_read", [
                      [
                          ["res_model", "=", CHECK_MODEL],
                          ["res_id", "in", ids],
                          ["res_field", "=", false],
                      ],
                  ], { fields: ["id", "name", "mimetype", "res_id"], order: "id" })
                : [];

            for (const check of checks) {
                check.note = check.note || "";
                check.savedNote = check.note;
                check.attachments = attachments.filter(
                    (file) => (Array.isArray(file.res_id) ? file.res_id[0] : file.res_id) === check.id
                );
            }
            const sections = new Map();
            for (const check of checks) {
                const sectionName = check.section || _t("Other");
                if (!sections.has(sectionName)) {
                    sections.set(sectionName, { name: sectionName, checks: [] });
                }
                sections.get(sectionName).checks.push(check);
            }
            this.state.sections = [...sections.values()];
        } catch (error) {
            this.notification.add(error.message || _t("Review checks could not be loaded."), {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    onNoteInput(check, event) {
        check.note = event.target.value;
        const currentTimer = this.noteTimers.get(check.id);
        if (currentTimer) {
            clearTimeout(currentTimer);
        }
        this.noteTimers.set(check.id, setTimeout(() => this.saveNote(check), 500));
    }

    async saveNote(check) {
        const currentTimer = this.noteTimers.get(check.id);
        if (currentTimer) {
            clearTimeout(currentTimer);
            this.noteTimers.delete(check.id);
        }
        if (!this.state.canWrite || check.note === check.savedNote) {
            return;
        }
        const note = check.note;
        try {
            await this.orm.call(CHECK_MODEL, "write", [[check.id], { note }]);
            check.savedNote = note;
        } catch (error) {
            check.note = check.savedNote;
            this.notification.add(error.message || _t("The review note could not be saved."), {
                type: "danger",
            });
        }
    }

    async onStatusChange(check, value) {
        if (!this.state.canWrite || (value === "supervised" && !this.state.canSupervise)) {
            return;
        }
        const previousValue = check.state;
        check.state = value;
        try {
            await this.orm.call(CHECK_MODEL, "write", [[check.id], { state: value }]);
            await this.env.reload?.();
        } catch (error) {
            check.state = previousValue;
            this.notification.add(error.message || _t("The review status could not be saved."), {
                type: "danger",
            });
        }
    }

    async onFilesUploaded(check, uploadedFiles) {
        const failedUpload = uploadedFiles.find((file) => file.error);
        if (failedUpload) {
            this.notification.add(failedUpload.error, {
                title: _t("Uploading error"),
                type: "danger",
            });
            return;
        }
        await this.loadCheckAttachments(check);
    }

    async loadCheckAttachments(check) {
        try {
            check.attachments = await this.orm.call(ATTACHMENT_MODEL, "search_read", [
                [
                    ["res_model", "=", CHECK_MODEL],
                    ["res_id", "=", check.id],
                    ["res_field", "=", false],
                ],
            ], { fields: ["id", "name", "mimetype", "res_id"], order: "id" });
        } catch (error) {
            this.notification.add(error.message || _t("The evidence files could not be loaded."), {
                type: "danger",
            });
        }
    }

    async removeEvidence(check, attachment) {
        try {
            const [linkedAttachment] = await this.orm.call(ATTACHMENT_MODEL, "search_read", [
                [
                    ["id", "=", attachment.id],
                    ["res_model", "=", CHECK_MODEL],
                    ["res_id", "=", check.id],
                    ["res_field", "=", false],
                ],
            ], { fields: ["id"] });
            if (!linkedAttachment) {
                throw new Error(_t("This file is no longer attached to the review check."));
            }
            await this.orm.call(ATTACHMENT_MODEL, "unlink", [[attachment.id]]);
            check.attachments = check.attachments.filter((file) => file.id !== attachment.id);
        } catch (error) {
            this.notification.add(error.message || _t("The evidence file could not be removed."), {
                type: "danger",
            });
        }
    }

    getAttachmentUrl(attachment) {
        return `/web/content/${attachment.id}?download=true`;
    }
}

registry.category("fields").add("ff_working_file_check_cards", {
    component: WorkingFileCheckCards,
    supportedTypes: ["one2many"],
});
