from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    ca_diff_type = fields.Selection(
        selection=[
            ('40HC', '40HC'),
            ('20ST', '20ST'),
            ('GROUPAGE', 'GROUPAGE'),
        ],
        string='Type',
    )
    ca_diff_n_fournisseur = fields.Char(
        string='N# Fournisseur',
        related='partner_id.ref',
        store=True,
    )
    ca_diff_date_depart = fields.Date(string='ETD')
    ca_diff_date_prvue_initiale = fields.Date(string='ETD initiale')
    ca_diff_dispo_confirmee = fields.Date(string='Dispo confirmée')
    ca_diff_embarquement = fields.Boolean(string='Embarquement', default=False)
    ca_diff_pod_1 = fields.Selection(
        selection=[
            ('SHANGHAI', 'SHANGHAI'),
            ('WUHAN', 'WUHAN'),
            ('QINGDAO', 'QINGDAO'),
            ('NANJING', 'NANJING'),
            ('NINGBO', 'NINGBO'),
            ('PORT KELUNG', 'PORT KELUNG'),
            ('NEW YORK', 'NEW YORK'),
            ('JIUJIANG', 'JIUJIANG'),
            ('CHITTAGONG', 'CHITTAGONG'),
            ('KLANG', 'KLANG'),
        ],
        string='POL',
    )
    ca_diff_transitaire = fields.Selection(
        selection=[
            ('SCAN GLOBAL', 'SCAN GLOBAL'),
            ('EUROTERMINAL', 'EUROTERMINAL'),
        ],
        string='Transitaire',
    )
    ca_diff_taux_eur_usd = fields.Float(string='Taux €/$')
    ca_diff_fret = fields.Integer(string='Fret', default=0)
    ca_diff_transport_achat = fields.Integer(string='Douane', default=0)
    ca_diff_transport_po = fields.Float(string='Transport PO')
    ca_diff_etat_facture = fields.Selection(
        string='Etat Facture',
        related='invoice_status',
        store=True,
    )
    ca_diff_observations_achats = fields.Text(string='Observations')
    ca_diff_field_qrjIt = fields.Text(string='New Texte multiligne')


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    ca_diff_date_initiale = fields.Date(
        string='Date Initiale',
        related='order_id.ca_diff_date_prvue_initiale',
        store=True,
        readonly=True,
    )
    ca_diff_ref_fournisseur = fields.Char(
        string='Ref Fournisseur',
        related='order_id.partner_ref',
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Conditionnement : colonnes « Conditionnement » / « Nb Carton » de la
    # vue formulaire et affichage PDF bon de commande
    # (report_cadiffusion.report_purchaseorder_document).
    # En v15 elles venaient de product_packaging_id / product_packaging_qty ;
    # en v19 product.packaging n'existe plus, le conditionnement est porté par
    # les UDM d'emballage du produit (product.template.uom_ids, ex. « CARTON
    # DE 12 ») et la quantité de ligne reste en pièces (UDM de base). Même
    # implémentation que côté vente (sale_order.py) : le conditionnement est
    # choisi par l'utilisateur parmi les UDM du produit (pré-rempli avec le
    # plus grand carton) et stocké, saisir Nb Carton met à jour la quantité.
    # ------------------------------------------------------------------
    carton_uom_id = fields.Many2one(
        'uom.uom',
        string='Conditionnement',
        compute='_compute_carton_uom_id',
        store=True,
        readonly=False,
    )
    nb_carton = fields.Float(
        string='Nb Carton',
        compute='_compute_nb_carton',
        inverse='_inverse_nb_carton',
        digits='Product Unit',
    )

    def _cadiffusion_default_carton_uom(self):
        """UDM d'emballage « carton » par défaut : l'UDM de la ligne
        elle-même si elle a été saisie dans un conditionnement (ratio > 1
        vers l'UDM de base, ex. UDM d'achat fournisseur), sinon celle du
        produit (voir product.template._cadiffusion_carton_uom)."""
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
        """UDM d'emballage effective de la ligne : le conditionnement choisi
        par l'utilisateur, sinon le défaut."""
        self.ensure_one()
        return self.carton_uom_id or self._cadiffusion_default_carton_uom()

    def _cadiffusion_pieces(self):
        """Quantité de la ligne en pièces (UDM de base du produit ; on
        convertit si la ligne est saisie dans une autre UDM)."""
        self.ensure_one()
        qty = self.product_qty
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

    @api.depends('product_id', 'product_uom_id', 'product_qty', 'carton_uom_id')
    def _compute_nb_carton(self):
        for line in self:
            carton_uom = line._cadiffusion_carton_uom()
            if not carton_uom:
                line.nb_carton = 0.0
                continue
            per_carton = carton_uom._compute_quantity(
                1.0, line.product_id.uom_id, raise_if_failure=False)
            line.nb_carton = (
                line._cadiffusion_pieces() / per_carton if per_carton else 0.0)

    def _inverse_nb_carton(self):
        """Saisir un nombre de cartons met à jour la quantité de la ligne
        (2 × CARTON DE 20 → 40), comme product_packaging_qty en v15."""
        for line in self:
            carton_uom = line._cadiffusion_carton_uom()
            if not carton_uom:
                continue
            base_uom = line.product_id.uom_id
            per_carton = carton_uom._compute_quantity(
                1.0, base_uom, raise_if_failure=False)
            if not per_carton:
                continue
            pieces = line.nb_carton * per_carton
            line_uom = line.product_uom_id
            if line_uom and base_uom and line_uom != base_uom:
                qty = base_uom._compute_quantity(
                    pieces, line_uom, raise_if_failure=False) or pieces
            else:
                qty = pieces
            line.product_qty = qty

    @staticmethod
    def _cadiffusion_format_qty(value):
        """Formatage compact d'un nombre : entier sans décimale, sinon 2 max."""
        if value == int(value):
            return str(int(value))
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def _cadiffusion_carton_qty_display(self):
        """Nombre de cartons de la ligne, formaté compact ; chaîne vide si la
        ligne n'a pas de conditionnement."""
        self.ensure_one()
        if not self._cadiffusion_carton_uom():
            return ''
        return self._cadiffusion_format_qty(self.nb_carton)

    def _cadiffusion_carton_label(self):
        """Libellé du conditionnement (ex. « CARTON DE 12 ») ; vide si aucun."""
        self.ensure_one()
        return self._cadiffusion_carton_uom().name or ''
