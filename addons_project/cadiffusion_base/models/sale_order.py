from odoo import api, fields, models
from odoo.tools import float_is_zero, float_round


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cad_n_client = fields.Char(
        string='N# Client',
        related='partner_id.ref',
        readonly=True,
    )
    cad_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='partner_id.cad_code_service_chorus',
        store=True,
    )
    cad_categorie_client = fields.Selection(
        string='Categorie Client',
        related='partner_id.cad_categorie_client',
        readonly=True,
    )
    cad_assurance = fields.Selection(
        string='Assur',
        related='partner_id.cad_assurance',
        store=True,
        readonly=True,
    )
    cad_livraison = fields.Html(
        string='Instructions Livraison',
        related='partner_shipping_id.comment',
        readonly=True,
    )
    cad_notes_internes = fields.Html(
        string='Notes internes',
        related='partner_id.comment',
        readonly=True,
    )
    cad_prospect = fields.Boolean(
        string='Prospect',
        related='partner_id.cad_prospect',
        readonly=True,
    )
    # Created with Studio in production after the switch to v19
    # (x_studio_related_field_3a8_1k1oqd81b), shown on the quotation form by
    # that Studio view; declared here since 19.0.1.0.32.
    cad_bloquer = fields.Boolean(
        string='Bloquer',
        related='partner_id.credit_on_hold',
        readonly=True,
    )

    def _create_invoices(self, grouped=False, final=False, date=None):
        """When an invoice is created from one or several sale orders, insert a
        ``line_section`` line for every distinct delivery order (``stock.picking``)
        in state ``done`` that contributed product lines. The section name is the
        picking ``name`` (e.g. ``WH/OUT/00012``).

        Sections are written into the invoice as real ``account.move.line``
        records (display_type='line_section'), so they survive editing, are
        visible in the form, and require no special PDF logic — the standard
        section rendering takes care of them."""
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            move._cadiffusion_insert_picking_sections()
        return moves


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    cad_reference = fields.Char(
        string='Référence',
        related='product_id.default_code',
        store=True,
    )
    cad_n_commande = fields.Char(
        string='N# Commande',
        related='order_id.client_order_ref',
        store=True,
        readonly=True,
    )
    cad_availability = fields.Float(
        string='Availability',
        related='product_id.qty_available',
        readonly=True,
    )
    cad_date_souhaitee = fields.Datetime(
        string='Date souhaitée',
        related='order_id.commitment_date',
        store=True,
    )
    cad_date_livraison = fields.Datetime(
        string='Date livraison',
        related='move_ids.date',
        store=True,
    )
    # Same standard computation (price_subtotal / product_uom_qty), but
    # stored with the "Product Price" precision (4 decimals) instead of the
    # currency rounding of the standard Monetary field, which flattened
    # sub-cent unit prices (0.0161 -> 0.02).
    price_reduce_taxexcl = fields.Float(
        compute='_compute_price_reduce_taxexcl',
        digits='Product Price',
        store=True,
        precompute=True,
    )
    # Équivalents v19 des colonnes v15 « Colis » (product_packaging_id) et
    # « Nb Carton » (product_packaging_qty), supprimées avec product.packaging.
    # Le colis est choisi par l'utilisateur parmi les conditionnements du
    # produit (pré-rempli avec le plus grand carton) ; stocké pour que le
    # choix survive aux enregistrements et soit utilisable par les rapports.
    carton_uom_id = fields.Many2one(
        'uom.uom',
        string='Colis',
        compute='_compute_carton_uom_id',
        store=True,
        readonly=False,
    )
    nb_carton = fields.Integer(
        string='Nb Carton',
        compute='_compute_nb_carton',
        inverse='_inverse_nb_carton',
    )

    # ------------------------------------------------------------------
    # Conditionnement : affichage PDF commande
    # (report_cadiffusion.report_saleorder_document) et colonnes
    # « Colis » / « Nb Carton » de la vue formulaire.
    # Le conditionnement est porté par les UDM d'emballage du produit
    # (product.template.uom_ids, ex. « CARTON DE 500 »), pas par l'UDM de
    # la ligne (qui reste en pièces). On dérive donc tout du produit.
    # ------------------------------------------------------------------
    def _cadiffusion_default_carton_uom(self):
        """UDM d'emballage « carton » par défaut : l'UDM de la ligne
        elle-même si elle a été saisie dans un conditionnement (ratio > 1
        vers l'UDM de base), sinon celle du produit (voir
        product.template._cadiffusion_carton_uom)."""
        self.ensure_one()
        if not self.product_id:
            return self.env['uom.uom']
        base_uom = self.product_id.uom_id
        line_uom = self.product_uom_id
        if line_uom and line_uom != base_uom:
            ratio = line_uom._compute_quantity(
                1.0, base_uom, raise_if_failure=False)
            if ratio and ratio > 1:
                return line_uom
        return self.product_id.product_tmpl_id._cadiffusion_carton_uom()

    def _cadiffusion_carton_uom(self):
        """UDM d'emballage effective de la ligne : le colis choisi par
        l'utilisateur, sinon le défaut."""
        self.ensure_one()
        return self.carton_uom_id or self._cadiffusion_default_carton_uom()

    def _cadiffusion_pieces(self):
        """Quantité de la ligne en pièces (UDM de base du produit ; la ligne
        est normalement saisie en pièces, on convertit par sécurité si elle
        était saisie dans une UDM carton)."""
        self.ensure_one()
        qty = self.product_uom_qty
        product = self.product_id
        line_uom = self.product_uom_id
        base_uom = product.uom_id if product else line_uom
        if product and line_uom and base_uom and line_uom != base_uom:
            return line_uom._compute_quantity(
                qty, base_uom, raise_if_failure=False)
        return qty

    @api.depends('product_id', 'product_uom_id')
    def _compute_carton_uom_id(self):
        for line in self:
            line.carton_uom_id = line._cadiffusion_default_carton_uom()

    def _cadiffusion_pieces_per_carton(self):
        """Nombre de pièces (UDM de base) dans un carton, 0 sans colis."""
        self.ensure_one()
        carton_uom = self._cadiffusion_carton_uom()
        if not carton_uom:
            return 0.0
        return carton_uom._compute_quantity(
            1.0, self.product_id.uom_id, raise_if_failure=False) or 0.0

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty',
                 'carton_uom_id')
    def _compute_nb_carton(self):
        for line in self:
            per_carton = line._cadiffusion_pieces_per_carton()
            if not per_carton:
                line.nb_carton = 0
                continue
            # Un carton entamé compte pour un carton entier (même convention
            # que la colonne COLIS du BL) : le nombre affiché reste rond.
            # float_round UP plutôt que ceil(round(x, 2)) : 1 pièce d'un
            # CARTON DE 2000 (0,0005) donnait 0 carton.
            line.nb_carton = int(float_round(
                line._cadiffusion_pieces() / per_carton,
                precision_rounding=1.0, rounding_method='UP'))

    @api.onchange('product_id', 'product_uom_qty', 'product_uom_id',
                  'carton_uom_id')
    def _onchange_round_qty_to_carton(self):
        """Only whole cartons are sold: while the user edits the line, round
        the quantity up to the next full carton (CARTON DE 12, 30 → 36;
        CARTON DE 2000, 7000 → 8000; a freshly added product starts at one
        carton instead of 1 piece). Done in an onchange, not in a compute,
        so that quantities written by code (imports, EDI, tests) are left
        untouched."""
        for line in self:
            if line.display_type or line.is_downpayment:
                continue
            pieces = line._cadiffusion_pieces()
            if pieces <= 0:
                continue
            nb_carton = line.nb_carton
            per_carton = line._cadiffusion_pieces_per_carton()
            if not per_carton or float_is_zero(
                    nb_carton * per_carton - pieces,
                    precision_rounding=line.product_uom_id.rounding or 0.01):
                continue
            line._inverse_nb_carton()

    def _inverse_nb_carton(self):
        """Saisir un nombre de cartons met à jour la quantité de la ligne
        (2 × CARTON DE 2000 → 4000), comme product_packaging_qty en v15."""
        for line in self:
            per_carton = line._cadiffusion_pieces_per_carton()
            if not per_carton:
                continue
            base_uom = line.product_id.uom_id
            pieces = line.nb_carton * per_carton
            line_uom = line.product_uom_id
            if line_uom and base_uom and line_uom != base_uom:
                qty = base_uom._compute_quantity(
                    pieces, line_uom, raise_if_failure=False) or pieces
            else:
                qty = pieces
            line.product_uom_qty = qty

    @api.onchange('nb_carton')
    def _onchange_nb_carton(self):
        """Push the carton count into the quantity while the user is still
        editing the form. The web client's ``onchange`` never runs inverse
        methods: on a new line the inverse only ran inside ``create()``,
        where precomputed fields (``price_subtotal``...) are protected against
        recomputation, so the subtotal stayed computed on the default
        quantity of 1 (45 × CARTON DE 2000 → 0.02 € instead of 1 449 €)."""
        self._inverse_nb_carton()

    def _cadiffusion_price_per_piece(self):
        """Prix unitaire par pièce, remise déduite.

        On calcule ``price_unit × (1 - remise%)`` plutôt que d'utiliser
        ``price_reduce_taxexcl`` : ce dernier est un champ *Monetary* arrondi à
        2 décimales (devise), ce qui écraserait les prix unitaires sub-centime
        (ex. 0,0135 → 0,01). ``price_unit`` est en précision « Product Price »
        (4 décimales). On ramène ensuite à l'UDM de base du produit pour rester
        correct même si une ligne était saisie dans une UDM carton."""
        self.ensure_one()
        base_price = self.price_unit * (1.0 - (self.discount or 0.0) / 100.0)
        if not self.product_id:
            return base_price
        base_uom = self.product_id.uom_id
        line_uom = self.product_uom_id
        if not line_uom or line_uom == base_uom:
            return base_price
        ratio = line_uom._compute_quantity(1.0, base_uom, raise_if_failure=False)
        if not ratio:
            return base_price
        return base_price / ratio

    @staticmethod
    def _cadiffusion_format_qty(value):
        """Formatage compact d'un nombre : entier sans décimale, sinon 2 max."""
        if value == int(value):
            return str(int(value))
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def _cadiffusion_qty_display(self):
        """Libellé quantité du PDF commande : uniquement le nombre de pièces
        (la quantité de ligne est exprimée dans l'UDM de base = la pièce ;
        on convertit par sécurité si une ligne était saisie dans une UDM carton).

        Ex. : « 30000 pièces »."""
        self.ensure_one()
        pieces = self._cadiffusion_pieces()
        unit_word = 'pièce' if pieces == 1 else 'pièces'
        return '%s %s' % (self._cadiffusion_format_qty(pieces), unit_word)
