from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCartonRounding(TransactionCase):
    """Sale order lines are sold by whole cartons: typing a quantity in the
    form rounds it up to the next full carton, and the carton count never
    shows 0 for a non-empty line."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        unit = cls.env.ref('uom.product_uom_unit')
        cls.carton_12 = cls.env['uom.uom'].create({
            'name': 'CARTON DE 12',
            'relative_factor': 12.0,
            'relative_uom_id': unit.id,
        })
        cls.carton_2000 = cls.env['uom.uom'].create({
            'name': 'CARTON DE 2000',
            'relative_factor': 2000.0,
            'relative_uom_id': unit.id,
        })
        cls.product_12 = cls.env['product.product'].create({
            'name': 'Bobine',
            'type': 'consu',
            'uom_id': unit.id,
            'uom_ids': [(6, 0, cls.carton_12.ids)],
        })
        cls.product_2000 = cls.env['product.product'].create({
            'name': 'Manchette',
            'type': 'consu',
            'uom_id': unit.id,
            'uom_ids': [(6, 0, cls.carton_2000.ids)],
        })
        cls.product_loose = cls.env['product.product'].create({
            'name': 'Sold by piece',
            'type': 'consu',
            'uom_id': unit.id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Customer'})

    def _new_line(self, product):
        order_form = Form(self.env['sale.order'])
        order_form.partner_id = self.partner
        line = order_form.order_line.new()
        line.product_id = product
        return order_form, line

    def test_new_product_starts_at_one_carton(self):
        _order_form, line = self._new_line(self.product_2000)
        self.assertEqual(line.nb_carton, 1)
        self.assertEqual(line.product_uom_qty, 2000)

    def test_quantity_rounded_up_to_full_carton(self):
        _order_form, line = self._new_line(self.product_12)
        line.product_uom_qty = 30
        self.assertEqual(line.product_uom_qty, 36)
        self.assertEqual(line.nb_carton, 3)

        _order_form, line = self._new_line(self.product_2000)
        line.product_uom_qty = 7000
        self.assertEqual(line.product_uom_qty, 8000)
        self.assertEqual(line.nb_carton, 4)

    def test_exact_multiple_is_kept(self):
        _order_form, line = self._new_line(self.product_12)
        line.product_uom_qty = 24
        self.assertEqual(line.product_uom_qty, 24)
        self.assertEqual(line.nb_carton, 2)

    def test_carton_count_sets_quantity(self):
        _order_form, line = self._new_line(self.product_2000)
        line.nb_carton = 3
        self.assertEqual(line.product_uom_qty, 6000)

    def test_product_without_carton_is_not_rounded(self):
        _order_form, line = self._new_line(self.product_loose)
        line.product_uom_qty = 7
        self.assertEqual(line.product_uom_qty, 7)
        self.assertEqual(line.nb_carton, 0)

    def test_quantity_written_by_code_is_kept(self):
        """Only the form rounds; a quantity written by code (imports, EDI)
        is left as is, and the carton count still rounds up."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product_2000.id,
                'product_uom_qty': 1,
            })],
        })
        self.assertEqual(order.order_line.product_uom_qty, 1)
        self.assertEqual(order.order_line.nb_carton, 1)

    # purchase.order.line shares the same Colis / Nb Carton structure.
    def _new_purchase_line(self, product):
        order_form = Form(self.env['purchase.order'])
        order_form.partner_id = self.partner
        line = order_form.order_line.new()
        line.product_id = product
        return order_form, line

    def test_purchase_new_product_starts_at_one_carton(self):
        _order_form, line = self._new_purchase_line(self.product_2000)
        self.assertEqual(line.nb_carton, 1)
        self.assertEqual(line.product_qty, 2000)

    def test_purchase_quantity_rounded_up_to_full_carton(self):
        _order_form, line = self._new_purchase_line(self.product_12)
        line.product_qty = 30
        self.assertEqual(line.product_qty, 36)
        self.assertEqual(line.nb_carton, 3)

    def test_purchase_quantity_written_by_code_is_kept(self):
        order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.product_2000.id,
                'product_qty': 1,
            })],
        })
        self.assertEqual(order.order_line.product_qty, 1)
        self.assertEqual(order.order_line.nb_carton, 1)

    def test_invoice_carton_count_never_zero(self):
        """Invoice lines are read-only on cartons: the invoiced quantity is
        kept, only the carton count is rounded up."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_2000.id,
                'quantity': 1,
                'price_unit': 1.0,
            })],
        })
        line = move.invoice_line_ids
        self.assertEqual(line.quantity, 1)
        self.assertEqual(line.nb_carton, 1)
