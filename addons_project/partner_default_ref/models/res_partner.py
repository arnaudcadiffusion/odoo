from odoo import api, models


class ResParnter(models.Model):
    _inherit = 'res.partner'

    @api.model
    def _commercial_fields(self):
        res = super(ResParnter, self)._commercial_fields() + ['ref']
        return res