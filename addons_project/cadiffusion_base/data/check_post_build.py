#!/usr/bin/env python3
"""Contrôle de conformité post-build (test / staging / production).

Outil de développement — PAS chargé par Odoo (absent du manifest et des
imports), au même titre que build_carton_uom_v15.py.

Rejoue EN LECTURE SEULE les post-conditions de tout ce que cadiffusion_base
réaffirme à l'install ou à l'upgrade (post_init_hook, migrations/, data/
fix_stale_data.xml et core_view_activation.xml) et signale ce qui a dérivé.
Aucune écriture, aucun commit.

Raison d'être : ces réaffirmations ne s'exécutent qu'AU MOMENT de l'install ou
de l'upgrade du module. Entre deux builds, plus rien ne relit l'état — un
réglage remis à zéro par la plateforme d'upgrade, un `-u` qui n'a pas eu lieu
ou une migration passée sans effet ne se voient nulle part. Ce script rend la
vérification reproductible au lieu de la laisser à l'œil humain.

Usage (odoo shell, script sur stdin) :

  local :
    docker exec -i odoo19 odoo shell -c /etc/odoo/odoo.conf --no-http \
      --addons-path=/mnt/enterprise,/mnt/extra-addons,/mnt/shared-addons,\
/mnt/extra-addons/cadiffusionV19/addons_project,\
/mnt/extra-addons/cadiffusionV19/addons_oca,\
/mnt/extra-addons/cadiffusionV19/addons_tier \
      -d cadiffusion_test \
      < addons_project/cadiffusion_base/data/check_post_build.py

  Odoo.sh (shell du build) :
    odoo-bin shell -d $PGDATABASE < check_post_build.py

Sortie : une ligne par contrôle (OK / KO / ??), puis un récapitulatif.
  OK — l'état attendu est en place
  KO — dérive : à corriger (upgrade du module, ou écriture manuelle)
  ?? — contrôle non concluant (donnée absente de cette base) : à regarder

Ajouter un contrôle = ajouter une fonction _check_xxx(env) et l'appeler dans
CHECKS. Chaque nouveau réglage « posé à la main » repéré sur une base doit
arriver ici en même temps que dans _apply_manual_settings_from_test_base.
"""
import csv

from odoo.modules.module import get_manifest
from odoo.tools import file_open

# Source unique des attentes : les constantes et les fonctions de diff
# utilisées par le post_init_hook et les scripts de migrations/. Rien n'est
# redéfini ici, donc rien ne peut diverger.
from odoo.addons.cadiffusion_base import (
    _APPLY,
    _PICKING_TYPE_BARCODES,
    _REFERENCE_SPECS,
    _reference_diff,
    _unece_categ_for_tax_name,
)

RESULTS = []


def add(status, label, expected, actual):
    RESULTS.append((status, label, str(expected), str(actual)))


def check(label, expected, actual):
    add('OK' if expected == actual else 'KO', label, expected, actual)


def unknown(label, why):
    add('??', label, '-', why)


def scalar(env, query, params=None):
    # psycopg interprète les % de la requête dès qu'un tuple de paramètres est
    # fourni, même vide : les LIKE '%...%' cassent. On n'en passe donc que s'il
    # y en a vraiment.
    env.cr.execute(query, params) if params else env.cr.execute(query)
    row = env.cr.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Module lui-même : sans upgrade effectif, aucun des contrôles suivants n'a de
# sens — c'est la première chose à regarder quand un réglage « censé être posé »
# ne l'est pas.
# ---------------------------------------------------------------------------
def _check_module(env):
    module = env['ir.module.module'].search([('name', '=', 'cadiffusion_base')])
    if not module:
        return unknown("cadiffusion_base installé", "module absent de la base")
    check("cadiffusion_base installé", 'installed', module.state)
    check("cadiffusion_base à la version du code",
          get_manifest('cadiffusion_base')['version'], module.latest_version)


