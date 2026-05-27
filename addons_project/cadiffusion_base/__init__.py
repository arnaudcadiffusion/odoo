# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """
    Sur install fresh, Odoo n'exécute pas les scripts de migrations/.
    On rejoue donc ici toute la logique des migrations 19.0.1.0.1 → 19.0.1.0.10
    pour aligner l'état du système (vues Studio archivées, rapports redirigés,
    filtres corrigés, données copiées) comme si on venait d'un upgrade depuis v15/v16.

    Idempotent : chaque opération filtre déjà sur l'état avant modification
    (WHERE active = true, NOT ILIKE, IS NULL, etc.).
    """
    cr = env.cr
    _migrate_19_0_1_0_1(cr)
    _migrate_19_0_1_0_2(cr)
    _migrate_19_0_1_0_3(cr)
    _migrate_19_0_1_0_4(cr)
    _migrate_19_0_1_0_5(cr)
    _migrate_19_0_1_0_6(cr)
    _migrate_19_0_1_0_7(cr)
    _migrate_19_0_1_0_8(cr)
    _migrate_19_0_1_0_9(cr)
    _migrate_19_0_1_0_10(cr)


# ---------------------------------------------------------------------------
# 19.0.1.0.1 — Archive companies obsolètes
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_1(cr):
    cr.execute("""
        UPDATE res_company
        SET active = false
        WHERE name IN ('ACES', 'PERSO', 'INNOVIA', 'ARKHE', 'SCI START')
          AND active = true
    """)


# ---------------------------------------------------------------------------
# 19.0.1.0.2 — Désactive rapport Studio facture + redirige report_name
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_2(cr):
    cr.execute("""
        UPDATE ir_ui_view
        SET active = false
        WHERE id IN (
            SELECT res_id FROM ir_model_data
            WHERE module = 'studio_customization'
              AND name = 'studio_report_docume_a5c6eec8-51b2-4025-a28e-1577b5abcb0d_document'
              AND model = 'ir.ui.view'
        )
    """)
    cr.execute("""
        UPDATE ir_act_report_xml
        SET report_name = 'report_cadiffusion.report_invoice_with_payments'
        WHERE report_name LIKE '%studio_report_docume_a5c6eec8%'
          AND model = 'account.move'
    """)


# ---------------------------------------------------------------------------
# 19.0.1.0.3 — Archive toutes les vues Studio, rétablit transmit_method,
#              redirige rapports vers report_invoice_with_payments
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_3(cr):
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


# ---------------------------------------------------------------------------
# 19.0.1.0.4 — Archive rapports Studio sauf 'Factures Autre' et 'Facture TCARE'
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_4(cr):
    keep = (
        'factures_sans_paieme_ef6af8d0-5ebc-472e-9d25-22d565f71397',
        'pieces_comptables_ra_f16b32c4-f6ea-4d4e-bc8a-d341f6a3a987',
    )
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
    """, (keep,))


# ---------------------------------------------------------------------------
# 19.0.1.0.5 — Restaure 'Factures Autre' et 'Facture TCARE' vers nos templates
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_5(cr):
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


# ---------------------------------------------------------------------------
# 19.0.1.0.6 — Masque TOUS les rapports Studio pour account.move
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_6(cr):
    cr.execute("""
        UPDATE ir_act_report_xml
        SET binding_model_id = NULL
        WHERE model = 'account.move'
          AND id IN (
              SELECT res_id FROM ir_model_data
              WHERE module = 'studio_customization'
                AND model = 'ir.actions.report'
          )
    """)


# ---------------------------------------------------------------------------
# 19.0.1.0.7 — Copie x_studio_article_cmd → article_cmd
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_7(cr):
    # Le champ x_studio_article_cmd n'existe que si Studio l'a créé en v15/v16.
    # Sur une base fresh sans Studio, la colonne n'existe pas -> NOOP.
    cr.execute("""
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'sale_order_line'
          AND column_name = 'x_studio_article_cmd'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        UPDATE sale_order_line
        SET article_cmd = x_studio_article_cmd
        WHERE (article_cmd IS NULL OR article_cmd = '')
          AND x_studio_article_cmd IS NOT NULL
          AND x_studio_article_cmd != ''
    """)


# ---------------------------------------------------------------------------
# 19.0.1.0.8 — Archive vues Studio couvertes par cadiffusion_base/report_cadiffusion
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_8(cr):
    covered_models = (
        'stock.picking',
        'stock.move',
        'purchase.order',
        'sale.order',
        'sale.order.line',
    )
    report_name_patterns = (
        '%report_delivery%',
        '%report_purchaseorder%',
        '%report_purchasequotation%',
        '%report_mrporder%',
        '%studio_report_docume%',
    )

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
    """, (covered_models,))

    for pattern in report_name_patterns:
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


# ---------------------------------------------------------------------------
# 19.0.1.0.9 — Archive vues Studio supplémentaires (account, product, etc.)
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_9(cr):
    covered_models = (
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
    """, (covered_models,))


# ---------------------------------------------------------------------------
# 19.0.1.0.10 — Corrige filtres ir.filters utilisant price_reduce (supprimé en v19)
# ---------------------------------------------------------------------------
def _migrate_19_0_1_0_10(cr):
    cr.execute("""
        UPDATE ir_filters
        SET sort = REPLACE(sort, 'price_reduce', 'price_reduce_taxexcl')
        WHERE sort ILIKE '%price_reduce%'
          AND sort NOT ILIKE '%price_reduce_taxexcl%'
    """)
