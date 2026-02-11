# Copyright 2018 Shine IT 
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    packaging_qty = fields.Integer(string="Pack Qty", compute='_compute_packaging_qty')
    product_packaging_id = fields.Many2one('product.packaging')

    @api.depends('quantity','product_packaging_id','product_uom_id')
    def _compute_packaging_qty(self):
        for record in self:
            if record.product_packaging_id:
                default_uom = record.product_id.uom_id
                product_qty = record.quantity
                pack = record.product_packaging_id
                q = default_uom._compute_quantity(pack.qty, record.product_uom_id)
                try:
                    record.packaging_qty = product_qty//q +1 if product_qty%q else product_qty//q
                except ZeroDivisionError:
                    raise ValidationError("The Packaging Contained Quantity Should not set to \
                           Zero")
            else:
                record.packaging_qty = False

class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _mig_15_copy_invoice_data(self, order_by='ail.sequence, ail.id'):
        # ail.line_margin > 0 or ail.margin_subtotal_signed > 0 or ail.product_packaging is not null and 
        self._cr.execute('''select id from product_packaging''')
        packaging_list = [p[0] for p in self._cr.fetchall()]
        self._cr.execute('''
        select ai.move_id,ail.id,ail.sequence,ail.name, ail.price_total,ail.line_margin,ail.margin_subtotal_signed,ail.product_packaging
        from account_invoice_line ail left join account_invoice ai on (ai.id=ail.invoice_id)
        where ai.mig_15 = false
        order by ai.id,%s
        ''' % order_by)
        res_group = {}
        lines = self._cr.fetchall()
        for line in lines:
          if line[0] in res_group:
            res_group[line[0]].append(list(line))
          else:
            res_group[line[0]] = list([line])
        print(res_group.keys())
        def batch(iterable, n=1):
            l = len(iterable)
            for ndx in range(0, l, n):
                yield iterable[ndx:min(ndx + n, l)]
        for move_id in res_group.keys():
            move_cr = self.pool.cursor()
            error = False
            move_cr.execute('''
              select id, name,price_total,line_margin,margin_subtotal_signed,product_packaging_id
              from account_move_line ail where move_id=%s and exclude_from_invoice_tab=false
              order by %s
            '''% (move_id, order_by)) 
            nlines = move_cr.fetchall()
            print(res_group[move_id])
            print('moveid:%s olines:%s nlines:%s' % (move_id, len(res_group[move_id]), len(nlines)))
            for i, nline in enumerate(nlines):
                oline = res_group[move_id][i]
                n_id = nline[0]
                o_line_margin = oline[5]
                o_margin_subtotal_signed = oline[6]
                o_product_packaging = oline[7]
                if oline[3] != nline[1] or oline[4] != nline[2]:
                    print('!!! ERROR !!! Old: %s\n  New: %s l: %s' % (oline, nline, i+1))
                    error = True
                    break
                else:
                    if o_line_margin != 0:
                        move_cr.execute('''UPDATE account_move_line set line_margin = %s where id=%s''' % (o_line_margin, n_id))
                    if o_margin_subtotal_signed != 0:
                        move_cr.execute('''UPDATE account_move_line set margin_subtotal_signed = %s where id=%s''' % (o_margin_subtotal_signed, n_id))
                    if o_product_packaging and o_product_packaging in packaging_list:
                        move_cr.execute('''UPDATE account_move_line set  product_packaging_id= %s where id=%s''' % (o_product_packaging, n_id))
            if error:
                move_cr.rollback()
            else:
                print('>>>> UPDATE <<<< move_id:%s ' % move_id)
                move_cr.execute('''UPDATE account_invoice set mig_15=true where move_id=%s''' % (move_id))
                move_cr.commit()
            move_cr.close()


