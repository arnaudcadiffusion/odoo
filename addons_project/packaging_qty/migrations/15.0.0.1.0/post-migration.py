# Copyright 2021 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

from odoo import api, SUPERUSER_ID

def _get_compute_packaging_qty(record):
    packaging_qty = False
    if record.product_packaging_id:
        product_qty = record.product_qty
        default_uom = record.product_id.uom_id
        pack = record.product_packaging_id
        q = default_uom._compute_quantity(pack.qty, record.product_uom_id)
        packaging_qty = product_qty//q +1 if product_qty%q else product_qty//q
    else:
        packaging_qty = False
    return packaging_qty

def migrate(cr, version):
    # Purchase Order
    # cr.execute('ALTER table purchase_order_line add product_packaging_qty double precision')
    env = api.Environment(cr, SUPERUSER_ID, {})
    pol_obj = env['purchase.order.line']
    pols = pol_obj.search([])
    for pol in pols:
        packaging_qty = _get_compute_packaging_qty(pol)
        if packaging_qty:
            cr.execute("""
            UPDATE purchase_order_line set product_packaging_qty={} where id={}
            """.format(packaging_qty, pol.id))