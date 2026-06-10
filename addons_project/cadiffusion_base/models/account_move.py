# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _inherit = 'account.account'

    x_studio_code_taxe = fields.Char(
        string='Code taxe',
        related='tax_ids.name',
        store=True,
        translate=False,
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='partner_id.parent_id.x_studio_code_service_chorus',
        store=True,
    )
    x_studio_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='partner_id.category_id',
    )
    x_studio_field_rHWR6 = fields.Many2many(
        'res.partner',
        'account_move_partner_rel',
        'move_id',
        'partner_id',
        string='Contact',
    )

    is_draft_duplicated_ref_ids = fields.Boolean(
        string='Has Draft Duplicates',
        compute='_compute_is_draft_duplicated_ref_ids',
    )

    @api.depends('duplicated_ref_ids')
    def _compute_is_draft_duplicated_ref_ids(self):
        for move in self:
            drafts = move.duplicated_ref_ids.filtered(lambda m: m.state == 'draft')
            move.is_draft_duplicated_ref_ids = bool(drafts)
            move.is_exact_move_duplicate = any(
                d.amount_total == move.amount_total for d in drafts
            )

    def action_delete_duplicates(self):
        drafts = self.duplicated_ref_ids.filtered(lambda m: m.state == 'draft')
        drafts.button_cancel()
        drafts.unlink()
        return True

    def _cadiffusion_insert_picking_sections(self):
        """Insert ``line_section`` rows above each contiguous group of product
        lines that share the same done ``stock.picking``.

        Called from ``sale.order._create_invoices`` so the data is materialised
        once at invoice creation. Each section is named ``BL : <picking.name>``.

        Sequence trick: existing line sequences are multiplied by 10, then each
        section is inserted at ``(first_product_of_group.sequence) - 5`` — i.e.
        just before its group, without colliding with neighbours."""
        self.ensure_one()
        product_lines = self.invoice_line_ids.sorted(key=lambda l: l.sequence).filtered(
            lambda l: l.display_type == 'product'
        )
        if not product_lines:
            return

        # Resolve picking name per line in a single batched read.
        product_lines.mapped('sale_line_ids.move_ids.picking_id.state')
        picking_by_line = {}
        for line in product_lines:
            if not line.sale_line_ids:
                picking_by_line[line.id] = ''
                continue
            done_pickings = line.sale_line_ids.move_ids.picking_id.filtered(
                lambda p: p.state == 'done'
            )
            picking_by_line[line.id] = done_pickings[:1].name or ''

        # Detect picking changes BEFORE we touch sequences.
        sections_specs = []  # list of (anchor_line_id, picking_name)
        prev_name = None
        for line in product_lines:
            current_name = picking_by_line.get(line.id, '')
            if current_name and current_name != prev_name:
                sections_specs.append((line.id, current_name))
                prev_name = current_name

        if not sections_specs:
            return

        # Spread existing sequences ×10 so we can drop sections in between.
        for ln in self.invoice_line_ids:
            ln.sequence = max((ln.sequence or 0) * 10, 10)

        sections_to_create = []
        for anchor_id, picking_name in sections_specs:
            anchor = self.invoice_line_ids.browse(anchor_id)
            sections_to_create.append({
                'name': 'BL : %s' % picking_name,
                'display_type': 'line_section',
                'move_id': self.id,
                'sequence': max(anchor.sequence - 5, 1),
            })
        self.env['account.move.line'].create(sections_to_create)

    def regular_pdf_invoice_to_facturx_invoice(self, pdf_bytesio):
        """Defensive wrapper around the OCA factur-x embed call.

        The native implementation calls ``facturx.generate_from_file`` (binary
        operation on the PDF stream). On large invoices, malformed PDFs or
        memory-constrained workers this call can segfault and kill the Odoo
        worker process — which manifests as 'server se coupe' for the user
        clicking Print Invoice.

        Here we catch any exception, log it, and return the raw PDF without the
        embedded XML. The user gets their PDF; only the Factur-X compliance
        is silently dropped for that single render (the rest of the workflow
        — Chorus, etc. — keeps working since the XML is regenerated when
        actually transmitted)."""
        try:
            return super().regular_pdf_invoice_to_facturx_invoice(pdf_bytesio)
        except Exception as exc:  # noqa: BLE001 — intentionally broad to keep worker alive
            _logger.warning(
                "Factur-X embedding failed for invoice %s (id=%s); returning plain PDF. Error: %s",
                getattr(self, 'name', '?'), getattr(self, 'id', '?'), exc,
                exc_info=True,
            )
            return None


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    x_studio_cmup = fields.Float(
        string='CMUP',
        related='sale_line_ids.purchase_price',
        store=True,
        readonly=True,
    )
    x_studio_date = fields.Date(
        string='Date Facture',
        related='move_id.date',
        store=True,
        readonly=True,
    )

    def _cadiffusion_price_per_piece(self):
        """Return ``price_unit_reduced`` converted to the product's base UOM
        so the invoice PDF always shows a per-piece price even when the line
        is denominated in a packaging UOM (carton of 100, lot of 20, etc.).

        Falls back to ``price_unit_reduced`` if the line has no product or if
        its UOM already matches the product's base UOM (so behaviour is
        unchanged for pieces)."""
        self.ensure_one()
        base_price = getattr(self, 'price_unit_reduced', self.price_unit)
        if not self.product_id:
            return base_price
        base_uom = self.product_id.uom_id
        line_uom = self.product_uom_id
        if not line_uom or line_uom == base_uom:
            return base_price
        # Convert 1 unit of line_uom into base_uom: gives the number of base
        # units in one line unit. price_per_base = price_per_line / ratio.
        ratio = line_uom._compute_quantity(1.0, base_uom, raise_if_failure=False)
        if not ratio:
            return base_price
        return base_price / ratio


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='move_id.x_studio_code_service_chorus',
    )
    x_studio_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='move_id.x_studio_etiquettes_clients',
    )
    x_studio_field_rHWR6 = fields.Many2many(
        'res.partner',
        string='Contact',
        related='move_id.x_studio_field_rHWR6',
    )


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    x_studio_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='move_id.x_studio_code_service_chorus',
    )
    x_studio_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='move_id.x_studio_etiquettes_clients',
    )
    x_studio_field_rHWR6 = fields.Many2many(
        'res.partner',
        string='Contact',
        related='move_id.x_studio_field_rHWR6',
    )
