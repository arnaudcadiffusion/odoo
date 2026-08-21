from odoo import api, models


class AccountEdiXmlUbl_Bis3(models.AbstractModel):
    _inherit = "account.edi.xml.ubl_bis3"

    # Selection values of res.partner.fr_chorus_required (l10n_fr_chorus_account)
    # that mean "this customer really goes through Chorus Pro". ``False`` (unset)
    # and ``'none'`` both mean "not required" and must NOT trigger the override.
    _CADIFFUSION_CHORUS_REQUIRED_VALUES = (
        "service",
        "engagement",
        "service_or_engagement",
        "service_and_engagement",
    )

    @api.model
    def _is_customer_behind_chorus_pro(self, customer):
        """Recognise CaDiffusion's Chorus Pro customers.

        Odoo core (``account_edi_ubl_cii``) only treats a customer as being
        "behind Chorus Pro" when its Peppol endpoint is the central AIFE hub
        ``0009:11000201100044``. The whole ``l10n_fr_facturx_chorus_pro`` BIS3
        customisation is gated behind this single predicate:

        * ``cbc:BuyerReference``              -> ``move.buyer_reference`` (Code de Service)
        * ``cac:OrderReference/cbc:ID``       -> ``move.purchase_order_reference`` (Engagement Juridique)
        * ``cac:PartyIdentification/cbc:ID``  -> ``partner.company_registry`` (SIRET, schemeID 0009) for FR parties
        * ``cac:PartyLegalEntity/cbc:CompanyID`` -> idem

        CaDiffusion addresses each French public entity at its *own* Peppol
        endpoint (not the central AIFE hub) and flags Chorus customers through
        the OCA ``l10n_fr_chorus_account`` / ``account_invoice_transmit_method``
        mechanism instead. Without this override the core predicate is always
        ``False`` for our invoices, so none of the corrections above apply:
        ``BuyerReference`` falls back to the customer ``ref`` and the various
        ``CompanyID`` nodes fall back to the VAT number.

        We therefore additionally consider a customer to be behind Chorus Pro
        when it is configured for the ``fr-chorus`` transmission method, or when
        ``fr_chorus_required`` is set to a real value (i.e. not unset / ``none``).

        ``customer`` is the commercial partner (the caller passes
        ``vals['customer'].commercial_partner_id``); both fields below live on
        the commercial partner, so reading them here is correct.
        """
        if super()._is_customer_behind_chorus_pro(customer):
            return True
        return (
            customer.customer_invoice_transmit_method_code == "fr-chorus"
            or customer.fr_chorus_required in self._CADIFFUSION_CHORUS_REQUIRED_VALUES
        )

    def _add_invoice_header_nodes(self, document_node, vals):
        """Keep the Chorus Pro fix scoped to what the client requested.

        ``l10n_fr_facturx_chorus_pro._add_invoice_header_nodes`` does two things
        when the customer is behind Chorus Pro:

        * sets ``cbc:BuyerReference`` from ``move.buyer_reference`` -- WANTED;
        * rewrites ``cac:OrderReference/cbc:ID`` to
          ``move.purchase_order_reference`` (Engagement Juridique) -- NOT WANTED:
          the client's request only covers BuyerReference, PartyIdentification
          and PartyLegalEntity/CompanyID.

        We let the core logic run, then restore the standard ``cac:OrderReference``
        (as produced by ``account.edi.xml.ubl_20`` -- ``invoice.ref or invoice.name``
        plus ``SalesOrderID``), so OrderReference is left exactly as before.
        """
        super()._add_invoice_header_nodes(document_node, vals)

        invoice = vals["invoice"]
        if self._is_customer_behind_chorus_pro(vals["customer"].commercial_partner_id):
            document_node["cac:OrderReference"] = {
                "cbc:ID": {"_text": invoice.ref or invoice.name},
                "cbc:SalesOrderID": {
                    "_text": ",".join(
                        invoice.invoice_line_ids.sale_line_ids.order_id.mapped("name")
                    )
                } if "sale_line_ids" in invoice.invoice_line_ids._fields else None,
            }
