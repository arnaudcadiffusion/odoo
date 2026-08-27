"""Renommage réversible des champs Studio : ``x_studio_*`` → ``ca_diff_*``.

Le préfixe ``x_studio_`` est un vestige : ces champs ne sont plus des champs
Studio, ils sont déclarés en Python dans ``addons_project/``. Les renommer est
purement cosmétique et touche 129 champs sur 18 modèles — donc autant de
colonnes SQL, plus tout ce qui désigne un champ **par son nom** ailleurs qu'en
Python : filtres favoris, exports Excel enregistrés, domaines d'actions,
arch des vues, code des actions serveur, feuilles de calcul.

D'où ce module : **une seule table de correspondance** (``data/field_rename_map.csv``,
produite par ``data/build_field_rename_map.py``) rejouée dans les deux sens, et
un **journal en base** (``cadiffusion_field_rename``) écrit pendant l'opération
pour que le retour arrière inverse exactement ce qui a été fait — y compris
après un renommage partiel ou interrompu.

Rien ici n'est appelé automatiquement : ni le manifest, ni ``__init__.py``, ni
un script de ``migrations/`` ne déclenche le renommage. Tant qu'aucune
migration ne l'appelle, ce fichier est de l'outillage dormant.

--------------------------------------------------------------------------
Aller — dans cet ordre, jamais l'inverse
--------------------------------------------------------------------------

1. Sources (poste de dev, sur une branche dédiée) ::

       python3 data/rename_source_fields.py            # x_studio_ → ca_diff_
       git diff                                        # relecture
       git commit

2. Base, via un script de migration ``pre-migrate.py`` de la version qui
   embarque le commit ci-dessus ::

       from odoo.addons.cadiffusion_base import _apply_field_rename

       def migrate(cr, version):
           _apply_field_rename(cr)

   Le pre-migrate est obligatoire : à l'``-u``, l'ORM voit des champs
   ``ca_diff_*`` inconnus de la base et crée des colonnes VIDES à côté des
   ``x_studio_*``, sans jamais recopier les données. Le renommage doit être
   fait AVANT que le registre ne se recharge.

--------------------------------------------------------------------------
Retour — dans cet ordre, jamais l'inverse
--------------------------------------------------------------------------

1. Base d'abord, avec le code encore en ``ca_diff_*`` ::

       odoo shell -d LA_BASE
       >>> from odoo.addons.cadiffusion_base import _rollback_field_rename
       >>> _rollback_field_rename(env.cr)
       >>> env.cr.commit()

2. Sources ensuite ::

       python3 data/rename_source_fields.py --rollback
       git revert <commit>     # ou, si le commit n'est pas encore poussé

3. ``-u cadiffusion_base`` pour recharger le registre sur les anciens noms.

Le rollback lit le journal, pas la table de correspondance : il ne défait que
ce qui a réellement été appliqué, et il est sans effet (silencieux) si rien
n'a été renommé. Il reste possible tant que la table de journal existe, donc
indéfiniment — contrairement à une restauration de dump, il ne perd aucune
donnée saisie depuis le renommage.

--------------------------------------------------------------------------
Ce que le renommage NE couvre pas
--------------------------------------------------------------------------

* Les intégrations extérieures qui appellent Odoo par XML-RPC / JSON-RPC avec
  les noms techniques, et les modèles d'import Excel dont les en-têtes portent
  ces noms. Rien en base ne les liste : à recenser à la main avant la bascule.
* Les valeurs de suivi déjà écrites (``mail_tracking_value``) pointent le champ
  par sa clé étrangère : elles suivent le renommage sans intervention.
* Un champ resté ``state = 'manual'`` en base (relique Studio non reprise par
  le code) est signalé et renommé, mais Odoo interdit à un champ manuel de ne
  pas commencer par ``x_`` : le journal le marque pour que ce soit visible.
"""
import csv
import json
import logging
import os
import re

_logger = logging.getLogger(__name__)

OLD_PREFIX = 'x_studio_'
NEW_PREFIX = 'ca_diff_'

JOURNAL_TABLE = 'cadiffusion_field_rename'

