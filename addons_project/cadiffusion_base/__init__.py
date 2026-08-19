import csv
import logging

from odoo.tools import file_open

from . import models

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Sur install fresh, Odoo n'exécute pas les scripts de migrations/.
    On rejoue donc ici toute la logique des migrations 19.0.1.0.1 → 19.0.1.0.10
    pour aligner l'état du système (vues Studio archivées, rapports redirigés,
    filtres corrigés, données copiées) comme si on venait d'un upgrade depuis v15/v16,
    puis la réparation des données abîmées par la plateforme d'upgrade
    (_repair_upgrade_data — c'est le cas de chaque rebuild Odoo.sh par upgrade
    complet : le module y est installé neuf, jamais mis à jour).

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
    _apply_v15_carton_choices(env)
    _repair_upgrade_data(env)
    _configure_unece_exo_taxes(env)


# ---------------------------------------------------------------------------
# Reprise des conditionnements choisis en v15 (product_packaging_id des
# lignes de vente et d'achat, supprimé par l'upgrade sans conversion).
#
# ~90 % des lignes v15 utilisaient le plus grand conditionnement du produit,
# ce que le défaut calculé de carton_uom_id retrouve tout seul
# (_cadiffusion_default_carton_uom). Les CSV data/carton_uom_v15_*.csv ne
# contiennent QUE les écarts : les lignes dont le choix v15 diffère de ce
# défaut (1 101 achats, 27 493 ventes), sous la forme (id de ligne, nom
# normalisé de l'UDM v19 — les ids de lignes survivent à l'upgrade, pas les
# ids d'UDM, recréées à chaque passage de la plateforme).
#
# CSV générés depuis la base v15 (croisement cadiffusion16 × cadiffusion du
# 31/07/2026) par data/build_carton_uom_v15.py (outil dev, non chargé) : à
# régénérer depuis le dump v15 final si la bascule production repart d'une
# base plus récente — mode d'emploi dans son docstring.
#
# Partagée entre le post_init_hook (install fresh : rebuilds Odoo.sh) et
# migrations/19.0.1.0.17/post-migrate.py (bases déjà installées).
# Idempotent : UPDATE conditionnel (IS DISTINCT FROM), résolution du nom
# dans les UDM du produit actuel de la ligne (aucun effet si l'UDM n'y est
# plus).
# ---------------------------------------------------------------------------
def _apply_v15_carton_choices(env):
    specs = [
        ('sale_order_line',
         'cadiffusion_base/data/carton_uom_v15_sale_order_line.csv'),
        ('purchase_order_line',
         'cadiffusion_base/data/carton_uom_v15_purchase_order_line.csv'),
    ]
    for table, path in specs:
        with file_open(path) as csvfile:
            rows = [(int(r['line_id']), r['uom_name'])
                    for r in csv.DictReader(csvfile)]
        updated = 0
        for start in range(0, len(rows), 10000):
            chunk = rows[start:start + 10000]
            values_sql = ','.join(['(%s, %s)'] * len(chunk))
            params = [value for row in chunk for value in row]
            # Résout le nom d'UDM v15 (normalisé : majuscules, espaces
            # réduits) parmi les UDM d'emballage du produit de la ligne.
            env.cr.execute("""
                UPDATE {table} line
                   SET carton_uom_id = pick.uom_id
                  FROM (
                       SELECT DISTINCT ON (v.line_id) v.line_id, u.id AS uom_id
                         FROM (VALUES {values}) AS v(line_id, uom_name)
                         JOIN {table} l ON l.id = v.line_id
                         JOIN product_product pp ON pp.id = l.product_id
                         JOIN product_template_uom_uom_rel rel
                              ON rel.product_template_id = pp.product_tmpl_id
                         JOIN uom_uom u ON u.id = rel.uom_uom_id
                        WHERE btrim(regexp_replace(
                                  upper(coalesce(u.name->>'en_US', '')),
                                  '\\s+', ' ', 'g')) = v.uom_name
                        ORDER BY v.line_id, u.id
                       ) pick
                 WHERE line.id = pick.line_id
                   AND line.carton_uom_id IS DISTINCT FROM pick.uom_id
            """.format(table=table, values=values_sql), params)
            updated += env.cr.rowcount
        _logger.info(
            "cadiffusion_base: conditionnements v15 repris sur %s — "
            "%s ligne(s) mises à jour (%s écarts dans le CSV)",
            table, updated, len(rows))
    env.invalidate_all()

    # Historique inventaire : sur les moves FAITS, l'upgrade a laissé
    # packaging_uom_id = la pièce (les BL / réceptions ré-imprimés perdent
    # leur colonne Conditionnement — la réparation .14 ne recalculait que
    # les moves ouverts). En v15 le product_packaging_id du move était copié
    # depuis la ligne de commande : maintenant que carton_uom_id porte le
    # choix v15 exact, on le reprend depuis la ligne de vente / d'achat
    # liée. SQL set-based (~270 000 moves) ; les moves sans ligne de
    # commande (transferts internes, MRP) ne sont pas touchés.
    for line_table, line_fk in (('sale_order_line', 'sale_line_id'),
                                ('purchase_order_line', 'purchase_line_id')):
        env.cr.execute("""
            UPDATE stock_move move
               SET packaging_uom_id = line.carton_uom_id
              FROM {table} line
             WHERE line.id = move.{fk}
               AND move.state = 'done'
               AND line.carton_uom_id IS NOT NULL
               AND move.packaging_uom_id IS DISTINCT FROM line.carton_uom_id
        """.format(table=line_table, fk=line_fk))
        _logger.info(
            "cadiffusion_base: conditionnement v15 repris sur %s moves faits "
            "(via %s)", env.cr.rowcount, line_table)
    # Quantité de conditionnement cohérente (même formule que le compute
    # standard : product_uom_qty converti dans l'UDM de conditionnement).
    env.cr.execute("""
        UPDATE stock_move move
           SET packaging_uom_qty = move.product_uom_qty * lu.factor / pu.factor
          FROM uom_uom lu, uom_uom pu
         WHERE lu.id = move.product_uom
           AND pu.id = move.packaging_uom_id
           AND move.state = 'done'
           AND lu.factor IS NOT NULL
           AND pu.factor IS NOT NULL AND pu.factor != 0
           AND move.packaging_uom_qty IS DISTINCT FROM
               move.product_uom_qty * lu.factor / pu.factor
    """)
    _logger.info(
        "cadiffusion_base: quantité de conditionnement recalculée sur %s "
        "moves faits", env.cr.rowcount)
    env.invalidate_all()

    # Le conditionnement des moves ouverts (packaging_uom_id, stocké) dépend
    # du carton des lignes de vente/d'achat : recalcul ORM après reprise
    # (couvre aussi le repli « UDM carton du produit »), la quantité
    # (packaging_uom_qty) APRÈS le conditionnement.
    moves = env['stock.move'].search([('state', 'not in', ('done', 'cancel'))])
    env.add_to_compute(moves._fields['packaging_uom_id'], moves)
    moves.flush_recordset(['packaging_uom_id'])
    env.add_to_compute(moves._fields['packaging_uom_qty'], moves)
    moves.flush_recordset(['packaging_uom_qty'])
    _logger.info(
        "cadiffusion_base: conditionnement recalculé sur %s moves ouverts "
        "après reprise v15", len(moves))


