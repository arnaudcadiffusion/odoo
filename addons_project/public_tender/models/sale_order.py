from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tender_ids = fields.Many2many(
        'tender.order',
        'tender_order_sale_rel',
        'sale_ids',
        'tender_ids',
        compute='_compute_tenders')
    tender_info = fields.Text('Tender Info', compute='_compute_tender_info')

    @api.depends('order_line', 'order_line.product_uom_qty',
                 'order_line.product_uom_id', 'order_line.product_id',
                 'pricelist_id')
    def _compute_tenders(self):
        for record in self:
            related_tenders = self.env['tender.order']
            rule_ids = []
            for order in record.order_line:
                if not order.product_id:
                    continue
                product_context = dict(
                    self.env.context,
                    partner_id=record.partner_id.id,
                    date=record.date_order,
                    uom=order.product_uom_id.id)
                _, rule_id = record.pricelist_id.with_context(
                    product_context)._get_product_price_rule(
                        product=order.product_id,
                        quantity=order.product_uom_qty or 1.0,
                        uom=order.product_uom_id,
                        )

                rule_ids.append(rule_id)
            items = self.env['product.pricelist.item'].browse(rule_ids)
            used_pricelists = items.filtered(
                lambda r: r.applied_on == '1_product').mapped(
                    'base_pricelist_id')
            # 通过客户的tenders,sale使用的pricelist 来匹配使用了哪些tender

            for tender in record.partner_id.tender_ids:
                # if tender.end_of_the_tender and tender.end_of_the_tender < fields.Date.today():
                    # continue
                if tender.tender_pricelist_id in used_pricelists:
                    related_tenders |= tender
            record.tender_ids = related_tenders

    @api.depends('tender_ids')
    def _compute_tender_info(self):
        for record in self:
            info = []
            for tender in record.tender_ids:
                note = tender.note if tender.note else ''
                info.append('{} :     {}'.format(tender.name, note))
            record.tender_info = '\r\n'.join(info)
