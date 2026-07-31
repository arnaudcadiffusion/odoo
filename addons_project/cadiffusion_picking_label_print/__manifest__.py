{
    "name": "Cadiffusion Picking Label Print",
    "version": "19.0.1.0.1",
    "category": "Stock",
    "license": "AGPL-3",
    "summary": "Print picking labels from delivery orders",
    "author": "Shine IT",
    "website": "https://www.openerp.cn",
    "depends": [
        "sale_stock",
    ],
    "data": [
        "views/stock_picking_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/wizard_label_print_message.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "application": False,
}
