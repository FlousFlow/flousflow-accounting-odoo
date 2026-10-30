# Review Menu and Report Parity

Last live comparison: 2026-10-28

This ledger tracks the Community implementation against the FlousFlow Enterprise
Odoo 20 database. Menu names and report options are observations from the live
Review menu and report screens. Financial totals must be compared only on matched
company data and period.

The local Review menu follows the live grouping and order: Control (Journal
Items, Audit Trail, Journal Audit), Audit (Working Files, Annual Report),
Inventory Valuation, Regulatory
(Unrealized Currencies, Deferred Revenues, Deferred Expenses), Purchases, then
Sales. Inventory Valuation is a direct Review destination to match Enterprise.
`Draft Entries` remains an additional community work queue under Accounting.
The 2026-10-30 live comparison and local database menu records confirmed this
ordered hierarchy. Journal Audit exposes one **Audit** action for the scoped
journal-item drill-down; the duplicate **Journal Items** button was removed
because it invoked the same action.

## Journal Audit

| Capability | Enterprise | Community | Status |
| --- | --- | --- | --- |
| Review menu hierarchy | Control: Journal Items, Audit Trail, Journal Audit | Same destinations and order; suite-specific Entries to Review and Draft Entries remain under Accounting > Work Queues | Implemented and verified by Odoo menu tests |
| Review menu entry and interactive report | Yes | Yes | Implemented |
| Period, posted/draft/all entries | Month, Quarter, Fiscal Year and custom dates; posted, draft, or all | Month, Quarter, Fiscal Year and custom dates; posted, draft, or all | Browser tour verified period selection, quarter navigation, and custom date entry |
| Include payments | Yes | Yes | Implemented |
| Display scale | Currency, thousands, millions | Currency, thousands, millions | Implemented |
| Journal totals and expandable entries | Yes | Yes | Implemented |
| Review action | Marks entries reviewed; the per-journal action remains visible at zero pending | Calls Odoo's native `set_moves_checked` for eligible posted entries; the action is visible at zero pending and returns 0 without writes | Browser verified on the local zero-pending journal; handler remains company, period, state and group scoped |
| Tax summary and drill-down | Tax Summary links to the Taxes Applied journal-item list, grouped by Taxes then Account | Same destination and grouping; company, report period, target move state, and payment inclusion follow Journal Audit | Browser tour verified the destination and both active groupings; tax rows can also be opened individually |
| Audit drill-down grouping | Opens Journal Items scoped to the selected journal group and groups the lines by Journal Entry | The same core Journal Items action now receives `search_default_group_by_move`, in addition to the scoped company, journal, type, date, move-state, and payment filters | Enterprise UI confirmed invoice-level groups and expandable account lines. Local browser tour asserts the Journal Entry group-by facet after opening Audit. |
| Print | Yes | Yes | Implemented |
| XLSX export | Yes | Yes; Journals, Entries, and Taxes worksheets | Implemented and downloaded/validated |
| Send to Documents | Yes | No Documents module in the local addon path/database | Remaining platform integration |
| Insert in Article | Yes | No equivalent Knowledge integration in the local addon path/database | Remaining platform integration |

The live Enterprise report showed three entries awaiting review and a nonzero
Purchases balance. The local development database showed one posted
Miscellaneous Operations entry with no review pending and zero balance. These
are different databases and are not evidence of a report-calculation mismatch.

The local Review > Control menu now contains only the three Enterprise
destinations. The suite-specific Entries to Review queue remains accessible
under Accounting > Work Queues; Journal Items also remains available under
Accounting > Transactions.

## Purchase and Sales Accrual Review Queues

The live Enterprise Review menu exposes Bills To Receive, Billed Not Received,
Invoices To Be Issued, and Invoiced Not Delivered. The live queues are grouped
by Vendor or Customer and default to the last 365 days; each also has an
independent As of date control. Purchase rows show order, partner, product,
quantity, received, billed, unit price, and amount. Sales rows add description,
salesperson, Unit Cost, and Total Cost. In the observed Invoices To Be Issued
report, Total Cost equals the stored Unit Cost multiplied by the delivered
quantity at the selected report date.

