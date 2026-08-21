import csv
import logging
import os
import re

from odoo.modules.module import get_module_path
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
    _archive_post_upgrade_studio_views(env)
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
# Instantané de référence de la configuration.
#
# La base de recette — celle que le client a validée fonctionnalité par
# fonctionnalité — fait référence. data/build_reference_state.py en tire un CSV
# par modèle listé ci-dessous ; ils sont rejoués à chaque install et à chaque
# upgrade, donc à chaque remigration à blanc du staging comme à la bascule de
# production.
#
# Le problème qu'ils résolvent : une migration neuve repart des données de
# production et perd tout ce qui avait été réglé pendant la recette (vues
# désactivées par la plateforme d'upgrade, réglages posés à la main, rapports
# réaffectés…). Il y a trop de fonctionnalités pour les repasser une à une, et
# rien dans Odoo ne signale qu'un réglage est retombé : la personnalisation est
# simplement muette. Un ``-u`` n'y change rien — un ``<record>`` n'écrit que
# les champs qu'il déclare.
#
# Deux modes, et la distinction est délibérée :
#
#   APPLY  — réappliqué automatiquement. Réservé à ce dont la recette est la
#            seule source légitime (état actif des vues, cibles des rapports,
#            réglages que ce module possède déjà).
#   REPORT — comparé et signalé, jamais écrit. Tout ce dont la production peut
#            légitimement différer : modules installés, paramètres système,
#            filtres, actions. Écraser ces valeurs depuis un instantané de
#            staging casserait la production.
#
# Ajouter une couverture = ajouter une ligne ici, puis régénérer l'instantané.
# Le hook, data/check_post_build.py et les tests suivent automatiquement.
# ---------------------------------------------------------------------------
_APPLY = 'apply'
_REPORT = 'report'

# (nom du CSV, modèle, clé, champs comparés, mode)
# La clé est 'xmlid', un nom de champ, ou un tuple de champs.
_REFERENCE_SPECS = (
    ('views', 'ir.ui.view', 'xmlid', ('active',), _APPLY),
    ('reports', 'ir.actions.report', 'xmlid', ('report_name',), _APPLY),
    ('picking_types', 'stock.picking.type', 'xmlid', ('barcode', 'active'), _APPLY),
    ('companies', 'res.company', 'name',
     ('active', 'stock_move_email_validation'), _APPLY),
    ('modules', 'ir.module.module', 'name', ('state',), _REPORT),
    ('config_parameters', 'ir.config_parameter', 'key', ('value',), _REPORT),
)
# Volontairement absents : ir.actions.act_window et ir.filters. Testés le
# 20/08/2026 contre staging, ils n'ont produit que du bruit — dérive du contexte
# des actions du core entre deux versions d'Odoo, et copies personnelles de
# filtres datées. Une ligne ici les rétablit si un besoin apparaît.

# Valeurs de paramètres système jamais recopiées dans le dépôt : identifiants
# de base, jetons d'API, secrets. Seule leur PRÉSENCE est comparée.
_MASKED_PARAM_HINTS = ('token', 'key', 'secret', 'password', 'uuid', 'dbuuid')
# Le nom de la clé ne suffit pas : une URL de webhook porte son secret dans son
# chemin (la connaître suffit à poster dessus), sans qu'aucun mot ne l'annonce.
# On masque donc aussi sur la valeur.
_MASKED_VALUE_PATTERN = re.compile(r'https?://\S*/[0-9A-Za-z_-]{16,}')
_MASKED = '<masqué>'

# Pendant sa propre migration, le module mis à jour et ses dépendants sont en
# 'to upgrade' / 'to install'. Sans cette normalisation, chaque build signalerait
# un écart de configuration qui n'en est pas un.
_TRANSIENT_MODULE_STATES = {'to upgrade': 'installed', 'to install': 'installed'}


