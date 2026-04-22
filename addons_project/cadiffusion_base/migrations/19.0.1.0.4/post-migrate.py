"""
Migration 19.0.1.0.4 — post-upgrade

Archive (retire du menu Imprimer) les rapports Studio liés aux factures,
SAUF "Factures Autre" et "Facture TCARE" qui sont redirigés vers nos
templates hardcodés via report_main.xml et doivent rester visibles.
"""

_KEEP_STUDIO_REPORTS = (
    'factures_sans_paieme_ef6af8d0-5ebc-472e-9d25-22d565f71397',
    'pieces_comptables_ra_f16b32c4-f6ea-4d4e-bc8a-d341f6a3a987',
)


def migrate(cr, _version):
    cr.execute("""
        UPDATE ir_act_report_xml
        SET binding_model_id = NULL
        WHERE model = 'account.move'
          AND id IN (
              SELECT res_id FROM ir_model_data
              WHERE module = 'studio_customization'
                AND model = 'ir.actions.report'
                AND name NOT IN %s
          )
    """, (tuple(_KEEP_STUDIO_REPORTS),))