The Community module already had all four destinations and used Odoo's native
accrual search methods, but its views opened ungrouped, omitted the default
last-365-days filter, and lacked the sales cost columns. These queues now open
grouped by Vendor or Customer with the same default order-date filter. Sales
Unit Cost is stored using the product cost, company, sales currency/date, and
unit-of-measure conversion; Total Cost multiplies that unit cost by the delivered
or invoiced quantity at the selected As of date. The independent date picker
passes the date into Odoo's accrual context and reloads the same report. The
purchase queue uses that date to select eligible lines; both purchase and sales
group totals recalculate date-sensitive quantities and amounts. Unit Cost remains aggregated on grouped rows; Total Cost remains visible per line without a grouped subtotal, matching Enterprise. The cost fields are limited to accounting read groups.
No journal entries are created by these reports.

The date picker and grouped historical quantities are covered by Odoo model and
browser-tour tests. The four report actions now each open a dedicated matching
list view: Bills To Receive, Billed Not Received, Invoices To Be Issued, and
Invoiced Not Delivered. A regression test verifies each action-to-view mapping;
the local database was upgraded to module version 20.0.1.26.0 and its four
stored mappings were queried after the upgrade. The live Enterprise Bills To
Receive group shows an average Unit Price: 132.50 and 89.00 on its two lines
produce 110.75, while Amount totals 3,095. The local purchase lists now use the
average aggregator; their own-view test distinguishes purchase averages from
the existing sales sums. The expanded Enterprise Invoices To Be Issued group
shows unit-price lines 14,920, 5,222, and 3,730; their sum is the displayed
23,872. The local sales list retains its sum aggregator, with a matching
grouped-read regression test. Version 20.0.1.30.0 is installed on the local 8077
database, and the stored purchase and sales view arches were queried after the
upgrade. A live Enterprise Invoices To Be Issued view confirmed
that Total Cost follows the delivered quantity. The
unit-cost computation now switches to the sale line's company before reading
company-dependent product cost, matching Odoo's native sales margin cost
calculation; a two-company regression test verifies this behavior. Remaining
differences: the live Invoiced Not Delivered report contained no rows during
comparison; its Total Cost quantity basis is inferred from the deferred-revenue
workflow and still needs matched nonzero validation. The live Billed Not Received
report also returned no rows during the latest check, so line-level parity for
that queue remains unverified. Enterprise also exposes a Knowledge action from
the report menu;
the local Knowledge app is unavailable.

## Balance Sheet and Profit and Loss

Enterprise shows an information icon for each report line. Its popover exposes
the engine, label, formula, and calculated value. The Community Balance Sheet
now returns this formula metadata for every line and renders the icon for
regular users as well as developers. A read-only call against the local 8077
database returned 28 report lines with formula metadata; `Total ASSETS` reports
`CA.balance + FA.balance + PNCA.balance`. A headless browser tour on the local
database confirmed an info icon on every displayed row, then opened Total
ASSETS and verified that the popover shows Engine, Label, Formula, and Value,
including the expected aggregate formula. Numeric parity still requires
matching company data and report dates.

The Enterprise report settings menu contains XLSX, Send to Documents, and
Insert in Article. The Community settings button previously opened the print
options wizard instead. It now opens an output menu with XLSX, using the
existing report exporter and current company, dates, journals, move state,
comparison period, and debit/credit selection. The print button remains a
separate action. Documents and Knowledge integrations remain unavailable in
this Community addon environment.

## Deferred Expenses and Deferred Revenues

The live Deferred Expenses report has month, quarter, fiscal-year, and custom
date-range selections; no comparison or a selected number of previous periods;
ascending or descending ordering; comparison by amount or percentage; grouping
by account, product category, or product; options to show all entries and hide
zero lines; currency scale; print; and XLSX, Documents, and article actions.
On 2026-10-30, both Deferred Expenses and Deferred Revenues opened on September
2026, the previous calendar month. The live Deferred Revenues screen had no
rows. Deferred Revenues is also available under Review.

