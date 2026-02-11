# Copyright 2018 Shine IT
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    article_cmd = fields.Char('Article cmdé')

    # 不需要弹出数量不足的提醒
    # @api.onchange('product_uom_qty', 'product_uom', 'route_id')
    # def _onchange_product_id_check_availability(self):
    #     TODO: check equivalent of model product_packing

    #     if not self.product_id or not self.product_uom_qty or not self.product_uom:
    #         self.product_packaging_id = False
    #         return {}

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def print_invoice(self):
        invoices = self.mapped('invoice_ids')
        return self.env.ref('account.account_invoices').report_action(invoices)
