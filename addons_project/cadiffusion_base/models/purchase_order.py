# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    x_studio_type = fields.Selection(
        selection=[
            ('40HC', '40HC'),
            ('20ST', '20ST'),
            ('GROUPAGE', 'GROUPAGE'),
        ],
        string='Type',
    )
    x_studio_n_fournisseur = fields.Char(
        string='N# Fournisseur',
        related='partner_id.ref',
        store=True,
    )
    x_studio_date_depart = fields.Date(string='ETD')
    x_studio_date_prvue_initiale = fields.Date(string='ETD initiale')
    x_studio_dispo_confirmee = fields.Date(string='Dispo confirmée')
    x_studio_embarquement = fields.Boolean(string='Embarquement', default=False)
    x_studio_pod_1 = fields.Selection(
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
    x_studio_transitaire = fields.Selection(
        selection=[
            ('SCAN GLOBAL', 'SCAN GLOBAL'),
            ('EUROTERMINAL', 'EUROTERMINAL'),
        ],
        string='Transitaire',
    )
    x_studio_taux_eur_usd = fields.Float(string='Taux €/$')
    x_studio_fret = fields.Integer(string='Fret', default=0)
    x_studio_transport_achat = fields.Integer(string='Douane', default=0)
    x_studio_transport_po = fields.Float(string='Transport PO')
    x_studio_etat_facture = fields.Selection(
        string='Etat Facture',
        related='invoice_status',
        store=True,
    )
    x_studio_observations_achats = fields.Text(string='Observations')
    x_studio_field_qrjIt = fields.Text(string='New Texte multiligne')


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    x_studio_date_initiale = fields.Date(
        string='Date Initiale',
        related='order_id.x_studio_date_prvue_initiale',
        store=True,
        readonly=True,
    )
    x_studio_ref_fournisseur = fields.Char(
        string='Ref Fournisseur',
        related='order_id.partner_ref',
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Affichage PDF bon de commande
    # (report_cadiffusion.report_purchaseorder_document)
    # En v15 les colonnes « Carton » / « Unit Carton » venaient de
    # product_packaging_qty / product_packaging_id ; en v19 product.packaging
    # n'existe plus, le conditionnement est porté par les UDM d'emballage du
    # produit (product.template.uom_ids, ex. « CARTON DE 12 ») et la quantité
    # de ligne reste en pièces (UDM de base). On dérive donc tout du produit,
    # comme pour le rapport commande client (sale_order.py).
    # ------------------------------------------------------------------
    def _cadiffusion_carton_uom(self):
        """UDM d'emballage « carton » du produit de la ligne (voir
        product.template._cadiffusion_carton_uom)."""
        self.ensure_one()
        if not self.product_id:
            return self.env['uom.uom']
        return self.product_id.product_tmpl_id._cadiffusion_carton_uom()

    @staticmethod
    def _cadiffusion_format_qty(value):
        """Formatage compact d'un nombre : entier sans décimale, sinon 2 max."""
        if value == int(value):
            return str(int(value))
        return ('%.2f' % value).rstrip('0').rstrip('.')

    def _cadiffusion_carton_qty_display(self):
        """Nombre de cartons de la ligne (pièces ÷ pièces/carton), formaté
        compact ; chaîne vide si le produit n'a pas d'UDM carton."""
        self.ensure_one()
        carton_uom = self._cadiffusion_carton_uom()
        if not carton_uom:
            return ''
        base_uom = self.product_id.uom_id
        line_uom = self.product_uom_id
        if line_uom and base_uom and line_uom != base_uom:
            pieces = line_uom._compute_quantity(
                self.product_qty, base_uom, raise_if_failure=False)
        else:
            pieces = self.product_qty
        per_carton = carton_uom._compute_quantity(
            1.0, base_uom, raise_if_failure=False)
        if not per_carton:
            return ''
        return self._cadiffusion_format_qty(pieces / per_carton)

    def _cadiffusion_carton_label(self):
        """Libellé du conditionnement (ex. « CARTON DE 12 ») ; vide si aucun."""
        self.ensure_one()
        return self._cadiffusion_carton_uom().name or ''
