from odoo import fields, models


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    cad_franco = fields.Integer(
        string='Franco',
        default=0,
    )
    cad_origine = fields.Selection(
        selection=[
            ('ALLEMAGNE', 'ALLEMAGNE'),
            ('BANGLADESH', 'BANGLADESH'),
            ('BELGIQUE', 'BELGIQUE'),
            ('CHINE', 'CHINE'),
            ('FINLANDE', 'FINLANDE'),
            ('FRANCE', 'FRANCE'),
            ('ITALIE', 'ITALIE'),
            ('MALAISIE', 'MALAISIE'),
            ('PAYS BAS', 'PAYS BAS'),
            ('REP TCHEQUE', 'REP TCHEQUE'),
            ('SRI LANKA', 'SRI LANKA'),
            ('UK', 'UK'),
        ],
        string='Origine',
    )
    cad_provenance = fields.Selection(
        selection=[
            ('ALLEMAGNE', 'ALLEMAGNE'),
            ('BELGIQUE', 'BELGIQUE'),
            ('CHINE', 'CHINE'),
            ('FINLANDE', 'FINLANDE'),
            ('FRANCE', 'FRANCE'),
            ('ITALIE', 'ITALIE'),
            ('MALAISIE', 'MALAISIE'),
            ('PAYS BAS', 'PAYS BAS'),
            ('REP TCHEQUE', 'REP TCHEQUE'),
            ('SRI LANKA', 'SRI LANKA'),
            ('UK', 'UK'),
        ],
        string='Provenance',
    )
    cad_type_container = fields.Selection(
        selection=[
            ('Palette', 'Palette'),
            ('Euro', 'Euro'),
            ('Container', 'Container'),
            ('Carton', 'Carton'),
        ],
        string='Type',
    )
