{
    "name": "CA Date Format",
    "version": "19.0.1.0.0",
    "summary": "Display of the date in dd/mm/yyyy format",
    "category": "Custom",
    "author": "Nexources",
    "depends": ["cadiffusion_base"],
    "assets": {
        "web.assets_backend": [
            "ca_date_format/static/src/date_field_numeric.js",
        ],
    },
    "installable": True,
    # Sa seule dépendance est cadiffusion_base : auto_install le fait donc
    # installer dès que celui-ci l'est, sans intervention après migration. Il
    # remplace les options={"numeric": true} posées champ par champ dans Studio
    # sur la base de test (cf. views/studio_post_upgrade_views.xml).
    "auto_install": True,
    "license": "LGPL-3",
}
