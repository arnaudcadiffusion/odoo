"""
Migration 19.0.1.0.8 — post-upgrade

Archive les vues Studio encore actives dont le modèle est déjà couvert
par le code de cadiffusion_base ou report_cadiffusion, ainsi que les
customisations/copies de templates QWeb de rapport.

Conservées intentionnellement (non archivées) :
  - tender.order (vues spécifiques non couvertes)
  - account.* / product.* / mail.* (personnalisations uniques Studio)
"""


_COVERED_MODELS = (
    'stock.picking',
    'stock.move',
    'purchase.order',
    'sale.order',
    'sale.order.line',
)

_REPORT_NAME_PATTERNS = (
    '%report_delivery%',
    '%report_purchaseorder%',
    '%report_purchasequotation%',
    '%report_mrporder%',
    '%studio_report_docume%',
)


def migrate(cr, _version):
    # Archive vues form/list/tree/search/calendar couvertes par le code
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

    # Archive customisations et copies de templates QWeb rapport
    for pattern in _REPORT_NAME_PATTERNS:
        cr.execute("""
            UPDATE ir_ui_view
            SET active = false
            WHERE id IN (
                SELECT res_id FROM ir_model_data
                WHERE module = 'studio_customization'
                  AND model  = 'ir.ui.view'
            )
              AND type = 'qweb'
              AND name ILIKE %s
        """, (pattern,))
