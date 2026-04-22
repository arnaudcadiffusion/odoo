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

    # Archive (retire du menu) les rapports Studio pour account.move,
    # SAUF "Factures Autre" et "Facture TCARE" qui sont gérés via report_main.xml.
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
    """, (('factures_sans_paieme_ef6af8d0-5ebc-472e-9d25-22d565f71397',
            'pieces_comptables_ra_f16b32c4-f6ea-4d4e-bc8a-d341f6a3a987'),))