# Écarts connus et assumés, documentés ici plutôt que resignalés à chaque
# build. Clé : (nom du spec, clé de l'enregistrement).
_ACCEPTED_DIFFERENCES = {
    ('modules', 'l10n_fr_pdp'):
        "auto_install arrivé dans Odoo après la recette (réforme française "
        "PDP). Vérifié inerte sur staging le 20/08/2026 : aucun "
        "account_edi_proxy_client.user, donc _get_peppol_proxy_type() renvoie "
        "'peppol' et jamais 'pdp' — les mentions obligatoires BR-FR-05 ne sont "
        "pas ajoutées au XML CII, les méthodes d'envoi par défaut ne changent "
        "pas, les trois crons sont inactifs. Le module ne s'active qu'à "
        "l'inscription volontaire d'une société auprès d'un PDP.",
    ('modules', 'l10n_be_coda_extension_number'):
        "auto_install sur l10n_be_coda, installé pour EUROCONTACT (société "
        "belge). Aucun journal n'utilise le numéro d'extension.",
    ('modules', 'l10n_be_reports_vat_comment'):
        "auto_install sur l10n_be_reports (société belge EUROCONTACT).",
}


# Vues suivies : celles que livre ce dépôt (addons_project / addons_oca /
# addons_tier) et les vues Studio. Le core d'Odoo est volontairement exclu :
# ses 3 637 vues sont identiques d'une base à l'autre à version égale, et parmi
# celles qu'il livre archivées se trouvent les options de thème du site web
# (website.header_*, website.footer_*) dont l'état EST la configuration du
# site — l'aligner depuis un instantané écraserait un choix de production.
#
# Les rares vues du core à forcer sont déclarées une par une, avec leur raison,
# dans data/core_view_activation.xml et data/fix_stale_data.xml.
#
# Le périmètre est DÉRIVÉ du chemin des modules, pas listé : un module ajouté
# au dépôt est couvert sans que personne ait à y penser.
def _repo_modules(env):
    root = os.path.dirname(os.path.dirname(get_module_path('cadiffusion_base')))
    modules = {'studio_customization'}
    for module in env['ir.module.module'].search([('state', '=', 'installed')]):
        path = get_module_path(module.name)
        if path and os.path.realpath(path).startswith(os.path.realpath(root)):
            modules.add(module.name)
    return modules


def _reference_path(name):
    return 'cadiffusion_base/data/reference_%s.csv' % name


def _reference_value(value):
    """Sérialisation texte d'une valeur de champ, stable d'une base à l'autre.

    Les many2one sortent par leur nom, jamais par leur id : les ids sont
    recréés à chaque passage de la plateforme d'upgrade.
    """
    if hasattr(value, '_name'):
        return value.display_name or ''
    return str(value)


def _record_key(record, key):
    if isinstance(key, tuple):
        return '|'.join(_reference_value(record[field]) for field in key)
    return _reference_value(record[key])


def _reference_snapshot(env, model, key, fields):
    """{clé: {champ: texte}} de la base courante, pour un spec donné."""
    records = env[model].with_context(active_test=False).search([])
    followed_modules = _repo_modules(env) if model == 'ir.ui.view' else None
    if key == 'xmlid':
        env.cr.execute("""
            SELECT res_id, module || '.' || name FROM ir_model_data
             WHERE model = %s
        """, (model,))
        keys = dict(env.cr.fetchall())
    else:
        keys = {record.id: _record_key(record, key) for record in records}
    snapshot = {}
    for record in records:
        identifier = keys.get(record.id)
        if not identifier:
            # Enregistrement sans xmlid (créé à la main, ou par Studio) : pas
            # de clé stable entre deux bases, on ne le compare pas.
            continue
        if followed_modules is not None and \
                identifier.split('.')[0] not in followed_modules:
            continue
        values = {field: _reference_value(record[field]) for field in fields}
        if model == 'ir.module.module':
            values['state'] = _TRANSIENT_MODULE_STATES.get(
                values['state'], values['state'])
            # Les ~1 270 modules disponibles mais non installés ne disent rien
            # et pèseraient pour rien dans le dépôt : l'écart qui compte est
            # « installé en recette, absent ici ».
            if values['state'] != 'installed':
                continue
        if model == 'ir.config_parameter' and (
                any(hint in identifier.lower() for hint in _MASKED_PARAM_HINTS)
                or any(_MASKED_VALUE_PATTERN.search(value)
                       for value in values.values())):
            values = dict.fromkeys(values, _MASKED)
        snapshot[identifier] = values
    return snapshot


