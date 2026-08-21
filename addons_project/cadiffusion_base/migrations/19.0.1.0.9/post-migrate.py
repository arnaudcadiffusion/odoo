"""
Migration 19.0.1.0.9 — post-upgrade

Archive les vues Studio encore actives dont le modèle est désormais couvert
par le code de cadiffusion_base, report_cadiffusion ou public_tender.

Conservées intentionnellement (non archivées) :
  - Vues auto-générées Studio (type: activity, dashboard, map, pivot, cohort, gantt)
"""

_COVERED_MODELS = (
    'account.account',
    'account.move',
    'account.move.line',
    'ir.ui.view.custom',
    'mail.activity',
    'product.category',
    'product.pricelist',
    'product.template',
    'tender.order',
)


def migrate(cr, _version):
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND model  = 'ir.ui.view'
        )
          AND model IN %s
          AND type IN ('tree', 'list', 'form', 'search', 'calendar')
    """, (_COVERED_MODELS,))
