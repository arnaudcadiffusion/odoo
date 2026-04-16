from odoo import fields, models, _


class Tender(models.Model):
    _inherit = 'mail.thread'
    _name = 'tender.order'
    _description = 'Tender Order'

    note = fields.Text('Note')
    active = fields.Boolean('Active', default=True)
    name = fields.Char('Name', required=True)
    start_date = fields.Date('Start Date', tracking=True)
    end_date = fields.Date('End Date', tracking=True)
    end_of_the_tender = fields.Date('End Of The Tender', tracking=True)
    next_revision_date = fields.Datetime('Next Revision Date', tracking=True)
    last_revision_date = fields.Datetime('Last Revision Date')
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirm', 'confimed'),
        ],
        string='State',
        tracking=True,
        default='draft')
    tender_price_lines = fields.One2many(
        'tender.price.line',
        'tender_id',
        copy=True,
        string='Tender Order Lines')
    partner_ids = fields.Many2many(
        'res.partner',
        'tender_order_partner_rel',
        'tender_ids',
        'partner_ids')
    sale_ids = fields.Many2many(
        'sale.order',
        'tender_order_sale_rel',
        'tender_ids',
        'sale_ids',
        readonly=True)
    currency_id = fields.Many2one(
        'res.currency',
        related='tender_pricelist_id.currency_id',
        string='Currency')
    tender_pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Tender Pricelist',
        ondelete='restrict',
        copy=False)

    _sql_constraints = [('name_uniq', 'unique(name)', "Name Must Be Unique")]


    def copy(self, default=None):
        # TDE FIXME: should probably be copy_data
        self.ensure_one()
        if default is None:
            default = {}
        if 'name' not in default:
            default['name'] = _("%s (copy)") % self.name
        return super(Tender,self).copy(default=default)


    def _create_product_pricelist(self):
        item_obj = self.env['product.pricelist.item']
        if not self.tender_pricelist_id:
            product_pricelist = self.env['product.pricelist'].create({
                'name':'{}--{}'.format('Tender Pricelist', self.name),
                'item_ids':
                None
            })
            self.tender_pricelist_id = product_pricelist

        #对product_pricelist中已经存在的,与当前tender日期相同的items进行获取。
        exist_items = self.tender_pricelist_id.mapped('item_ids').filtered(
            lambda r: r.date_start == self.start_date and r.date_end == self.end_date and r.applied_on == '1_product' and r.compute_price == 'fixed'
        )
        # 构成产品{id:item} 字典
        # 若tender.order中的产品已经存在与items中，则进行更新操作.
        product_items_mapping = {
            item.product_tmpl_id.id: item
            for item in exist_items
        }
        for line in self.tender_price_lines:
            value = line._prepare_pricelist_items_value()
            value.update({'fixed_price': line.revision_price})
            item_id = product_items_mapping.get(
                line.product_id.product_tmpl_id.id, None)
            if item_id:
                item_id.write(value)
            else:
                value.update({
                    'pricelist_id':
                    line.tender_id.tender_pricelist_id.id,
                    'compute_price':
                    'fixed',
                })
                item_obj.create(value)

    def _del_useless_product_pricelist_item(self):
        # 在vlidate时，还要对tender.price.line中删除的product进行pricelist_item同步
        exist_items = self.tender_pricelist_id.mapped('item_ids').filtered(
            lambda r: r.date_start == self.start_date and r.date_end == self.end_date and r.applied_on == '1_product' and r.compute_price == 'fixed'
        )
        tender_product_tmpl = self.tender_price_lines.mapped(
            'product_id.product_tmpl_id.id')
        for item in exist_items:
            if item.product_tmpl_id.id not in tender_product_tmpl:
                item.unlink()

    def analyze_exist_product_pricelist(self):
        '''
             若pricelist_items
             中存在没设置起始时间，默认时间的item。则认为这是最新的
             start_date end_date 
           1.   None         None
           2.   2019/3/1      None
           3.   2019/3/5      None
           4.   None          2019/3/20
           5.   None          2019/3/10
           6.   2019/3/1      2019/5/1
           7.   2019/3/5      2019/4/1
           8.   2019/3/6      2019/5/1
           优先级顺序为 1-3-2-8-6-7-4-5

        '''
        if self.tender_pricelist_id:
            items = self.tender_pricelist_id.mapped('item_ids').filtered(
                lambda r: r.applied_on == '1_product' and r.compute_price == 'fixed'
            )
            if not items:
                return True

            # 没有起止时间优先级最大,取None None
            no_both_date_items = items.filtered(
                lambda r: not r.date_start and not r.date_end)
            if no_both_date_items:
                self.start_date = None
                self.end_date = None
                return self._write_tender_price_lines(no_both_date_items)

            # 没有截止时间，按开始时间最大,取2019/3/5 None
            no_end_date_items = items.filtered(lambda r: not r.date_end)
            if no_end_date_items:
                max_start_date = max(no_end_date_items.mapped('date_start'))
                self.start_date = max_start_date
                self.end_date = None
                product_items = no_end_date_items.filtered(
                    lambda r: r.date_start == max_start_date)
                return self._write_tender_price_lines(product_items)

            # 有截止时间，取最大开始时间 2019/3/6  2019/5/1
            max_end_date = max(items.mapped('date_end'))
            max_end_date_items = items.filtered(
                lambda r: r.date_end == max_end_date)
            max_start_date = max(max_end_date_items.mapped('date_start'))

            self.end_date = max_end_date
            self.start_date = max_start_date
            product_items = max_end_date_items.filtered(
                lambda r: r.date_start == max_start_date)
            return self._write_tender_price_lines(product_items)

    def _write_tender_price_lines(self, pricelist_items):
        tender_price_lines = []
        for item in pricelist_items:
            value = {
                'product_id': item.product_tmpl_id.product_variant_id.id,
                'min_quantity': item.min_quantity,
                'revision_price': item.fixed_price,
            }
            tender_price_lines.append((0,0,value))
        self.write({'tender_price_lines':tender_price_lines}) 

    def _update_partner_pricelist(self):
        if not self.partner_ids or not self.tender_pricelist_id:
            return
        partner_pricelists = self.env['product.pricelist']
        for partner in self.partner_ids:
            # 客户默认的pricelist为public pricelist
            # id=1,当客户使用的是这张价目表即可认为
            # 需要按照tender新建一张客户使用
            if partner.property_product_pricelist.id == 1:
                partner.property_product_pricelist = self.env['product.pricelist'].create({
                    'name': '{}---{}'.format('Customer Pricelist',partner.name),
                    'item_ids': None
                })
            partner_pricelists |= partner.property_product_pricelist

        if partner_pricelists:
            item_values = []
            for line in self.tender_price_lines:
                value = line._prepare_pricelist_items_value()
                value.update({
                    'compute_price': 'formula',
                    'base': 'pricelist',
                    'base_pricelist_id': line.tender_id.tender_pricelist_id.id,
                })
                item_values.append((0,0,value))
            partner_pricelists.write({'item_ids': item_values})
                 
    def _unlink_pricelist_item(self, pricelists):
        #在tender 中写入customer pricelist 时，先把原来的那些items
        #删掉。保证重新添加不会重复
        filtered_items = pricelists.mapped('item_ids').filtered(
            lambda r: r.base_pricelist_id == self.tender_pricelist_id)
        filtered_items.unlink()

    def action_confirm(self):
        # 先创建tender对应的价目表
        self._create_product_pricelist()
        # 获取tender中所以产品的tmp_id，若pricelist_items中多了这种产品，删除
        self._del_useless_product_pricelist_item()
        # 再在创建的价目表基础上对关联客户 的价目表进行产品的添加
        self._update_partner_pricelist()
        self.state = 'confirm'

    def action_reset(self):
        if not self.partner_ids:
            self.state = 'draft'
            return
        pricelists = self.partner_ids.mapped('property_product_pricelist')
        self._unlink_pricelist_item(pricelists)
        self.state = 'draft'

    def toggle_active(self):
        for record in self:
            if record.tender_pricelist_id:
                if record.state == 'confirm':
                    if record.active:
                        pricelists = record.mapped(
                            'partner_ids.property_product_pricelist')
                        record._unlink_pricelist_item(pricelists)
                    else:
                        record._update_partner_pricelist()
                record.tender_pricelist_id.active = not record.tender_pricelist_id.active
            record.active = not record.active


class TenderPriceLine(models.Model):
    _name = 'tender.price.line'
    _description = 'Tender Price Line'
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        domain=[('sale_ok', '=', True)],
        required=True)
    tender_id = fields.Many2one(
        'tender.order',
        ondelete='cascade',
        string='Tender Order', required=True)
    revision_price = fields.Float(
        "Unit Price", required=True, digits="Product Price", default=0.0
    )
    start_date = fields.Date('Start Date', related='tender_id.start_date')
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('confirm', 'confimed'),
        ], string='State')
    end_date = fields.Date('End Date', related='tender_id.end_date')
    min_quantity = fields.Integer('Min. Quantity', default=0)

    def _prepare_pricelist_items_value(self):
        value = {
            'applied_on': '1_product',
            'product_tmpl_id': self.product_id.product_tmpl_id.id,
            'min_quantity': self.min_quantity,
            'date_start': self.start_date,
            'date_end': self.end_date,
        }
        return value