# Le renommage se fait par lots plutôt qu'en une fois : un lot se relit, se
# vérifie et se défait ; 129 champs d'un coup, non. Chaque fonction accepte un
# ``only`` — un ensemble d'anciens noms — qui restreint aussi bien la réécriture
# des sources que celle de la base. Sans ``only``, tout le CSV est traité.
#
# Premier lot : les champs de transport et de préparation des BL et des OF,
# ceux qui viennent de recevoir copy=False (task#17998). Ils forment un groupe
# fonctionnel cohérent et ne sont cités par aucun script de migrations/.
TRANSPORT_BATCH = (
    'x_studio_transport',
    'x_studio_nb_palette',
    'x_studio_nb_palette_euro',
    'x_studio_premium_xpo',
    'x_studio_bl_groupe',
    'x_studio_id_bl_groupe',
    'x_studio_nb_bl_groupe',
    'x_studio_dpd_nb_colis',
    'x_studio_cout_transport',
    'x_studio_erreur_preparation',
    'x_studio_preparateur_kit',
    'x_studio_prparateur',
    'x_studio_impression_bl',
    'x_studio_impression_mo',
)

# Les six champs de tender.order déclarés par public_tender. Ce module se
# charge AVANT cadiffusion_base (qui en dépend) : ces champs doivent être
# renommés par un pre-migrate de public_tender, sinon son _auto_init crée des
# colonnes ca_diff_* vides avant que le script de cadiffusion_base ne passe.
TENDER_BATCH = (
    'x_studio_dbut_de_march',
    'x_studio_coordinateur',
    'x_studio_contact',
    'x_studio_tlphone',
    'x_studio_email',
    'x_studio_notes_march',
)

_MAP_FILE = 'cadiffusion_base/data/field_rename_map.csv'

# ``data/rename_source_fields.py`` s'exécute hors conteneur, sans Odoo dans le
# PYTHONPATH ; le repli relatif lui suffit puisqu'il ne touche qu'aux fichiers.
try:
    from odoo.tools import file_open
except ImportError:  # pragma: no cover - hors Odoo
    file_open = None


# ---------------------------------------------------------------------------
# Table de correspondance
# ---------------------------------------------------------------------------
def _open_map():
    if file_open is not None:
        return file_open(_MAP_FILE, 'r')
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'data', 'field_rename_map.csv')
    return open(path, encoding='utf-8')


def _load_field_rename_map(only=None):
    """[(model, old_name, new_name, ttype), ...] — l'ordre du CSV fait foi.

    ``only`` restreint aux anciens noms donnés (voir TRANSPORT_BATCH). Un nom
    inconnu du CSV est une erreur : il ne serait silencieusement pas renommé.
    """
    with _open_map() as handle:
        entries = [(row['model'], row['old_name'], row['new_name'], row['ttype'])
                   for row in csv.DictReader(handle)]
    if only is None:
        return entries
    only = set(only)
    unknown = only - {old for _model, old, _new, _ttype in entries}
    if unknown:
        raise ValueError('absents de la table de correspondance : %s'
                         % sorted(unknown))
    return [entry for entry in entries if entry[1] in only]


def _name_pairs(reverse=False, only=None):
    """Noms distincts à substituer dans du texte, sans le modèle.

    Un même nom peut vivre sur plusieurs modèles (``x_studio_etiquettes_clients``
    est sur account.move, account.payment et account.bank.statement.line) : une
    substitution textuelle ne sait de toute façon pas de quel modèle parle un
    domaine, et la correspondance est la même partout.
    """
    seen = {}
    for _model, old, new, _ttype in _load_field_rename_map(only):
        seen[new if reverse else old] = old if reverse else new
    # Les plus longs d'abord : une alternation regex est « leftmost-first », et
    # sans ce tri ``x_studio_transport`` pourrait être essayé avant
    # ``x_studio_transport_po``. (\b protège déjà, la ceinture est bon marché.)
    return sorted(seen.items(), key=lambda pair: len(pair[0]), reverse=True)


# Un contexte d'action ou de filtre colle le nom du champ derrière une clé :
# ``{'search_default_x_studio_transport': 1}``. Sans ces préfixes, la frontière
# de mot fait rater la substitution et le filtre par défaut tombe en silence.
# Les plus longs d'abord — « search_default_ » contient « default_ ».
_CONTEXT_PREFIXES = ('searchpanel_default_', 'search_default_', 'default_')

_TEXT_RE = {}


def _cache_key(reverse, only):
    return (reverse, None if only is None else frozenset(only))


