{
    "name": "Packaging Qty",
    "summary": "Add Packaging Information",
    "version": "19.0.1.0.0",
    "description": """
        Add packaging information on sale order lines,
        stock move lines, and account move lines.
        Automatically compute packaging quantity in sales.
    """,
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Shine IT <contact@openerp.cn>",
    "website": "https://www.openerp.cn",
    "depends": [
        "sale_stock",
        "account",
        "stock_dropshipping",
    ],
    "data": [
        "views/sale_order.xml",
        "views/stock_picking.xml",
        "views/account_move.xml",
    ],
    "installable": True,
    "application": False,
}
