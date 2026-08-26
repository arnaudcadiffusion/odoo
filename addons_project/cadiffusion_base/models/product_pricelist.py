from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    ca_diff_pricelist = fields.Char(
        string='Liste de prix de base',
        related='base_pricelist_id.name',
        store=True,
        translate=False,
    )
    ca_diff_ref = fields.Char(
        string='Ref',
        related='product_tmpl_id.default_code',
        store=True,
    )
