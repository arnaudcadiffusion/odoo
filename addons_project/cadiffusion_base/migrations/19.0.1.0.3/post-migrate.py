"""
Migration 19.0.1.0.3 — post-upgrade

Archive toutes les vues studio_customization et redirige les actions
rapport Studio vers report_cadiffusion.report_invoice_with_payments.
"""


def migrate(cr, _version):
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND model = 'ir.ui.view'
        )
    """)
    cr.execute("""
        UPDATE ir_ui_view
        SET active = true
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'account_invoice_transmit_method'
              AND name = 'view_partner_property_form'
              AND model = 'ir.ui.view'
        )
    """)
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE report_name LIKE '%studio_report_docume_a5c6eec8%'
          AND model = 'account.move'
    """)
