# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Réintroduit pour compatibilité avec account_invoice_facturx (OCA)
    # Le champ 'mobile' a été supprimé de res.partner en Odoo 19
    mobile = fields.Char(string='Mobile', tracking=True)

    x_studio_secteur = fields.Selection(
        selection=[
            ('100 - THOMAS', '100 - THOMAS'),
            ('210', '210 - DEVERGNIES'),
            ('220', '220'),
            ('230', '230'),
            ('240', '240'),
            ('260', '260'),
            ('300', '300'),
            ('310 - LESEUIL', '310 - LESEUIL'),
            ('320', '320'),
            ('330', '330 - DURAND'),
            ('340 - BARBERO', '340 - BARBERO'),
            ('350', '350'),
            ('400 - AUTRES', '400 - AUTRES'),
        ],
        string='Secteur',
    )
    x_studio_categorie_client = fields.Selection(
        selection=[
            ('AIDE A DOMICILE', 'AIDE A DOMICILE'),
            ('AMBULANCIER', 'AMBULANCIER'),
            ('COLLECTIVITE', 'COLLECTIVITE'),
            ('CRECHE', 'CRECHE'),
            ('INDUSTRIE-AGRO', 'DISTRIBUTEUR AGRO (HOTEL/RESTAURANT)'),
            ('GROSSISTE', 'DISTRIBUTEUR MEDICAL'),
            ('DIVERS', 'DIVERS'),
            ('EHPAD', 'EHPAD'),
            ('FABRICANT', 'FABRICANT'),
            ('FOURNISSEUR', 'FOURNISSEUR'),
            ('HOPITAL PRIVE - CLINIQUE', 'HOPITAL PRIVE - CLINIQUE'),
            ('HOPITAL PUBLIC', 'HOPITAL PUBLIC'),
            ('HYGIENISTE', 'HYGIENISTE'),
            ('INDUSTRIE', 'INDUSTRIE'),
            ('INTERNE', 'INTERNE'),
            ('PHARMACIE', 'PHARMACIE'),
            ('REVENDEUR MEDICAL', 'REVENDEUR MEDICAL'),
            ('SDIS', 'SDIS'),
            ('MEDICAL DIVERS', 'SPECIALITES MEDICALES'),
            ('VAD', 'VAD'),
            ('AUTRE', 'AUTRE'),
        ],
        string='Categorie Client',
    )
    x_studio_atradius = fields.Selection(
        selection=[
            ('ACCEPTEE', 'ACCEPTEE'),
            ('ANNULEE/REFUSEE', 'ANNULEE/REFUSEE'),
            ('NON DEFINI', 'NON DEFINI'),
            ('PUBLIC', 'PUBLIC'),
            ('EUROCONTACT', 'EUROCONTACT'),
            ('FOURNISSEUR', 'FOURNISSEUR'),
            ('INTERNE', 'INTERNE'),
        ],
        string='Assurance',
    )
    x_studio_livraison_xpo = fields.Selection(
        selection=[
            ('STANDARD', 'STANDARD'),
            ('PRENDRE RDV', 'PRENDRE RDV'),
            ('TARGET', 'TARGET'),
        ],
        string='Livraison XPO',
    )
    x_studio_code_service_chorus = fields.Char(string='Code Service Chorus')
    x_studio_assurance = fields.Char(string='Credit Safe')
    x_studio_notes_internes = fields.Text(string='Notes Internes')
    x_studio_prospect = fields.Boolean(string='Prospect', default=False)
    x_studio_adresse_echantillon = fields.Boolean(string='Adresse Echantillon', default=False)
    x_studio_interets_moratoires = fields.Boolean(string='Interets Moratoires', default=False)
    x_studio_livraison_vl = fields.Boolean(string='Livraison VL', default=False)
    x_studio_char_field_zcf7n = fields.Char(string='Fermeture 1')
    x_studio_fermeture_2 = fields.Char(string='Fermeture 2')
    x_studio_ouverture_1 = fields.Char(string='Ouverture 1')
    x_studio_ouverture_2 = fields.Char(string='Ouverture 2')
    x_studio_field_SlKde = fields.Boolean(string='New Case à cocher', default=False)

    x_order_partner_id_sale_order_line_count = fields.Integer(
        string='Vente Article',
        compute='_compute_order_partner_id_sale_order_line_count',
    )

    @api.depends()
    def _compute_order_partner_id_sale_order_line_count(self):
        for partner in self:
            results = self.env['sale.order.line'].search(
                [('order_partner_id', 'in', partner.ids)]
            )
            partner.x_order_partner_id_sale_order_line_count = len(results)
