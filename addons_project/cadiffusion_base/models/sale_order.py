# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_studio_n_client = fields.Char(
        string='N# Client',
        related='partner_id.ref',
        readonly=True,
    )
    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='partner_id.x_studio_code_service_chorus',
        store=True,
    )
    x_studio_categorie_client = fields.Selection(
        string='Categorie Client',
        related='partner_id.x_studio_categorie_client',
        readonly=True,
    )
    x_studio_assurance_bc = fields.Selection(
        string='Assur',
        related='partner_id.x_studio_atradius',
        store=True,
        readonly=True,
    )
    x_studio_etiquettes = fields.Many2many(
        'res.partner.category',
        string='Etiquettes client',
        related='partner_id.category_id',
        readonly=True,
    )
    x_studio_livraison = fields.Html(
        string='Instructions Livraison',
        related='partner_shipping_id.comment',
        readonly=True,
    )
    x_studio_notes_internes = fields.Html(
        string='Notes internes',
        related='partner_id.comment',
        readonly=True,
    )
    x_studio_prospect = fields.Boolean(
        string='Prospect',
        related='partner_id.x_studio_prospect',
        readonly=True,
    )
    x_studio_notes_commande = fields.Text(string='Notes Commande')
    x_studio_siret = fields.Char(string='SIRET')

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

    x_studio_article_cmd = fields.Char(string='Article Commandé')
    x_studio_rfrence = fields.Char(
        string='Référence',
        related='product_id.default_code',
        store=True,
    )
    x_studio_n_commande = fields.Char(
        string='N# Commande',
        related='order_id.client_order_ref',
        store=True,
        readonly=True,
    )
    x_studio_availability = fields.Float(
        string='Availability',
        related='product_id.qty_available',
        readonly=True,
    )
    x_studio_date_souhaite = fields.Datetime(
        string='Date souhaitée',
        related='order_id.commitment_date',
        store=True,
    )
    x_studio_date_livraison = fields.Datetime(
        string='Date livraison',
        related='move_ids.date',
        store=True,
    )
    x_studio_marge = fields.Float(
        string='Marge',
        compute='_compute_x_studio_marge',
        store=True,
    )

    @api.depends('price_unit', 'purchase_price', 'discount')
    def _compute_x_studio_marge(self):
        for rec in self:
            # price_reduce renamed to price_reduce_taxexcl in Odoo 19
            price = rec.price_reduce_taxexcl
            if rec.product_id and price:
                rec.x_studio_marge = (price - rec.purchase_price) / price
            else:
                rec.x_studio_marge = 0.0

    # ------------------------------------------------------------------
    # Affichage PDF commande (report_cadiffusion.report_saleorder_document)
    # Le conditionnement est porté par les UDM d'emballage du produit
    # (product.template.uom_ids, ex. « CARTON DE 500 »), pas par l'UDM de
    # la ligne (qui reste en pièces). On dérive donc tout du produit.
    # ------------------------------------------------------------------
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

    def _cadiffusion_packaging_uoms(self):
        """UDM d'emballage du produit (ratio vers l'UDM de base > 1),
        triées par ratio croissant. Renvoie une liste de tuples (ratio, uom)."""
        self.ensure_one()
        if not self.product_id:
            return []
        base_uom = self.product_id.uom_id
        cartons = []
        # Odoo 19 a supprimé uom.category_id : les uom_ids du produit forment
        # déjà un arbre de conversion commun, _compute_quantity suffit.
        for uom in self.product_id.product_tmpl_id.uom_ids:
            if uom == base_uom:
                continue
            ratio = uom._compute_quantity(1.0, base_uom, raise_if_failure=False)
            if ratio and ratio > 1:
                cartons.append((ratio, uom))
        cartons.sort(key=lambda c: c[0])
        return cartons

    @staticmethod
    def _cadiffusion_format_qty(value):
        """Formatage compact d'un nombre : entier sans décimale, sinon 2 max."""
        if value == int(value):
            return str(int(value))
        return ('%.2f' % value).rstrip('0').rstrip('.')

    @staticmethod
    def _cadiffusion_carton_label(name, plural):
        """« CARTON DE 500 » -> « carton de 500 » / « cartons de 500 » (pluriel)."""
        label = (name or '').strip().lower()
        if plural and ' de ' in label:
            head, sep, tail = label.partition(' de ')
            if not head.endswith('s'):
                head += 's'
            label = head + sep + tail
        return label

    def _cadiffusion_qty_display(self):
        """Libellé quantité du PDF commande : nombre de pièces + détail de
        tous les conditionnements du produit.

        Ex. : « 9000 pièces (180 cartons de 50 / 18 cartons de 500) ».
        Sans conditionnement, renvoie simplement la quantité."""
        self.ensure_one()
        qty = self.product_uom_qty
        product = self.product_id
        line_uom = self.product_uom_id
        base_uom = product.uom_id if product else line_uom
        if product and line_uom and base_uom and line_uom != base_uom:
            pieces = line_uom._compute_quantity(qty, base_uom, raise_if_failure=False)
        else:
            pieces = qty
        cartons = self._cadiffusion_packaging_uoms()
        if not cartons:
            return self._cadiffusion_format_qty(qty)
        unit_word = 'pièce' if pieces == 1 else 'pièces'
        parts = []
        for ratio, uom in cartons:
            count = pieces / ratio
            parts.append('%s %s' % (
                self._cadiffusion_format_qty(count),
                self._cadiffusion_carton_label(uom.name, count != 1),
            ))
        return '%s %s (%s)' % (
            self._cadiffusion_format_qty(pieces), unit_word, ' / '.join(parts),
        )
