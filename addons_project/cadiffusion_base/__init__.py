import csv
import logging

from odoo.tools import file_open

# Réexportés : les scripts de migrations/, les tests et les outils de data/
# importent ces noms depuis le paquet (la logique vit dans reference_state.py).
from .reference_state import (  # noqa: F401
    _APPLY,
    _REPORT,
    _REFERENCE_SPECS,
    _apply_reference_state,
    _reference_diff,
    _reference_snapshot,
)
# Outillage de renommage des champs Studio (x_studio_* → ca_diff_*). Rien ne
# l'appelle : il attend un pre-migrate côté aller, un odoo shell côté retour.
from .field_rename import (  # noqa: F401
    _apply_field_rename,
    _field_rename_status,
    _load_field_rename_map,
    _rollback_field_rename,
)
# Séquelles Studio / v15 laissées en base par la bascule : inventaire et
# quarantaine réversible. Dormant lui aussi, appelé à la main.
from .studio_debris import (  # noqa: F401
    _quarantine_studio_debris,
    _restore_studio_debris,
    _studio_debris,
    _studio_debris_status,
)
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

    L'instantané de référence (reference_state.py) est par ailleurs rejoué par
    data/reference_state.xml à chaque chargement des données — install et
    chaque ``-u`` —, avant nos vues ; l'appel en fin de hook est le dernier
    mot, après les corrections SQL ci-dessous.

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
    _archive_post_upgrade_studio_views(env)
    _delete_views_with_unknown_type(env)
    _apply_manual_settings_from_test_base(env)
    _apply_reference_state(env)


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
# Codes UNECE des taxes 0% de vente (exonération, export, livraisons
# intracommunautaires).
#
# Sans unece_type_code, generate_facturx_xml n'émet aucun bloc
# ApplicableTradeTax d'en-tête quand toutes les lignes de la facture portent
# une telle taxe (intérêts moratoires, journal « Factures IM »…) → XML
# invalide contre le XSD CII, envoi Chorus impossible.
#
# Une catégorie FAUSSE est pire qu'absente : le XML passe la validation en
# déclarant un régime de TVA qui n'est pas celui de la facture. La première
# version de cette fonction cherchait « EXO » en ilike SQL, qui matche en v19
# par sous-séquence de caractères ('EXO' → '%E%X%O%') : elle a posé la
# catégorie E (exonéré) sur les taxes export et intracommunautaires de
# CA DIFFUSION (constaté le 19/08/2026 sur les taxes 43, 44, 877 et 878). Les
# écritures déjà faites sont donc corrigées, pas seulement complétées.
#
# La réparation reste étroite, et c'est volontaire : une taxe export ou
# intracommunautaire restée SANS code relève d'un arbitrage comptable, pas
# d'une régression — data/check_post_build.py les signale pour décision. Et un
# code déjà posé qui n'est pas le E fautif (AE = autoliquidation) est un choix
# assumé auquel on ne touche pas.
#
# Partagée entre le post_init_hook (install fresh : rebuilds Odoo.sh, prod) et
# migrations/19.0.1.0.16 puis 19.0.1.0.21/post-migrate.py (bases déjà
# installées). Idempotent : n'écrit que si le code diffère de l'attendu.
# ---------------------------------------------------------------------------
def _unece_categ_for_tax_name(name):
    """Catégorie UNECE que le NOM de la taxe annonce, ou None quand il ne
    permet pas de trancher.

    E = exonéré, G = export hors UE, K = livraison intracommunautaire.
    L'ordre compte : « TVA 0% EU M » et « 0% Non EU » doivent sortir avant le
    repli sur l'exonération, et « Non EU » est un export, pas une livraison
    intracommunautaire.
    """
    normalized = ' '.join((name or '').upper().split())
    words = normalized.split()
    if 'INTRACOMMUNAUTAIRE' in normalized or ('EU' in words and 'NON' not in words):
        return 'K'
    if 'EXPORT' in normalized or 'NON EU' in normalized:
        return 'G'
    if 'EXO' in words:
        return 'E'
    return None


def _unece_code_record(env, code_type, code):
    return env['unece.code.list'].search(
        [('type', '=', code_type), ('code', '=', code)], limit=1)


