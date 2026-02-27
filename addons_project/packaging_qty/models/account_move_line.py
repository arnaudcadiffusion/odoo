from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    packaging_qty = fields.Integer(string="Pack Qty", compute="_compute_packaging_qty")
    product_packaging_id = fields.Many2one("uom.uom")
    product_uom_ids = fields.Many2many(
        "uom.uom",
        related="product_id.uom_ids",
    )

    @api.depends("quantity", "product_packaging_id", "product_uom_id")
    def _compute_packaging_qty(self):
        for record in self:
            if record.product_packaging_id:
                default_uom = record.product_id.uom_id
                product_qty = record.quantity
                pack = record.product_packaging_id
                q = record.product_uom_id._compute_quantity(
                    pack.relative_factor, default_uom
                )
                try:
                    record.packaging_qty = (
                        product_qty // q + 1 if product_qty % q else product_qty // q
                    )
                except ZeroDivisionError:
                    raise ValidationError(
                        "The Packaging Contained Quantity Should not set to \
                           Zero"
                    )
            else:
                record.packaging_qty = False
