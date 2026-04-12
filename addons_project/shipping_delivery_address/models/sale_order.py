from odoo import fields,api,models

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    @api.onchange('partner_id')
    def onchange_partner_id(self):
        # onchange_partner_id was removed in Odoo 17+; call super only if it exists
        parent = super(SaleOrder, self)
        if hasattr(parent, 'onchange_partner_id'):
            parent.onchange_partner_id()
        if not self.partner_id:
            return
        partner = self.partner_id.id
        if self.partner_id.parent_id:
            partner = self.partner_id.parent_id.id
        # A or (B and C)
        base_domain = ['|',('id','=',self.partner_id.id),'&',('parent_id','=',partner)]
        return {'domain':{'partner_invoice_id':base_domain + [('type','=','invoice')],
                          'partner_shipping_id':base_domain + [('type','=','delivery')]
                         }}