def _reference_diff(env, spec):
    """(écarts, absents ici, en plus ici) — n'écrit rien.

    Partagée avec data/check_post_build.py et les tests, qui doivent rester en
    lecture seule.
    """
    name, model, key, fields, __ = spec
    if model not in env:
        return [], [], []
    with file_open(_reference_path(name)) as csvfile:
        reference = {row['_key']: {field: row[field] for field in fields}
                     for row in csv.DictReader(csvfile)}
    current = _reference_snapshot(env, model, key, fields)
    differences = []
    for identifier, expected in reference.items():
        found = current.get(identifier)
        if found is None or (name, identifier) in _ACCEPTED_DIFFERENCES:
            continue
        for field in fields:
            if expected[field] == _MASKED or expected[field] == found[field]:
                continue
            differences.append((identifier, field, expected[field], found[field]))
    missing = sorted(set(reference) - set(current))
    extra = sorted(identifier for identifier in set(current) - set(reference)
                   if (name, identifier) not in _ACCEPTED_DIFFERENCES)
    return differences, missing, extra


def _apply_reference_state(env, only=None):
    """Réapplique les specs APPLY, signale les specs REPORT.

    ``only`` restreint aux specs nommés. L'état des vues est aligné en
    pre-migrate, avant le chargement des fichiers data : une de nos vues peut
    cibler un champ apporté par la vue d'un autre module, et un xpath ne résout
    que si cette vue-là est active. L'ordre du chargeur est pre-migrate →
    import du module → data → post-migrate.
    """
    for spec in _REFERENCE_SPECS:
        name, model, key, fields, mode = spec
        if only and name not in only:
            continue
        differences, missing, extra = _reference_diff(env, spec)
        if mode == _REPORT:
            if differences:
                _logger.warning(
                    "cadiffusion_base: %s écart(s) de configuration sur %s "
                    "(signalés, non corrigés) : %s", len(differences), model,
                    ['%s.%s : %s ≠ %s' % diff for diff in differences[:20]])
            if missing:
                _logger.warning(
                    "cadiffusion_base: %s enregistrement(s) %s présents en "
                    "recette et absents ici : %s", len(missing), model,
                    missing[:20])
            if extra:
                _logger.info(
                    "cadiffusion_base: %s enregistrement(s) %s présents ici et "
                    "absents de la recette : %s", len(extra), model, extra[:20])
            continue
        _apply_reference_differences(env, model, key, differences)
        if missing:
            _logger.info(
                "cadiffusion_base: %s enregistrement(s) %s de la recette "
                "absents ici (rien à appliquer)", len(missing), model)


def _apply_reference_differences(env, model, key, differences):
    if not differences:
        return
    identifiers = {identifier for identifier, __, __, __ in differences}
    if key == 'xmlid':
        records = {identifier: env.ref(identifier, raise_if_not_found=False)
                   for identifier in identifiers}
    else:
        found = env[model].with_context(active_test=False).search([])
        records = {_record_key(record, key): record for record in found}
    applied = 0
    for identifier, field, expected, current in differences:
        record = records.get(identifier)
        if not record:
            continue
        # Sous savepoint : un enregistrement devenu incohérent (vue dont le
        # xpath ne matche plus, contrainte métier) ne doit pas faire échouer
        # l'install ou l'upgrade.
        try:
            with env.cr.savepoint():
                record.write({field: _reference_write_value(record, field, expected)})
            applied += 1
            _logger.info(
                "cadiffusion_base: %s.%s remis à %r (était %r) d'après la "
                "recette", identifier, field, expected, current)
        except Exception:
            _logger.warning(
                "cadiffusion_base: %s.%s non applicable, laissé à %r",
                identifier, field, current, exc_info=True)
    _logger.info(
        "cadiffusion_base: %s — %s valeur(s) alignée(s) sur la recette "
        "(%s écart(s) relevé(s))", model, applied, len(differences))


def _reference_write_value(record, field, raw):
    """Retour du texte du CSV vers le type du champ (specs APPLY : scalaires)."""
    kind = record._fields[field].type
    if kind == 'boolean':
        return raw == 'True'
    if kind == 'integer':
        return int(raw or 0)
    if kind == 'float':
        return float(raw or 0)
    return raw if raw not in ('False', '') else False


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
