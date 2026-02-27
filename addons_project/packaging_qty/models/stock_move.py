

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'

    packaging_qty = fields.Integer(string="Pack Qty", compute="_compute_packaging_qty")
    product_packaging_id = fields.Many2one(related="packaging_uom_id")

    @api.depends('product_uom_qty')
    def _compute_packaging_qty(self):
        for record in self:
            if record.product_packaging_id:
                if record.quantity:
                    product_qty = record.quantity
                else:
                    product_qty = record.product_uom_qty
                default_uom = record.product_id.uom_id
                pack = record.product_packaging_id
                q = default_uom._compute_quantity(
                    pack.relative_factor, record.product_uom
                )
                try:
                    record.packaging_qty = product_qty//q +1 if product_qty%q else product_qty//q
                except ZeroDivisionError:
                    raise ValidationError("The Packaging Contained Quantity Should not set to \
                           Zero")
            else:
                record.packaging_qty = False