# ---------------------------------------------------------------------------
# Réparation des données laissées par la plateforme d'upgrade v15 → v19.
# Partagée entre le post_init_hook (install fresh : rebuilds Odoo.sh, prod)
# et migrations/19.0.1.0.14/post-migrate.py (bases déjà installées).
# Idempotent.
# ---------------------------------------------------------------------------
def _repair_upgrade_data(env):
    # 1. UDM sans facteur calculé : les UDM créées depuis les product.packaging
    #    v15 (« CARTON DE 10 », « BOITE »…) arrivent avec le champ calculé
    #    stocké ``factor`` à NULL. Toute conversion passant par elles renvoie
    #    alors 0 (colis des BL, prix à la pièce, quantités MRP…).
    env.cr.execute("SELECT count(*) FROM uom_uom WHERE factor IS NULL")
    nb_null = env.cr.fetchone()[0]
    uoms = env['uom.uom'].with_context(active_test=False).search([])
    env.add_to_compute(uoms._fields['factor'], uoms)
    uoms.flush_recordset(['factor'])
    _logger.info(
        "cadiffusion_base: facteurs UDM recalculés (%s NULL sur %s avant réparation)",
        nb_null, len(uoms))

    # 2. Conditionnement des moves ouverts : l'upgrade a mis packaging_uom_id
    #    à l'UDM pièce (perte du product_packaging_id v15). Le recalcul passe
    #    par la surcharge cadiffusion de _compute_packaging_uom_id (le carton).
    #    La quantité doit être recalculée APRÈS l'écriture du nouveau
    #    conditionnement, sinon elle est convertie avec l'ancien (la pièce).
    moves = env['stock.move'].search([('state', 'not in', ('done', 'cancel'))])
    env.add_to_compute(moves._fields['packaging_uom_id'], moves)
    moves.flush_recordset(['packaging_uom_id'])
    env.add_to_compute(moves._fields['packaging_uom_qty'], moves)
    moves.flush_recordset(['packaging_uom_qty'])
    _logger.info(
        "cadiffusion_base: conditionnement recalculé sur %s moves ouverts", len(moves))

    # 3. Réservations perdues : plus aucune stock.move.line sur les transferts
    #    non terminés alors que les pickings restent affichés « assigned ».
    #    On ré-exécute la réservation standard (action_assign), picking par
    #    picking sous savepoint : un transfert corrompu ne doit pas faire
    #    échouer l'install/upgrade. En v19, action_assign trie lui-même les
    #    moves par priorité / échéance / date.
    ok = ko = 0
    for picking in env['stock.picking'].search([
            ('state', 'in', ('confirmed', 'waiting', 'assigned'))]):
        try:
            with env.cr.savepoint():
                picking.action_assign()
            ok += 1
        except Exception:
            ko += 1
            _logger.warning(
                "cadiffusion_base: action_assign en échec sur %s (ignoré)",
                picking.name, exc_info=True)
    _logger.info(
        "cadiffusion_base: re-réservation terminée — %s transferts traités, %s en échec",
        ok, ko)


