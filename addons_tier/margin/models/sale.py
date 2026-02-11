# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
################################################################################

from odoo import models, fields, api, _

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    line_margin = fields.Float(string='Margin ', digits='Account',
                               store=True, readonly=True, compute='_calc_margin')


    @api.depends('price_unit', 'product_uom_qty', 'tax_ids', 'product_id', 'order_id.partner_id', 'order_id.currency_id')
    def _calc_margin(self):
        for res in self:
            line_mrg_tot = 0
            cmp = 0.0
            cmp = ((res.purchase_price or res.product_id.standard_price) * res.product_uom_qty)
            margin = res.price_subtotal - cmp
            res.line_margin = margin


    def _prepare_invoice_line(self, **optional_values):
        res = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        res.update({'purchase_price':self.purchase_price})
        return res

    
class sale_order(models.Model):
    _inherit = "sale.order"

    def _calc_margin(self):
        for order in self:
            margin_per = 0.0
            margin = 0.0
            cmp = 0.0
            for line in order.order_line:
                if line.product_id:
                    cmp += (line.purchase_price * line.product_uom_qty)
                    margin =  order.amount_total - ((line.purchase_price or line.product_id.standard_price) * line.product_uom_qty)
                    
            if order.amount_total != 0:
                margin = order.amount_untaxed - cmp
                order.update({
                    'margin_cust' : (margin * 100) / order.amount_untaxed,
                    'margin_calc' : order.amount_untaxed - cmp
                })
            else:
                order.update({
                    'margin_cust' : 0.0,
                    'margin_calc' : 0.0
                })

    
    margin_cust = fields.Float('Margin %', compute='_calc_margin' , readonly=True, store=True)
    margin_calc = fields.Float('Margin ', compute='_calc_margin' , readonly=True, store=True)


class SaleInvoiceReport(models.Model):
    _inherit = "sale.report"

    margin_subtotal_signed = fields.Float('Margin')

    def _select_sale(self):
        select_ = f"""
            MIN(l.id) AS id,
            l.product_id AS product_id,
            l.invoice_status AS line_invoice_status,
            t.uom_id AS product_uom_id,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.product_uom_qty * u.factor / u2.factor) ELSE 0 END AS product_uom_qty,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.qty_delivered * u.factor / u2.factor) ELSE 0 END AS qty_delivered,
            CASE WHEN l.product_id IS NOT NULL THEN SUM((l.product_uom_qty - l.qty_delivered) * u.factor / u2.factor) ELSE 0 END AS qty_to_deliver,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.qty_invoiced * u.factor / u2.factor) ELSE 0 END AS qty_invoiced,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.qty_to_invoice * u.factor / u2.factor) ELSE 0 END AS qty_to_invoice,
            CASE WHEN l.product_id IS NOT NULL THEN AVG(l.price_unit
                / {self._case_value_or_one('s.currency_rate')}
                * {self._case_value_or_one('account_currency_table.rate')}
                ) ELSE 0
            END AS price_unit,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.price_total
                / {self._case_value_or_one('s.currency_rate')}
                * {self._case_value_or_one('account_currency_table.rate')}
                ) ELSE 0
            END AS price_total,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.price_subtotal
                / {self._case_value_or_one('s.currency_rate')}
                * {self._case_value_or_one('account_currency_table.rate')}
                ) ELSE 0
            END AS price_subtotal,
            CASE WHEN l.product_id IS NOT NULL OR l.is_downpayment THEN SUM(l.untaxed_amount_to_invoice
                / {self._case_value_or_one('s.currency_rate')}
                * {self._case_value_or_one('account_currency_table.rate')}
                ) ELSE 0
            END AS untaxed_amount_to_invoice,
            CASE WHEN l.product_id IS NOT NULL OR l.is_downpayment THEN SUM(l.untaxed_amount_invoiced
                / {self._case_value_or_one('s.currency_rate')}
                * {self._case_value_or_one('account_currency_table.rate')}
                ) ELSE 0
            END AS untaxed_amount_invoiced,
            COUNT(*) AS nbr,
            s.name AS name,
            s.margin_calc AS margin_subtotal_signed,
            s.date_order AS date,
            s.state AS state,
            s.invoice_status as invoice_status,
            s.partner_id AS partner_id,
            s.user_id AS user_id,
            s.company_id AS company_id,
            s.campaign_id AS campaign_id,
            s.medium_id AS medium_id,
            s.source_id AS source_id,
            t.categ_id AS categ_id,
            s.pricelist_id AS pricelist_id,
            s.team_id AS team_id,
            p.product_tmpl_id,
            partner.commercial_partner_id AS commercial_partner_id,
            partner.country_id AS country_id,
            partner.industry_id AS industry_id,
            partner.state_id AS state_id,
            partner.zip AS partner_zip,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(p.weight * l.product_uom_qty * u.factor / u2.factor) ELSE 0 END AS weight,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(p.volume * l.product_uom_qty * u.factor / u2.factor) ELSE 0 END AS volume,
            l.discount AS discount,
            CASE WHEN l.product_id IS NOT NULL THEN SUM(l.price_unit * l.product_uom_qty * l.discount / 100.0
                / {self._case_value_or_one('s.currency_rate')}
                * {self._case_value_or_one('account_currency_table.rate')}
                ) ELSE 0
            END AS discount_amount,
            {self.env.company.currency_id.id} AS currency_id,
            concat('sale.order', ',', s.id) AS order_reference"""

        additional_fields_info = self._select_additional_fields()
        template = """,
            %s AS %s"""
        for fname, query_info in additional_fields_info.items():
            select_ += template % (query_info, fname)

        return select_
