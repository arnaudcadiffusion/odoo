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

    def _report_picking_name(self):
        """Return the delivery order (stock.picking) name linked to this invoice line.
        Used by the invoice PDF to display 'BL: XXX' sections grouping lines by delivery."""
        self.ensure_one()
        if not self.sale_line_ids:
            return ''
        pickings = self.sale_line_ids.move_ids.picking_id.filtered(lambda p: p.state == 'done')
        return pickings[:1].name or ''

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
        self.ensure_one()
        all_so = []
        for line in self.invoice_line_ids:
            if line.sale_line_ids:
                last_so_line = line.sale_line_ids[0]
                sale_order = last_so_line.order_id
                if sale_order in all_so:
                    continue
                else:
                    all_so.append(sale_order)
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
