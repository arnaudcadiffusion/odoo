# -*- coding: utf-8 -*-
"""
Hard-disable Factur-X XML embedding inside PDF invoices.

Why: the upstream OCA module ``account_invoice_facturx`` calls the
``facturx`` Python lib which manipulates the PDF stream at binary level.
On large invoices / malformed PDFs / memory-constrained Odoo.sh workers,
this call can segfault and kill the worker process — the user-visible
symptom is "le serveur se coupe" when clicking Print Invoice.

A Python ``try/except`` wrapper around ``regular_pdf_invoice_to_facturx_invoice``
(see ``account_move.py``) only catches Python exceptions, not segfaults.
We therefore short-circuit the embedding entirely by injecting the
``no_embedded_factur-x_xml`` context key that the OCA hook already checks
to skip its work.

Consequence: the PDF is returned without the embedded Factur-X XML.
The Factur-X workflow for Chorus continues to function because the XML
is regenerated and transmitted independently by the Chorus integration.

To re-enable the embedding on a per-call basis (e.g. once the upstream
bug is fixed), pass ``no_embedded_factur-x_xml=False`` explicitly in
the context when calling the report.
"""

from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_qweb_pdf_prepare_streams(self, report_ref, data, res_ids=None):
        ctx_key = 'no_embedded_factur-x_xml'
        if ctx_key not in self.env.context:
            self = self.with_context(**{ctx_key: True})
        return super()._render_qweb_pdf_prepare_streams(
            report_ref, data, res_ids=res_ids,
        )
