from lxml import etree

from odoo import Command
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install_l10n", "post_install", "-at_install")
class TestCadiffusionChorusBis3(AccountTestInvoicingCommon):
    """The Chorus Pro BIS3 corrections (BuyerReference, PartyIdentification and
    PartyLegalEntity/CompanyID) live in Odoo core's ``l10n_fr_facturx_chorus_pro``
    but are gated behind ``_is_customer_behind_chorus_pro`` (customer addressed at
    the central AIFE hub ``0009:11000201100044``).

    CaDiffusion addresses each French public entity at its *own* Peppol endpoint
    and flags Chorus customers through the OCA chorus / transmit-method fields, so
    that gate never fires. ``cadiffusion_base`` extends the predicate to recognise
    those customers. These tests pin the resulting XML.
    """

    @classmethod
    @AccountTestInvoicingCommon.setup_country("fr")
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        # CA Diffusion (supplier) — SIREN 384919999
        cls.company.write({
            "vat": "FR35384919999",
            "company_registry": "38491999900029",
        })

        cls.fr_chorus_method = cls.env["transmit.method"].create({
            "name": "Chorus Pro",
            "code": "fr-chorus",
            "customer_ok": True,
        })

        # CHU de Toulouse (customer) — SIREN 263100125 — reached at its OWN Peppol
        # endpoint, NOT the central AIFE hub, and flagged for the fr-chorus method.
        cls.chorus_customer = cls.env["res.partner"].create({
            "name": "CHU de Toulouse",
            "vat": "FR38263100125",
            "company_registry": "26310012500016",
            "country_id": cls.env.ref("base.fr").id,
            "ref": "01808",
            "customer_invoice_transmit_method_id": cls.fr_chorus_method.id,
        })

    def _export_tree(self, invoice):
        invoice.action_post()
        xml = self.env["account.edi.xml.ubl_bis3"]._export_invoice(invoice)[0]
        return etree.fromstring(xml)

    def _make_invoice(self, partner, **vals):
        return self.env["account.move"].create({
            "company_id": self.company.id,
            "partner_id": partner.id,
            "move_type": "out_invoice",
            "invoice_line_ids": [Command.create({
                "product_id": self.product_a.id,
                "price_unit": 100.0,
            })],
            **vals,
        })

    def test_chorus_corrections_applied(self):
        invoice = self._make_invoice(
            self.chorus_customer, buyer_reference="FOUGEN", ref="SE590450")
        tree = self._export_tree(invoice)

        # 1) BuyerReference = move.buyer_reference (Code de Service), not customer ref.
        self.assertEqual(tree.findtext("{*}BuyerReference"), "FOUGEN")

        # OrderReference must stay untouched (= invoice.ref), NOT rewritten to the
        # Engagement Juridique / purchase_order_reference. The client's request
        # only covers the 3 identity tags below.
        self.assertEqual(tree.findtext("{*}OrderReference/{*}ID"), "SE590450")
        self.assertNotEqual(tree.findtext("{*}OrderReference/{*}ID"), invoice.name)

        # 2) PartyIdentification/ID = company_registry (SIRET), schemeID 0009, both parties.
        supplier_id = tree.find(
            "{*}AccountingSupplierParty/{*}Party/{*}PartyIdentification/{*}ID")
        self.assertEqual(supplier_id.text, "38491999900029")
        self.assertEqual(supplier_id.attrib, {"schemeID": "0009"})
        customer_id = tree.find(
            "{*}AccountingCustomerParty/{*}Party/{*}PartyIdentification/{*}ID")
        self.assertEqual(customer_id.text, "26310012500016")
        self.assertEqual(customer_id.attrib, {"schemeID": "0009"})

        # 3 + 4) PartyLegalEntity/CompanyID = company_registry (SIRET), not VAT.
        supplier_legal = tree.find(
            "{*}AccountingSupplierParty/{*}Party/{*}PartyLegalEntity/{*}CompanyID")
        self.assertEqual(supplier_legal.text, "38491999900029")
        self.assertEqual(supplier_legal.attrib, {"schemeID": "0009"})
        customer_legal = tree.find(
            "{*}AccountingCustomerParty/{*}Party/{*}PartyLegalEntity/{*}CompanyID")
        self.assertEqual(customer_legal.text, "26310012500016")
        self.assertEqual(customer_legal.attrib, {"schemeID": "0009"})

    def test_chorus_via_fr_chorus_required(self):
        """The secondary signal (fr_chorus_required) also triggers the corrections."""
        customer = self.env["res.partner"].create({
            "name": "Mairie de X",
            "vat": "FR38263100125",
            "company_registry": "26310012500016",
            "country_id": self.env.ref("base.fr").id,
            "invoice_sending_method": "fr_chorus",
            "fr_chorus_required": "service",
        })
        invoice = self._make_invoice(customer, buyer_reference="SVC42")
        tree = self._export_tree(invoice)
        self.assertEqual(tree.findtext("{*}BuyerReference"), "SVC42")
        customer_legal = tree.find(
            "{*}AccountingCustomerParty/{*}Party/{*}PartyLegalEntity/{*}CompanyID")
        self.assertEqual(customer_legal.text, "26310012500016")

    def test_non_chorus_customer_unchanged(self):
        """A French customer NOT flagged for Chorus keeps standard EN16931
        behaviour: CompanyID = VAT and BuyerReference = customer ref."""
        private = self.env["res.partner"].create({
            "name": "Client Prive SARL",
            "vat": "FR38263100125",
            "company_registry": "26310012500016",
            "country_id": self.env.ref("base.fr").id,
            "ref": "CUST-001",
        })
        invoice = self._make_invoice(private)
        tree = self._export_tree(invoice)

        self.assertEqual(tree.findtext("{*}BuyerReference"), "CUST-001")
        customer_legal = tree.find(
            "{*}AccountingCustomerParty/{*}Party/{*}PartyLegalEntity/{*}CompanyID")
        self.assertEqual(customer_legal.text, "FR38263100125")
