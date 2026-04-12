# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_studio_douane = fields.Char(
        string='Nomenclature douanière',
    )
    x_studio_taux_de_douane_ = fields.Float(
        string='Taux de douane %',
    )
    x_studio_type_container = fields.Selection(
        selection=[
            ('20ST', '20ST'),
            ('40HC', '40HC'),
        ],
        string='Type Container',
    )
    x_studio_pieces_par_container = fields.Integer(
        string='Pièces par Container',
        default=0,
    )
    x_studio_marque = fields.Selection(
        selection=[
            ('CA', 'CA'),
            ('AUTRE', 'AUTRE'),
            ('MDD', 'MDD'),
            ('VPC', 'VPC'),
        ],
        string='Marque (variante)',
    )
    x_studio_marque_1 = fields.Selection(
        string='Marque',
        related='product_variant_ids.x_studio_marque',
        store=True,
    )
    x_studio_longueur_carton = fields.Float(string='Longueur Carton')
    x_studio_largeur_carton = fields.Float(string='Largeur Carton')
    x_studio_hauteur_carton = fields.Float(string='Hauteur Carton')
    x_studio_poids_carton = fields.Float(string='Poids Carton')
    x_studio_nb_carton_p1 = fields.Char(string='Nb Carton P1')
    x_studio_nb_carton_p2 = fields.Char(string='Nb Carton P2')
    x_studio_nb_piece_p1 = fields.Char(string='Nb Piece P1')
    x_studio_nb_piece_p2 = fields.Char(string='Nb Piece P2')
    x_studio_hauteur_p1 = fields.Char(string='Hauteur P1')
    x_studio_hauteur_p2 = fields.Char(string='Hauteur P2')
    x_studio_float_field_K1jhz = fields.Float(string='New Décimal')
    x_studio_field_iPtqU = fields.Date(string='New Date')
    x_studio_field_UQwvT = fields.Char(string='New Texte')
