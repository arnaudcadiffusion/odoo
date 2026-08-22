"""Instantané de référence de la configuration : prise, comparaison, rejeu.

Ces fonctions vivent ici, hors de ``__init__.py``, pour être importables par
``models/reference_state.py`` — le modèle abstrait que
``data/reference_state.xml`` appelle via ``<function>`` à chaque install et à
chaque ``-u`` du module. Importées depuis ``__init__.py``, qui charge
``models`` avant de définir quoi que ce soit, elles feraient un import
circulaire. ``__init__.py`` les réexporte : les scripts de migrations/, les
tests et les outils de data/ continuent d'écrire
``from odoo.addons.cadiffusion_base import _apply_reference_state``.
"""
import csv
import logging
import os
import re

from odoo.modules.module import get_module_path
from odoo.tools import file_open

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Instantané de référence de la configuration.
#
# La base de recette — celle que le client a validée fonctionnalité par
# fonctionnalité — fait référence. data/build_reference_state.py en tire un CSV
# par modèle listé ci-dessous ; ils sont rejoués à chaque install et à chaque
# ``-u`` du module (data/reference_state.xml, puis le post_init_hook en fin
# d'install), donc à chaque remigration à blanc du staging comme à la
# bascule de production.
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

# Paramètres propres à chaque base par nature — jamais comparés ni pris dans
# l'instantané : ils diffèrent entre la recette, un staging remigré et la
# production sans que rien n'ait dérivé, et resignaleraient six « écarts » à
# chaque build (publisher_warranty.cloc y déverse en plus un JSON entier).
_VOLATILE_PARAMS = (
    'calendar_sms.last_sms_cron',
    'database.create_date',
    'database.expiration_date',
    'database.expiration_reason',
    'database.is_neutralized',
    'mail.catchall.domain',
    'publisher_warranty.cloc',
    'upgrade.start.time',
    'web.base.url',
)

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
        # Sans avertissement : studio_customization est un pseudo-module que
        # web_studio inscrit dans ir_module_module sans code sur disque, et
        # get_module_path logguerait « manifest not found » à chaque rejeu.
        path = get_module_path(module.name, display_warning=False)
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


def _is_volatile(model, identifier):
    return model == 'ir.config_parameter' and identifier in _VOLATILE_PARAMS


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
        if _is_volatile(model, identifier):
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
        # Le filtre vaut aussi pour un CSV antérieur à _VOLATILE_PARAMS.
        reference = {row['_key']: {field: row[field] for field in fields}
                     for row in csv.DictReader(csvfile)
                     if not _is_volatile(model, row['_key'])}
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
        value = _reference_write_value(record, field, expected)
        # Sous savepoint : un enregistrement devenu incohérent (vue dont le
        # xpath ne matche plus, contrainte métier) ne doit pas faire échouer
        # l'install ou l'upgrade.
        try:
            with env.cr.savepoint():
                if model == 'ir.ui.view' and field == 'active' and not value:
                    _archive_view(record)
                else:
                    record.write({field: value})
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


def _archive_view(view):
    """Archive une vue sans passer par write().

    Depuis la 19, ``ir.ui.view.write`` revalide l'arch dès que ``active``
    change — archivage compris (base/models/ir_ui_view.py, ``write``). Or une
    vue Studio v15 devenue invalide en v19 (attribut ``modifiers``,
    ``quick_add`` du calendrier…) est précisément celle qu'il faut archiver :
    Odoo ne valide que les vues custom ACTIVES, archivée elle sort du radar.
    Constaté sur le build 36768993 du 21/08/2026 : le rejeu relevait les
    écarts mais write() refusait quatre des cinq vues, qui ressortaient en
    « invalid custom view(s) ». Même voie SQL que _migrate_19_0_1_0_3 ; les
    caches que write() purge le sont aussi.
    """
    view.env.cr.execute(
        "UPDATE ir_ui_view SET active = false WHERE id = %s", (view.id,))
    view.invalidate_recordset(['active'])
    view.env.registry.clear_cache()
    view.env.registry.clear_cache('templates')


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
