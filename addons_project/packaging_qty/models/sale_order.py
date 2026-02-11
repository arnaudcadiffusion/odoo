# Copyright 2018 Shine IT
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare, float_round

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _compute_packaging_amount(self):
        default_uom = self.product_id.uom_id
        pack = self.product_packaging_id
        q = default_uom._compute_quantity(pack.qty, self.product_uom)
        return q


    def _mapping_invoice_delivery_by_qty(self,qty_to_invoice):
        """
        Create the invoice_line associated to the stock_move
        :param qty_to_invoice: use this qty to mapping invoice_line and stock_moves 
        :return String: the name of stock_picking
        """
        self.ensure_one()
        moves = self.move_ids.filtered(lambda move:move.state=='done')
        todo_moves = self.env['stock.move']
        for move in moves:
            todo_moves |= move
            if sum(todo_moves.mapped('quantity_done')) == qty_to_invoice:
                return ','.join(todo_moves.mapped('picking_id.name'))

    # 创建invoice_line时候加入packaging信息
    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleOrderLine,self)._prepare_invoice_line(**optional_values)
        so_line = self.browse(res.get('sale_line_ids')[0][1])
        res.update({'product_packaging_id': so_line[0].product_packaging_id.id})
        return res

    #改写原先的onchange。选择packaging时不进行check
    @api.onchange('product_packaging_id')
    def _onchange_product_packaging_id(self):
        if self.product_packaging_id:
            return {}

    @api.onchange('product_packaging_id')
    def _onchange_product_packaging_id(self):
        if not self.product_packaging_id:
            self.product_packaging_qty = False
        else:
            self.product_packaging_qty = 1
            self._onchange_product_packaging_qty()
            
    @api.onchange('product_uom', 'product_uom_qty')
    def _onchange_update_product_packaging_qty(self):
        if not self.product_packaging_id:
            self.product_packaging_qty = False
        else:
            packaging_uom = self.product_packaging_id.product_uom_id
            packaging_uom_qty = self.product_uom._compute_quantity(self.product_uom_qty, packaging_uom)
            self.product_packaging_qty = float_round(packaging_uom_qty / self.product_packaging_id.qty, precision_rounding=packaging_uom.rounding)

    @api.onchange('product_uom_qty')
    def _onchange_check_product_qty(self):
        if self.product_packaging_id:
            q = self._compute_packaging_amount()
            if q == 0:
                return {'warning':{'title':'Zero Warning!',
                                   'message':'Packaging Contained Quantity\
                                   Cant Set to Zero'}}
            if self.product_uom_qty % q:
                old_product_uom_qty = self.product_uom_qty
                new_product_uom_qty = q * (self.product_uom_qty//q+1)
                return {'warning': {'title':'Qty Warning!',
                                    'message':'Your input quantity is \
                                    %.2f,however the packaging is %.2f bases.\
                                    I will change your quantity to %.2f.'
                                    %(old_product_uom_qty,q,new_product_uom_qty)},
                        'value':{'product_uom_qty':new_product_uom_qty}
                       }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _compute_sequence(self, name, index):
        return name.count(',')*300+index*10


    def _create_invoices(self, grouped=False, final=False):
        account_invoice = super(SaleOrder,self)._create_invoices(grouped,final)
        for invoice in account_invoice:
            picking_name = {}
            for index,line in enumerate(invoice.invoice_line_ids):
                if line.sale_line_ids:
                    so_line = line.sale_line_ids[0]
                    name = so_line._mapping_invoice_delivery_by_qty(line.quantity)
                    if not name:
                        line.write({'sequence':0})
                        continue
                    if name and name not in picking_name:
                        seq = self._compute_sequence(name,index)
                        section_name = '{} [{}]'.format(name,so_line.order_id.client_order_ref)
                        picking_name[name] = {'name':section_name,'seq':seq}

                    # +1 防止覆盖seq为0的section
                    invoice_line_new_seq = picking_name[name]['seq']+1
                    line.write({'sequence':invoice_line_new_seq})
            for pick in picking_name.values():
                invoice.invoice_line_ids=[(0,0,{'name':pick['name'],'sequence':pick['seq'],'display_type':'line_section'})]
        return account_invoice

    @api.model
    def _prepare_purchase_order_line_data(self, so_line, date_order, company):
        """ Generate purchase order line values, from the SO line
            :param so_line : origin SO line
            :rtype so_line : sale.order.line record
            :param date_order : the date of the orgin SO
            :param company : the company in which the PO line will be created
            :rtype company : res.company record
        """

        result = super(SaleOrder,self)._prepare_purchase_order_line_data(so_line, date_order, company)
        result['product_packaging_id'] = so_line.product_packaging_id.id
        result['product_packaging_qty'] = so_line.product_packaging_qty
        return result