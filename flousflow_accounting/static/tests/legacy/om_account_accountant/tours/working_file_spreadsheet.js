import { registry } from "@web/core/registry";

const PERSISTED_CELL_CONTENT = "Embedded autosave verification";

async function waitFor(assertion, message) {
    const started = Date.now();
    while (Date.now() - started < 10000) {
        if (assertion()) {
            return;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
    }
    throw new Error(message);
}

function findComponent(component, name, visited = new Set(), names = []) {
    if (!component || visited.has(component)) {
        return undefined;
    }
    if (component.constructor?.name === name) {
        return component;
    }
    names.push(component.constructor?.name || "unknown");
    visited.add(component);
    const componentChildren = Object.values(component.__owl__?.children || {}).map(
        (child) => child.component
    );
    const bdomChildren = Array.isArray(component.__owl__?.bdom?.children)
        ? component.__owl__.bdom.children.map((child) => child?.child?.component)
        : [];
    for (const child of [...componentChildren, ...bdomChildren]) {
        const found = findComponent(child, name, visited, names);
        if (found) {
            return found;
        }
    }
    return undefined;
}

registry.category("web_tour.tours").add("ff_working_file_spreadsheet_embedded", {
    steps: () => [
        {
            trigger: ".o_notebook_headers button[name='spreadsheet']",
            run: "click",
        },
        {
            trigger: ".o_working_file_spreadsheet_embedded .o_spreadsheet_container",
            async run() {
                const status = document.querySelector(
                    ".o_working_file_spreadsheet_embedded [role='status']"
                )?.innerText;
                if (status?.trim() !== "Saved") {
                    throw new Error(`Embedded spreadsheet did not reach Saved state: ${status}`);
                }
                const editor = findComponent(
                    odoo.__WOWL_DEBUG__.root,
                    "WorkingFileSpreadsheetEditor"
                );
                if (!editor) {
                    throw new Error("Could not locate embedded editor. Components: " + names.slice(0, 50).join(", "));
                }
                editor.model.dispatch("UPDATE_CELL", {
                    sheetId: editor.model.getters.getActiveSheetId(),
                    col: 0,
                    row: 0,
                    content: PERSISTED_CELL_CONTENT,
                });
                await waitFor(
                    () => editor.state.status === "saved" && !editor.hasUnsavedChanges,
                    "The embedded spreadsheet did not autosave its changed cell."
                );
                const [record] = await editor.orm.read(
                    "account.working.file",
                    [editor.props.recordId],
                    ["spreadsheet_data"]
                );
                if (!record.spreadsheet_data.includes(PERSISTED_CELL_CONTENT)) {
                    throw new Error("The saved spreadsheet snapshot did not include the edited cell.");
                }
            },
        },
        {
            trigger: ".o_working_file_spreadsheet_embedded .o_spreadsheet_container",
            run: () => window.location.reload(),
            expectUnloadPage: true,
        },
        {
            trigger: ".o_notebook_headers button[name='spreadsheet']",
            run: "click",
        },
        {
            trigger: ".o_working_file_spreadsheet_embedded .o_spreadsheet_container",
            async run() {
                const editor = findComponent(
                    odoo.__WOWL_DEBUG__.root,
                    "WorkingFileSpreadsheetEditor"
                );
                if (!editor) {
                    throw new Error("Could not locate the reloaded embedded spreadsheet editor.");
                }
                const position = {
                    sheetId: editor.model.getters.getActiveSheetId(),
                    col: 0,
                    row: 0,
                };
                const cell = editor.model.getters.getCell(position);
                if (cell?.content !== PERSISTED_CELL_CONTENT) {
                    throw new Error(
                        `The saved cell did not survive a page reload: ${cell?.content}`
                    );
                }
                const [record] = await editor.orm.read(
                    "account.working.file",
                    [editor.props.recordId],
                    ["spreadsheet_data"]
                );
                if (!record.spreadsheet_data.includes(PERSISTED_CELL_CONTENT)) {
                    throw new Error("The reloaded record snapshot lost the edited cell.");
                }
            },
        },
        {
            trigger: "button[name='action_open_spreadsheet']",
            run: "click",
        },
        {
            trigger: ".o_action.o_working_file_spreadsheet .o_spreadsheet_container",
            run() {
                const status = document.querySelector(
                    ".o_action.o_working_file_spreadsheet [role='status']"
                )?.innerText;
                if (status?.trim() !== "Saved") {
                    throw new Error(`Full-screen spreadsheet action did not load: ${status}`);
                }
            },
        },
    ],
});
