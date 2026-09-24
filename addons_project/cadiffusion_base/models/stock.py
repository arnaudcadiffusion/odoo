from odoo import api, fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    cad_date_prevue = fields.Datetime(
        string='Date prévue',
        related='picking_id.scheduled_date',
        store=True,
        readonly=True,
    )
    cad_partenaire = fields.Char(
        string='Partenaire',
        related='picking_id.partner_id.commercial_partner_id.name',
        store=True,
        readonly=True,
    )
    cad_prix_remise = fields.Float(
        string='Prix Remise',
        compute='_compute_cad_prix_remise',
        store=True,
    )

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
    def _compute_cad_prix_remise(self):
        for rec in self:
            rec.cad_prix_remise = rec.sale_line_id.price_reduce_taxexcl or 0.0

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    cad_transport = fields.Selection(
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
    cad_nb_palette = fields.Integer(string='Nb Palette', default=0, copy=False)
    cad_nb_palette_euro = fields.Integer(string='Nb Palette EURO', default=0, copy=False)
    cad_dpd_nb_colis = fields.Integer(string='Nb Etiquette DPD', default=0, copy=False)
    cad_cout_transport = fields.Float(string='Cout Transport', copy=False)
    cad_nb_bl_groupe = fields.Integer(string='Nb BL groupe', default=0, copy=False)
    cad_bl_groupe = fields.Boolean(string='BL groupe', default=False, copy=False)
    cad_id_bl_groupe = fields.Text(string='ID BL groupe', copy=False)
    cad_impression_bl = fields.Boolean(
        string='Impression BL',
        default=False,
        copy=False,
        tracking=True,
    )
    cad_erreur_client = fields.Boolean(string='Erreur Client', default=False)
    cad_erreur_preparation = fields.Boolean(string='Erreur Preparation', default=False, copy=False)
    cad_erreur_saisie = fields.Boolean(string='Erreur Saisie', default=False)
    cad_autres = fields.Boolean(string='Autres', default=False)
    cad_notes_erreur = fields.Text(string='Notes Erreur')
    cad_notes_internes = fields.Text(
        string='Notes Internes',
        related='sale_id.partner_shipping_id.cad_notes_internes',
        store=True,
        readonly=True,
    )
    cad_livraison = fields.Html(
        string='Instruction livraison',
        related='sale_id.partner_shipping_id.comment',
        store=True,
    )
    cad_n_commande = fields.Char(
        string='N# Commande',
        related='sale_id.client_order_ref',
        store=True,
    )
    cad_n_partenaire = fields.Char(
        string='N# Partenaire',
        related='partner_id.ref',
        store=True,
    )
    cad_mode_livraison_xpo = fields.Selection(
        string='Mode Livraison XPO',
        related='partner_id.cad_livraison_xpo',
        store=True,
        readonly=True,
    )
    # Choices managed by the users in ca.diffusion.preparer
    # (Inventory → Configuration → Preparers): the hardcoded list
    # inherited from the v15 dump drifted from production (blank tab).
    cad_preparateur = fields.Selection(
        selection=lambda self: self.env['ca.diffusion.preparer']
            ._selection_for('transfer'),
        string='Préparateur',
        copy=False,
    )
    cad_premium_xpo = fields.Boolean(string='Premium XPO', default=False, copy=False)

    @api.constrains('cad_preparateur')
    def _check_cad_preparateur(self):
        self.env['ca.diffusion.preparer']._check_field_values(
            self, 'cad_preparateur', 'transfer')


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    cad_ref_article = fields.Char(
        string='Ref Article',
        related='product_id.default_code',
        store=True,
    )