def _text_regex(reverse=False, only=None):
    key = _cache_key(reverse, only)
    if key not in _TEXT_RE:
        pairs = _name_pairs(reverse, only)
        _TEXT_RE[key] = (
            re.compile(r'\b(%s)?(%s)\b'
                       % ('|'.join(_CONTEXT_PREFIXES),
                          '|'.join(re.escape(old) for old, _new in pairs))),
            dict(pairs),
        )
    return _TEXT_RE[key]


def _rename_fields_in_text(text, reverse=False, only=None):
    """Substitue les noms de champs dans du texte quelconque (source, domaine,
    arch de vue, code d'action serveur), sur frontière de mot uniquement."""
    if not text:
        return text
    pattern, mapping = _text_regex(reverse, only)
    return pattern.sub(
        lambda match: (match.group(1) or '') + mapping[match.group(2)], text)


# Les méthodes qui portent le nom du champ : ``_compute_x_studio_marge``. La
# frontière de mot les protège de la substitution des champs (le ``_`` qui
# précède est un caractère de mot), et ce sont des noms Python, pas des noms de
# champs — ils ne peuvent donc apparaître qu'en source, jamais en base. Les
# renommer en même temps évite de laisser la moitié du préfixe derrière soi.
_HELPER_PREFIXES = ('_compute', '_inverse', '_search', '_onchange', '_default')
_HELPER_RE = {}


def _helper_regex(reverse=False, only=None):
    key = _cache_key(reverse, only)
    if key not in _HELPER_RE:
        source = NEW_PREFIX if reverse else OLD_PREFIX
        if only is None:
            tail = r'\w+'
        else:
            # Restreint aux suffixes du lot : sans ça, un lot renommerait les
            # méthodes de champs qu'il ne touche pas.
            tail = '|'.join(
                re.escape(old[len(OLD_PREFIX):])
                for _m, old, _n, _t in _load_field_rename_map(only))
        _HELPER_RE[key] = re.compile(
            r'\b(%s)_%s(%s)\b' % ('|'.join(_HELPER_PREFIXES), source, tail))
    return _HELPER_RE[key]


def _rename_helpers_in_text(text, reverse=False, only=None):
    target = OLD_PREFIX if reverse else NEW_PREFIX
    return _helper_regex(reverse, only).sub(
        lambda match: '%s_%s%s' % (match.group(1), target, match.group(2)), text)


# ---------------------------------------------------------------------------
# Côté sources
# ---------------------------------------------------------------------------
_SOURCE_SUFFIXES = ('.py', '.xml', '.js', '.csv')
_SOURCE_SKIP_DIRS = ('__pycache__', '.git', 'node_modules')
# Les fichiers de l'outillage lui-même : la table de correspondance est écrite
# en anciens noms des deux côtés (la réécrire ferait perdre la clé du retour
# arrière), et les trois autres ne citent des noms de champs que pour
# documenter ou tester le renommage.
_SOURCE_SKIP_FILES = (
    'field_rename_map.csv',
    'field_rename.py',
    'build_field_rename_map.py',
    'test_field_rename.py',
    # studio_debris.py et ses satellites citent les séquelles laissées en base
    # par la bascule v15 : ces objets-là ne sont jamais renommés, leur nom dans
    # la documentation doit rester celui qu'ils portent en base.
    'studio_debris.py',
    'check_studio_debris.py',
    'test_studio_debris.py',
)


def _rewrite_sources(root, reverse=False, dry_run=False, only=None):
    """Réécrit les sources sous ``root``. Retourne [(chemin, occurrences), ...]."""
    touched = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in _SOURCE_SKIP_DIRS]
        for filename in sorted(filenames):
            if not filename.endswith(_SOURCE_SUFFIXES):
                continue
            if filename in _SOURCE_SKIP_FILES:
                continue
            path = os.path.join(dirpath, filename)
            # newline='' des deux côtés : une partie du dépôt est en CRLF
            # (public_tender, report_cadiffusion). Sans ça la réécriture
            # normaliserait les fins de ligne et le diff deviendrait illisible.
            with open(path, encoding='utf-8', newline='') as handle:
                before = handle.read()
            after = _rename_fields_in_text(before, reverse, only)
            if filename.endswith('.py'):
                after = _rename_helpers_in_text(after, reverse, only)
            if after == before:
                continue
            pattern, _mapping = _text_regex(reverse, only)
            occurrences = len(pattern.findall(before))
            if filename.endswith('.py'):
                occurrences += len(_helper_regex(reverse, only).findall(before))
            touched.append((path, occurrences))
            if not dry_run:
                with open(path, 'w', encoding='utf-8', newline='') as handle:
                    handle.write(after)
    return touched