# ---------------------------------------------------------------------------
# post_init_hook / migrations 19.0.1.0.1 → .20
# ---------------------------------------------------------------------------
_OBSOLETE_COMPANIES = ('ACES', 'PERSO', 'INNOVIA', 'ARKHE', 'SCI START')


def _check_companies(env):
    still_active = env['res.company'].search([
        ('name', 'in', _OBSOLETE_COMPANIES), ('active', '=', True)])
    check("sociétés obsolètes archivées (.1)", [], still_active.mapped('name'))


def _check_manual_settings(env):
    """.20 — réglages posés à la main sur la base de test, que la plateforme
    d'upgrade ne rapporte pas de la production."""
    company = env.ref('base.main_company', raise_if_not_found=False)
    if not company:
        unknown("base.main_company", "xmlid absent")
    else:
        check("confirmation e-mail des mouvements de stock (%s)" % company.name,
              True, company.stock_move_email_validation)
    for xmlid, barcode in _PICKING_TYPE_BARCODES:
        picking_type = env.ref(xmlid, raise_if_not_found=False)
        if not picking_type:
            unknown("code-barres %s" % xmlid, "xmlid absent")
        else:
            check("code-barres %s" % xmlid, barcode, picking_type.barcode)


def _check_uom_factors(env):
    """.14 / _repair_upgrade_data — une UDM sans facteur renvoie 0 à toute
    conversion (colis des BL, prix à la pièce, quantités MRP)."""
    check("UDM sans facteur", 0,
          scalar(env, "SELECT count(*) FROM uom_uom WHERE factor IS NULL"))


def _check_filters(env):
    """.10 — price_reduce supprimé en v19."""
    check("filtres triant sur price_reduce", 0, scalar(env, """
        SELECT count(*) FROM ir_filters
         WHERE sort ILIKE '%price_reduce%'
           AND sort NOT ILIKE '%price_reduce_taxexcl%'
    """))


def _check_article_cmd(env):
    """.7 — copie x_studio_article_cmd → article_cmd."""
    if not scalar(env, """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'sale_order_line'
           AND column_name = 'x_studio_article_cmd'
    """):
        return add('OK', "reprise de x_studio_article_cmd", 'sans objet',
                   'colonne Studio absente')
    check("lignes de vente sans article_cmd repris", 0, scalar(env, """
        SELECT count(*) FROM sale_order_line
         WHERE (article_cmd IS NULL OR article_cmd = '')
           AND x_studio_article_cmd IS NOT NULL
           AND x_studio_article_cmd != ''
    """))


# ---------------------------------------------------------------------------
# Vues
# ---------------------------------------------------------------------------
_FORCED_ACTIVE_VIEWS = (
    # data/core_view_activation.xml — bouton « Retour » du transfert
    'stock_account.view_picking_form',
    # data/fix_stale_data.xml — champs transmit method sur le partenaire
    'account_invoice_transmit_method.view_partner_property_form',
)


def _check_forced_views(env):
    for xmlid in _FORCED_ACTIVE_VIEWS:
        view = env.ref(xmlid, raise_if_not_found=False)
        if not view:
            unknown("vue %s active" % xmlid, "xmlid absent")
        else:
            check("vue %s active" % xmlid, True, view.active)


def _check_studio_views(env):
    """.3 / .8 / .9 / _archive_post_upgrade_studio_views — le contenu Studio est
    repris en XML : les deux jeux ne doivent pas se superposer."""
    env.cr.execute("""
        SELECT v.id, v.name FROM ir_ui_view v
          JOIN ir_model_data d ON d.res_id = v.id
         WHERE d.model = 'ir.ui.view' AND d.module = 'studio_customization'
           AND v.active
    """)
    rows = env.cr.fetchall()
    check("vues Studio encore actives", [], [name for __, name in rows])


