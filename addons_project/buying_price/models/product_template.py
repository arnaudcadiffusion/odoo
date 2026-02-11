from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    buying_price = fields.Float(string="Buying Price", digits="Product Price")

    number_of_hours
