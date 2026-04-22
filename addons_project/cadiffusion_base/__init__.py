# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    _deactivate_all_studio(env.cr)


def _deactivate_all_studio(cr):
    # Archive toutes les vues Studio — nos vues XML les remplacent.
    # Safe : 0 lignes si studio_customization n'est pas installé.
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND model = 'ir.ui.view'
        )
    """)

    # Rétablit la vue transmit_method qui doit toujours rester active.
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

    # Redirige les actions rapport pointant sur un template Studio cassé.
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE report_name LIKE '%studio_report_docume_a5c6eec8%'
          AND model = 'account.move'
    """)
