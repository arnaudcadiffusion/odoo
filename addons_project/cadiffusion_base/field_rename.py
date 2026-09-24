"""Reversible rename of the Studio fields: ``x_studio_*`` -> ``cad_*``.

The ``x_studio_`` prefix is a leftover: these fields are no longer Studio
fields, they are declared in Python in ``addons_project/``. Renaming them
touches their SQL columns plus everything that names a field **by its name**
outside Python: favourite filters, saved exports, action domains, view archs,
server action code, spreadsheets.

Hence this module: **one mapping table** (``data/field_rename_map.csv``, built
by ``data/build_field_rename_map.py`` from the customer's decisions in
``data/field_decisions.csv``) and a **database journal**
(``cadiffusion_field_rename``) written during the operation, so that the
rollback undoes exactly what was done - including after a partial or
interrupted rename.

--------------------------------------------------------------------------
History
--------------------------------------------------------------------------

A first, mechanical rename ``x_studio_*`` -> ``ca_diff_*`` went to production
(19.0.1.0.27 / .28, public_tender 19.0.1.0.1) and was rolled back by
19.0.1.0.29. Its batches stay in the journal, marked as reverted.

The current rename follows the "Tri champs studio v15" spreadsheet agreed with
the customer (September 2026): kept fields get an explicit ``cad_*`` name,
deleted fields are removed from the sources and quarantined in the database
(``studio_debris._retire_fields``, see ``data/field_retire_map.csv``). It is
applied by the pre-migrates of cadiffusion_base 19.0.1.0.32 and public_tender
19.0.1.0.3.

Names are NOT mechanical: two old names may converge on the same new name on
different models (``x_studio_atradius`` on res.partner and
``x_studio_assurance_bc`` on sale.order both become ``cad_assurance``). A text
substitution cannot tell which model a domain talks about, so the reverse
substitution is ambiguous for those names: the rollback does not rely on it,
it restores each rewritten text row from the value saved in the journal.

--------------------------------------------------------------------------
Forward - in this order, never the reverse
--------------------------------------------------------------------------

1. Sources::

       python3 data/build_field_rename_map.py   # CSV tables, from decisions
       python3 data/rename_source_fields.py     # x_studio_ -> cad_
       git diff

2. Database, from a ``pre-migrate.py`` of the version shipping the sources
   above (``_apply_field_rename(cr)``). The pre-migrate is mandatory: on
   ``-u`` the ORM would otherwise create EMPTY ``cad_*`` columns next to the
   ``x_studio_*`` ones and never copy the data. A module declaring renamed
   fields and loaded BEFORE this one needs its own pre-migrate restricted to
   its fields (public_tender, ``only=TENDER_BATCH``).

3. ``SOURCE_PREFIX`` / ``STALE_PREFIX`` follow the sources: the fresh-install
   repair copies the data towards the columns the sources declare.

--------------------------------------------------------------------------
Rollback - a single deployment
--------------------------------------------------------------------------

Same constraint as forward, mirrored: the database must be restored BEFORE
the registry reloads on the old names. The rollback therefore travels INSIDE
the revert commit, as a pre-migrate calling
``_rollback_field_rename_batches(cr)`` (as 19.0.1.0.29 did), plus the same
call restricted to ``TENDER_BATCH`` in public_tender. Sources come back with
``git revert`` - ``rename_source_fields.py --rollback`` cannot revert the
converging names.

The rollback reads the journal, not the mapping table: it only undoes what
was actually applied, and does nothing (silently) when nothing was renamed.

On a database without journal (Odoo.sh rebuild by full upgrade: the module is
installed fresh, migrations do not run), there is nothing to undo and
``_repair_orphan_field_rename_data`` copies the data of the old columns into
the ones the ORM just created.

--------------------------------------------------------------------------
Not covered
--------------------------------------------------------------------------

* External integrations calling Odoo over XML-RPC / JSON-RPC with technical
  names, and Excel import templates whose headers carry those names. Nothing
  in the database lists them: to be checked by hand before the switch.
* Tracking values (``mail_tracking_value``) point to the field by foreign
  key: they follow the rename without any action.
* A field still ``state = 'manual'`` in the database (Studio field the code
  did not declare yet, e.g. ``cad_bloquer``) is renamed, switched to
  ``state = 'base'`` in the same statement - Odoo refuses a manual field
  without the ``x_`` prefix - and flagged in the journal (``manual_field``),
  so that the rollback makes it manual again.
"""
import csv
import json
import logging
import os
import re

_logger = logging.getLogger(__name__)