def _check_reference(env):
    """Diff avec l'instantané de la base de recette (data/reference_*.csv,
    régénérables par data/build_reference_state.py).

    Les specs APPLY sont ce que le hook réapplique tout seul : un écart y est
    un KO, il aurait dû être corrigé. Les specs REPORT ne sont jamais écrites —
    un écart y est à trancher, pas une anomalie en soi.
    """
    for spec in _REFERENCE_SPECS:
        name, model, key, fields, mode = spec
        differences, missing, extra = _reference_diff(env, spec)
        detail = ['%s.%s : %s ≠ %s' % difference
                  for difference in differences[:12]]
        if len(differences) > 12:
            detail.append('… et %s autres' % (len(differences) - 12))
        if mode == _APPLY:
            check("recette — %s" % name, [], detail)
        elif differences:
            unknown("recette — %s" % name,
                    "%s écart(s) à trancher : %s" % (len(differences), detail))
        else:
            add('OK', "recette — %s" % name, [], [])
        if missing:
            unknown("recette — %s absents ici" % name,
                    "%s : %s" % (len(missing), missing[:8]))
        if extra and mode == _REPORT:
            unknown("recette — %s en plus ici" % name,
                    "%s : %s" % (len(extra), extra[:8]))


def _check_chorus_view_chain(env):
    """Les conditions Chorus (view_res_partner_chorus_conditions) ne
    s'appliquent que si TOUTE la chaîne d'héritage est active : une vue parente
    archivée désactive silencieusement la fille."""
    chain = ('l10n_fr_chorus_account.view_partner_form',
             'cadiffusion_base.view_res_partner_chorus_conditions')
    for xmlid in chain:
        view = env.ref(xmlid, raise_if_not_found=False)
        if not view:
            unknown("chaîne Chorus : %s" % xmlid, "xmlid absent")
        else:
            check("chaîne Chorus : %s active" % xmlid, True, view.active)


# ---------------------------------------------------------------------------
# Rapports
# ---------------------------------------------------------------------------
_KEPT_STUDIO_REPORTS = (
    ('studio_customization.factures_sans_paieme_'
     'ef6af8d0-5ebc-472e-9d25-22d565f71397',
     'report_cadiffusion.report_invoice_autre'),
    ('studio_customization.pieces_comptables_ra_'
     'f16b32c4-f6ea-4d4e-bc8a-d341f6a3a987',
     'report_cadiffusion.report_invoice_tcare'),
)


def _check_reports(env):
    """.2 / .4 / .5 / .6 — les rapports Studio pointent vers nos templates et
    ne s'affichent plus dans le menu Imprimer."""
    for xmlid, report_name in _KEPT_STUDIO_REPORTS:
        report = env.ref(xmlid, raise_if_not_found=False)
        if not report:
            unknown("rapport %s" % xmlid.split('.')[-1][:24], "xmlid absent")
        else:
            check("rapport %s redirigé" % xmlid.split('.')[-1][:24],
                  report_name, report.report_name)
    check("rapports account.move pointant encore sur le template Studio", 0,
          scalar(env, """
        SELECT count(*) FROM ir_act_report_xml
         WHERE model = 'account.move'
           AND report_name LIKE '%studio_report_docume_a5c6eec8%'
    """))
    check("rapports Studio encore proposés dans « Imprimer »", 0, scalar(env, """
        SELECT count(*) FROM ir_act_report_xml r
          JOIN ir_model_data d ON d.res_id = r.id
         WHERE d.model = 'ir.actions.report' AND d.module = 'studio_customization'
           AND r.model = 'account.move' AND r.binding_model_id IS NOT NULL
    """))


def _check_footer_param(env):
    """data/fix_stale_data.xml — répétition du numéro de facture en pied de
    page. Le contrôle d'Odoo est `if get_param(...)` : seule la chaîne vide
    désactive (« 0 » ou « False » sont vrais)."""
    # Pas get_param : il renvoie son défaut sur une valeur vide (`or default`),
    # ce qui rend la chaîne vide attendue indistinguable d'un paramètre absent.
    param = env['ir.config_parameter'].sudo().search(
        [('key', '=', 'account.display_name_in_footer')])
    if not param:
        return unknown("numéro de facture répété en pied de page",
                       "paramètre absent (défaut d'Odoo : activé)")
    check("numéro de facture répété en pied de page (désactivé)",
          '', param.value or '')


