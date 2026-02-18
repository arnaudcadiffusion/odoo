# Copyright 2018 Shine IT 
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class StockMove(models.Model):
    _inherit = 'stock.move'
    packaging_qty = fields.Integer(string="Pack Qty",compute="_compute_packaging_qty")

    @api.depends('product_uom_qty')
    def _compute_packaging_qty(self):
        for record in self:
            if record.product_packaging_id:
                if record.quantity_done:
                    product_qty = record.quantity_done
                else:
                    product_qty = record.product_uom_qty
                default_uom = record.product_id.uom_id
                pack = record.product_packaging_id
                q = default_uom._compute_quantity(pack.qty, record.product_uom_id)
                try:
                    record.packaging_qty = product_qty//q +1 if product_qty%q else product_qty//q
                except ZeroDivisionError:
                    raise ValidationError("The Packaging Contained Quantity Should not set to \
                           Zero")
            else:
                record.packaging_qty = False


class StockRule(models.Model):
    _inherit = 'stock.rule'

    # 利用stockrule 把sale.order.line中的包裹信息传入stock.move模型中
    def _get_stock_move_values(self, product_id, product_qty, product_uom_id, location_id, name, origin, values, group_id):
        result = super(StockRule, self)._get_stock_move_values(product_id, product_qty, product_uom_id, location_id, name, origin, values, group_id)
        if result.get('sale_line_id', False):
            so_line = self.env['sale.order.line'].browse(result['sale_line_id'])
            result['product_packaging_id'] = so_line.product_packaging_id.id
        return result

    # 对mto过程中产生po.line的赋值函数继承。添加packaging信息
    # 如果是直运。则直接使用so_line的pack信息。否则则使用move上pack的信息
    def _prepare_purchase_order_line(self, product_id, product_qty, product_uom_id, values, po, partner):
        result = super(StockRule,self)._prepare_purchase_order_line(product_id,product_qty,product_uom_id,values,po,partner)
        dropshipping_so = values.get('sale_line_id',False)
        if dropshipping_so:
            so_line = self.env['sale.order.line'].browse(dropshipping_so)
            result['product_packaging_id'] = so_line.product_packaging_id.id
            return result
        move_id = values.get('move_dest_ids',False)
        if move_id:
            result['product_packaging_id'] = move_id[0].product_packaging_id.id
        return result


