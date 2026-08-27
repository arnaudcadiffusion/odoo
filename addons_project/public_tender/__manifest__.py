{
    "name": "Tender Order",
    "summary": "Public Tender Management",
    "version": "19.0.1.0.1",
    "description": """
        Manage public tenders integrated with sales orders.
    """,
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Shine IT <contact@openerp.cn>",
    "website": "https://www.openerp.cn",
    "depends": [
        "sale_management",
        "product",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/tender.xml",
        "views/res_partner.xml",
        "views/product_pricelist.xml",
        "views/sale_order.xml",
    ],
    "installable": True,
    "application": False,
}
