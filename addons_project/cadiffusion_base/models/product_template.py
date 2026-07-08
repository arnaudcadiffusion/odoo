# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _cadiffusion_carton_uom(self):
        """UDM d'emballage « carton » du produit : l'entrée de ``uom_ids`` au
        ratio vers l'UDM de base le plus élevé (> 1, ce qui écarte l'UDM de
        base et ses alias à la pièce, ex. « PIECE » facteur 1). On prend la
        plus grande car en v15, sur les produits multi-conditionnement
        (ex. SACHET DE 10 + CARTON DE 100), les lignes utilisaient le plus
        grand conditionnement dans 95 % des cas ; à ratio égal (ex. SACHET
        DE 10 et CARTON DE 10), on préfère l'UDM nommée « CARTON… », le
        conditionnement effectivement utilisé en v15. Utilisé par les
        rapports PDF (bon de commande fournisseur, bons de livraison)."""
        self.ensure_one()
        base_uom = self.uom_id
        best_uom = self.env['uom.uom']
        best_ratio = 1.0
        best_is_carton = False
        for uom in self.uom_ids:
            ratio = uom._compute_quantity(1.0, base_uom, raise_if_failure=False)
            if not ratio or ratio <= 1:
                continue
            is_carton = (uom.name or '').upper().startswith('CARTON')
            if ratio > best_ratio or (ratio == best_ratio
                                      and is_carton and not best_is_carton):
                best_uom, best_ratio, best_is_carton = uom, ratio, is_carton
        return best_uom

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
