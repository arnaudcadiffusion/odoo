"""
Migration 19.0.1.0.7 — post-upgrade

Copie x_studio_article_cmd → article_cmd sur toutes les lignes de commande
où article_cmd est vide. Cela aligne les données Studio (v15/v16) avec le
champ article_cmd lu par le picking et les rapports.
"""


def migrate(cr, _version):
    cr.execute("""
        UPDATE sale_order_line
        SET article_cmd = x_studio_article_cmd
        WHERE (article_cmd IS NULL OR article_cmd = '')
          AND x_studio_article_cmd IS NOT NULL
          AND x_studio_article_cmd != ''
    """)