OLD_PREFIX = 'x_studio_'
NEW_PREFIX = 'cad_'

# Prefix under which the SOURCES declare the fields, and the one that can only
# survive in the database. The fresh-install repair and the integrity check
# derive the copy direction from them: flip them together with the sources.
SOURCE_PREFIX = NEW_PREFIX
STALE_PREFIX = OLD_PREFIX

JOURNAL_TABLE = 'cadiffusion_field_rename'

# The six tender.order fields declared by public_tender. That module loads
# BEFORE cadiffusion_base (which depends on it): its own pre-migrate renames
# them, otherwise its _auto_init creates empty cad_* columns before the script
# of cadiffusion_base runs. Every function takes an ``only`` - a set of old
# names - restricting the rename, sources and database alike.
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

    ``only`` restreint aux anciens noms donnés (voir TENDER_BATCH). Un nom
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
    """Distinct names to substitute in text, regardless of the model.

    The same name may live on several models (``x_studio_code_service_chorus``
    is on five): a text substitution cannot tell which model a domain talks
    about anyway, and forward the mapping is the same everywhere.

    Backwards it is not: ``cad_assurance`` comes from ``x_studio_atradius``
    (res.partner) AND ``x_studio_assurance_bc`` (sale.order). Such converging
    names are left out of the reverse pairs - the rollback restores the texts
    from the journal instead (``_restore_text_rows``).
    """
    forward = {}
    for _model, old, new, _ttype in _load_field_rename_map(only):
        forward[old] = new
    if reverse:
        sources = {}
        for old, new in forward.items():
            sources.setdefault(new, set()).add(old)
        pairs = {new: olds.pop() for new, olds in sources.items() if len(olds) == 1}
    else:
        pairs = forward
    # Les plus longs d'abord : une alternation regex est « leftmost-first », et
    # sans ce tri ``x_studio_transport`` pourrait être essayé avant
    # ``x_studio_transport_po``. (\b protège déjà, la ceinture est bon marché.)
    return sorted(pairs.items(), key=lambda pair: len(pair[0]), reverse=True)


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


# Methods carrying the field name: ``_compute_x_studio_marge``. The word
# boundary shields them from the field substitution (the leading ``_`` is a
# word character), and they are Python names, not field names - they only
# appear in sources, never in the database. Renaming them together avoids
# leaving half of the old name behind: ``_compute_x_studio_prix_remise``
# becomes ``_compute_cad_prix_remise``.
_HELPER_PREFIXES = ('_compute', '_inverse', '_search', '_onchange', '_default',
                    '_check')
_HELPER_RE = {}


def _helper_regex(reverse=False, only=None):
    key = _cache_key(reverse, only)
    if key not in _HELPER_RE:
        pairs = _name_pairs(reverse, only)
        _HELPER_RE[key] = (
            re.compile(r'\b(%s)_(%s)\b'
                       % ('|'.join(_HELPER_PREFIXES),
                          '|'.join(re.escape(old) for old, _new in pairs))),
            dict(pairs),
        )
    return _HELPER_RE[key]


def _rename_helpers_in_text(text, reverse=False, only=None):
    pattern, mapping = _helper_regex(reverse, only)
    return pattern.sub(
        lambda match: '%s_%s' % (match.group(1), mapping[match.group(2)]), text)


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
    # The customer's decisions and the retired fields: old names on purpose.
    'field_decisions.csv',
    'field_retire_map.csv',
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
                occurrences += len(_helper_regex(reverse, only)[0].findall(before))
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


