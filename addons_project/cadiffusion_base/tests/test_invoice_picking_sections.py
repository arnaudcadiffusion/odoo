from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvoicePickingSections(TransactionCase):
    """Customer invoices created from a sale order carry a ``BL : <picking>``
    section above the lines of each delivery. With several deliveries, each
    invoice names the delivery slip it actually covers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'BL Customer'})
        cls.product = cls.env['product.product'].create({
            'name': 'Delivered product',
            'type': 'consu',
            'invoice_policy': 'delivery',
            'list_price': 10.0,
        })
        cls.other_product = cls.env['product.product'].create({
            'name': 'Other delivered product',
            'type': 'consu',
            'invoice_policy': 'delivery',
            'list_price': 5.0,
        })

    def _confirm_order(self, lines, client_order_ref=False):
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'client_order_ref': client_order_ref,
            'order_line': [
                Command.create({'product_id': product.id, 'product_uom_qty': qty})
                for product, qty in lines
            ],
        })
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 1)
        return order

    def _deliver(self, picking, quantities):
        """Validate ``picking`` with ``quantities`` ({product: qty}) and return
        the backorder created for the remainder, if any."""
        for move in picking.move_ids:
            move.quantity = quantities.get(move.product_id, 0.0)
            move.picked = True
        result = picking.button_validate()
        if isinstance(result, dict):
            wizard = Form(
                self.env[result['res_model']].with_context(result['context'])
            ).save()
            wizard.process()
        self.assertEqual(picking.state, 'done')
        return self.env['stock.picking'].search([('backorder_id', '=', picking.id)])

    def _sections(self, invoice):
        return invoice.invoice_line_ids.filtered(
            lambda l: l.display_type == 'line_section'
        ).sorted('sequence').mapped('name')

    def test_second_invoice_names_second_delivery(self):
        order = self._confirm_order([(self.product, 10)])
        first_picking = order.picking_ids
        second_picking = self._deliver(first_picking, {self.product: 4})
        self.assertTrue(second_picking)

        first_invoice = order._create_invoices()
        self.assertEqual(self._sections(first_invoice), ['BL : %s' % first_picking.name])

        self._deliver(second_picking, {self.product: 6})
        second_invoice = order._create_invoices()
        self.assertEqual(second_invoice.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product').quantity, 6)
        self.assertEqual(
            self._sections(second_invoice), ['BL : %s' % second_picking.name]
        )

    def test_single_invoice_spanning_two_deliveries(self):
        order = self._confirm_order([(self.product, 10)])
        first_picking = order.picking_ids
        second_picking = self._deliver(first_picking, {self.product: 4})
        self._deliver(second_picking, {self.product: 6})

        invoice = order._create_invoices()
        self.assertEqual(
            self._sections(invoice),
            ['BL : %s, %s' % (first_picking.name, second_picking.name)],
        )

    def test_lines_grouped_per_delivery_with_customer_reference(self):
        order = self._confirm_order(
            [(self.product, 3), (self.other_product, 2)], client_order_ref='PO-42'
        )
        first_picking = order.picking_ids
        # First delivery ships only the first product, the backorder the second.
        second_picking = self._deliver(first_picking, {self.product: 3})
        self._deliver(second_picking, {self.other_product: 2})

        invoice = order._create_invoices()
        self.assertEqual(
            self._sections(invoice),
            [
                'BL : %s - PO-42' % first_picking.name,
                'BL : %s - PO-42' % second_picking.name,
            ],
        )
        lines = invoice.invoice_line_ids.sorted('sequence')
        self.assertEqual(
            lines.mapped('display_type'),
            ['line_section', 'product', 'line_section', 'product'],
        )

    def test_cancelled_invoice_does_not_consume_delivery(self):
        order = self._confirm_order([(self.product, 10)])
        first_picking = order.picking_ids
        second_picking = self._deliver(first_picking, {self.product: 4})

        cancelled = order._create_invoices()
        cancelled.button_cancel()
        again = order._create_invoices()
        self.assertEqual(self._sections(again), ['BL : %s' % first_picking.name])
        self.assertTrue(second_picking)
