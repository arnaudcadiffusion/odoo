from odoo import fields, models


class TenderOrder(models.Model):
    _inherit = 'tender.order'

    cad_debut_marche = fields.Date(string='Début de Marché')
    cad_coordinateur = fields.Char(string='Coordinateur')
    cad_contact = fields.Char(string='Contact')
    cad_telephone = fields.Char(string='Téléphone')
    cad_email = fields.Char(string='Email')
    cad_notes_marche = fields.Text(string='Notes Marché')
