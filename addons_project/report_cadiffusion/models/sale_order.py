# Copyright 2018 Shine IT
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
from odoo import fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    article_cmd = fields.Char('Article cmdé')

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def print_invoice(self):
        invoices = self.mapped('invoice_ids')
        return self.env.ref('account.account_invoices').report_action(invoices)
