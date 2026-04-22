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

    # Redirige toutes les actions rapport account.move qui utilisent encore
    # un template Odoo standard ou Studio (copie) vers notre template custom.
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE model = 'account.move'
          AND (
              report_name LIKE '%studio_report%'
              OR report_name LIKE 'account.report_invoice_copy%'
          )
    """)