def _configure_unece_exo_taxes(env):
    # On écrit les many2one unece_type_id / unece_categ_id, PAS les champs
    # unece_type_code / unece_categ_code : ces derniers sont des related
    # stockés en lecture seule (related='unece_categ_id.code'). Les écrire
    # remplit la colonne sans renseigner le m2o source — le code tient jusqu'au
    # premier recalcul du related (mise à jour d'account_tax_unece, écriture
    # sur le m2o…), puis retombe à vide et le bloc ApplicableTradeTax disparaît
    # silencieusement du XML. C'est ce qu'avait laissé la version précédente
    # (taxes 876 et 879 de la base de test : code posé, m2o vide) ; ces taxes
    # sont réparées ici au passage.
    vat = _unece_code_record(env, 'tax_type', 'VAT')
    taxes = env['account.tax'].with_context(active_test=False).search([
        ('type_tax_use', '=', 'sale'),
        ('amount', '=', 0),
    ])
    updated = []
    for tax in taxes:
        expected = _unece_categ_for_tax_name(tax.name)
        if not expected:
            continue
        current = tax.unece_categ_id.code
        if not current:
            if expected != 'E':
                continue        # arbitrage comptable, pas une régression
        elif current != 'E' or expected == 'E':
            continue            # code assumé (AE…), ou déjà correct
        categ = _unece_code_record(env, 'tax_categ', expected)
        if not vat or not categ:
            _logger.warning(
                "cadiffusion_base: nomenclature UNECE incomplète "
                "(type VAT: %s, catégorie %s: %s) — taxe %s laissée en l'état",
                bool(vat), expected, bool(categ), tax.name)
            continue
        updated.append('%s (%s) : %s → VAT/%s' % (
            tax.name, tax.company_id.name, current or 'aucun code', expected))
        tax.write({'unece_type_id': vat.id, 'unece_categ_id': categ.id})
    _logger.info(
        "cadiffusion_base: codes UNECE posés sur %s taxe(s) 0%% de vente %s",
        len(updated), updated)


# ---------------------------------------------------------------------------
# Vues Studio créées SUR LA BASE DE TEST après l'upgrade v15 → v19 (du
# 23/06/2026 au 16/08/2026). Leur contenu est repris en XML dans
# views/studio_post_upgrade_views.xml (pour les 6 qui portent une vraie
# personnalisation) ou couvert par le module ca_date_format (pour les 5 qui ne
# faisaient que poser options={"numeric": true} sur des champs date).
# On archive donc les originales pour que les deux jeux ne se superposent pas.
#
# Partagée entre le post_init_hook (install fresh : rebuilds Odoo.sh, bascule
# production — où ces vues n'existent pas, la fonction est alors sans effet) et
# migrations/19.0.1.0.18/post-migrate.py (bases déjà installées, dont Test).
# Idempotent : ne touche que les vues encore actives.
# ---------------------------------------------------------------------------
_POST_UPGRADE_STUDIO_VIEWS = (
    # reprises en XML dans views/studio_post_upgrade_views.xml
    'odoo_studio_account__5ebc3022-8ee2-4f9a-b39f-6b561d1a87fc',  # account.move form
    'odoo_studio_account__fe18d761-19ff-4d44-a51e-6a2dd54b2e3a',  # account.move list
    'odoo_studio_res_part_fe80bac8-bda7-4e20-99af-b2fa5ab7bc9f',  # res.partner form
    'odoo_studio_res_part_a506c976-31da-4edd-9769-32b5529c9ada',  # res.partner list
    'odoo_studio_sale_ord_008e3e26-eabf-4641-a7cd-e38b161f7b04',  # sale.order form
    'odoo_studio_product__b078226b-0ce9-4622-bf22-59d3d743640c',  # product.product form
    # couvertes par ca_date_format (options numeric sur des champs date)
    'odoo_studio_stock_pi_4d29c376-3963-40fd-bf93-e3680b8ee33d',  # stock.picking form
    'odoo_studio_stock_pi_b072fb10-8cf8-412a-8ddf-bf2c6a5ad336',  # stock.picking list
    'odoo_studio_tender_o_4544821c-46f5-4ad7-bbdc-538c59fb737d',  # tender.order form
    'odoo_studio_tender_o_e9ccd7b2-8c58-460c-a42c-3eaa61d7a3e5',  # tender.order list
    'odoo_studio_sale_ord_26ce5b94-ea86-4ea4-94d7-e85bdd57882b',  # sale.order list
)


def _archive_post_upgrade_studio_views(env):
    env.cr.execute("""
        UPDATE ir_ui_view
           SET active = false
         WHERE active = true
           AND id IN (
               SELECT res_id FROM ir_model_data
                WHERE module = 'studio_customization'
                  AND model  = 'ir.ui.view'
                  AND name IN %s
           )
    """, (_POST_UPGRADE_STUDIO_VIEWS,))
    _logger.info(
        "cadiffusion_base: %s vue(s) Studio post-upgrade archivée(s) "
        "(contenu repris en XML / couvert par ca_date_format)",
        env.cr.rowcount)


