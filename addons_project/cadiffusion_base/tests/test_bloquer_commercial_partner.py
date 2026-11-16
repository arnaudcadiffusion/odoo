from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBloquerCommercialPartner(TransactionCase):
    """The Studio "Bloquer" tick of the quotation reads the hold of the
    main customer record, whatever address the order is placed on."""

    def setUp(self):
        self.addCleanup(self.registry.reset_changes)
        self.addCleanup(self.registry.clear_all_caches)
        super().setUp()
        if 'credit_on_hold' not in self.env['res.partner']._fields:
            self.skipTest("res.partner.credit_on_hold is not installed")
        self.SaleOrder = self.env['sale.order']
        self.fname = self.SaleOrder._BLOQUER_STUDIO_FIELD
        self.field = self.env['ir.model.fields']._get('sale.order', self.fname)
        if not self.field:
            # the field only exists in production: recreate it as Studio did
            self.field = self.env['ir.model.fields'].create({
                'model_id': self.env['ir.model']._get_id('sale.order'),
                'name': self.fname,
                'field_description': 'Bloquer',
                'ttype': 'boolean',
                'related': self.SaleOrder._BLOQUER_STUDIO_RELATED,
                'readonly': True,
                'store': False,
            })
        company = self.env['res.partner'].create({
            'name': 'Held customer',
            'is_company': True,
            'credit_on_hold': True,
        })
        delivery = self.env['res.partner'].create({
            'name': 'Held customer warehouse',
            'parent_id': company.id,
            'type': 'delivery',
            'credit_on_hold': False,
        })
        self.order = self.SaleOrder.create({'partner_id': delivery.id})

    def test_hold_follows_commercial_partner(self):
        self.field.related = self.SaleOrder._BLOQUER_STUDIO_RELATED
        self.assertFalse(self.order[self.fname])

        self.SaleOrder._bloquer_follow_commercial_partner()

        self.assertEqual(self.field.related, self.SaleOrder._BLOQUER_RELATED)
        self.order.invalidate_recordset()
        self.assertTrue(self.order[self.fname])

    def test_unexpected_related_is_left_alone(self):
        self.field.related = 'partner_id.active'

        with self.assertLogs('odoo.addons.cadiffusion_base.models.sale_order',
                             level='WARNING'):
            self.SaleOrder._bloquer_follow_commercial_partner()

        self.assertEqual(self.field.related, 'partner_id.active')
