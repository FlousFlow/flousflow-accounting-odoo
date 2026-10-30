import json

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from dateutil.relativedelta import relativedelta


class AccountWorkingFileTemplate(models.Model):
    _name = "account.working.file.template"
    _description = "Accounting Working File Checklist Template"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    section = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    evidence_required = fields.Boolean(default=False)
    active = fields.Boolean(default=True)


class AccountWorkingFile(models.Model):
    _name = "account.working.file"
    _description = "Accounting Working File"
    _inherit = ["mail.thread", "mail.activity.mixin", "spreadsheet.mixin"]
    _order = "date_to desc, id desc"
    _check_company_auto = True

    _company_name_unique = models.Constraint(
        "UNIQUE(company_id, name)",
        "An accounting working file with this name already exists for this company.",
    )

    name = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
        index=True, tracking=True,
    )
    date_from = fields.Date(string="Start Date", required=True, tracking=True)
    date_to = fields.Date(string="End Date", required=True, tracking=True)
    state = fields.Selection(
        [
            ("in_progress", "In Progress"),
            ("reviewed", "Reviewed"),
            ("validated", "Certified"),
        ],
        default="in_progress", required=True, copy=False, tracking=True, index=True,
    )
    check_ids = fields.One2many(
        "account.working.file.check", "file_id", string="Review Checks", copy=True,
    )
    balance_line_ids = fields.One2many(
        "account.working.file.balance", "file_id", string="Balances", copy=False,
    )
    check_count = fields.Integer(compute="_compute_progress", store=True)
    reviewed_count = fields.Integer(compute="_compute_progress", store=True)
    progress = fields.Float(compute="_compute_progress", store=True)
    balance_line_count = fields.Integer(compute="_compute_balance_line_count")
    balance_reviewed_count = fields.Integer(compute="_compute_balance_progress")
    balance_progress = fields.Float(compute="_compute_balance_progress")
    currency_id = fields.Many2one(related="company_id.currency_id")

    @api.depends("check_ids", "check_ids.state")
    def _compute_progress(self):
        for record in self:
            checks = record.check_ids
            completed = checks.filtered(lambda check: check.state != "pending")
            record.check_count = len(checks)
            record.reviewed_count = len(completed)
            record.progress = 100.0 * len(completed) / len(checks) if checks else 0.0

    @api.depends("balance_line_ids")
    def _compute_balance_line_count(self):
        for record in self:
            record.balance_line_count = len(record.balance_line_ids)

    @api.depends("balance_line_ids", "balance_line_ids.state")
    def _compute_balance_progress(self):
        for record in self:
            reviewed = record.balance_line_ids.filtered(
                lambda line: line.state == "reviewed"
            )
            record.balance_reviewed_count = len(reviewed)
            record.balance_progress = (
                100.0 * len(reviewed) / len(record.balance_line_ids)
                if record.balance_line_ids else 0.0
            )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_to < record.date_from:
                raise ValidationError(_("The end date cannot be earlier than the start date."))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "check_ids" in fields_list:
            templates = self.env["account.working.file.template"].search(
                [("active", "=", True)]
            )
            values["check_ids"] = [
                fields.Command.create({
                    "sequence": template.sequence,
                    "section": template.section,
                    "name": template.name,
                    "description": template.description,
                    "template_id": template.id,
                    "evidence_required": template.evidence_required,
                })
                for template in templates
            ]
        return values

    def _sync_balance_lines(self):
        BalanceLine = self.env["account.working.file.balance"]
        Account = self.env["account.account"]
        for file_record in self:
            accounts = Account.with_company(file_record.company_id).search(
                [("company_ids", "in", file_record.company_id.id), ("active", "=", True)],
                order="code, id",
            )
            existing_account_ids = set(file_record.balance_line_ids.account_id.ids)
            missing_accounts = accounts.filtered(lambda account: account.id not in existing_account_ids)
            if missing_accounts:
                BalanceLine.create([
                    {
                        "file_id": file_record.id,
                        "account_id": account.id,
                        "sequence": sequence * 10,
                    }
                    for sequence, account in enumerate(missing_accounts, start=1)
                ])

    def action_refresh_balance_lines(self):
        if not (
            self.env.user.has_group("account.group_account_user")
            or self.env.user.has_group("account.group_account_manager")
        ):
            raise AccessError(_("Only accounting users can refresh working-file balances."))
        if any(file_record.state == "validated" for file_record in self):
            raise UserError(_("Reopen the working file before refreshing its account list."))
        self._sync_balance_lines()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        files = super().create(vals_list)
        templates = self.env["account.working.file.template"].search([("active", "=", True)])
        for vals, file_record in zip(vals_list, files):
            if "check_ids" not in vals and not file_record.check_ids:
                file_record.check_ids = [
                    fields.Command.create({
                        "sequence": template.sequence,
                        "section": template.section,
                        "name": template.name,
                        "description": template.description,
                        "template_id": template.id,
                        "evidence_required": template.evidence_required,
                    })
                    for template in templates
                ]
            # The web form can send an explicit empty one2many command while
            # creating a file. Always reconcile the account snapshot so that
            # this does not leave a newly created review file without balances.
            file_record._sync_balance_lines()
            file_record.message_post(body=_("Working file created for %(name)s.", name=file_record.name))
        return files

    def action_mark_reviewed(self):
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only accounting managers can mark a working file as reviewed."))
        for file_record in self:
            if file_record.state == "reviewed":
                continue
            if file_record.state != "in_progress":
                raise UserError(_("Reopen the working file before reviewing it again."))
            # Enterprise shows Reviewed even while some checklist items remain pending.
            super(AccountWorkingFile, file_record).write({"state": "reviewed"})
            file_record.message_post(body=_("Working file marked as reviewed."))
        return True

    def action_validate(self):
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only accounting managers can certify a working file."))
        for file_record in self:
            if file_record.state == "validated":
                continue
            if not file_record.check_ids:
                raise UserError(_("Load or add review checks before validating this working file."))
            pending = file_record.check_ids.filtered(
                lambda check: check.state == "pending"
            )
            if pending:
                raise UserError(_("Every review check must be resolved before certification."))
            super(AccountWorkingFile, file_record).write({"state": "validated"})
            file_record.message_post(body=_("Working file certified."))
        return True

    def action_reopen(self):
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only accounting managers can reopen a working file."))
        for file_record in self:
            if file_record.state == "in_progress":
                continue
            super(AccountWorkingFile, file_record).write({"state": "in_progress"})
        self.message_post(body=_("Working file reopened for changes."))
        return True

    def write(self, vals):
        if "state" in vals:
            raise UserError(_("Use the Validate or Reopen action to change the working file status."))
        if "company_id" in vals and any(file_record.balance_line_ids for file_record in self):
            raise UserError(_("The company cannot be changed after account balances have been added."))
        if any(file_record.state == "validated" for file_record in self):
            raise UserError(_("Reopen the working file before changing it."))
        return super().write(vals)

    def unlink(self):
        if any(file_record.state == "validated" for file_record in self):
            raise UserError(_("Reopen the working file before deleting it."))
        return super().unlink()

    def action_open_balances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Balances"),
            "res_model": "account.working.file.balance",
            "view_mode": "list,form",
            "search_view_id": self.env.ref(
                "flousflow_accounting.acc__view_account_working_file_balance_search"
            ).id,
            "domain": [("file_id", "=", self.id)],
            "context": {"default_file_id": self.id},
        }

    def action_open_checks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Review Checks"),
            "res_model": "account.working.file.check",
            "view_mode": "list,form",
            "search_view_id": self.env.ref(
                "flousflow_accounting.acc__view_account_working_file_check_search"
            ).id,
            "domain": [("file_id", "=", self.id)],
            "context": {"default_file_id": self.id},
        }

    def action_open_spreadsheet(self):
        self.ensure_one()
        can_edit = (
            self.state != "validated"
            and (
                self.env.user.has_group("account.group_account_user")
                or self.env.user.has_group("account.group_account_manager")
            )
        )
        return {
            "type": "ir.actions.client",
            "name": _("Spreadsheet: %(name)s", name=self.name),
            "tag": "flousflow_accounting.acc__working_file_spreadsheet",
            "params": {"record_id": self.id, "can_edit": can_edit},
        }

    @api.readonly
    def get_working_file_spreadsheet_snapshot(self):
        self.ensure_one()
        self.check_access("read")
        if self.spreadsheet_data:
            return json.loads(self.spreadsheet_data)
        return self._empty_spreadsheet_data()


