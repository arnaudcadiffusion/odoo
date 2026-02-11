# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
################################################################################

from odoo import models, fields, api, _

class account_invoice_line(models.Model):

    _inherit = "account.move.line"

    line_margin = fields.Float(string='Margin', digits='Account',store=True, readonly=True,compute='_calc_margin')
    purchase_price =  fields.Float('Cost', compute='_get_product_cost' ,digits='Product Price')
    margin_subtotal_signed = fields.Float(string='Margin Signed', readonly=True,store=True, compute='_calc_margin')

    @api.depends('product_id')
    def _get_product_cost(self):
        for n in self:
            frm_cur = self.env.company.currency_id
            to_cur = n.move_id.currency_id
            purchase_price = n.product_id.standard_price
            product_uom = n.product_id.uom_id
            if product_uom and n.product_uom_id and n.product_uom_id != n.product_id.uom_id:
                purchase_price = n.product_id.uom_id._compute_price(purchase_price, n.product_uom_id)
            price = frm_cur._convert(
                                    purchase_price, to_cur,
                                    n.move_id.company_id or self.env.company,
                                    fields.Date.today(), round=False)
            n.purchase_price =  price

    @api.depends('price_unit', 'discount', 'tax_ids', 'quantity',
                 'product_id', 'move_id.partner_id', 'move_id.currency_id')
    def _calc_margin(self):
        for res in self:
            line_mrg_tot = 0
            cmp = 0.0
            cmp = ((res.purchase_price or res.product_id.standard_price) * res.quantity)
            margin = res.price_subtotal - cmp
            res.line_margin = margin
            margin_subtotal_signed = margin
            sign = res.move_id.move_type in ['in_refund', 'out_refund'] and -1 or 1
            res.margin_subtotal_signed = margin_subtotal_signed * sign



    
class account_invoice(models.Model):
    _inherit = "account.move"

    margin_cust = fields.Float('Margin %', compute='_calc_margin')
    margin_calc = fields.Float('Margin', compute='_calc_margin')
    
    @api.depends('invoice_line_ids')
    def _calc_margin(self): 
        for order in self:
            line_mrg_tot = 0
            margin = 0.0
            cmp = 0.0
            for line in order.invoice_line_ids:
                cmp += (line.purchase_price * line.quantity)
                margin = line.price_subtotal - ((line.purchase_price or line.product_id.standard_price) * line.quantity)
                line_mrg_tot += margin 
            if order.amount_total != 0 and order.amount_untaxed != 0:
                order.update({
                    'margin_cust' : (line_mrg_tot * 100) / order.amount_untaxed,
                    'margin_calc' : line_mrg_tot
                })
            else:
                order.update({
                    'margin_cust' : 0.0,
                    'margin_calc' : 0.0
                })


