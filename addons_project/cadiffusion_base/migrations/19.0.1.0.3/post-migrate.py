"""
Migration 19.0.1.0.3 — post-upgrade

- Désactive les vues Studio héritant de report_cadiffusion.report_invoice_document
  (priority=99, XPath vers ancienne structure → page blanche au rendu PDF).
- Redirige toute action rapport pointant encore sur le template Studio vers
  report_cadiffusion.report_invoice_with_payments (si 19.0.1.0.2 a tourné
  avant l'ajout de ce SQL, la redirection n'a pas eu lieu).
SQL safe : 0 lignes affectées si les enregistrements n'existent pas.
"""


def migrate(cr, version):
    # Désactive les vues Studio inherit sur notre template rapport
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE key IN (
            'gen_key.248a10',
            'gen_key.08fa7f'
        )
    """)

    # Désactive via XMLID également (robustesse si la clé diffère en prod)
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND name IN (
                'odoo_studio_report_i_b8fa811f-edd8-4bf1-84c3-1bb9ffd7f7fd',
                'odoo_studio_report_i_0289ee3f-6a08-4671-9dc3-82641c1b5ee7'
              )
              AND model = 'ir.ui.view'
        )
    """)

    # Redirige toute action rapport pointant encore sur le template Studio cassé
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE report_name LIKE '%studio_report_docume_a5c6eec8%'
          AND model = 'account.move'
    """)