The local suite has `om_account_asset` asset and revenue-recognition boards.
Review now exposes separate Deferred Expenses and Deferred Revenues interactive
reports. Both now default to the previous calendar month to match Enterprise.
They use the monthly asset schedule moves and their actual recognition
account lines, with month/quarter/fiscal-year/custom date selection,
posted/all entries, account/category/product grouping, the journal selector,
a selected count of preceding-period comparisons, amount or percentage changes,
ascending/descending ordering, hide-zero, company-currency scaling, print, and
drill-down to the matching journal entries. Their XLSX export includes Schedule
and Entries worksheets and preserves period and comparison filters. New assets
retain their source invoice line so product grouping can use the actual product.

The Deferred schedule now offers an `Options` dropdown with `Unfold All` and
`Hide lines at 0`, matching the Enterprise option-menu placement. It also shows
expandable asset detail rows beneath each account, category, or product total.
The parent-row amounts remain the report totals; child assets show their own
recognized amounts and comparison values. Existing row clicks still open the
matching journal entries. An isolated accounting fixture verifies that child
detail amounts and comparisons reconcile to the parent, and the browser tour
checks the option-menu toggle. A live nonempty Enterprise schedule is still
needed to confirm its exact hierarchy and presentation.

Remaining differences: the local report also exposes a Posted/All Entries
filter that is not present in the inspected Enterprise filter panel. The local
Deferred Expenses toolbar also exposes a journal selector, while the inspected
Enterprise Deferred Expenses page has no journal filter (Deferred Revenues does
have one). The Enterprise actions to send the report to Documents
or insert it into an article are unavailable because those apps are absent from
the local Odoo 20 addons path. Existing assets created before the
source-invoice-line field was added have no product link and fall back to the
asset name for product grouping. At the 2026-10-30 recheck, the local database
returned no deferred-revenue rows for September (matching the live Enterprise
page); the deferred-expense report returned one account group with two posted
entries totaling 583.33. The database has three asset categories and three
assets. These are different datasets, so the nonzero schedule arithmetic has
not yet been validated against matched records.
An isolated accounting fixture now verifies nonzero quarter totals and prior-
period comparison against three posted depreciation moves (300.00 each total),
and confirms that a February drill-down returns only the February move. A live
matched-company comparison remains outstanding.

The Enterprise report options include an independent `Unfold All` control,
separate from `Hide lines at 0` and the posted/all-entries target. The local
report now provides one expandable asset-detail level beneath each selected
grouping and a matching expand/collapse-all control. The Enterprise Deferred
Expenses screen had no rows for either September 2026 or FY 2025 during this
inspection, so exact hierarchy and presentation parity on nonempty schedules
still needs matched-data confirmation.

## Working Files

Enterprise exposes Working Files from Review as an audit dossier, not as a
Documents folder. The current live cycle screen exposes Cycle and Balances
navigation. Its audit checklist contains 52 checks grouped by accounting area,
with review states, notes, evidence uploads, and activity history. The cycle also
has a Spreadsheet tab. The observed Enterprise file opens a blank Sheet1 in the
spreadsheet editor, with File/Edit/View/Insert/Format/Data/Help menus and a
"Saved" status indicator. A browser tour now edits a cell, waits for the Saved
state, reloads the working-file page, reopens Spreadsheet, and confirms the cell
value both in the reloaded editor model and the record snapshot.

