"""
Migration 19.0.1.0.26 — pre-upgrade

mrp.production.x_studio_conditionnement passe de Char à Many2one(uom.uom) :
le nom des UDM est traduit (« SACHET DE 20 » en anglais, « CARTON DE 20 » en
français) et le Char figeait le libellé de la langue du calcul. La colonne
varchar est supprimée avant que l'ORM ne crée la colonne integer ; la valeur
est entièrement dérivée du produit et recalculée en post-migration.
"""


def migrate(cr, version):
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'mrp_production'
           AND column_name = 'x_studio_conditionnement'
           AND data_type <> 'integer'
        """
    )
    if cr.fetchone():
        cr.execute("ALTER TABLE mrp_production DROP COLUMN x_studio_conditionnement")
