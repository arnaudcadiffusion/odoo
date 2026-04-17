{
    "name": "Cadiffusion Report",
    "summary": "Add Invoice and Picking Report",
    "version": "19.0.1.0.0",
    "description": """
    Re-design delivery slip and invoice report, remove the Studio generated
    reports. Add text field 'article cmdé' on sale_order_line, picking and
    invoice.
    """,
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Shine IT <contact@openerp.cn>",
    "website": "http://www.openerp.cn/",
    "depends": [
        "sale_stock",
        "account",
        "purchase",
        "sales_team",
    ],
    "data": [
        "views/sale_order.xml",
        "views/stock_picking.xml",
        "views/account_invoice.xml",
        "report/report_main.xml",
        "report/report_invoice.xml",
        "report/report_purchase_order.xml",
        "report/report_delivery_order.xml",
        "report/report_delivery_order_reserved.xml",
        "report/report_sale_order.xml",
        
        # 'report/report_external_layout_boxed.xml',  # à adapter si nécessaire
    ],
    "installable": True,
    "application": False,
}
