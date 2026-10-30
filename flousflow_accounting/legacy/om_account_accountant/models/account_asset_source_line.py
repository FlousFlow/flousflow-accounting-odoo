from odoo import fields, models


class AccountAssetAsset(models.Model):
    _inherit = "account.asset.asset"

    invoice_line_id = fields.Many2one(
        "account.move.line",
        string="Source Invoice Line",
        index=True,
        copy=False,
        readonly=True,
        ondelete="set null",
    )


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    def _prepare_asset_vals(self):
        values_list = super()._prepare_asset_vals()
        for values in values_list:
            values["invoice_line_id"] = self.id
        return values_list