def _rewrite_column(cr, table, column, reverse, jsonb=False, only=None,
                    batch=None):
    """Réécrit une colonne ligne à ligne. Retourne le nombre de lignes modifiées.

    Le filtre ``strpos`` évite de relire des tables entières : seules les lignes
    qui portent réellement le préfixe cherché sont chargées.

    With ``batch``, every rewritten row is journaled with its value before and
    after: the rollback puts the saved value back rather than substituting
    backwards, which the converging names make ambiguous.
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
        if batch:
            _journal(cr, batch=batch, direction='forward', scope='text_row',
                     table_name=table,
                     details=json.dumps({'column': column, 'row_id': row_id,
                                         'jsonb': jsonb, 'before': value,
                                         'after': new_value}))
        changed += 1
    return changed


def _rewrite_text_targets(cr, reverse=False, only=None, batch=None):
    """Passe textuelle globale. Retourne {"table.colonne": lignes modifiées}."""
    details = {}
    for table, columns, jsonb_columns in _TEXT_TARGETS:
        if not _table_exists(cr, table):
            continue
        for column in columns + jsonb_columns:
            if not _column_exists(cr, table, column):
                continue
            changed = _rewrite_column(cr, table, column, reverse,
                                      jsonb=column in jsonb_columns, only=only,
                                      batch=batch)
            if changed:
                details['%s.%s' % (table, column)] = changed
    return details


def _restore_text_rows(cr, batch):
    """Puts back the texts a batch rewrote, from the journal. Returns
    {"table.column": restored rows}.

    A row edited since the rename (its value no longer matches the journaled
    one) is not overwritten: the edit would be lost. It gets the reverse
    substitution instead, which covers every name but the converging ones,
    and is logged so it can be checked by hand.
    """
    cr.execute("""SELECT table_name, details FROM %s
                   WHERE batch = %%s AND direction = 'forward'
                     AND scope = 'text_row' AND reverted_on IS NULL
                   ORDER BY id DESC""" % JOURNAL_TABLE, (batch,))
    restored = {}
    for table, row in cr.fetchall():
        column, row_id, jsonb = row['column'], row['row_id'], row['jsonb']
        if not (_table_exists(cr, table) and _column_exists(cr, table, column)):
            continue
        expression = '%s::text' % column if jsonb else column
        cr.execute('SELECT %s FROM %s WHERE id = %%s' % (expression, table),
                   (row_id,))
        current = cr.fetchone()
        if not current:
            continue  # row deleted since: nothing to restore
        if current[0] == row['after']:
            value = row['before']
        else:
            value = _rename_fields_in_text(current[0], reverse=True)
            _logger.warning(
                '%s.%s id=%s edited since the rename: reverse substitution '
                'applied, converging names (cad_assurance, cad_type_container) '
                'to check by hand', table, column, row_id)
        cast = '%s::jsonb' if jsonb else '%s'
        cr.execute('UPDATE %s SET %s = %s WHERE id = %%s'
                   % (table, column, cast), (value, row_id))
        key = '%s.%s' % (table, column)
        restored[key] = restored.get(key, 0) + 1
    return restored


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
def _rename_one_field(cr, model, old, new, manual=False):
    """Renomme un champ en base : colonne, ir_model_fields, xmlid.

    ``manual`` is set by the rollback for a field the journal flagged as a
    Studio field: it gets its ``state = 'manual'`` back with its ``x_`` name.

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

    # Odoo forbids a manual field without the x_ prefix (CHECK constraint
    # ir_model_fields_name_manual_field): a Studio field the code now declares
    # (cad_bloquer) becomes a regular field together with its new name, as
    # the -u would make it anyway. The rollback turns it back into a manual one.
    new_state = state
    if state == 'manual' and not new.startswith('x_'):
        new_state = 'base'
    elif manual and new.startswith('x_'):
        new_state = 'manual'
    cr.execute('UPDATE ir_model_fields SET name = %s, state = %s WHERE id = %s',
               (new, new_state, field_id))
    # xmlid du champ : field_<table>__<nom>. Sans cette mise à jour, le prochain
    # chargement du module recrée un enregistrement de champ en double.
    # Only the xmlid the ORM derives from the field name: a Studio xmlid
    # (studio_customization, random name) is left as is, otherwise the
    # rollback could not give it its name back.
    if table:
        cr.execute("""UPDATE ir_model_data SET name = %s
                       WHERE model = 'ir.model.fields' AND res_id = %s
                         AND name = %s""",
                   ('field_%s__%s' % (table, new), field_id,
                    'field_%s__%s' % (table, old)))
    # Same for the values of a Selection field: selection__<model>__<field>__
    # <value>. Left under the old name, _process_end would take them for
    # orphans and unlink the ir_model_fields_selection rows.
    xmodel = model.replace('.', '_')
    old_prefix = 'selection__%s__%s__' % (xmodel, old)
    cr.execute("""UPDATE ir_model_data
                     SET name = %s || substr(name, %s)
                   WHERE model = 'ir.model.fields.selection'
                     AND strpos(name, %s) = 1
                     AND res_id IN (SELECT id FROM ir_model_fields_selection
                                     WHERE field_id = %s)""",
               ('selection__%s__%s__' % (xmodel, new), len(old_prefix) + 1,
                old_prefix, field_id))

    if new_state != state:
        _logger.info('%s.%s -> %s: state %s -> %s', model, old, new, state, new_state)
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
    """Renames x_studio_* to cad_* in the database and journals the batch.

    ``only`` restricts the operation to a subset of old names - see
    TENDER_BATCH. Only the fields of the mapping table are concerned: fields
    DECLARED in the sources, plus the few Studio fields created in production
    after the switch that the code now declares (``DATABASE_ONLY`` in
    ``data/build_field_rename_map.py``).

    Idempotent: a renamed field is no longer in ``ir_model_fields`` under its
    old name, so it is skipped, and a fully replayed batch journals nothing.
    Called from a ``pre-migrate.py`` (see the module header). The rollback goes
    through ``_rollback_field_rename`` - on purpose there is only one path.
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

    details = _rewrite_text_targets(cr, reverse=False, only=only, batch=batch)
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

    cr.execute("""SELECT model, new_name, old_name, manual_field FROM %s
                   WHERE batch = %%s AND direction = 'forward' AND scope = 'field'
                     AND reverted_on IS NULL
                   ORDER BY id DESC""" % JOURNAL_TABLE, (batch,))
    entries = cr.fetchall()
    for model, current, previous, manual in entries:
        _rename_one_field(cr, model, current, previous, manual=manual)

    # Texts come back from the journal when the batch saved them (every batch
    # since the cad_ rename). The batches of the reverted ca_diff_ rename
    # journaled counters only: for those, reverse substitution restricted to
    # the fields of THIS batch, so that another applied batch is not undone.
    cr.execute("""SELECT 1 FROM %s WHERE batch = %%s AND scope = 'text_row'
                   LIMIT 1""" % JOURNAL_TABLE, (batch,))
    if cr.fetchone():
        details = _restore_text_rows(cr, batch)
    else:
        details = _rewrite_text_targets(
            cr, reverse=True,
            only={previous for _m, _c, previous, _manual in entries} or None)
    cr.execute('UPDATE %s SET reverted_on = now() WHERE batch = %%s' % JOURNAL_TABLE,
               (batch,))
    _journal(cr, batch=batch, direction='backward', scope='text',
             details=json.dumps(details))
    _logger.info('rollback du lot %s : %d champs, %s',
                 batch, len(entries), details or 'aucune référence textuelle')
    return batch


def _applied_batches(cr, only=None):
    """Lots encore appliqués, du plus récent au plus ancien.

    ``only`` restreint aux lots qui ont renommé un des champs donnés. C'est ce
    qui permet à public_tender de défaire SES champs depuis son propre
    pre-migrate, sans connaître le numéro du lot : il varie d'une base à
    l'autre selon l'ordre dans lequel les upgrades s'y sont succédé.
    """
    if not _table_exists(cr, JOURNAL_TABLE):
        return []
    query = ("SELECT DISTINCT batch FROM %s WHERE direction = 'forward'"
             " AND scope = 'field' AND reverted_on IS NULL" % JOURNAL_TABLE)
    params = []
    if only is not None:
        query += ' AND old_name IN %s'
        params.append(tuple(only))
    # Le tri se fait en Python : PostgreSQL refuse un ORDER BY sur une
    # expression absente de la liste d'un SELECT DISTINCT, et un batch::int en
    # SQL casserait de toute façon sur une valeur non numérique.
    cr.execute(query, params)
    return sorted({batch for (batch,) in cr.fetchall()}, key=int, reverse=True)


def _rollback_field_rename_batches(cr, only=None):
    """Défait TOUS les lots encore appliqués, du plus récent au plus ancien.

    ``_rollback_field_rename`` ne défait qu'UN lot par appel, et le renommage
    est parti en trois lots (tender, transport, puis le reste) : un seul appel
    laisserait la base à moitié renommée, code et base désaccordés. Retourne la
    liste des lots défaits.

    Idempotent : sans lot en attente — base jamais renommée, ou déjà défaite —
    ne fait rien et n'échoue pas.
    """
    batches = _applied_batches(cr, only)
    for batch in batches:
        _rollback_field_rename(cr, batch)
    if not batches:
        _logger.info('rollback : aucun lot de renommage en attente')
    else:
        _logger.info('rollback : %d lot(s) défait(s) — %s',
                     len(batches), ', '.join(batches))
    return batches


def _source_and_stale_columns(old, new):
    """(column the sources expect, column that is only a leftover).

    Derived from SOURCE_PREFIX: since 19.0.1.0.32 the sources declare
    ``cad_*``, so the new name must carry the data and the old ``x_studio_*``
    column is what a dump that was never migrated still carries.
    """
    return (old, new) if SOURCE_PREFIX == OLD_PREFIX else (new, old)


def _repair_orphan_field_rename_data(cr):
    """Rapatrie les données restées dans la colonne que les sources n'utilisent plus.

    Deux situations amènent une base à porter les DEUX colonnes, la bonne vide
    et l'autre pleine :

    * un rebuild Odoo.sh par la plateforme d'upgrade — le module y est
      INSTALLÉ neuf sur un dump de production, les scripts de migrations/ ne
      tournent pas, et l'ORM a créé la colonne attendue par les sources, vide,
      à côté de celle que porte le dump ;
    * a database restored from a dump taken on the other side of the rename,
      then updated: the journal is missing or settled there, so neither the
      rename nor ``_rollback_field_rename_batches`` has anything to do.

    Ce n'est PAS un renommage (les deux colonnes existent déjà) : on recopie la
    donnée, colonne par colonne, uniquement là où la cible est entièrement
    NULL — puis on laisse l'autre colonne en place, inerte, comme trace ;
    studio_debris.py saura la recenser.

    The direction follows SOURCE_PREFIX: since 19.0.1.0.32 the ``x_studio_*``
    columns of a dump are copied into the ``cad_*`` ones. Called by the
    post_init_hook and the post-migrate of 19.0.1.0.32. No effect when only
    one of the two columns exists, that is on any consistent database.
    """
    repaired = 0
    for model, old, new, _ttype in _load_field_rename_map():
        target, stale = _source_and_stale_columns(old, new)
        table = _model_table(cr, model)
        if not (table and _column_exists(cr, table, target)
                and _column_exists(cr, table, stale)):
            continue
        cr.execute('SELECT count("%s"), count("%s") FROM "%s"'
                   % (target, stale, table))
        target_count, stale_count = cr.fetchone()
        if target_count:
            # La cible porte déjà des données : ne rien écraser. Si l'autre en
            # a davantage, _assert_field_rename_integrity le signalera.
            if target_count < stale_count:
                _logger.error(
                    '%s : %s porte %d valeurs et %s seulement %d — recopie '
                    'refusée pour ne rien écraser, à arbitrer à la main',
                    table, stale, stale_count, target, target_count)
            continue
        cr.execute('UPDATE "%s" SET "%s" = "%s" WHERE "%s" IS NOT NULL'
                   % (table, target, stale, stale))
        if cr.rowcount:
            repaired += 1
            _logger.warning(
                "%s.%s recopié vers %s (%d lignes) — la colonne d'origine "
                "reste en place, à écarter via studio_debris",
                table, stale, target, cr.rowcount)
    return repaired


def _verify_field_rename(cr):
    """Contrôle d'intégrité : aucune donnée ne doit rester hors d'atteinte du code.

    Pour chaque champ stocké de la table de correspondance, trois états sont
    sains :

    * colonne des sources seule — état nominal, le code lit la donnée ;
    * colonne vestige seule     — renommage en attente ou déjà défait par
      ALTER TABLE (le contenu a suivi la colonne) ;
    * les deux                  — base réparée : celle qu'attendent les sources
      doit porter AU MOINS autant de valeurs non nulles que l'autre.

    Tout autre cas est une anomalie : de la donnée dort dans une colonne
    qu'aucun champ ne référence. Retourne la liste des anomalies ; l'appelant
    décide d'en faire une erreur (les post-migrate et le post_init_hook la
    lèvent : mieux vaut un build rouge qu'une perte muette).
    """
    anomalies = []
    for model, old, new, _ttype in _load_field_rename_map():
        target, stale = _source_and_stale_columns(old, new)
        table = _model_table(cr, model)
        if not table:
            continue
        if not _column_exists(cr, table, stale):
            continue  # état nominal (ou champ jamais stocké ici) : rien à perdre
        if not _column_exists(cr, table, target):
            continue  # la donnée a suivi la colonne : rien à perdre
        cr.execute('SELECT count("%s"), count("%s") FROM "%s"'
                   % (stale, target, table))
        stale_count, target_count = cr.fetchone()
        if target_count < stale_count:
            anomalies.append(
                '%s : %d valeurs dans %s mais %d dans %s (recopie incomplète)'
                % (table, stale_count, stale, target_count, target))
    return anomalies


def _assert_field_rename_integrity(cr):
    """Lève si des données du renommage manquent. À appeler après chaque étape
    qui touche aux colonnes (post-migrate, post_init_hook) : l'exception
    annule la transaction d'upgrade, rien n'est commité en l'état."""
    anomalies = _verify_field_rename(cr)
    if anomalies:
        raise ValueError(
            'renommage x_studio_/cad_ : donnees manquantes, upgrade '
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