# ---------------------------------------------------------------------------
# Côté base — inventaire de ce qui désigne un champ par son nom
# ---------------------------------------------------------------------------
# (table, colonnes texte, colonnes jsonb). Chaque table et chaque colonne est
# vérifiée dans information_schema avant d'être touchée : la liste couvre des
# modules qui ne sont pas tous installés (documents, spreadsheet) et des
# colonnes qui bougent d'une version d'Odoo à l'autre.
_TEXT_TARGETS = (
    ('ir_filters', ('domain', 'context', 'sort'), ()),
    ('ir_exports_line', ('name',), ()),
    ('ir_ui_view', (), ('arch_db',)),
    ('ir_ui_view_custom', ('arch',), ()),
    ('ir_act_window', ('domain', 'context'), ()),
    ('ir_act_server', ('code', 'value', 'update_path'), ()),
    ('ir_server_object_lines', ('value',), ()),
    ('ir_rule', ('domain_force',), ()),
    ('ir_model_fields', ('related', 'depends', 'compute', 'domain'), ()),
    ('base_automation', ('filter_domain', 'filter_pre_domain'), ()),
    ('mail_activity_plan_template', ('note',), ()),
    ('documents_document', ('spreadsheet_data',), ()),
    ('spreadsheet_dashboard', ('spreadsheet_data',), ()),
)


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s",
               (table,))
    return bool(cr.fetchone())


