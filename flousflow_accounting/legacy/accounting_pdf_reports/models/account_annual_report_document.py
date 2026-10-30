from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.pdf import merge_pdf


class AccountAnnualReportTemplate(models.Model):
    _name = "account.annual.report.template"
    _description = "Annual Report Template"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", index=True)
    section_ids = fields.One2many(
        "account.annual.report.template.section", "template_id", string="Sections",
        copy=True,
    )


class AccountAnnualReportTemplateSection(models.Model):
    _name = "account.annual.report.template.section"
    _description = "Annual Report Template Section"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "account.annual.report.template", required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    content = fields.Html(sanitize=True, translate=True)
    page_break_before = fields.Boolean(string="Start on a New Page")


class AccountAnnualReportDocument(models.Model):
    _name = "account.annual.report.document"
    _description = "Annual Report"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_to desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="Title", required=True, tracking=True)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company,
        index=True, tracking=True,
    )
    date_from = fields.Date(
        string="Start Date", required=True,
        default=lambda self: self._default_date_from(), tracking=True,
    )
    date_to = fields.Date(
        string="End Date", required=True,
        default=lambda self: self._default_date_to(), tracking=True,
    )
    responsible_user_ids = fields.Many2many(
        "res.users", "annual_report_document_user_rel", "report_id", "user_id",
        string="Responsible Users", default=lambda self: self.env.user,
    )
    template_id = fields.Many2one(
        "account.annual.report.template", string="Template", check_company=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        default=lambda self: self.env.ref(
            "flousflow_accounting.apr__annual_report_template_standard", raise_if_not_found=False,
        ),
    )
    section_ids = fields.One2many(
        "account.annual.report.document.section", "report_id", string="Pages and Sections",
        copy=True,
    )
    attachment_ids = fields.Many2many(
        "ir.attachment", "annual_report_document_attachment_rel", "report_id", "attachment_id",
        string="Attachments", check_company=True,
    )
    image_attachment_ids = fields.Many2many(
        "ir.attachment", compute="_compute_attachment_groups",
    )
    other_attachment_ids = fields.Many2many(
        "ir.attachment", compute="_compute_attachment_groups",
    )
    currency_id = fields.Many2one(related="company_id.currency_id", store=True)

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(year=today.year - 1, month=1, day=1)

    @api.model
    def _default_date_to(self):
        today = fields.Date.context_today(self)
        return today.replace(year=today.year - 1, month=12, day=31)

    @api.depends("attachment_ids", "attachment_ids.mimetype")
    def _compute_attachment_groups(self):
        for report in self:
            report.image_attachment_ids = report.attachment_ids.filtered(
                lambda attachment: (attachment.mimetype or "").startswith("image/")
            )
            report.other_attachment_ids = report.attachment_ids.filtered(
                lambda attachment: attachment.mimetype != "application/pdf"
                and not (attachment.mimetype or "").startswith("image/")
            )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        template_id = values.get("template_id")
        if "section_ids" in fields_list and template_id and not values.get("section_ids"):
            template = self.env["account.annual.report.template"].browse(template_id)
            values["section_ids"] = [
                Command.create({
                    "sequence": section.sequence,
                    "name": section.name,
                    "content": section.content,
                    "page_break_before": section.page_break_before,
                })
                for section in template.section_ids
            ]
        return values

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for report in self:
            if report.date_from and report.date_to and report.date_from > report.date_to:
                raise ValidationError(_("The start date must be before the end date."))

    @api.onchange("template_id")
    def _onchange_template_id(self):
        for report in self:
            if report.template_id:
                report.section_ids = [
                    Command.create({
                        "sequence": section.sequence,
                        "name": section.name,
                        "content": section.content,
                        "page_break_before": section.page_break_before,
                    })
                    for section in report.template_id.section_ids
                ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "template_id" not in vals:
                vals["template_id"] = self.default_get(["template_id"]).get("template_id")
            if vals.get("template_id") and not vals.get("section_ids"):
                template = self.env["account.annual.report.template"].browse(vals["template_id"])
                vals["section_ids"] = [
                    Command.create({
                        "sequence": section.sequence,
                        "name": section.name,
                        "content": section.content,
                        "page_break_before": section.page_break_before,
                    })
                    for section in template.section_ids
                ]
        return super().create(vals_list)

    def action_print_pdf(self):
        self.ensure_one()
        self.check_access("read")
        if any(
            attachment.company_id and attachment.company_id != self.company_id
            for attachment in self.attachment_ids
        ):
            raise UserError(_("Remove attachments that belong to another company before printing."))

        pdf_content, output_type = self.env["ir.actions.report"]._render_qweb_pdf(
            "flousflow_accounting.apr__report_annual_document", res_ids=self.ids,
        )
        if output_type != "pdf":
            raise UserError(_("The PDF engine did not return a PDF document."))

        attached_pdfs = [
            attachment.raw
            for attachment in self.attachment_ids.sorted("id")
            if attachment.mimetype == "application/pdf" and attachment.raw
        ]
        if attached_pdfs:
            try:
                pdf_content = merge_pdf([pdf_content, *attached_pdfs])
            except Exception as error:
                raise UserError(_("One of the attached PDF files could not be added to the report.")) from error

        filename = "%s.pdf" % (self.name.replace("/", "-").strip() or _("Annual Report"))
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "raw": pdf_content,
            "mimetype": "application/pdf",
            "res_model": self._name,
            "res_id": self.id,
            "company_id": self.company_id.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }


class AccountAnnualReportDocumentSection(models.Model):
    _name = "account.annual.report.document.section"
    _description = "Annual Report Page or Section"
    _order = "sequence, id"
    _check_company_auto = True

    report_id = fields.Many2one(
        "account.annual.report.document", required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(related="report_id.company_id", store=True, index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)
    content = fields.Html(sanitize=True, translate=True)
    page_break_before = fields.Boolean(string="Start on a New Page")
