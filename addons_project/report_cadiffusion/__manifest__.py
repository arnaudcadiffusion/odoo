{
    "name": "Cadiffusion Report",
    "summary": "Add Invoice and Picking Report",
    "version": "19.0.1.0.4",
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
        # NB : les rapports (facture + commande) appellent des méthodes de
        # cadiffusion_base (_cadiffusion_price_per_piece, _cadiffusion_qty_display…)
        # mais UNIQUEMENT au rendu QWeb (t-esc/t-out) — ce n'est PAS un besoin
        # d'install. On ne déclare donc PAS la dépendance : l'ajouter forcerait
        # l'installation de tout le graphe cadiffusion_base à chaque upgrade de
        # report_cadiffusion et casserait le build si cadiffusion_base échoue.
        # (cadiffusion_base reste requis au moment d'imprimer ; il est installé
        # séparément, comme pour le rapport facture qui fonctionne déjà ainsi.)
    ],
    "data": [
        # Nettoyage des doublons de rapports générés par Odoo Studio
        # (studio_customization) qui polluent le menu Imprimer et lèvent
        # « Modèle introuvable » à l'impression.
        "data/cleanup_studio_reports.xml",
        "views/sale_order.xml",
        "views/stock_picking.xml",
        "views/account_invoice.xml",
        "report/report_main.xml",
        "report/report_invoice.xml",
        "report/report_invoice_autre.xml",
        "report/report_purchase_order.xml",
        "report/report_purchase_quotation.xml",
        "report/report_delivery_order.xml",
        "report/report_delivery_order_reserved.xml",
        "report/report_sale_order.xml",
        
        'report/report_external_layout_boxed.xml',
    ],
    "installable": True,
    "application": False,
}
