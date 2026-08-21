"""
Migration 19.0.1.0.2 — post-upgrade

- Désactive le rapport Studio (studio_report_docume_a5c6eec8...) qui utilise
  encore tax_totals_json (supprimé en Odoo 17+).  Notre rapport
  report_cadiffusion.report_invoice_document le remplace.
  SQL safe : affecte 0 lignes si l'enregistrement n'existe pas.

- Ajoute account_payment_mode dans les dépendances (via manifest) pour garantir
  le chargement avant account_invoice_transmit_method.
"""


def migrate(cr, version):
    # Désactive le rapport Studio facture (tax_totals_json obsolète)
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE id IN (
            SELECT res_id
            FROM ir_model_data
            WHERE module = 'studio_customization'
              AND name = 'studio_report_docume_a5c6eec8-51b2-4025-a28e-1577b5abcb0d_document'
              AND model = 'ir.ui.view'
        )
    """)

    # Redirige toute action rapport pointant encore sur le template Studio vers
    # notre rapport personnalisé (report_cadiffusion.report_invoice_with_payments).
    # Cela corrige l'AttributeError 'tax_totals_json' sur les factures TCARE, etc.
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE report_name LIKE '%studio_report_docume_a5c6eec8%'
          AND model = 'account.move'
    """)
