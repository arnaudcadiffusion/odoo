from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductValuePrecision(TransactionCase):
    """A manual cost correction below the cent is kept as typed, and the next
    full average-cost recomputation restarts from it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['decimal.precision'].search([('name', '=', 'Product Price')]).digits = 4
        cls.company = cls.env.company
        cls.company.currency_id.rounding = 0.01
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.supplier_location = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_location = cls.env.ref('stock.stock_location_customers')
        cls.category = cls.env['product.category'].create({
            'name': 'AVCO sub-cent',
            'property_cost_method': 'average',
            'property_valuation': 'periodic',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Vis 0.0129',
            'is_storable': True,
            'categ_id': cls.category.id,
            'standard_price': 1.0,
        })

    def _move(self, qty, location_from, location_to):
        move = self.env['stock.move'].create({
            'product_id': self.product.id,
            'product_uom': self.product.uom_id.id,
            'product_uom_qty': qty,
            'location_id': location_from.id,
            'location_dest_id': location_to.id,
        })
        move._action_confirm()
        move._action_assign()
        move.move_line_ids.quantity = qty
        move.picked = True
        return move

    def test_manual_correction_keeps_product_price_precision(self):
        self.product.standard_price = 0.0129
        value = self.env['product.value'].search([('product_id', '=', self.product.id)], order='id desc', limit=1)
        self.assertEqual(value.value, 0.0129)
        self.env.cr.execute("SELECT value FROM product_value WHERE id = %s", (value.id,))
        self.assertEqual(float(self.env.cr.fetchone()[0]), 0.0129)

    def test_full_avco_recompute_restarts_from_the_unrounded_cost(self):
        # Stock on hand, then a sub-cent correction recorded in product.value.
        self._move(10000, self.supplier_location, self.stock_location)._action_done()
        self.product.standard_price = 0.0129
        # A receipt validated together with a delivery takes the full
        # recomputation path, which restarts from the last product.value.
        move_in = self._move(10000, self.supplier_location, self.stock_location)
        move_out = self._move(5000, self.stock_location, self.customer_location)
        (move_in | move_out)._action_done()
        self.assertAlmostEqual(self.product.standard_price, 0.0129, places=6)
        # The move values that feed accounting stay rounded to the currency.
        self.assertEqual(move_in.value, 129.0)
        self.assertEqual(move_out.value, 64.5)
