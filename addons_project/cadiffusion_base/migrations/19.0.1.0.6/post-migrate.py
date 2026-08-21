"""
Migration 19.0.1.0.6 — post-upgrade

Masque TOUS les rapports Studio pour account.move.
Les actions Factures Autre et Facture TCARE sont désormais définies
directement dans report_invoice_autre.xml (module report_cadiffusion)
avec nos propres XML IDs — plus de dépendance aux UUIDs Studio.
"""


def migrate(cr, _version):
    cr.execute("""
        UPDATE ir_act_report_xml
        SET binding_model_id = NULL
        WHERE model = 'account.move'
          AND id IN (
              SELECT res_id FROM ir_model_data
              WHERE module = 'studio_customization'
                AND model = 'ir.actions.report'
          )
    """)