# ---------------------------------------------------------------------------
# Réglages posés à la main sur la base de test et absents de la production.
#
# Identifiés en comparant la base de test de mai (build 35344202) avec
# l'upgrade neuf du 19/08/2026 (build 36652311) : ces deux écritures ne
# laissaient aucune trace exploitable en SQL (pas de tracking sur res.company
# ni sur stock.picking.type), c'est le diff champ par champ qui les a révélées.
#
#  - barcode des types d'opération de l'entrepôt principal : l'upgrade les
#    ramène aux valeurs par défaut d'Odoo (WH-RECEIPTS / WH-DELIVERY) alors que
#    les douchettes et les étiquettes sont calées sur WHIN / WHOUT.
#  - stock_move_email_validation sur CA DIFFUSION : confirmation par e-mail à
#    la validation d'un mouvement de stock.
#
# Partagée entre le post_init_hook (install fresh : rebuilds Odoo.sh, bascule
# production) et migrations/19.0.1.0.20/post-migrate.py (bases déjà installées).
# Idempotent : écriture conditionnelle, sans effet si l'enregistrement est
# absent ou déjà à la bonne valeur.
# ---------------------------------------------------------------------------
_PICKING_TYPE_BARCODES = (
    ('stock.picking_type_in', 'WHIN'),
    ('stock.picking_type_out', 'WHOUT'),
)


def _apply_manual_settings_from_test_base(env):
    for xmlid, barcode in _PICKING_TYPE_BARCODES:
        picking_type = env.ref(xmlid, raise_if_not_found=False)
        if picking_type and picking_type.barcode != barcode:
            picking_type.barcode = barcode
            _logger.info(
                "cadiffusion_base: code-barres du type d'opération %s remis à %s",
                xmlid, barcode)

    company = env.ref('base.main_company', raise_if_not_found=False)
    if company and not company.stock_move_email_validation:
        company.stock_move_email_validation = True
        _logger.info(
            "cadiffusion_base: confirmation par e-mail des mouvements de stock "
            "réactivée sur %s", company.display_name)


# ---------------------------------------------------------------------------
# Vues dont le type n'existe plus dans Odoo 19.
#
# La plateforme d'upgrade laisse passer deux vues Studio de type « dashboard »
# (v15, web_dashboard) : le type a disparu de la sélection de ir.ui.view.type,
# mais la valeur reste en base. Le nettoyage automatique d'Odoo — ondelete
# « set null » sur les valeurs de sélection retirées — ne joue que pour le
# module qui déclarait la valeur ; ici plus aucun module ne la déclare, donc
# personne ne nettoie.
#
# Côté client, le champ « Type » de Paramètres → Technique → Vues cherche le
# libellé de la valeur, ne le trouve pas et lit `undefined[1]` : la liste ne
# s'affiche plus (« An error occured in the owl lifecycle », remonté en
# production le 24/08/2026). Archiver ne suffit pas — la liste replante dès
# qu'on coche « Archivé », et le formulaire de la vue aussi.
#
# La suppression est sans regret : aucun moteur de rendu ne connaît plus ce
# type, et rien ne les référence (héritage, action, vue de recherche). Le
# périmètre est DÉRIVÉ de la sélection courante du champ, pas listé : un type
# retiré par une version ultérieure sera couvert sans que personne y pense.
#
# Idempotent : la recherche ne renvoie rien une fois le ménage fait.
# ---------------------------------------------------------------------------
def _delete_views_with_unknown_type(env):
    View = env['ir.ui.view']
    known_types = View._fields['type'].get_values(env)
    views = View.with_context(
        active_test=False,
        # cascade sur les vues héritées, comme le fait la désinstallation d'un
        # module : une vue fille d'un type mort ne survivrait à rien.
        _force_unlink=True,
    ).search([('type', 'not in', known_types)])
    if not views:
        return
    _logger.info(
        "cadiffusion_base: %s vue(s) d'un type inconnu en v19 supprimée(s) : %s",
        len(views),
        ', '.join('%s (%s, %s)' % (view.name, view.model, view.type)
                  for view in views))
    views.unlink()


# ---------------------------------------------------------------------------
# Instantané de référence de la configuration : voir reference_state.py.
# Rejoué par data/reference_state.xml à chaque install et à chaque -u du
# module (avant nos vues), puis par le post_init_hook en fin d'install.
# ---------------------------------------------------------------------------


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
