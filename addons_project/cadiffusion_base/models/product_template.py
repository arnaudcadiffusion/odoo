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

    cad_taux_de_douane = fields.Float(
        string='Taux de douane %',
    )
    cad_type_container = fields.Selection(
        selection=[
            ('20ST', '20ST'),
            ('40HC', '40HC'),
        ],
        string='Type Container',
    )
    cad_pieces_par_container = fields.Integer(
        string='Pièces par Container',
        default=0,
    )
    cad_marque = fields.Selection(
        selection=[
            ('CA', 'CA'),
            ('AUTRE', 'AUTRE'),
            ('MDD', 'MDD'),
            ('VPC', 'VPC'),
        ],
        string='Marque (variante)',
    )
    cad_longueur_carton = fields.Float(string='Longueur Carton')
    cad_largeur_carton = fields.Float(string='Largeur Carton')
    cad_hauteur_carton = fields.Float(string='Hauteur Carton')
    cad_poids_carton = fields.Float(string='Poids Carton')
    cad_nb_carton_p1 = fields.Char(string='Nb Carton P1')
    cad_nb_carton_p2 = fields.Char(string='Nb Carton P2')
    cad_nb_piece_p1 = fields.Char(string='Nb Piece P1')
    cad_nb_piece_p2 = fields.Char(string='Nb Piece P2')
    cad_hauteur_p1 = fields.Char(string='Hauteur P1')
    cad_hauteur_p2 = fields.Char(string='Hauteur P2')
