from odoo import models, fields


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    sequence = fields.Integer(default=16)