The Community suite now exposes Working Files under Review with a cycle kanban,
checklist cards labeled by accounting area, and a Balances tab. New files use the
52 check names and eight sections observed on the live Enterprise 2025 cycle.
Reviewers can mark checks Pending Review or Reviewed, add notes and multiple
supporting files per check, and use chatter. Existing single-file evidence remains
available for records created before multi-file evidence was added. Evidence upload
and removal are blocked after the working file is validated. The old generic starter
templates are archived, not deleted; administrator-created active templates remain
available and are added to future files. Existing working-file snapshots are not
rewritten when templates change. The list view remains available alongside the
cycle cards. A Spreadsheet tab now opens the native Odoo spreadsheet editor for
the working file. The workbook is stored on the record and autosaves after edits;
auditors and validated files open read-only. This uses the installed Community
`spreadsheet` model and editor component rather than the read-only dashboard
surface. The Spreadsheet tab now mounts the Odoo editor inside the working file,
alongside Cycles and Balances as in Enterprise. The existing full-screen open
action remains as an additional shortcut. A local browser tour verified that the
embedded editor loads, handles a cell update, reaches its Saved state, and
persists the edited value in the Odoo snapshot; it also verifies that the
full-screen shortcut still opens. The same browser tour confirms that the
edited cell survives a full page reload and is present in the reloaded editor.
Accounting managers can validate or reopen a file, and validation is blocked
until every checklist item is reviewed. Company-scoped access is applied.

The working-file kanban card now shows two separate completion bars like the
Enterprise card: reviewed balance accounts / total balance accounts, followed
by reviewed checks / total checks. A test verifies that reviewing a balance
line updates the card's balance count and percentage.

Opening a file from the Enterprise list lands on Cycles. The local dossier now
opens on its Cycles checklist tab, followed by Balances and Spreadsheet, rather
than landing on Balances first. A view-order test protects this navigation order.

The Balances tab creates one line for each active account in the file's company.
It shows current-period balance, the corresponding prior-year balance,
variation, variation percentage, last comment, and review status, with account
type filters. Posted `account.move.line` data is used; accounts that carry
opening balances are calculated through the period end, while income and
expense accounts use the selected date range. A Refresh Accounts action adds
new company accounts without replacing comments or review statuses.

The balance arithmetic now has isolated posted-entry coverage: a balance-sheet
account carries its historical opening balance through the selected end date,
and a revenue account includes only activity inside the current and prior-year
periods. The fixture also verifies variation and percentage calculations. Both
tests pass on the local Odoo 20 database; this confirms the Community rules, not
numeric equality with the live Enterprise company's ledger.

Enterprise account names in the Balances view open Journal Items filtered to
that account and the review period, with posted entries selected. Community
account names now use the same drill-down destination and scope it to the
working-file company, account, dates, and posted state. A local test confirms
that in-period posted lines appear while out-of-period and draft lines are
excluded; the account-name field is wired to the link widget in the list view.

The local development file initially opened with zero balance rows although its
company had 50 active accounts. The web form can submit an explicit empty
one2many value, which bypassed the old create-time sync. File creation now
always reconciles account rows, and the current development file has been
refreshed to 50 account rows without altering journal entries. A regression
test covers creation with the empty one2many payload.

Spreadsheet save/reload now has browser coverage. Overall parity remains partial.
Several Enterprise checklist prompts refer to Belgian
GAAP or account numbers 17/42; those
jurisdiction-specific instructions were observed in the Enterprise company and need
review before applying them to Egyptian entities. The live Enterprise balance table
had 52 accounts; the local company
has 50 active accounts and only two posted journal-item rows. The local balance
view therefore still needs a matched-period comparison against the Enterprise
ledger before numeric parity is established. The local database has no
fiscal-year records, so the
Community date range does not depend on a configured fiscal year.

### Live approval and data recheck — 2026-10-30

The Enterprise file `Audit 2025` currently has 52 checks, 18 resolved, and 34
still pending. A read-only open of a pending check's status menu showed exactly
Pending Review, Reviewed, Supervised, and Exception, matching the four choices
in the local OWL component. The parent header displays Reviewed and its Certify
button is enabled with those 34 checks pending. No certification action was
triggered during this read-only comparison.