# ---------------------------------------------------------------------------
# Taxes UNECE — sans unece_type_code, generate_facturx_xml n'émet aucun bloc
# ApplicableTradeTax d'en-tête : XML invalide contre le XSD CII, envoi Chorus
# impossible. Mais une catégorie FAUSSE est pire qu'absente : elle passe la
# validation XSD en déclarant un régime de TVA qui n'est pas celui de la
# facture (exonération au lieu d'export ou de livraison intracommunautaire).
# ---------------------------------------------------------------------------
def _check_unece_taxes(env):
    """Sans code UNECE, generate_facturx_xml n'émet aucun bloc
    ApplicableTradeTax d'en-tête → XML invalide contre le XSD CII. Une
    catégorie FAUSSE est pire : le XML passe la validation en déclarant un
    régime de TVA qui n'est pas celui de la facture."""
    taxes = env['account.tax'].with_context(active_test=False).search([
        ('type_tax_use', '=', 'sale'), ('amount', '=', 0)])
    mislabelled, exo_without_code, undecided, not_durable = [], [], [], []
    for tax in taxes:
        label = "%s « %s » (%s)" % (tax.id, tax.name, tax.company_id.name)
        # unece_*_code est un related stocké : une colonne remplie sans son
        # many2one source retombera à vide au premier recalcul.
        if (tax.unece_type_code and not tax.unece_type_id) or \
                (tax.unece_categ_code and not tax.unece_categ_id):
            not_durable.append(label)
        expected = _unece_categ_for_tax_name(tax.name)
        if not expected:
            continue
        current = tax.unece_categ_id.code
        if current == expected and tax.unece_type_id.code == 'VAT':
            continue
        if current == 'E':
            # Séquelle de la première version de _configure_unece_exo_taxes
            # (ilike « EXO », qui matche par sous-séquence en v19).
            mislabelled.append("%s : E au lieu de %s" % (label, expected))
        elif not current:
            (exo_without_code if expected == 'E' else undecided).append(label)
        # Tout autre code posé (AE = autoliquidation…) est un choix assumé.
    check("codes UNECE non durables (colonne remplie, m2o vide)", [], not_durable)
    check("taxes export/intracom marquées « exonéré » (séquelle du ilike)",
          [], mislabelled)
    check("taxes « EXO » de vente sans code UNECE", [], exo_without_code)
    if undecided:
        unknown("taxes export/intracom sans code UNECE",
                "%s taxes, à trancher avec la comptabilité : %s"
                % (len(undecided), ', '.join(sorted(
                    {tax.split('«')[1].split('»')[0].strip()
                     for tax in undecided}))))
    else:
        add('OK', "taxes export/intracom sans code UNECE", [], [])


CHECKS = (
    _check_module,
    _check_companies,
    _check_manual_settings,
    _check_uom_factors,
    _check_filters,
    _check_article_cmd,
    _check_forced_views,
    _check_studio_views,
    _check_reference,
    _check_chorus_view_chain,
    _check_reports,
    _check_footer_param,
    _check_unece_taxes,
)


def run(env):
    for checker in CHECKS:
        try:
            checker(env)
        except Exception as error:                      # noqa: BLE001
            unknown(checker.__name__, "erreur : %s" % error)
    width = max(len(label) for __, label, __, __ in RESULTS)
    print("\n=== Conformité post-build — base %s ===\n" % env.cr.dbname)
    for status, label, expected, actual in RESULTS:
        print("[%s] %-*s  attendu %-22s constaté %s"
              % (status, width, label, expected, actual))
    counts = {status: sum(1 for r in RESULTS if r[0] == status)
              for status in ('OK', 'KO', '??')}
    print("\n%(OK)s OK — %(KO)s KO — %(??)s à vérifier\n" % counts)
    return counts['KO']


run(env)  # noqa: F821  (fourni par odoo shell)
