from odoo import models,api


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.onchange('partner_id')
    def _onchange_partner_id_saleman(self):
        for inv in self:
            if inv.partner_id.user_id:
                inv.invoice_user_id = inv.partner_id.user_id
            