def _column_exists(cr, table, column):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = %s AND column_name = %s""", (table, column))
    return bool(cr.fetchone())


def _model_table(cr, model):
    """Table SQL d'un modèle, lue en base plutôt que déduite du nom.

    Le renommage tourne en pre-migrate, avant que le registre ne soit à jour :
    on ne peut pas passer par ``env[model]._table``. ``ir_model`` ne stocke pas
    la table, mais la convention Odoo (points → underscores) est fiable pour
    les 18 modèles concernés ; on vérifie tout de même son existence.
    """
    table = model.replace('.', '_')
    return table if _table_exists(cr, table) else None


def _rewrite_column(cr, table, column, reverse, jsonb=False, only=None):
    """Réécrit une colonne ligne à ligne. Retourne le nombre de lignes modifiées.

    Le filtre ``LIKE`` évite de relire des tables entières : seules les lignes
    qui portent réellement un des deux préfixes sont chargées.
    """
    # strpos plutôt que LIKE : dans un motif LIKE, « _ » est un joker, et
    # '%x_studio_%' ramènerait bien plus de lignes que voulu.
    needle = NEW_PREFIX if reverse else OLD_PREFIX
    expression = '%s::text' % column if jsonb else column
    cr.execute(
        'SELECT id, %s FROM %s WHERE strpos(%s, %%s) > 0'
        % (expression, table, expression), (needle,))
    rows = cr.fetchall()
    changed = 0
    for row_id, value in rows:
        new_value = _rename_fields_in_text(value, reverse, only)
        if new_value == value:
            continue
        cast = '%s::jsonb' if jsonb else '%s'
        cr.execute('UPDATE %s SET %s = %s WHERE id = %%s'
                   % (table, column, cast), (new_value, row_id))
        changed += 1
    return changed


def _rewrite_text_targets(cr, reverse=False, only=None):
    """Passe textuelle globale. Retourne {"table.colonne": lignes modifiées}."""
    details = {}
    for table, columns, jsonb_columns in _TEXT_TARGETS:
        if not _table_exists(cr, table):
            continue
        for column in columns + jsonb_columns:
            if not _column_exists(cr, table, column):
                continue
            changed = _rewrite_column(cr, table, column, reverse,
                                      jsonb=column in jsonb_columns, only=only)
            if changed:
                details['%s.%s' % (table, column)] = changed
    return details


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
def _ensure_journal(cr):
    cr.execute("""
        CREATE TABLE IF NOT EXISTS %s (
            id serial PRIMARY KEY,
            batch varchar NOT NULL,
            direction varchar NOT NULL,
            scope varchar NOT NULL,
            model varchar,
            old_name varchar,
            new_name varchar,
            table_name varchar,
            column_renamed boolean DEFAULT false,
            manual_field boolean DEFAULT false,
            details jsonb,
            applied_on timestamp NOT NULL DEFAULT now(),
            reverted_on timestamp
        )""" % JOURNAL_TABLE)


def _next_batch(cr):
    cr.execute('SELECT coalesce(max(batch::int), 0) + 1 FROM %s' % JOURNAL_TABLE)
    return str(cr.fetchone()[0])


def _journal(cr, **values):
    columns = sorted(values)
    cr.execute(
        'INSERT INTO %s (%s) VALUES (%s)'
        % (JOURNAL_TABLE, ', '.join(columns), ', '.join(['%s'] * len(columns))),
        [values[column] for column in columns])


def _pending_batch(cr):
    """Dernier lot appliqué et pas encore défait, ou None."""
    if not _table_exists(cr, JOURNAL_TABLE):
        return None
    cr.execute("""SELECT batch FROM %s
                   WHERE direction = 'forward' AND reverted_on IS NULL
                   ORDER BY id DESC LIMIT 1""" % JOURNAL_TABLE)
    row = cr.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Renommage d'un champ
# ---------------------------------------------------------------------------
def _rename_one_field(cr, model, old, new):
    """Renomme un champ en base : colonne, ir_model_fields, xmlid.

    Retourne le dict à journaliser, ou None si le champ est introuvable — cas
    normal quand un module n'est pas installé sur cette base.
    """
    cr.execute("""SELECT f.id, f.store, f.state
                    FROM ir_model_fields f
                   WHERE f.model = %s AND f.name = %s""", (model, old))
    row = cr.fetchone()
    if not row:
        _logger.info('%s.%s absent de ir_model_fields — ignoré', model, old)
        return None
    field_id, stored, state = row

    table = _model_table(cr, model)
    column_renamed = False
    if table and stored and _column_exists(cr, table, old):
        if _column_exists(cr, table, new):
            raise ValueError(
                "%s.%s existe déjà : renommage impossible sans perte. "
                "Vérifier qu'un -u n'a pas déjà créé la colonne vide." % (table, new))
        cr.execute('ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"' % (table, old, new))
        column_renamed = True

    cr.execute('UPDATE ir_model_fields SET name = %s WHERE id = %s', (new, field_id))
    # xmlid du champ : field_<table>__<nom>. Sans cette mise à jour, le prochain
    # chargement du module recrée un enregistrement de champ en double.
    if table:
        cr.execute("""UPDATE ir_model_data SET name = %s
                       WHERE model = 'ir.model.fields' AND res_id = %s""",
                   ('field_%s__%s' % (table, new), field_id))

    if state == 'manual':
        _logger.warning(
            "%s.%s est encore un champ manuel (Studio) : Odoo impose le préfixe "
            "x_ aux champs manuels, l'édition par l'interface le refusera.",
            model, old)
    return {
        'model': model,
        'old_name': old,
        'new_name': new,
        'table_name': table,
        'column_renamed': column_renamed,
        'manual_field': state == 'manual',
    }


# ---------------------------------------------------------------------------
# Points d'entrée
# ---------------------------------------------------------------------------
def _delegated_targets(cr, entries):
    """Modèles qui portent un champ renommé sans figurer dans la table.

    Les modèles délégués (``_inherits``) reçoivent de l'ORM un miroir de chaque
    champ du parent : product.product mirrorise product.template, res.users
    mirrorise res.partner. Ces lignes de ``ir_model_fields`` ne sont écrites
    par aucun code, mais si on les laisse sous l'ancien nom la base garde des
    champs fantômes — visibles dans les listes de champs de l'interface —
    jusqu'à ce que l'ORM finisse par les nettoyer. On les renomme avec les
    autres, et le journal les rend réversibles de la même façon.

    Ça ne déborde pas du périmètre « champs déclarés dans les sources » : un
    miroir n'est pas un champ de plus, c'est le même champ vu depuis le modèle
    enfant, et seuls les noms présents dans ``entries`` sont cherchés. Un champ
    que la base porte sans qu'aucun code ne le déclare n'est jamais touché —
    c'est le domaine de ``studio_debris.py``.
    """
    known = {(model, old) for model, old, _new, _ttype in entries}
    targets = []
    for old, new in {old: new for _m, old, new, _t in entries}.items():
        cr.execute('SELECT model FROM ir_model_fields WHERE name = %s', (old,))
        targets += [(model, old, new) for (model,) in cr.fetchall()
                    if (model, old) not in known]
    return targets


def _apply_field_rename(cr, only=None):
    """Renomme x_studio_* en ca_diff_* en base et journalise le lot.

    ``only`` restreint l'opération à un sous-ensemble d'anciens noms — voir
    TRANSPORT_BATCH. Seuls les champs DÉCLARÉS dans les sources sont concernés :
    la table de correspondance est produite à partir de ``addons_project``, rien
    n'est renommé sur la foi de ce que porte la base.

    Idempotent : un champ déjà renommé est absent de ``ir_model_fields`` sous
    son ancien nom, donc ignoré, et un lot entièrement rejoué ne journalise
    rien. Appelable depuis un ``pre-migrate.py`` (voir l'en-tête du module). Le
    retour arrière passe par ``_rollback_field_rename`` — il n'y a
    volontairement qu'un seul chemin.
    """
    _ensure_journal(cr)
    batch = _next_batch(cr)
    entries = _load_field_rename_map(only)
    targets = [(model, old, new) for model, old, new, _ttype in entries]
    targets += _delegated_targets(cr, entries)
    renamed = 0
    for model, old, new in targets:
        entry = _rename_one_field(cr, model, old, new)
        if entry is None:
            continue
        _journal(cr, batch=batch, direction='forward', scope='field', **entry)
        renamed += 1

    if not renamed:
        _logger.info('renommage : aucun champ à renommer (déjà fait ?)')
        return None

    details = _rewrite_text_targets(cr, reverse=False, only=only)
    _journal(cr, batch=batch, direction='forward', scope='text',
             details=json.dumps(details))
    _logger.info('renommage du lot %s : %d champs, %s',
                 batch, renamed, details or 'aucune référence textuelle')
    return batch


def _rollback_field_rename(cr, batch=None):
    """Défait un lot de renommage à partir du journal.

    Sans ``batch``, défait le dernier lot appliqué et non encore défait. Ne
    rejoue PAS la table de correspondance : seules les lignes réellement
    journalisées sont inversées, ce qui rend le retour arrière correct même
    après un renommage partiel ou interrompu.
    """
    if not _table_exists(cr, JOURNAL_TABLE):
        _logger.info('aucun journal de renommage — rien à défaire')
        return None
    batch = batch or _pending_batch(cr)
    if not batch:
        _logger.info('aucun lot de renommage à défaire')
        return None

    cr.execute("""SELECT model, new_name, old_name FROM %s
                   WHERE batch = %%s AND direction = 'forward' AND scope = 'field'
                     AND reverted_on IS NULL
                   ORDER BY id DESC""" % JOURNAL_TABLE, (batch,))
    entries = cr.fetchall()
    for model, current, previous in entries:
        _rename_one_field(cr, model, current, previous)

    # La passe textuelle se limite aux champs que CE lot a renommés : un autre
    # lot déjà appliqué ne doit pas être défait au passage.
    details = _rewrite_text_targets(
        cr, reverse=True, only={previous for _m, _c, previous in entries} or None)
    cr.execute('UPDATE %s SET reverted_on = now() WHERE batch = %%s' % JOURNAL_TABLE,
               (batch,))
    _journal(cr, batch=batch, direction='backward', scope='text',
             details=json.dumps(details))
    _logger.info('rollback du lot %s : %d champs, %s',
                 batch, len(entries), details or 'aucune référence textuelle')
    return batch


def _repair_field_rename_after_fresh_install(cr):
    """Rapatrie les données laissées en x_studio_* par une install fraîche.

    Sur un rebuild Odoo.sh par la plateforme d'upgrade, le module est INSTALLÉ
    neuf sur un dump de production : les scripts de migrations/ ne tournent
    pas, et l'ORM a déjà créé les colonnes ca_diff_* vides à côté des
    x_studio_* pleines. Ce n'est PAS un renommage (les colonnes neuves
    existent déjà) : on recopie la donnée, colonne par colonne, uniquement là
    où la cible est entièrement NULL — puis on laisse l'ancienne colonne en
    place, inerte, comme trace ; studio_debris.py saura la recenser.

    Appelé par le post_init_hook. Sans effet sur une base déjà migrée par le
    pre-migrate (l'ancienne colonne n'existe plus) et sur une base pas encore
    renommée (la nouvelle n'existe pas).
    """
    repaired = 0
    for model, old, new, _ttype in _load_field_rename_map():
        table = _model_table(cr, model)
        if not (table and _column_exists(cr, table, old)
                and _column_exists(cr, table, new)):
            continue
        cr.execute('SELECT count("%s"), count("%s") FROM "%s"' % (new, old, table))
        new_count, old_count = cr.fetchone()
        if new_count:
            # La cible porte déjà des données : ne rien écraser. Si l'ancienne
            # en a davantage, _assert_field_rename_integrity le signalera.
            if new_count < old_count:
                _logger.error(
                    '%s : %s porte %d valeurs et %s seulement %d — recopie '
                    'refusée pour ne rien écraser, à arbitrer à la main',
                    table, old, old_count, new, new_count)
            continue
        cr.execute('UPDATE "%s" SET "%s" = "%s" WHERE "%s" IS NOT NULL'
                   % (table, new, old, old))
        if cr.rowcount:
            repaired += 1
            _logger.warning(
                "install fraîche : %s.%s recopié vers %s (%d lignes) — "
                "l'ancienne colonne reste en place, à écarter via "
                "studio_debris", table, old, new, cr.rowcount)
    return repaired


def _verify_field_rename(cr):
    """Contrôle d'intégrité après renommage : aucune donnée ne doit manquer.

    Pour chaque champ stocké de la table de correspondance, trois états sont
    sains :

    * ancienne colonne seule  — pas encore renommé (état d'origine) ;
    * nouvelle colonne seule  — renommé par ALTER TABLE (le contenu a suivi) ;
    * les deux                — install fraîche réparée : la nouvelle doit
      porter AU MOINS autant de valeurs non nulles que l'ancienne.

    Tout autre cas est une anomalie. Retourne la liste des anomalies ;
    l'appelant décide d'en faire une erreur (les post-migrate et le
    post_init_hook la lèvent : mieux vaut un build rouge qu'une perte muette).
    """
    anomalies = []
    for model, old, new, _ttype in _load_field_rename_map():
        table = _model_table(cr, model)
        if not table:
            continue
        if not _column_exists(cr, table, old):
            continue  # renommée (ou jamais stockée ici) : rien à perdre
        if not _column_exists(cr, table, new):
            continue  # pas encore renommée : état d'origine, rien à perdre
        cr.execute('SELECT count("%s"), count("%s") FROM "%s"' % (old, new, table))
        old_count, new_count = cr.fetchone()
        if new_count < old_count:
            anomalies.append(
                '%s : %d valeurs dans %s mais %d dans %s (recopie incomplète)'
                % (table, old_count, old, new_count, new))
    return anomalies


def _assert_field_rename_integrity(cr):
    """Lève si des données du renommage manquent. À appeler après chaque étape
    qui touche aux colonnes (post-migrate, post_init_hook) : l'exception
    annule la transaction d'upgrade, rien n'est commité en l'état."""
    anomalies = _verify_field_rename(cr)
    if anomalies:
        raise ValueError(
            'renommage x_studio_/ca_diff_ : donnees manquantes, upgrade '
            'interrompu avant commit : ' + ' ; '.join(anomalies))
    _logger.info('renommage : integrite des donnees verifiee, aucune anomalie')


def _field_rename_status(cr):
    """État lisible du renommage, pour un contrôle en lecture seule."""
    if not _table_exists(cr, JOURNAL_TABLE):
        return {'applied': False, 'batch': None, 'fields': 0}
    batch = _pending_batch(cr)
    if not batch:
        return {'applied': False, 'batch': None, 'fields': 0}
    cr.execute("""SELECT count(*) FROM %s
                   WHERE batch = %%s AND scope = 'field' AND reverted_on IS NULL"""
               % JOURNAL_TABLE, (batch,))
    return {'applied': True, 'batch': batch, 'fields': cr.fetchone()[0]}
