from odoo import api, models


class ReportAnnualDocument(models.AbstractModel):
    _name = "report.flousflow_accounting.apr__report_annual_document"
    _description = "Annual Report Document"

    @api.model
    def _get_report_values(self, docids, data=None):
        documents = self.env["account.annual.report.document"].browse(docids)
        documents.check_access("read")
        return {
            "doc_ids": documents.ids,
            "doc_model": "account.annual.report.document",
            "docs": documents,
        }
