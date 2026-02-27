# Copyright 2018 Shine IT
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _
from odoo.tools.float_utils import float_compare, float_round
from odoo.exceptions import UserError, ValidationError


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    product_packaging_id = fields.Many2one(related="product_uom_id")
    product_packaging_qty = fields.Float(related="product_uom_qty")

    # @api.onchange('product_packaging_id')
    # def _onchange_product_packaging_id(self):
    #     if not self.product_packaging_id:
    #         self.product_packaging_qty = False
    #     else:
    #         self.product_packaging_qty = 1
    #         self._onchange_product_packaging_qty()

    # @api.onchange('product_uom_id', 'product_qty')
    # def _onchange_update_product_packaging_qty(self):
    #     if not self.product_packaging_id:
    #         self.product_packaging_qty = 0
    #     else:
    #         packaging_uom = self.product_packaging_id.product_uom_id
    #         packaging_uom_qty = self.product_uom_id._compute_quantity(self.product_qty, packaging_uom)
    #         self.product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty, precision_rounding=packaging_uom.rounding)

    def _compute_packaging_amount(self):
        default_uom = self.product_id.uom_id
        pack = self.product_packaging_id
        q = default_uom._compute_quantity(pack.qty, self.product_uom_id)
        return q

    @api.onchange('product_qty')
    def _onchange_check_product_qty(self):
        if self.product_packaging_id:
            q = self._compute_packaging_amount()
            if q == 0:
                return {'warning':{'title':'Zero Warning!',
                                   'message':'Packaging Contained Quantity\
                                   Cant Set to Zero'}}
            if self.product_qty % q:
                old_product_qty = self.product_qty
                new_product_qty = q * (self.product_qty//q+1)
                return {'warning': {'title':'Qty Warning!',
                                    'message':'Your input quantity is \
                                    %.2f,however the packaging is %.2f bases.\
                                    I will change your quantity to %.2f.'
                                    %(old_product_qty,q,new_product_qty)},
                        'value':{'product_qty':new_product_qty}
                       }

    # PO_Line 转为stock_move 时添加packaging 信息
    def _prepare_stock_moves(self, picking):
        """ Prepare the stock moves data for one order line. This function returns a list of
        dictionary ready to be used in stock.move's create()
        """
        res = super(PurchaseOrderLine,self)._prepare_stock_moves(picking)
        for record in res:
            if self.product_packaging_id:
                record['product_packaging_id'] = self.product_packaging_id.id
        return res


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    #使用内部创建so功能时传入packaging信息
    @api.model
    def _prepare_sale_order_line_data(self, line, company):
        """ Generate the Sales Order Line values from the PO line
            :param line : the origin Purchase Order Line
            :rtype line : purchase.order.line record
            :param company : the company of the created SO
            :rtype company : res.company record
            :param sale_id : the id of the SO
        """
        result = super(PurchaseOrder,self)._prepare_sale_order_line_data(line,company)
        result['product_packaging_id'] = line.product_packaging_id.id
        result['product_packaging_qty'] = line.product_packaging_qty
        return result
