# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
################################################################################


from odoo import models, fields, api, _
from odoo.tools import format_amount,float_round


class product_product(models.Model):
    _inherit = "product.template"

    def _calc_margin(self):
        currency = self.currency_id
        for product in self:
            ans = 0
            product_margin  = 0
            if product.list_price == 0 or product.standard_price == 0:
                ans = 0
            else:
                if self.env.company.account_price_include == 'tax_excluded':
                    ans = ((product.list_price - product.standard_price) / product.list_price) * 100
                    product_margin = product.list_price - product.standard_price
                else:
                    res = product.taxes_id.filtered(lambda t: t.company_id == self.env.company).compute_all(
                        product.list_price, product=product, partner=self.env['res.partner']
                    )
                    excluded = res['total_excluded']
                    amount_value = float_round(excluded, precision_rounding=currency.rounding)
                    
                    ans = ((amount_value - product.standard_price) / amount_value) * 100
                    product_margin = amount_value - product.standard_price
            product.update({'margin' : ans,'product_margin_calc':product_margin})                      
                           
    margin = fields.Float('Margin %', compute='_calc_margin' , readonly=True)
    product_margin_calc = fields.Float('Margin ', compute='_calc_margin' , readonly=True)
    list_price = fields.Float('Sale Price', digits='Product Price', help="Base price to compute the customer price. Sometimes called the catalog price.")
    
    standard_price = fields.Float(digits='Product Price',groups="base.group_user", string="Cost Price")
