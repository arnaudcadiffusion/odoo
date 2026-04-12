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
