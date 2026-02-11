from odoo import models

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    def _get_product_purchase_description(self, product_lang):
        """Override to include product default_code (reference) in description"""
        name = super()._get_product_purchase_description(product_lang)

        default_code = product_lang.with_context(partner_id=False).default_code
        if default_code and default_code not in name:
            parts = name.split("\n", 1)
            parts[0] = "{} ({})".format(parts[0], default_code)
            name = "\n".join(parts)

        return name
