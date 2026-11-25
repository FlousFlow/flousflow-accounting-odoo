from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SalesCommissionBatch(models.Model):
    _name = "ff.sales.commission.batch"
    _description = "Sales Commission Run"
    _order = "date_to desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Reference", required=True, readonly=True, copy=False, default="New", index=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company, index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    plan_id = fields.Many2one(
        "ff.sales.commission.plan", string="Commission Plan", required=True, check_company=True,
        domain="[('active', '=', True), ('company_id', '=', company_id)]",
    )
    date_from = fields.Date(string="Period From", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="Period To", required=True, default=fields.Date.context_today)
    state = fields.Selection(
        [("draft", "Draft"), ("calculated", "Calculated"), ("posted", "Posted")],
        default="draft", required=True, readonly=True, copy=False, index=True,
    )
    calculated_at = fields.Datetime(string="Last Calculated On", readonly=True, copy=False)
    line_ids = fields.One2many("ff.sales.commission.line", "batch_id", string="Salespeople", readonly=True)
    move_id = fields.Many2one(
        "account.move", string="Commission Journal Entry", readonly=True, copy=False, check_company=True,
    )
    salesperson_count = fields.Integer(compute="_compute_totals")
    total_sales = fields.Monetary(compute="_compute_totals", currency_field="currency_id", store=True)
    total_collected = fields.Monetary(compute="_compute_totals", currency_field="currency_id", store=True)
    total_commission = fields.Monetary(compute="_compute_totals", currency_field="currency_id", store=True)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = sequence.next_by_code("ff.sales.commission.batch") or "New"
        return super().create(vals_list)

    @api.depends("line_ids", "line_ids.sales_net", "line_ids.collected_gross", "line_ids.commission_amount")
    def _compute_totals(self):
        for batch in self:
            batch.salesperson_count = len(batch.line_ids)
            batch.total_sales = sum(batch.line_ids.mapped("sales_net"))
            batch.total_collected = sum(batch.line_ids.mapped("collected_gross"))
            batch.total_commission = sum(batch.line_ids.mapped("commission_amount"))

    @api.constrains("date_from", "date_to", "company_id", "plan_id")
    def _check_period_and_company(self):
        for batch in self:
            if batch.date_from and batch.date_to and batch.date_from > batch.date_to:
                raise ValidationError(_("The period start date must be on or before the end date."))
            if batch.plan_id and batch.plan_id.company_id != batch.company_id:
                raise ValidationError(_("The commission plan and the run must belong to the same company."))

    def write(self, vals):
        if not self.env.context.get("allow_commission_state_write"):
            if {"state", "move_id", "calculated_at"}.intersection(vals):
                raise UserError(_("Use the Calculate and Post actions to change a commission run."))
            if any(batch.state != "draft" for batch in self) and vals:
                raise UserError(_("A calculated or posted commission run is locked."))
        return super().write(vals)

    def _check_calculate_access(self):
        if not (
            self.env.user.has_group("account.group_account_invoice")
            or self.env.user.has_group("account.group_account_manager")
        ):
            raise UserError(_("Only accounting users can calculate salesperson commissions."))

    def action_calculate(self):
        self._check_calculate_access()
        for batch in self:
            if batch.state == "posted":
                raise UserError(_("Posted commission runs cannot be recalculated."))
            if not batch.plan_id.active:
                raise UserError(_("Activate the commission plan before calculating this run."))
            if batch.plan_id.company_id != batch.company_id:
                raise UserError(_("The selected plan belongs to a different company."))
            if not batch.plan_id.target_ids:
                raise UserError(_("Add salesperson targets to the commission plan before calculating."))
            if batch.plan_id.method == "sales_then_collection" and any(
                not target.sales_target or not target.collection_target for target in batch.plan_id.target_ids
            ):
                raise UserError(_("This method requires both a sales and a collection target for every salesperson."))

            company = batch.company_id
            targets = batch.plan_id.target_ids
            users = targets.mapped("salesperson_id")
            sales_by_user = defaultdict(float)
            source_rows_by_user = defaultdict(list)

            Move = self.env["account.move"].sudo().with_company(company)
            invoices = Move.search([
                ("company_id", "=", company.id),
                ("invoice_user_id", "in", users.ids),
                ("move_type", "in", ("out_invoice", "out_refund")),
                ("state", "=", "posted"),
                ("invoice_date", ">=", batch.date_from),
                ("invoice_date", "<=", batch.date_to),
            ])
            for invoice in invoices:
                user_id = invoice.invoice_user_id.id
                sales_amount = invoice.amount_untaxed_signed
                sales_by_user[user_id] += sales_amount
                source_rows_by_user[user_id].append({
                    "invoice_id": invoice.id,
                    "source_date": invoice.invoice_date,
                    "sales_net": sales_amount,
                })

            # Collections are counted only when Odoo has reconciled an inbound payment
            # or bank-statement transaction against a posted customer invoice.
            partials = self.env["account.partial.reconcile"].sudo().with_company(company).search([
                ("company_id", "=", company.id),
                ("max_date", ">=", batch.date_from),
                ("max_date", "<=", batch.date_to),
                ("debit_move_id.account_id.account_type", "=", "asset_receivable"),
                ("debit_move_id.move_id.company_id", "=", company.id),
                ("debit_move_id.move_id.move_type", "=", "out_invoice"),
                ("debit_move_id.move_id.state", "=", "posted"),
                ("debit_move_id.move_id.invoice_user_id", "in", users.ids),
            ])
            collected_by_invoice_and_move = defaultdict(float)
            collection_date_by_key = {}
            invoice_by_id = {}
            for partial in partials:
                invoice_line = partial.debit_move_id
                invoice = invoice_line.move_id
                counterpart = partial.credit_move_id
                payment = counterpart.payment_id
                statement_line = counterpart.statement_line_id
                if payment:
                    if payment.payment_type != "inbound" or payment.move_id.state != "posted":
                        continue
                    collection_date = payment.date
                    collection_move = payment.move_id
                elif statement_line and counterpart.move_id.state == "posted":
                    collection_date = statement_line.date
                    collection_move = counterpart.move_id
                else:
                    # Credit notes, write-offs, exchange differences, and manual
                    # journal entries are not cash collections.
                    continue
                if not collection_date or not (batch.date_from <= collection_date <= batch.date_to):
                    continue
                total_signed = invoice.amount_total_signed
                untaxed_share = abs(invoice.amount_untaxed_signed / total_signed) if total_signed else 0.0
                key = (invoice.id, collection_move.id)
                collected_by_invoice_and_move[key] += partial.amount
                collection_date_by_key[key] = collection_date
                invoice_by_id[invoice.id] = invoice
                user_id = invoice.invoice_user_id.id
                source_rows_by_user[user_id].append({
                    "invoice_id": invoice.id,
                    "collection_move_id": collection_move.id,
                    "source_date": collection_date,
                    "collected_gross": partial.amount,
                    "collected_net": partial.amount * untaxed_share,
                })

            # Combine reconciliation fragments for the same invoice/payment pair.
            grouped_sources = defaultdict(dict)
            for user_id, rows in source_rows_by_user.items():
                for row in rows:
                    key = (row["invoice_id"], row.get("collection_move_id", False))
                    grouped = grouped_sources[user_id].setdefault(key, {
                        "invoice_id": row["invoice_id"],
                        "collection_move_id": row.get("collection_move_id", False),
                        "source_date": row["source_date"],
                        "sales_net": 0.0,
                        "collected_gross": 0.0,
                        "collected_net": 0.0,
                    })
                    grouped["sales_net"] += row.get("sales_net", 0.0)
                    if row.get("collection_move_id"):
                        grouped["collected_gross"] = collected_by_invoice_and_move[key]
                        invoice = invoice_by_id[row["invoice_id"]]
                        total_signed = invoice.amount_total_signed
                        untaxed_share = abs(invoice.amount_untaxed_signed / total_signed) if total_signed else 0.0
                        grouped["collected_net"] = grouped["collected_gross"] * untaxed_share
                        grouped["source_date"] = collection_date_by_key[key]

            line_commands = []
            for target in targets:
                user_id = target.salesperson_id.id
                sales = company.currency_id.round(sales_by_user[user_id])
                source_rows = list(grouped_sources[user_id].values())
                collected_gross = company.currency_id.round(sum(row["collected_gross"] for row in source_rows))
                collected_net = company.currency_id.round(sum(row["collected_net"] for row in source_rows))
                sales_achievement = sales / target.sales_target * 100.0 if target.sales_target else 0.0
                collection_achievement = (
                    collected_gross / target.collection_target * 100.0 if target.collection_target else 0.0
                )
                combined_target = target.sales_target + target.collection_target
                combined_achievement = (
                    (sales + collected_gross) / combined_target * 100.0 if combined_target else 0.0
                )
                if batch.plan_id.method == "sales_then_collection":
                    eligible = sales_achievement >= batch.plan_id.minimum_achievement
                    tier_measure = collection_achievement
                else:
                    eligible = combined_achievement >= batch.plan_id.minimum_achievement
                    tier_measure = combined_achievement
                tier = batch.plan_id.tier_ids.filtered(
                    lambda item: item.minimum_achievement <= tier_measure
                )[-1:]
                rate = tier.rate_percent if eligible and tier else 0.0
                commission = company.currency_id.round(collected_net * rate / 100.0)
                line_commands.append({
                    "batch_id": batch.id,
                    "salesperson_id": user_id,
                    "target_sales": target.sales_target,
                    "target_collection": target.collection_target,
                    "sales_net": sales,
                    "collected_gross": collected_gross,
                    "collected_net": collected_net,
                    "sales_achievement": sales_achievement,
                    "collection_achievement": collection_achievement,
                    "combined_achievement": combined_achievement,
                    "eligible": eligible,
                    "commission_rate": rate,
                    "commission_amount": commission,
                    "source_rows": source_rows,
                })

            batch.line_ids.sudo().unlink()
            Line = self.env["ff.sales.commission.line"].sudo()
            for vals in line_commands:
                source_rows = vals.pop("source_rows")
                line = Line.create(vals)
                if source_rows:
                    self.env["ff.sales.commission.source"].sudo().create([
                        dict(row, line_id=line.id) for row in source_rows
                    ])
            batch.with_context(allow_commission_state_write=True).write({
                "state": "calculated",
                "calculated_at": fields.Datetime.now(),
            })
        return True

    def action_post(self):
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only an accounting manager can post a commission run."))
        for batch in self:
            if batch.state != "calculated" or batch.move_id:
                raise UserError(_("Calculate this commission run before posting it."))
            if not batch.line_ids.filtered(lambda line: line.commission_amount > 0):
                raise UserError(_("There are no earned commissions to post in this run."))

            self.env.cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", [6112026, batch.company_id.id])
            overlapping = self.search([
                ("id", "!=", batch.id),
                ("company_id", "=", batch.company_id.id),
                ("state", "=", "posted"),
                ("date_from", "<=", batch.date_to),
                ("date_to", ">=", batch.date_from),
            ])
            posted_salespeople = set(overlapping.mapped("line_ids.salesperson_id").ids)
            current_salespeople = set(batch.line_ids.filtered(
                lambda line: line.commission_amount > 0
            ).mapped("salesperson_id").ids)
            if posted_salespeople.intersection(current_salespeople):
                raise UserError(_(
                    "A posted commission run already covers part of this period for one or more salespeople. "
                    "Use a non-overlapping period to avoid paying the same commission twice."
                ))

            plan = batch.plan_id
            plan._check_accounting_configuration()
            move_lines = []
            for line in batch.line_ids.filtered(lambda item: item.commission_amount > 0):
                partner = line.salesperson_id.partner_id
                label = _("Sales commission: %(salesperson)s", salesperson=line.salesperson_id.display_name)
                amount = batch.currency_id.round(line.commission_amount)
                move_lines.extend([
                    (0, 0, {
                        "name": label,
                        "account_id": plan.expense_account_id.id,
                        "partner_id": partner.id,
                        "debit": amount,
                        "credit": 0.0,
                    }),
                    (0, 0, {
                        "name": label,
                        "account_id": plan.payable_account_id.id,
                        "partner_id": partner.id,
                        "debit": 0.0,
                        "credit": amount,
                    }),
                ])
            move = self.env["account.move"].create({
                "move_type": "entry",
                "company_id": batch.company_id.id,
                "journal_id": plan.journal_id.id,
                "date": batch.date_to,
                "ref": _("Sales commissions %(reference)s", reference=batch.name),
                "line_ids": move_lines,
            })
            move.action_post()
            batch.with_context(allow_commission_state_write=True).write({
                "move_id": move.id,
                "state": "posted",
            })
        return {
            "type": "ir.actions.act_window",
            "name": _("Commission Journal Entry"),
            "res_model": "account.move",
            "res_id": self[:1].move_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_("This commission run does not have a journal entry yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Commission Journal Entry"),
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }


class SalesCommissionLine(models.Model):
    _name = "ff.sales.commission.line"
    _description = "Sales Commission Result"
    _order = "salesperson_id"
    _check_company_auto = True

    batch_id = fields.Many2one(
        "ff.sales.commission.batch", required=True, ondelete="cascade", index=True, check_company=True,
    )
    company_id = fields.Many2one(related="batch_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="batch_id.currency_id", store=True)
    salesperson_id = fields.Many2one("res.users", string="Salesperson", required=True, readonly=True)
    target_sales = fields.Monetary(string="Net Sales Target", currency_field="currency_id", readonly=True)
    target_collection = fields.Monetary(string="Collection Target", currency_field="currency_id", readonly=True)
    sales_net = fields.Monetary(string="Net Sales", currency_field="currency_id", readonly=True)
    collected_gross = fields.Monetary(string="Collections Incl. VAT", currency_field="currency_id", readonly=True)
    collected_net = fields.Monetary(string="Collections Excl. VAT", currency_field="currency_id", readonly=True)
    sales_achievement = fields.Float(string="Sales Achievement (%)", readonly=True)
    collection_achievement = fields.Float(string="Collection Achievement (%)", readonly=True)
    combined_achievement = fields.Float(string="Combined Achievement (%)", readonly=True)
    eligible = fields.Boolean(string="Eligible", readonly=True)
    commission_rate = fields.Float(string="Commission Rate (%)", readonly=True)
    commission_amount = fields.Monetary(string="Commission Amount", currency_field="currency_id", readonly=True)
    source_ids = fields.One2many("ff.sales.commission.source", "line_id", string="Source Documents", readonly=True)

    _batch_salesperson_unique = models.Constraint(
        "unique(batch_id, salesperson_id)", "Each salesperson can appear only once in a commission run."
    )


class SalesCommissionSource(models.Model):
    _name = "ff.sales.commission.source"
    _description = "Sales Commission Source"
    _order = "source_date, invoice_id, collection_move_id"
    _check_company_auto = True

    line_id = fields.Many2one(
        "ff.sales.commission.line", required=True, ondelete="cascade", index=True, check_company=True,
    )
    company_id = fields.Many2one(related="line_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="line_id.currency_id", store=True)
    source_date = fields.Date(string="Source Date", readonly=True)
    invoice_id = fields.Many2one(
        "account.move", string="Customer Invoice / Credit Note", readonly=True, check_company=True,
    )
    collection_move_id = fields.Many2one(
        "account.move", string="Receipt / Bank Transaction", readonly=True, check_company=True,
    )
    sales_net = fields.Monetary(string="Net Sales", currency_field="currency_id", readonly=True)
    collected_gross = fields.Monetary(string="Collection Incl. VAT", currency_field="currency_id", readonly=True)
    collected_net = fields.Monetary(string="Collection Excl. VAT", currency_field="currency_id", readonly=True)