The local database `flousflow_om_accountant_dev20_20261028` now has
`om_account_accountant` `20.0.1.34.33` installed, 52 active templates across
the same eight sections, and seven evidence-required templates, matching the
seven upload actions currently visible on Enterprise's `Audit 2025` checklist.
An earlier count of five missed Accounting Process and Asset Register. Upgrade
`20.0.1.34.33` restores those two defaults on templates and both linked and
legacy check rows (older rows without `template_id`); it only changes the
evidence-required flag. The local page at `/odoo/action-651/14` now renders
seven Upload File actions, matching the live view. Its sole working
file has 52 pending checks and 50 balance rows; it covers
2026-10-28 through 2026-10-29, so its progress and balances are not directly
comparable to Enterprise's 2025 file. The local check selector implements the
same four states, notes, and evidence uploads. Local files now have In Progress,
Reviewed, and Certified stages; Mark Reviewed permits pending checks, while
certification still requires all checks to be resolved. Existing Validate from
In Progress remains for backward compatibility. The Enterprise Certify button
being enabled does not prove that its server accepts certification with pending
checks; this still requires a disposable Enterprise record, so the local gate
remains unchanged pending evidence. Local stage visuals are now confirmed after
upgrade; note autosave and evidence upload/removal remain open. Supervised is now enforced on
the server as manager-only for both record creation and updates, matching the
permission used to expose that state in the UI. The full
`TestWorkingFileBalances` class passed 12 tests after the upgrade. Enterprise's
Certify control was enabled with 34 pending checks, but its server-side gate
cannot be established without changing the live audit record. Keep that gate as
an open parity question for a disposable Enterprise record. The local browser
session expired during this recheck, so local visual, note autosave, and evidence
upload/removal verification remain open.

## Bills To Receive live comparison — 2026-10-30

Enterprise `/odoo/action-843` showed an as-of date of 2026-10-30, Gemini
Furniture with 2 records, quantity 25, received 25, billed 0, average unit price
110.75, and amount 3,095.00. The local ORM returned the same date-scoped P00005
lines: Office Lamp 20 × 132.50 and Office Chair 5 × 89.00. Quantity, received,
billed, average unit price, and amount match. The local list's hidden optional
Description field is extra; Enterprise's **Add Custom Field** menu action is an
Odoo Studio capability unavailable in the Community runtime. Local UI rendering
and a nonempty Billed Not Received comparison remain unverified.

## Sales Review grouped-cost parity — 2026-10-30

Enterprise `/odoo/action-446` showed a grouped Unit Cost of 4,200 for three
Acme lines but no grouped Total Cost subtotal. Its detail Total Costs were
30,000, 8,000 and 7,000. Local `review_menu.xml` formerly requested a grouped
sum for Total Cost in both sales Review queues. Those two view aggregators have
been removed; the per-line cost calculation and field remain, and Unit Cost
still aggregates. The local database has no matching sales records and the local
browser session is unauthenticated, so its rendered UI and values remain
unverified. The focused suite passed 9 tests, including line-cost calculations
and a view regression check; the local module is installed as `20.0.1.34.20`.

## Annual Report New dialog comparison — 2026-10-30

Enterprise Review > Audit > Annual Report currently opens a setup Kanban.
Selecting New displays title, start/end dates, responsible users and the Annual
Report template; the live defaults are January 1–December 31, 2025 and the
current user. Its title placeholder is `Example, Annual Financial Overview FY`
(shown as `مثال، نظرة عامة على الوضع المالي السنوي AR` in the live Arabic UI).
The local default-get result matches the dates, current-user assignment, and
template. `accounting_pdf_reports` `2.0.71` now matches the title placeholder
and includes the observed Arabic translation. Its focused annual-document
suite passed 6 tests with no failures, and the new view is installed in the
local 8077 database. The local browser session remains unauthenticated and the
database has no Arabic language enabled, so dialog geometry and translated
rendering remain unverified. No Enterprise report was created; the New dialog
was dismissed without saving.
