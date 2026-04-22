"""
Migration 19.0.1.0.5 — post-upgrade

Restaure "Factures Autre" et "Facture TCARE" dans le menu Imprimer :
- repointe leur report_name vers notre template hardcodé report_invoice_autre
- réaffecte binding_model_id à account.move pour les rendre visibles
"""

_STUDIO_REPORTS = (
    'factures_sans_paieme_ef6af8d0-5ebc-472e-9d25-22d565f71397',    # Factures Autre
    'pieces_comptables_ra_f16b32c4-f6ea-4d4e-bc8a-d341f6a3a987',    # Facture TCARE
)


def migrate(cr, _version):
    model_id_sql = "SELECT id FROM ir_model WHERE model = 'account.move' LIMIT 1"

    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_autre',
            binding_model_id = (%s)
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND model  = 'ir.actions.report'
              AND name   = %%s
        )
    """ % model_id_sql, ('factures_sans_paieme_ef6af8d0-5ebc-472e-9d25-22d565f71397',))

    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_tcare',
            binding_model_id = (%s)
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND model  = 'ir.actions.report'
              AND name   = %%s
        )
    """ % model_id_sql, ('pieces_comptables_ra_f16b32c4-f6ea-4d4e-bc8a-d341f6a3a987',))