class AccountWorkingFileCheck(models.Model):
    _name = "account.working.file.check"
    _description = "Accounting Working File Review Check"
    _inherit = ["mail.thread"]
    _order = "sequence, id"
    _check_company_auto = True

    file_id = fields.Many2one(
        "account.working.file", required=True, ondelete="cascade", index=True,
        check_company=True,
    )
    company_id = fields.Many2one(related="file_id.company_id", store=True, index=True)
    template_id = fields.Many2one(
        "account.working.file.template", ondelete="set null", copy=False,
    )
    sequence = fields.Integer(default=10)
    section = fields.Char(required=True, translate=True)
    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    evidence_required = fields.Boolean(default=False)
    state = fields.Selection(
        [
            ("pending", "Pending Review"),
            ("reviewed", "Reviewed"),
            ("supervised", "Supervised"),
            ("exception", "Exception"),
        ],
        default="pending", required=True, tracking=True, index=True,
    )
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    reviewed_on = fields.Datetime(readonly=True, copy=False, tracking=True)
    note = fields.Text(tracking=True)
    evidence = fields.Binary(attachment=True)
    evidence_filename = fields.Char()
    evidence_attachment_storage_ids = fields.One2many(
        "ir.attachment", "res_id", string="Evidence Attachment Storage",
        domain=[("res_model", "=", "account.working.file.check"), ("res_field", "=", False)],
        copy=False,
    )
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment", string="Supporting Evidence",
        compute="_compute_evidence_attachment_ids",
        inverse="_inverse_evidence_attachment_ids",
    )
    evidence_attachment_count = fields.Integer(compute="_compute_evidence_attachment_ids")

    def _check_supervised_status_access(self, vals):
        if (
            vals.get("state") == "supervised"
            and not self.env.user.has_group("account.group_account_manager")
        ):
            raise AccessError(_("Only accounting managers can mark a review check as supervised."))

    @api.depends("evidence_attachment_storage_ids")
    def _compute_evidence_attachment_ids(self):
        for check in self:
            check.evidence_attachment_ids = check.evidence_attachment_storage_ids
            check.evidence_attachment_count = len(check.evidence_attachment_storage_ids)

    def _inverse_evidence_attachment_ids(self):
        for check in self:
            check.evidence_attachment_storage_ids = check.evidence_attachment_ids

    def write(self, vals):
        self._check_supervised_status_access(vals)
        if any(check.file_id.state == "validated" for check in self):
            raise UserError(_("Reopen the working file before changing its review checks."))
        if vals.get("file_id"):
            target_file = self.env["account.working.file"].browse(vals["file_id"])
            if target_file.state == "validated":
                raise UserError(_("Reopen the working file before moving review checks into it."))
        if vals.get("state") in ("reviewed", "supervised", "exception"):
            vals = {**vals, "reviewer_id": self.env.user.id, "reviewed_on": fields.Datetime.now()}
        elif vals.get("state") == "pending":
            vals = {**vals, "reviewer_id": False, "reviewed_on": False}
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_supervised_status_access(vals)
        file_ids = {vals.get("file_id") for vals in vals_list if vals.get("file_id")}
        files = self.env["account.working.file"].browse(file_ids)
        if any(file_record.state == "validated" for file_record in files):
            raise UserError(_("Reopen the working file before adding review checks."))
        for vals in vals_list:
            if vals.get("state") in ("reviewed", "supervised", "exception"):
                vals.update(reviewer_id=self.env.user.id, reviewed_on=fields.Datetime.now())
        return super().create(vals_list)

    def unlink(self):
        if any(check.file_id.state == "validated" for check in self):
            raise UserError(_("Reopen the working file before removing its review checks."))
        return super().unlink()


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _check_working_file_evidence_mutable(self, references):
        check_ids = {
            res_id for res_model, res_id in references
            if res_model == "account.working.file.check" and res_id
        }
        checks = self.env["account.working.file.check"].browse(check_ids).exists()
        if any(check.file_id.state == "validated" for check in checks):
            raise UserError(_("Reopen the working file before changing its supporting evidence."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_working_file_evidence_mutable({
            (vals.get("res_model"), vals.get("res_id")) for vals in vals_list
        })
        return super().create(vals_list)

    def write(self, vals):
        references = {(attachment.res_model, attachment.res_id) for attachment in self}
        if "res_model" in vals or "res_id" in vals:
            references.update({
                (vals.get("res_model", attachment.res_model), vals.get("res_id", attachment.res_id))
                for attachment in self
            })
        self._check_working_file_evidence_mutable(references)
        return super().write(vals)

    def unlink(self):
        self._check_working_file_evidence_mutable({
            (attachment.res_model, attachment.res_id) for attachment in self
        })
        return super().unlink()


class AccountWorkingFileBalance(models.Model):
    _name = "account.working.file.balance"
    _description = "Accounting Working File Account Balance"
    _inherit = ["mail.thread"]
    _order = "sequence, account_id"
    _check_company_auto = True

    _file_account_unique = models.Constraint(
        "UNIQUE(file_id, account_id)",
        "An account can only appear once in a working file balance review.",
    )

    file_id = fields.Many2one(
        "account.working.file", required=True, ondelete="cascade", index=True,
        check_company=True,
    )
    company_id = fields.Many2one(related="file_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="file_id.currency_id")
    account_id = fields.Many2one(
        "account.account", required=True, index=True, check_company=True,
    )
    account_code = fields.Char(compute="_compute_account_display")
    account_name = fields.Char(related="account_id.name")
    account_type = fields.Selection(related="account_id.account_type", store=True, index=True)
    sequence = fields.Integer(default=10)
    balance = fields.Monetary(compute="_compute_balances", currency_field="currency_id")
    balance_previous = fields.Monetary(compute="_compute_balances", currency_field="currency_id")
    variation = fields.Monetary(compute="_compute_variation", currency_field="currency_id")
    variation_percent = fields.Float(compute="_compute_variation", digits=(16, 2))
    last_comment = fields.Text(tracking=True)
    state = fields.Selection(
        [("pending", "Pending Review"), ("reviewed", "Reviewed")],
        default="pending", required=True, tracking=True, index=True,
    )
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False, tracking=True)
    reviewed_on = fields.Datetime(readonly=True, copy=False, tracking=True)

    @api.depends("account_id", "company_id")
    def _compute_account_display(self):
        for line in self:
            account = line.account_id.with_company(line.company_id) if line.company_id else line.account_id
            line.account_code = account.code

    def action_open_journal_items(self):
        self.ensure_one()
        working_file = self.file_id
        return {
            "type": "ir.actions.act_window",
            "name": _("Journal Items"),
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": [
                ("company_id", "=", working_file.company_id.id),
                ("account_id", "=", self.account_id.id),
                ("date", ">=", working_file.date_from),
                ("date", "<=", working_file.date_to),
                ("parent_state", "=", "posted"),
            ],
            "context": {
                "default_company_id": working_file.company_id.id,
                "search_default_posted": 1,
            },
        }

    @api.depends("file_id.date_from", "file_id.date_to", "account_id", "company_id")
    def _compute_balances(self):
        for line in self:
            line.balance = 0.0
            line.balance_previous = 0.0
        lines_by_file = {}
        for line in self:
            if line.file_id and line.account_id:
                lines_by_file.setdefault(line.file_id, []).append(line)

        for file_record, lines in lines_by_file.items():
            company = file_record.company_id
            accounts = self.env["account.account"].with_company(company).browse(
                [line.account_id.id for line in lines]
            )
            opening_ids = accounts.filtered("include_initial_balance").ids
            period_ids = accounts.filtered(lambda account: not account.include_initial_balance).ids
            prior_from = file_record.date_from - relativedelta(years=1)
            prior_to = file_record.date_to - relativedelta(years=1)
            MoveLine = self.env["account.move.line"].with_company(company)

            def sum_balances(date_from, date_to):
                totals = {}
                common_domain = [
                    ("company_id", "=", company.id),
                    ("parent_state", "=", "posted"),
                    ("date", "<=", date_to),
                ]
                if opening_ids:
                    groups = MoveLine._read_group(
                        common_domain + [("account_id", "in", opening_ids)],
                        ["account_id"], ["balance:sum"],
                    )
                    totals.update({account.id: balance or 0.0 for account, balance in groups if account})
                if period_ids:
                    groups = MoveLine._read_group(
                        common_domain + [
                            ("account_id", "in", period_ids),
                            ("date", ">=", date_from),
                        ],
                        ["account_id"], ["balance:sum"],
                    )
                    totals.update({account.id: balance or 0.0 for account, balance in groups if account})
                return totals

            current_totals = sum_balances(file_record.date_from, file_record.date_to)
            previous_totals = sum_balances(prior_from, prior_to)
            for line in lines:
                line.balance = company.currency_id.round(current_totals.get(line.account_id.id, 0.0))
                line.balance_previous = company.currency_id.round(previous_totals.get(line.account_id.id, 0.0))

    @api.depends("balance", "balance_previous")
    def _compute_variation(self):
        for line in self:
            line.variation = line.balance - line.balance_previous
            line.variation_percent = (
                (line.variation / abs(line.balance_previous) * 100.0)
                if line.balance_previous else 0.0
            )

    @api.constrains("company_id", "account_id")
    def _check_account_company(self):
        for line in self:
            if line.company_id and line.account_id and line.company_id not in line.account_id.company_ids:
                raise ValidationError(_("The account must be available to the working file company."))

    def write(self, vals):
        if any(line.file_id.state == "validated" for line in self):
            raise UserError(_("Reopen the working file before changing its balance reviews."))
        if vals.get("state") == "reviewed":
            vals = {**vals, "reviewer_id": self.env.user.id, "reviewed_on": fields.Datetime.now()}
        elif vals.get("state") == "pending":
            vals = {**vals, "reviewer_id": False, "reviewed_on": False}
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state") == "reviewed":
                vals.update(reviewer_id=self.env.user.id, reviewed_on=fields.Datetime.now())
        return super().create(vals_list)

    def unlink(self):
        if any(line.file_id.state == "validated" for line in self):
            raise UserError(_("Reopen the working file before removing its balance reviews."))
        return super().unlink()
