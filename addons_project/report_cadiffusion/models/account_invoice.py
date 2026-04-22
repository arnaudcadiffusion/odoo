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
