import logging
import math
from io import BytesIO

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf import OdooPdfFileReader, OdooPdfFileWriter

_logger = logging.getLogger(__name__)


class AccountAccount(models.Model):
    _inherit = 'account.account'

    ca_diff_code_taxe = fields.Char(
        string='Code taxe',
        related='tax_ids.name',
        store=True,
        translate=False,
    )


class AccountMove(models.Model):
    _inherit = 'account.move'

    ca_diff_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        compute='_compute_ca_diff_code_service_chorus',
        store=True,
        readonly=False,
    )

    @api.depends('partner_id', 'partner_id.ca_diff_code_service_chorus',
                 'partner_id.parent_id.ca_diff_code_service_chorus')
    def _compute_ca_diff_code_service_chorus(self):
        """Take the chorus service code from the billing address (partner_id).
        Fall back to the parent partner's code if the billing contact itself
        doesn't have one — covers the case where the code is stored on the
        commercial entity rather than on the billing contact."""
        for move in self:
            partner = move.partner_id
            move.ca_diff_code_service_chorus = (
                partner.ca_diff_code_service_chorus
                or (partner.parent_id and partner.parent_id.ca_diff_code_service_chorus)
                or False
            )

    @api.depends('name', 'state')
    def _compute_purchase_order_reference(self):
        """Set 'Engagement juridique' (Chorus PRO) to the invoice number once
        the invoice is posted. Keeps the field editable so users can override."""
        for move in self:
            if move.state == 'posted' and move.name and move.name != '/':
                move.purchase_order_reference = move.name

    purchase_order_reference = fields.Char(
        compute='_compute_purchase_order_reference',
        store=True,
        readonly=False,
    )
    ca_diff_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='partner_id.category_id',
    )
    ca_diff_field_rHWR6 = fields.Many2many(
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

    def _chorus_get_invoice(self, chorus_invoice_format):
        """Envoi Chorus au format pdf_factur-x : le PDF DOIT contenir le XML.

        Surtout NE PAS réactiver l'embedding OCA (lib facturx) sur ce
        chemin : ``facturx.generate_from_file`` tue le worker Odoo.sh
        (502 reproductible en ~7 s — même segfault que celui qui a motivé
        la désactivation globale dans ir_actions_report.py). On laisse donc
        le rendu produire un PDF nu, puis on embarque le XML OCA (qui porte
        le code service Chorus en BuyerReference) avec le writer PDF natif
        d'Odoo — la même machinerie que le flux Envoyer/Peppol
        (account_edi_ubl_cii), éprouvée sur ce build Odoo.sh."""
        if chorus_invoice_format == "pdf_factur-x":
            content = super()._chorus_get_invoice(chorus_invoice_format)
            content = self._chorus_embed_facturx_xml(content)
            self._chorus_check_facturx_xml_embedded(content)
            return content
        return super()._chorus_get_invoice(chorus_invoice_format)

    def _chorus_embed_facturx_xml(self, pdf_content):
        """Embarque le XML Factur-X OCA dans le PDF avec odoo.tools.pdf,
        en répliquant account_edi_ubl_cii/_hook_invoice_document_after_
        pdf_report_render : pièce jointe AFRelationship=Alternative,
        conversion PDF/A-3 et métadonnées XMP Factur-X."""
        self.ensure_one()
        xml_bytes = self.generate_facturx_xml()
        reader = OdooPdfFileReader(BytesIO(pdf_content), strict=False)
        writer = OdooPdfFileWriter()
        writer.cloneReaderDocumentRoot(reader)
        writer.addAttachment(
            "factur-x.xml", xml_bytes,
            subtype="text/xml", afrelationship="/Alternative")
        if not writer.is_pdfa:
            try:
                writer.convert_to_pdfa()
            except Exception:
                _logger.exception(
                    "Conversion PDF/A échouée pour l'envoi Chorus de %s "
                    "(PDF envoyé sans conformité PDF/A)", self.name)
        metadata = self.env["ir.qweb"]._render(
            "account_edi_ubl_cii.account_invoice_pdfa_3_facturx_metadata",
            {"title": self.name, "date": fields.Date.context_today(self)},
        )
        writer.add_file_metadata(str(metadata).encode())
        buf = BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def _chorus_check_facturx_xml_embedded(self, pdf_content):
        """Chorus Pro rejette un flux pdf_factur-x dont le PDF ne contient
        pas de factur-x.xml embarqué : on échoue ici avec un message clair
        plutôt que chez Chorus. Lecture via odoo.tools.pdf (PAS la lib
        facturx, dont la partie pypdf tue le worker sur Odoo.sh).

        NB : ne pas tester avec ``b'factur-x.xml' in pdf_content`` — les
        streams pypdf sont compressés, faux négatif garanti."""
        self.ensure_one()
        try:
            reader = OdooPdfFileReader(BytesIO(pdf_content), strict=False)
            names = [name for name, _data in reader.getAttachments()]
        except Exception:
            _logger.exception("Lecture des pièces jointes PDF impossible (%s)",
                              self.name)
            names = []
        if "factur-x.xml" not in names:
            raise UserError(self.env._(
                "Le PDF généré pour la facture %s ne contient pas le fichier "
                "XML Factur-X embarqué exigé par Chorus Pro. L'embedding "
                "Factur-X a échoué ou a été sauté — consulter les logs "
                "serveur.", self.display_name))

    def generate_facturx_xml(self):
        """Pré-contrôle : le schéma CII exige au moins un bloc de ventilation
        TVA (ApplicableTradeTax) dans l'en-tête. Il n'est émis que si une
        ligne est sans taxe (groupe Exonéré) ou porte une taxe configurée
        UNECE 'VAT'. Si toutes les lignes ne portent que des taxes non
        configurées (cas réel : facture 260470 d'intérêts moratoires avec
        « TVA 0% EXO » sans codes UNECE), l'OCA générerait un XML invalide
        rejeté par le XSD avec un message trompeur sur
        SpecifiedTradePaymentTerms. On échoue ici avec la vraie cause."""
        self.ensure_one()
        product_lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type == "product")
        has_vat_group = any(not line.tax_ids for line in product_lines) or any(
            tax.unece_type_code == "VAT" for tax in product_lines.tax_ids)
        if product_lines and not has_vat_group:
            bad_taxes = product_lines.tax_ids.filtered(
                lambda tax: tax.unece_type_code != "VAT")
            raise UserError(self.env._(
                "Facture %(invoice)s : impossible de générer la ventilation "
                "TVA exigée par Factur-X car aucune taxe des lignes n'est "
                "configurée comme TVA. Renseigner le Type de taxe UNECE "
                "'VAT' et la Catégorie UNECE (ex. 'Exempt from tax' pour "
                "une taxe d'exonération 0%%) sur : %(taxes)s "
                "(Comptabilité > Configuration > Taxes).",
                invoice=self.display_name,
                taxes=", ".join(bad_taxes.mapped("display_name"))))
        return super().generate_facturx_xml()

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

    ca_diff_cmup = fields.Float(
        string='CMUP',
        related='sale_line_ids.purchase_price',
        store=True,
        readonly=True,
    )
    ca_diff_date = fields.Date(
        string='Date Facture',
        related='move_id.date',
        store=True,
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Conditionnement : affichage v15 « Colis » / « Nb Carton » de la
    # facture (vue back-office + PDF report_cadiffusion.report_invoice).
    # Même logique que sale.order.line, mais en lecture seule : la
    # quantité facturée vient de la commande / du BL, on ne la modifie
    # pas depuis le nombre de cartons.
    # ------------------------------------------------------------------
    carton_uom_id = fields.Many2one(
        'uom.uom',
        string='Colis',
        compute='_compute_carton_uom_id',
    )
    nb_carton = fields.Integer(
        string='Nb Carton',
        compute='_compute_nb_carton',
    )

    def _cadiffusion_carton_uom(self):
        """UDM d'emballage « carton » de la ligne : l'UDM de la ligne
        elle-même si elle est libellée dans un conditionnement (ratio > 1
        vers l'UDM de base), sinon le colis choisi sur la ligne de commande
        d'origine (comme le BL — en v15 le product_packaging_id de la
        facture était copié depuis la commande), sinon celle du produit
        (voir product.template._cadiffusion_carton_uom)."""
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
        sale_carton = self.sale_line_ids.carton_uom_id[:1]
        if sale_carton:
            return sale_carton
        return self.product_id.product_tmpl_id._cadiffusion_carton_uom()

    def _cadiffusion_pieces(self):
        """Quantité de la ligne en pièces (UDM de base du produit ; on
        convertit par sécurité si la ligne était libellée dans une UDM
        carton)."""
        self.ensure_one()
        qty = self.quantity
        product = self.product_id
        line_uom = self.product_uom_id
        base_uom = product.uom_id if product else line_uom
        if product and line_uom and base_uom and line_uom != base_uom:
            return line_uom._compute_quantity(
                qty, base_uom, raise_if_failure=False)
        return qty

    @api.depends('product_id', 'product_uom_id', 'sale_line_ids.carton_uom_id')
    def _compute_carton_uom_id(self):
        for line in self:
            line.carton_uom_id = line._cadiffusion_carton_uom()

    @api.depends('product_id', 'product_uom_id', 'quantity',
                 'sale_line_ids.carton_uom_id')
    def _compute_nb_carton(self):
        for line in self:
            carton_uom = line._cadiffusion_carton_uom()
            if not carton_uom:
                line.nb_carton = 0
                continue
            per_carton = carton_uom._compute_quantity(
                1.0, line.product_id.uom_id, raise_if_failure=False)
            qty = line._cadiffusion_pieces() / per_carton if per_carton else 0.0
            # Un carton entamé compte pour un carton entier (même convention
            # que la colonne COLIS du BL) : le nombre affiché reste rond.
            line.nb_carton = int(math.ceil(round(qty, 2)))

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

    ca_diff_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='move_id.ca_diff_code_service_chorus',
    )
    ca_diff_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='move_id.ca_diff_etiquettes_clients',
    )
    ca_diff_field_rHWR6 = fields.Many2many(
        'res.partner',
        string='Contact',
        related='move_id.ca_diff_field_rHWR6',
    )


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    ca_diff_code_service_chorus = fields.Char(
        string='Code Service Chorus',
        related='move_id.ca_diff_code_service_chorus',
    )
    ca_diff_etiquettes_clients = fields.Many2many(
        'res.partner.category',
        string='Etiquettes clients',
        related='move_id.ca_diff_etiquettes_clients',
    )
    ca_diff_field_rHWR6 = fields.Many2many(
        'res.partner',
        string='Contact',
        related='move_id.ca_diff_field_rHWR6',
    )
