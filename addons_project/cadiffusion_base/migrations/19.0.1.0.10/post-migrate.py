"""
Migration 19.0.1.0.10 — post-upgrade

Corrige les filtres sauvegardés (ir.filters) qui trient sur 'price_reduce',
champ supprimé dans Odoo 19 et remplacé par 'price_reduce_taxexcl'.

Sans cette correction, l'application du filtre par défaut sur sale.order.line
(menu Ventes > Analyse > Lignes de ventes) lève un ValueError côté ORM lors
du tri SQL.
"""


def migrate(cr, _version):
    cr.execute("""
        UPDATE ir_filters
        SET sort = REPLACE(sort, 'price_reduce', 'price_reduce_taxexcl')
        WHERE sort ILIKE '%price_reduce%'
          AND sort NOT ILIKE '%price_reduce_taxexcl%'
    """)
