{
    "name": "PO Display Default Code",
    "summary": "Display default code in PO description",
    "version": "19.0.1.0.0",
    "description": """
        When creating a new purchase order, the product's description is updated with the
        product's display_name. This means it will be the '[supplier code] supplier name'.
        This module changes the format to '[supplier code], [default code] supplier name'.
    """,
    "category": "Purchase",
    "license": "LGPL-3",
    "author": "Shine IT",
    "website": "https://www.openerp.cn/",
    "depends": [
        "purchase",
    ],
    "data": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
