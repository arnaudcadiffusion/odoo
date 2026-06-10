# Copyright 2018 Shine IT
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    article_cmd = fields.Char('Article cmdé', related='sale_line_ids.article_cmd',related_sudo=True)
    price_unit_reduced = fields.Float(string='Reduce Price',compute="_compute_reduced_price",digits="Product Price"
)

    @api.depends('price_unit', 'discount')
    def _compute_reduced_price(self):
        for record in self:
            record.price_unit_reduced = record.price_unit * (1- (record.discount or 0.0)/100.0)

    def _report_price_per_piece(self):
        """Return the unit price expressed in the product's base UOM (price per piece).
        If the invoice line UOM equals the product's base UOM, returns price_unit_reduced.
        Otherwise converts to base UOM for display."""
        self.ensure_one()
        if not self.product_id or not self.quantity:
            return self.price_unit_reduced
        base_uom = self.product_id.uom_id
        line_uom = self.product_uom_id
        if not line_uom or line_uom == base_uom:
            return self.price_unit_reduced
        qty_base = line_uom._compute_quantity(self.quantity, base_uom)
        if not qty_base:
            return self.price_unit_reduced
        return self.price_subtotal / qty_base

class AccountMove(models.Model):
    _inherit = 'account.move'


    # @api.model
    # def _get_invoice_report_names(self):
    #     return super(AccountMove, self)._get_invoice_report_names() + ['report_cadiffusion.report_invoice_with_payments']

    def _report_sale_order(self):
        """Return all unique sale orders linked to this invoice.

        Optimization: uses set-based deduplication (O(1)) instead of list
        membership (O(N)) with record comparison. The previous implementation
        was called up to 5 times per PDF render via the *_date helpers — for
        large invoices this caused wkhtmltopdf to time out and the worker to
        be killed."""
        self.ensure_one()
        seen_ids = set()
        all_so = self.env['sale.order']
        # Batched prefetch of sale_line_ids → order_id so the loop below does
        # not trigger one query per invoice line.
        sale_lines = self.invoice_line_ids.mapped('sale_line_ids')
        sale_lines.mapped('order_id')
        for line in self.invoice_line_ids:
            if not line.sale_line_ids:
                continue
            sale_order = line.sale_line_ids[0].order_id
            if not sale_order or sale_order.id in seen_ids:
                continue
            seen_ids.add(sale_order.id)
            all_so |= sale_order
        return all_so

    def _report_sale_order_date(self):
        try:
            all_so = self._report_sale_order()
            if all_so:
                return all_so[0].date_order
        except Exception:
            pass
        return None

    def _report_sale_effective_date(self):
        try:
            all_so = self._report_sale_order()
            if all_so:
                val = all_so[0].effective_date
                return val if val else None
        except Exception:
            pass
        return None

    def _report_picking_name_by_line(self):
        """Pre-compute {invoice_line_id: picking_name} for all product lines of the
        invoice in a single batch (avoids N+1 queries during PDF rendering).

        Only pickings in state 'done' are considered. Returns the name of the first
        matching picking. Wrapped in try/except so a corrupted relation never aborts
        the PDF generation."""
        self.ensure_one()
        result = {}
        try:
            product_lines = self.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product'
            )
            if not product_lines:
                return result
            # Force prefetch in batched queries instead of one query per line.
            all_sale_lines = product_lines.mapped('sale_line_ids')
            all_moves = all_sale_lines.mapped('move_ids')
            all_pickings = all_moves.mapped('picking_id')
            all_pickings.mapped('state')
            all_pickings.mapped('name')

            for line in product_lines:
                sale_lines = line.sale_line_ids
                if not sale_lines:
                    result[line.id] = ''
                    continue
                done_pickings = sale_lines.move_ids.picking_id.filtered(
                    lambda p: p.state == 'done'
                )
                result[line.id] = (done_pickings[:1].name or '') if done_pickings else ''
        except Exception:
            # Never let a missing/odd relation crash the report.
            return result
        return result
