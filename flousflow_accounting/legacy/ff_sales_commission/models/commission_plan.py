from odoo import _, api, fields, models, Command
from odoo.exceptions import ValidationError


class SalesCommissionPlan(models.Model):
    _name = "ff.sales.commission.plan"
    _description = "Sales Commission Plan"
    _order = "company_id, name"
    _check_company_auto = True

    name = fields.Char(string="Plan Name", required=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)
    method = fields.Selection(
        [
            ("sales_then_collection", "Sales target first, then collection achievement"),
            ("combined", "Combined sales and collection achievement"),
        ],
        string="Commission Method", required=True, default="sales_then_collection",
    )
    minimum_achievement = fields.Float(
        string="Minimum Achievement (%)", required=True, default=80.0,
        help="The salesperson must meet this percentage before any commission is earned.",
    )
    target_ids = fields.One2many(
        "ff.sales.commission.target", "plan_id", string="Salesperson Targets", copy=True,
    )
    tier_ids = fields.One2many(
        "ff.sales.commission.tier", "plan_id", string="Commission Tiers", copy=True,
        order="minimum_achievement asc, id asc",
    )
    journal_id = fields.Many2one(
        "account.journal", string="Commission Journal", required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    expense_account_id = fields.Many2one(
        "account.account", string="Commission Expense Account", required=True,
        domain="[('account_type', 'in', ('expense', 'expense_depreciation')), ('company_ids', 'in', [company_id])]",
        check_company=True,
    )
    payable_account_id = fields.Many2one(
        "account.account", string="Commission Payable Account", required=True,
        domain="[('account_type', '=', 'liability_payable'), ('company_ids', 'in', [company_id])]",
        check_company=True,
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if "tier_ids" in fields_list and not values.get("tier_ids"):
            middle_rate = 1.5 if values.get("method", "sales_then_collection") == "combined" else 1.2
            values["tier_ids"] = [
                Command.create({"minimum_achievement": 80.0, "rate_percent": middle_rate}),
                Command.create({"minimum_achievement": 100.0, "rate_percent": 2.0}),
            ]
        return values

    @api.onchange("method")
    def _onchange_method(self):
        """Use the example's default middle tier while preserving custom plan rates."""
        for plan in self:
            middle = plan.tier_ids.filtered(lambda tier: tier.minimum_achievement == 80.0)[:1]
            if middle and middle.rate_percent in (1.2, 1.5):
                middle.rate_percent = 1.5 if plan.method == "combined" else 1.2

    @api.constrains("minimum_achievement", "tier_ids")
    def _check_commission_rules(self):
        for plan in self:
            if not 0 < plan.minimum_achievement <= 100:
                raise ValidationError(_("Minimum achievement must be greater than 0 and no more than 100 percent."))
            if not plan.tier_ids:
                raise ValidationError(_("Add at least one commission tier to the plan."))
            thresholds = plan.tier_ids.mapped("minimum_achievement")
            if len(thresholds) != len(set(thresholds)):
                raise ValidationError(_("Commission tier thresholds must be unique."))
            if any(value < plan.minimum_achievement or value > 10000 for value in thresholds):
                raise ValidationError(_("Each commission tier must start at or above the minimum achievement."))

    @api.constrains("company_id", "journal_id", "expense_account_id", "payable_account_id")
    def _check_accounting_configuration(self):
        for plan in self:
            if plan.journal_id and (plan.journal_id.type != "general" or plan.journal_id.company_id != plan.company_id):
                raise ValidationError(_("Choose a general journal belonging to the plan company."))
            if plan.expense_account_id and plan.company_id not in plan.expense_account_id.company_ids:
                raise ValidationError(_("The commission expense account must belong to the plan company."))
            if plan.payable_account_id and plan.company_id not in plan.payable_account_id.company_ids:
                raise ValidationError(_("The commission payable account must belong to the plan company."))
            if plan.expense_account_id and plan.expense_account_id.account_type not in (
                "expense", "expense_depreciation"
            ):
                raise ValidationError(_("The commission expense account must be an expense account."))
            if plan.payable_account_id and plan.payable_account_id.account_type != "liability_payable":
                raise ValidationError(_("The commission payable account must be a payable account."))


class SalesCommissionTarget(models.Model):
    _name = "ff.sales.commission.target"
    _description = "Salesperson Commission Target"
    _order = "salesperson_id"
    _check_company_auto = True

    plan_id = fields.Many2one(
        "ff.sales.commission.plan", required=True, ondelete="cascade", index=True, check_company=True,
    )
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="plan_id.currency_id", store=True)
    salesperson_id = fields.Many2one(
        "res.users", string="Salesperson", required=True, domain=[("share", "=", False)],
    )
    sales_target = fields.Monetary(
        string="Net Sales Target", currency_field="currency_id", required=True, default=0.0,
    )
    collection_target = fields.Monetary(
        string="Collection Target", currency_field="currency_id", required=True, default=0.0,
    )

    _plan_salesperson_unique = models.Constraint(
        "unique(plan_id, salesperson_id)", "A salesperson can only have one target in a commission plan."
    )
    _targets_non_negative = models.Constraint(
        "CHECK(sales_target >= 0 AND collection_target >= 0)",
        "Sales and collection targets cannot be negative.",
    )

    @api.constrains("salesperson_id", "sales_target", "collection_target", "plan_id")
    def _check_salesperson_and_targets(self):
        for target in self:
            if target.salesperson_id.share:
                raise ValidationError(_("Portal users cannot be commission salespersons."))
            if target.plan_id.company_id not in target.salesperson_id.company_ids:
                raise ValidationError(_("The salesperson must have access to the commission plan company."))
            if not target.sales_target and not target.collection_target:
                raise ValidationError(_("Set at least one sales or collection target for each salesperson."))
            if target.plan_id.method == "sales_then_collection" and (
                not target.sales_target or not target.collection_target
            ):
                raise ValidationError(_("This method requires both a sales target and a collection target."))


class SalesCommissionTier(models.Model):
    _name = "ff.sales.commission.tier"
    _description = "Sales Commission Tier"
    _order = "minimum_achievement asc, id asc"
    _check_company_auto = True

    plan_id = fields.Many2one(
        "ff.sales.commission.plan", required=True, ondelete="cascade", index=True, check_company=True,
    )
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    minimum_achievement = fields.Float(
        string="From Achievement (%)", required=True, default=80.0,
    )
    rate_percent = fields.Float(
        string="Commission Rate (%)", required=True, default=1.2,
    )

    _tier_threshold_unique = models.Constraint(
        "unique(plan_id, minimum_achievement)", "A plan cannot contain duplicate commission tier thresholds."
    )
    _tier_values_valid = models.Constraint(
        "CHECK(minimum_achievement >= 0 AND rate_percent >= 0 AND rate_percent <= 100)",
        "Tier thresholds and commission rates must be valid percentages.",
    )
