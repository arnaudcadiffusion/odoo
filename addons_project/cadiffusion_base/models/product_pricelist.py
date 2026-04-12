# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    x_studio_pricelist = fields.Char(
        string='Pricelist',
        related='base_pricelist_id.name',
        store=True,
    )
    x_studio_ref = fields.Char(
        string='Ref',
        related='product_tmpl_id.default_code',
        store=True,
    )
