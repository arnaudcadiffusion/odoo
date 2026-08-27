from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    x_studio_pricelist = fields.Char(
        string='Liste de prix de base',
        related='base_pricelist_id.name',
        store=True,
        translate=False,
    )
    x_studio_ref = fields.Char(
        string='Ref',
        related='product_tmpl_id.default_code',
        store=True,
    )
