from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    x_studio_date_prvu = fields.Datetime(
        string='Date prévue',
        related='picking_id.scheduled_date',
        store=True,
        readonly=True,
    )
    x_studio_date_transfert = fields.Datetime(
        string='Date transfert',
        related='move_line_ids.date',
        store=True,
        readonly=True,
    )
    x_studio_partenaire = fields.Char(
        string='Partenaire',
        related='picking_id.partner_id.commercial_partner_id.name',
        store=True,
        readonly=True,
    )
    x_studio_prix_remise = fields.Float(
        string='Prix Remise',
        compute='_compute_x_studio_prix_remise',
        store=True,
    )
    x_studio_char_field_U2Qbo = fields.Char(string='New Texte')
    x_studio_field_x143A = fields.Date(string='New Date')

    # ------------------------------------------------------------------
    # Colonne « Conditionnement » des opérations de transfert.
    # En v15 le move portait product_packaging_id (le carton, hérité de la
    # ligne de commande) ; en v19 le champ natif packaging_uom_id retombe
    # sur l'UDM de la ligne (la pièce), d'où « Pièce(s) » partout. On le
    # remplace par le colis choisi sur la ligne de vente ou d'achat
    # (carton_uom_id), sinon par l'UDM carton du produit. La « Qté de
    # conditionnement » (packaging_uom_qty, ex. 42 000 pièces → 42 cartons)
    # suit d'elle-même.
    # ------------------------------------------------------------------
    @api.depends('sale_line_id.carton_uom_id', 'purchase_line_id.carton_uom_id',
                 'product_id')
    def _compute_packaging_uom_id(self):
        super()._compute_packaging_uom_id()
        for move in self:
            carton = (move.sale_line_id.carton_uom_id
                      or move.purchase_line_id.carton_uom_id)
            if not carton and move.product_id:
                # ne remplace que le repli trivial du standard (UDM de base) ;
                # un vrai conditionnement hérité des moves liés est conservé
                current = move.packaging_uom_id
                if not current or current in (move.product_id.uom_id, move.product_uom):
                    carton = move.product_id.product_tmpl_id._cadiffusion_carton_uom()
            if carton:
                move.packaging_uom_id = carton

    @api.depends('sale_line_id.price_reduce_taxexcl')
    def _compute_x_studio_prix_remise(self):
        for rec in self:
            rec.x_studio_prix_remise = rec.sale_line_id.price_reduce_taxexcl or 0.0

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    x_studio_transport = fields.Selection(
        selection=[
            ('XPO', 'XPO P'),
            ('XPO KG', 'XPO KG'),
            ('GEFCO_P', 'GEFCO P'),
            ('GEFCO_KG', 'GEFCO KG'),
            ('DPD', 'DPD'),
            ('ROUSSEL', 'ROUSSEL'),
            ('HEPPNER', 'HEPPNER'),
            ('CEVA AFFRETEMENT', 'CEVA AFFRETEMENT'),
            ('XPO AFFRETEMENT', 'XPO AFFRETEMENT'),
            ('AUTRE', 'AUTRE'),
            ('ENLEVEMENT', 'ENLEVEMENT'),
            ('DIRECT', 'DIRECT'),
            ('GEFCO', 'GEFCO'),
        ],
        string='Transport',
        copy=False,
    )
    x_studio_nb_palette = fields.Integer(string='Nb Palette', default=0, copy=False)
    x_studio_nb_palette_euro = fields.Integer(string='Nb Palette EURO', default=0, copy=False)
    x_studio_dpd_nb_colis = fields.Integer(string='Nb Etiquette DPD', default=0, copy=False)
    x_studio_cout_transport = fields.Float(string='Cout Transport', copy=False)
    x_studio_nb_bl_groupe = fields.Integer(string='Nb BL groupe', default=0, copy=False)
    x_studio_bl_groupe = fields.Boolean(string='BL groupe', default=False, copy=False)
    x_studio_id_bl_groupe = fields.Text(string='ID BL groupe', copy=False)
    x_studio_impression_bl = fields.Boolean(
        string='Impression BL',
        default=False,
        copy=False,
        tracking=True,
    )
    x_studio_erreur_client = fields.Boolean(string='Erreur Client', default=False)
    x_studio_erreur_preparation = fields.Boolean(string='Erreur Preparation', default=False, copy=False)
    x_studio_erreur_saisie = fields.Boolean(string='Erreur Saisie', default=False)
    x_studio_autres = fields.Boolean(string='Autres', default=False)
    x_studio_notes_erreur = fields.Text(string='Notes Erreur')
    x_studio_notes_internes = fields.Text(
        string='Notes Internes',
        related='sale_id.partner_shipping_id.x_studio_notes_internes',
        store=True,
        readonly=True,
    )
    x_studio_livraison = fields.Html(
        string='Instruction livraison',
        related='sale_id.partner_shipping_id.comment',
        store=True,
    )
    x_studio_n_commande = fields.Char(
        string='N# Commande',
        related='sale_id.client_order_ref',
        store=True,
    )
    x_studio_n_partenaire = fields.Char(
        string='N# Partenaire',
        related='partner_id.ref',
        store=True,
    )
    x_studio_cre_par = fields.Char(
        string='Créé par',
        related='sale_id.create_uid.name',
        store=True,
    )
    x_studio_field_GzsJK = fields.Char(
        string='Créé par (utilisateur)',
        related='create_uid.name',
        store=True,
    )
    x_studio_field_p3dnG = fields.Char(
        string='Réf. fournisseur',
        related='purchase_id.partner_ref',
        store=True,
        readonly=True,
    )
    x_studio_mode_livraison_xpo = fields.Selection(
        string='Mode Livraison XPO',
        related='partner_id.x_studio_livraison_xpo',
        store=True,
        readonly=True,
    )
    x_studio_prparateur = fields.Selection(
        selection=[
            ('CYRIL', 'CYRIL'),
            ('MANUEL', 'MANUEL'),
            ('ZAHIA', 'ZAHIA'),
            ('SABINE', 'SABINE'),
            ('DAVID', 'DAVID'),
            ('FLORIAN', 'FLORIAN'),
            ('INTERIM', 'INTERIM'),
            ('PASCAL', 'PASCAL'),
            ('ANCIEN SALARIE', 'ANCIEN SALARIE'),
        ],
        string='Préparateur',
        copy=False,
    )
    x_studio_premium_xpo = fields.Boolean(string='Premium XPO', default=False, copy=False)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    x_studio_ref_article = fields.Char(
        string='Ref Article',
        related='product_id.default_code',
        store=True,
    )
    x_studio_substitution = fields.Char(
        string='Substitution',
    )