# ---------------------------------------------------------------------------
# Codes UNECE des taxes d'exonération 0% (« TVA 0% EXO »).
# Sans unece_type_code='VAT', generate_facturx_xml n'émet aucun bloc
# ApplicableTradeTax d'en-tête quand toutes les lignes de la facture portent
# une telle taxe (intérêts moratoires, journal « Factures IM »…) → XML
# invalide contre le XSD CII, envoi Chorus impossible.
# Partagée entre le post_init_hook (install fresh : rebuilds Odoo.sh, prod)
# et migrations/19.0.1.0.16/post-migrate.py (bases déjà installées).
# Idempotent : ne touche que les taxes 0% « EXO » encore sans type UNECE.
# ---------------------------------------------------------------------------
def _configure_unece_exo_taxes(env):
    candidates = env['account.tax'].with_context(active_test=False).search([
        ('type_tax_use', '=', 'sale'),
        ('amount', '=', 0),
        ('unece_type_code', '=', False),
    ])
    # Pas de ilike SQL sur le nom : en v19 il matche par sous-séquence de
    # caractères ('EXO' → '%E%X%O%') et attraperait aussi « TVA 0% EXPORT »
    # / « TVA 0% export (vente) », dont la catégorie UNECE correcte est G
    # (export), pas E (exonération).
    taxes = candidates.filtered(
        lambda tax: (tax.name or '').strip().upper() == 'TVA 0% EXO')
    if taxes:
        taxes.write({'unece_type_code': 'VAT', 'unece_categ_code': 'E'})
    _logger.info(
        "cadiffusion_base: codes UNECE VAT/E configurés sur %s taxe(s) 0%% EXO %s",
        len(taxes), taxes.mapped('display_name'))


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
