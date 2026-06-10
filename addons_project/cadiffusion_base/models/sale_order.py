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
