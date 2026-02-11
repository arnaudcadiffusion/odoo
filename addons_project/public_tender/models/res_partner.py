from odoo import models, fields


class Partner(models.Model):
    _inherit = 'res.partner'

    tender_ids = fields.Many2many('tender.order', 'tender_order_partner_rel',
                                  'partner_ids','tender_ids')

