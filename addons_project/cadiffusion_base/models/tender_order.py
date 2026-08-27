from odoo import fields, models


class TenderOrder(models.Model):
    _inherit = 'tender.order'

    x_studio_dbut_de_march = fields.Date(string='Début de Marché')
    x_studio_coordinateur = fields.Char(string='Coordinateur')
    x_studio_contact = fields.Char(string='Contact')
    x_studio_tlphone = fields.Char(string='Téléphone')
    x_studio_email = fields.Char(string='Email')
    x_studio_notes_march = fields.Text(string='Notes Marché')
