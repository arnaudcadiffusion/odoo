# Copyright 2021 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)

def migrate(cr, version):
    pass 
    # cr.execute("UPDATE purchase_order_line set product_packaging_id=product_packaging where product_packaging in (select id from product_packaging)")
    # cr.execute("UPDATE stock_move set product_packaging_id=product_packaging where product_packaging in (select id from product_packaging)")