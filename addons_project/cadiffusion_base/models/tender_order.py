from odoo import fields, models


class TenderOrder(models.Model):
    _inherit = 'tender.order'

    ca_diff_dbut_de_march = fields.Date(string='Début de Marché')
    ca_diff_coordinateur = fields.Char(string='Coordinateur')
    ca_diff_contact = fields.Char(string='Contact')
    ca_diff_tlphone = fields.Char(string='Téléphone')
    ca_diff_email = fields.Char(string='Email')
    ca_diff_notes_march = fields.Text(string='Notes Marché')
