{
    "name": "Default Partner Ref",
    "summary": "Default Ref On Partner",
    "version": "19.0.1.0.0",
    "description": """
        1. When a customer creates a new child partner, the parent's internal reference
           will be the child's default value
        2. Add the city search bar
    """,
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Shine IT",
    "website": "https://www.openerp.cn/",
    "depends": [
        "base",
        "sale",
        "account",
        # "l10n_fr_chorus_account",
    ],
    "data": [
        "views/res_partner.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
