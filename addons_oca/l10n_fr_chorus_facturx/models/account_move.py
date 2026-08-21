# Copyright 2017-2020 Akretion (http://www.akretion.com)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _cii_trade_contact_department_name(self, partner):
        # Only add chorus service department for the buyer contact (BT-56).
        # Applying it to the seller contact (BT-41) is semantically wrong and
        # triggers CII-SR-465: PersonName and DepartmentName are mutually
        # exclusive — you cannot have both in the same DefinedTradeContact.
        if partner != self.partner_id:
            return super()._cii_trade_contact_department_name(partner)
        chorus_service = self._get_chorus_service()
        if chorus_service:
            return chorus_service.name or partner.name
        return super()._cii_trade_contact_department_name(partner)

    def _cii_trade_agreement_buyer_ref(self, partner):
        chorus_service = self._get_chorus_service()
        if chorus_service:
            return chorus_service.code
        return super()._cii_trade_agreement_buyer_ref(partner)

    def _chorus_get_invoice(self, chorus_invoice_format):
        self.ensure_one()
        if chorus_invoice_format == "xml_cii":
            chorus_file_content = self.with_context(
                fr_chorus_cii16b=True
            ).generate_facturx_xml()[0]
        elif chorus_invoice_format == "pdf_factur-x":
            # v19 port fix: reference the report action by xmlid, not by
            # report_name — v19 _get_report() raises when the report_name
            # lookup fails (here because report_cadiffusion redirects the
            # invoice report to its own template) instead of falling back.
            # The Factur-X XML is embedded during rendering by
            # account_invoice_facturx (_render_qweb_pdf_prepare_streams),
            # whatever the template.
            chorus_file_content, filetype = self.env["ir.actions.report"]._render(
                "account.account_invoices", [self.id]
            )
            assert filetype == "pdf", "wrong filetype"
        else:
            chorus_file_content = super()._chorus_get_invoice(chorus_invoice_format)
        return chorus_file_content

    def _prepare_facturx_attachments(self):
        res = super()._prepare_facturx_attachments()
        for attach in self.chorus_attachment_ids:
            res[attach.name] = {
                "filedata": attach.raw,
                "modification_datetime": attach.write_date,
                "creation_datetime": attach.create_date,
            }
        return res
