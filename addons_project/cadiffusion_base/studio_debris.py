"""Séquelles Studio / v15 en base : inventaire, mise en quarantaine, restauration.

La bascule v15 → v19 a laissé en base des objets que plus aucun code ne
connaît. Ils sont inertes — l'ORM construit l'interface depuis le registre
Python, pas depuis ``ir_model_fields`` — mais ils faussent tout inventaire, ils
occupent de la place, et ils passent au travers du renommage ``x_studio_*`` →
``ca_diff_*`` (voir ``field_rename.py``), qui ne sait renommer que ce qui est
déclaré quelque part.

Trois familles, relevées le 2026-08-26 sur la base locale ET sur le build Test
d'Odoo.sh — qui donnent exactement les mêmes chiffres, 187 champs ``x_studio_``
en base ; la production est la même base :

* **champs fantômes** (23) — miroirs de délégation que l'ORM avait créés sur
  ``product.product`` et ``res.users`` pour refléter un champ de
  ``product.template`` / ``res.partner``. Le parent a disparu, le miroir est
  resté : ``related = 'partner_id.x_studio_notes_interne'`` alors que
  ``res.partner.x_studio_notes_interne`` n'existe plus. Non stockés, donc
  aucune donnée derrière.
* **colonnes orphelines** (1) — ``sale_order.x_studio_assurance``, 38 195
  valeurs, aucun champ déclaré ni en v15 ni en v19. C'était un ``related``
  stocké vers ``res.partner.x_studio_assurance`` (le Char « Credit Safe », à ne
  pas confondre avec la Selection ``x_studio_atradius`` que la commande porte
  toujours sous ``x_studio_assurance_bc``). Le champ a été retiré de Studio
  avant le dump v15, la colonne est restée. Elle est figée : 37 874 des 38 195
  valeurs diffèrent du Credit Safe courant du client, et dans la même
  proportion en v15 — plus rien ne l'écrit depuis des années.

  **Décidé le 2026-08-26 : cet historique n'est pas conservé.** La colonne part
  en quarantaine avec le reste, puis sera supprimée. Si la décision devait être
  revue avant le ``DROP``, la donnée est toujours là sous
  ``zz_dead_x_studio_assurance`` — mais il faudrait alors la redéclarer avec un
  ``fields.Char(readonly=True)`` NU : un ``related=... store=True`` ferait
  recalculer les 38 195 lignes par l'ORM et écraserait l'instantané.
* **tables mortes** (2) — ``account_invoice`` (82 231 lignes) et
  ``account_invoice_line`` (258 772), l'ancien modèle ``account.invoice``
  remplacé par ``account.move`` depuis la v13. Les données ont été migrées, les
  tables sont restées ; aucun modèle ``account.invoice`` n'est enregistré.

--------------------------------------------------------------------------
Rien n'est supprimé
--------------------------------------------------------------------------

``_quarantine_studio_debris`` ne fait que **déplacer** :

* une colonne orpheline est renommée ``zz_dead_<colonne>`` ;
* une table morte est renommée ``zz_dead_<table>`` ;
* une ligne de champ fantôme est supprimée de ``ir_model_fields``, mais son
  contenu intégral est recopié en JSON dans le journal avant de partir.

Les données restent donc en place et récupérables. Un vrai ``DROP`` est une
seconde décision, prise plus tard, une fois que plusieurs semaines de
production ont confirmé que rien ne réclame ces objets — et à ce moment-là il
se fait à la main, en connaissance de cause, pas par un script.

Chaque catégorie s'active séparément : appeler la fonction sans argument ne
fait rien. C'est délibéré — on ne met pas en quarantaine 340 000 lignes par
défaut d'attention.

--------------------------------------------------------------------------
Usage (odoo shell, ou n'importe quel curseur psycopg2)
--------------------------------------------------------------------------

Inventaire, en lecture seule — c'est aussi ce qu'affiche
``data/check_studio_debris.py`` ::

    from odoo.addons.cadiffusion_base import _studio_debris
    _studio_debris(env.cr)

Quarantaine, catégorie par catégorie ::

    from odoo.addons.cadiffusion_base import _quarantine_studio_debris
    _quarantine_studio_debris(env.cr, ghost_fields=True)
    env.cr.commit()

Retour arrière — remet tout en place, dans l'ordre inverse ::

    from odoo.addons.cadiffusion_base import _restore_studio_debris
    _restore_studio_debris(env.cr)
    env.cr.commit()

L'ordre vis-à-vis du renommage n'a pas d'importance : les deux outils ne se
recouvrent pas. Le renommage ne touche que ce qui est déclaré, la quarantaine
que ce qui ne l'est plus.

--------------------------------------------------------------------------
Retired fields (19.0.1.0.32)
--------------------------------------------------------------------------

The fields the customer chose to delete ("Tri champs studio v15",
``data/field_retire_map.csv``) are removed from the sources. Left alone, the
next ``-u`` would have Odoo unlink their ``ir_model_fields`` rows (orphan
xmlids, ``ir.model.data._process_end``) and DROP their columns. The
pre-migrate of 19.0.1.0.32 calls ``_retire_fields`` first, which:

* renames each stored column to ``zz_dead_<column>`` (and the relation table
  of a stored many2many to ``zz_dead_<table>``);
* detaches the field from its xmlids (and those of its selection values), so
  that ``_process_end`` no longer sees it: the ``ir_model_fields`` row stays,
  inert, with its tracking values;
* archives the favourite filters naming a retired field - applying one would
  raise an error in the web client;
* strips the ``<field>`` nodes of retired fields from the active views in
  database. During the upgrade a view is validated together with its sibling
  inherited views, some of them not reloaded yet (or never: Studio views,
  views removed from the XML): one stale reference fails the whole ``-u``. A
  view using a retired field any other way (locator, ``replace`` content,
  expression) is archived instead.

Everything is journaled (kinds ``retired_field``, ``retired_filter``,
``retired_view``) and
undone by ``_restore_studio_debris`` like the other kinds.

Les noms cités dans ce fichier sont ceux que ces objets portent EN BASE. Ils ne
suivent pas le renommage ``x_studio_*`` → ``ca_diff_*`` — un objet que plus
aucun code ne déclare n'a rien qui puisse le renommer — et ``field_rename.py``
laisse donc ce fichier de côté quand il réécrit les sources.
"""
import csv
import json
import logging
import re

from lxml import etree

_logger = logging.getLogger(__name__)

# Les deux préfixes se cherchent ensemble : une base déjà renommée porte ses
# séquelles sous l'ancien nom (elles ont échappé au renommage) et ses champs
# vivants sous le nouveau.
_PREFIXES = ('x_studio_', 'ca_diff_')

QUARANTINE_PREFIX = 'zz_dead_'
JOURNAL_TABLE = 'cadiffusion_studio_debris'

# PostgreSQL tronque les identifiants à 63 octets : un nom de table déjà long
# perdrait sa fin, et la restauration ne retrouverait pas son objet.
_MAX_IDENTIFIER = 63


def _table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s",
               (table,))
    return bool(cr.fetchone())


def _quarantine_name(name):
    quarantined = QUARANTINE_PREFIX + name
    if len(quarantined) > _MAX_IDENTIFIER:
        raise ValueError(
            "« %s » dépasse %d caractères une fois préfixé : PostgreSQL le "
            "tronquerait et la restauration ne le retrouverait pas."
            % (quarantined, _MAX_IDENTIFIER))
    return quarantined


# ---------------------------------------------------------------------------
# Inventaire (lecture seule)
# ---------------------------------------------------------------------------
def _model_tables(cr):
    """{table SQL: modèle} pour les modèles réellement enregistrés."""
    cr.execute('SELECT model FROM ir_model')
    return {model.replace('.', '_'): model for (model,) in cr.fetchall()}


def _related_target(cr, model, related):
    """Suit un chemin ``related`` et retourne (modèle, champ) d'arrivée.

    Retourne None si un maillon manque — c'est précisément ce qui définit un
    miroir fantôme : le chemin ne mène nulle part.
    """
    segments = related.split('.')
    current = model
    for segment in segments[:-1]:
        cr.execute("""SELECT relation FROM ir_model_fields
                       WHERE model = %s AND name = %s""", (current, segment))
        row = cr.fetchone()
        if not row or not row[0]:
            return None
        current = row[0]
    return current, segments[-1]


def _ghost_fields(cr):
    """Miroirs de délégation dont le champ parent n'existe plus.

    Filet de sécurité volontairement serré : on ne retient qu'un champ NON
    STOCKÉ (donc sans donnée derrière) dont le ``related`` pointe dans le vide.
    Un champ stocké, ou dont le parent existe, n'est jamais candidat.
    """
    ghosts = []
    for prefix in _PREFIXES:
        cr.execute("""SELECT id, model, name, related, ttype, field_description
                        FROM ir_model_fields
                       WHERE strpos(name, %s) = 1
                         AND store IS NOT TRUE
                         AND related IS NOT NULL
                       ORDER BY model, name""", (prefix,))
        for field_id, model, name, related, ttype, label in cr.fetchall():
            target = _related_target(cr, model, related)
            if target is None:
                reason = 'chemin related interrompu'
            else:
                cr.execute("""SELECT 1 FROM ir_model_fields
                               WHERE model = %s AND name = %s""", target)
                if cr.fetchone():
                    continue  # le parent existe : miroir légitime
                reason = '%s.%s n\'existe pas' % target
            ghosts.append({
                'id': field_id, 'model': model, 'name': name,
                'related': related, 'ttype': ttype, 'label': label,
                'reason': reason,
            })
    return ghosts


def _orphan_columns(cr):
    """Colonnes préfixées d'une table vivante, sans champ correspondant."""
    tables = _model_tables(cr)
    orphans = []
    for prefix in _PREFIXES:
        cr.execute("""SELECT table_name, column_name FROM information_schema.columns
                       WHERE table_schema = 'public' AND strpos(column_name, %s) = 1
                       ORDER BY table_name, column_name""", (prefix,))
        for table, column in cr.fetchall():
            model = tables.get(table)
            if not model:
                continue  # table morte : traitée par _dead_tables
            cr.execute("""SELECT 1 FROM ir_model_fields
                           WHERE model = %s AND name = %s""", (model, column))
            if cr.fetchone():
                continue
            cr.execute('SELECT count(*) FROM "%s" WHERE "%s" IS NOT NULL'
                       % (table, column))
            orphans.append({'table': table, 'model': model, 'column': column,
                            'values': cr.fetchone()[0]})
    return orphans


def _dead_tables(cr):
    """Tables portant des colonnes préfixées et dont le modèle n'existe plus."""
    tables = _model_tables(cr)
    dead = {}
    for prefix in _PREFIXES:
        cr.execute("""SELECT DISTINCT table_name FROM information_schema.columns
                       WHERE table_schema = 'public' AND strpos(column_name, %s) = 1
                       ORDER BY table_name""", (prefix,))
        for (table,) in cr.fetchall():
            if table in tables or table in dead or table.startswith(QUARANTINE_PREFIX):
                continue
            cr.execute('SELECT count(*) FROM "%s"' % table)
            dead[table] = {'table': table, 'rows': cr.fetchone()[0]}
    return sorted(dead.values(), key=lambda entry: entry['table'])


def _studio_debris(cr):
    """Inventaire complet, sans aucune écriture."""
    return {
        'ghost_fields': _ghost_fields(cr),
        'orphan_columns': _orphan_columns(cr),
        'dead_tables': _dead_tables(cr),
    }


# ---------------------------------------------------------------------------
# Journal
# ---------------------------------------------------------------------------
def _ensure_journal(cr):
    cr.execute("""
        CREATE TABLE IF NOT EXISTS %s (
            id serial PRIMARY KEY,
            batch varchar NOT NULL,
            kind varchar NOT NULL,
            identifier varchar NOT NULL,
            quarantined_as varchar,
            payload jsonb,
            applied_on timestamp NOT NULL DEFAULT now(),
            restored_on timestamp
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
    if not _table_exists(cr, JOURNAL_TABLE):
        return None
    cr.execute("""SELECT batch FROM %s WHERE restored_on IS NULL
                   ORDER BY id DESC LIMIT 1""" % JOURNAL_TABLE)
    row = cr.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Quarantaine
# ---------------------------------------------------------------------------
def _quarantine_studio_debris(cr, ghost_fields=False, orphan_columns=False,
                              dead_tables=False, only=None):
    """Met de côté les séquelles demandées. Sans argument : ne fait rien.

    Chaque catégorie est explicite parce qu'elles n'ont ni le même poids ni le
    même risque : supprimer 23 lignes de métadonnées inertes n'engage rien,
    écarter 340 000 lignes de facturation v15 se décide.

    ``only`` restricts ghost fields and orphan columns to the given names, so
    that a migration only sets aside what was decided, whatever else the
    inventory finds on that database.
    """
    if not (ghost_fields or orphan_columns or dead_tables):
        _logger.info('aucune catégorie demandée — rien à faire')
        return None

    _ensure_journal(cr)
    batch = _next_batch(cr)
    debris = _studio_debris(cr)
    if only is not None:
        only = set(only)
        debris['ghost_fields'] = [ghost for ghost in debris['ghost_fields']
                                  if ghost['name'] in only]
        debris['orphan_columns'] = [orphan for orphan in debris['orphan_columns']
                                    if orphan['column'] in only]
    counts = {}

    if ghost_fields:
        for ghost in debris['ghost_fields']:
            # Sauvegarde intégrale avant suppression : la ligne pourra être
            # réinsérée telle quelle, son id compris.
            cr.execute('SELECT row_to_json(f) FROM ir_model_fields f WHERE id = %s',
                       (ghost['id'],))
            row = cr.fetchone()
            if not row:
                continue
            cr.execute("""SELECT coalesce(json_agg(d), '[]'::json) FROM ir_model_data d
                           WHERE model = 'ir.model.fields' AND res_id = %s""",
                       (ghost['id'],))
            xmlids = cr.fetchone()[0]
            cr.execute("""DELETE FROM ir_model_data
                           WHERE model = 'ir.model.fields' AND res_id = %s""",
                       (ghost['id'],))
            cr.execute('DELETE FROM ir_model_fields WHERE id = %s', (ghost['id'],))
            _journal(cr, batch=batch, kind='ghost_field',
                     identifier='%s.%s' % (ghost['model'], ghost['name']),
                     payload=json.dumps({'field': row[0], 'xmlids': xmlids}))
        counts['ghost_fields'] = len(debris['ghost_fields'])

    if orphan_columns:
        for orphan in debris['orphan_columns']:
            quarantined = _quarantine_name(orphan['column'])
            cr.execute('ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
                       % (orphan['table'], orphan['column'], quarantined))
            _journal(cr, batch=batch, kind='orphan_column',
                     identifier='%s.%s' % (orphan['table'], orphan['column']),
                     quarantined_as=quarantined, payload=json.dumps(orphan))
        counts['orphan_columns'] = len(debris['orphan_columns'])

    if dead_tables:
        for dead in debris['dead_tables']:
            quarantined = _quarantine_name(dead['table'])
            cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (dead['table'], quarantined))
            _journal(cr, batch=batch, kind='dead_table', identifier=dead['table'],
                     quarantined_as=quarantined, payload=json.dumps(dead))
        counts['dead_tables'] = len(debris['dead_tables'])

    _logger.info('quarantaine lot %s : %s', batch, counts or 'rien à écarter')
    return batch


def _restore_studio_debris(cr, batch=None):
    """Remet en place un lot mis en quarantaine.

    Sans ``batch``, restaure le dernier lot non encore restauré. Lit le
    journal, jamais l'inventaire : ce qui n'a pas été écarté n'est pas touché.
    """
    if not _table_exists(cr, JOURNAL_TABLE):
        _logger.info('aucun journal de quarantaine — rien à restaurer')
        return None
    batch = batch or _pending_batch(cr)
    if not batch:
        _logger.info('aucun lot de quarantaine à restaurer')
        return None

    cr.execute("""SELECT kind, identifier, quarantined_as, payload FROM %s
                   WHERE batch = %%s AND restored_on IS NULL
                   ORDER BY id DESC""" % JOURNAL_TABLE, (batch,))
    for kind, identifier, quarantined, payload in cr.fetchall():
        if kind == 'dead_table':
            cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (quarantined, identifier))
        elif kind == 'orphan_column':
            table, column = identifier.split('.', 1)
            cr.execute('ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
                       % (table, quarantined, column))
        elif kind == 'ghost_field':
            _restore_ghost_field(cr, payload)
        elif kind == 'retired_field':
            _restore_retired_field(cr, payload)
        elif kind == 'retired_filter':
            cr.execute('UPDATE ir_filters SET active = true WHERE id = %s',
                       (payload['id'],))
        elif kind == 'retired_view':
            cr.execute("""UPDATE ir_ui_view SET arch_db = %s::jsonb, active = true
                           WHERE id = %s""", (payload['arch_db'], payload['id']))

    cr.execute('UPDATE %s SET restored_on = now() WHERE batch = %%s' % JOURNAL_TABLE,
               (batch,))
    _logger.info('lot %s restauré', batch)
    return batch


def _restore_ghost_field(cr, payload):
    """Réinsère une ligne ir_model_fields depuis sa sauvegarde JSON.

    ``json_populate_record`` reconstruit la ligne colonne par colonne : pas de
    liste de champs figée ici, donc rien à maintenir quand Odoo en ajoute une.
    """
    field = payload['field']
    cr.execute("""INSERT INTO ir_model_fields
                  SELECT (json_populate_record(null::ir_model_fields, %s::json)).*
                  ON CONFLICT (id) DO NOTHING""", (json.dumps(field),))
    for xmlid in payload.get('xmlids') or []:
        cr.execute("""INSERT INTO ir_model_data
                      SELECT (json_populate_record(null::ir_model_data, %s::json)).*
                      ON CONFLICT (id) DO NOTHING""", (json.dumps(xmlid),))


# ---------------------------------------------------------------------------
# Retired fields
# ---------------------------------------------------------------------------
_RETIRE_MAP_FILE = 'cadiffusion_base/data/field_retire_map.csv'


_DECISIONS_FILE = 'cadiffusion_base/data/field_decisions.csv'


def _load_retire_map():
    """[(model, name), ...] of the fields removed from the sources."""
    from odoo.tools import file_open
    with file_open(_RETIRE_MAP_FILE, 'r') as handle:
        return [(row['model'], row['name']) for row in csv.DictReader(handle)]


def _decided_deletions():
    """Every name the customer chose to delete, declared or not."""
    from odoo.tools import file_open
    with file_open(_DECISIONS_FILE, 'r') as handle:
        return {row['old_name'] for row in csv.DictReader(handle)
                if row['decision'] == 'delete'}


def _column_exists(cr, table, column):
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = %s AND column_name = %s""", (table, column))
    return bool(cr.fetchone())


def _retire_targets(cr, entries):
    """The retired fields plus their delegation mirrors.

    product.product mirrors every product.template field and res.users every
    res.partner field (``_inherits``): those rows carry the same xmlid module
    and would be unlinked by ``_process_end`` as well. They are not stored, so
    only their xmlids are at stake.
    """
    targets = list(entries)
    known = set(entries)
    for model, name in entries:
        cr.execute("""SELECT model FROM ir_model_fields
                       WHERE name = %s AND model <> %s AND store IS NOT TRUE
                         AND related LIKE %s""", (name, model, '%.' + name))
        for (mirror,) in cr.fetchall():
            if (mirror, name) not in known:
                known.add((mirror, name))
                targets.append((mirror, name))
    return targets


def _retire_fields(cr, entries=None):
    """Quarantines the fields removed from the sources. Returns the batch, or
    None when there was nothing left to retire.

    Idempotent: a field whose xmlids are already detached and whose column is
    already set aside journals nothing.
    """
    entries = _load_retire_map() if entries is None else list(entries)
    _ensure_journal(cr)
    batch = _next_batch(cr)
    retired = 0
    for model, name in _retire_targets(cr, entries):
        cr.execute("""SELECT id, store, relation_table FROM ir_model_fields
                       WHERE model = %s AND name = %s""", (model, name))
        row = cr.fetchone()
        if not row:
            continue
        field_id, stored, relation_table = row
        payload = {'model': model, 'name': name, 'field_id': field_id,
                   'table': None, 'column': None, 'relation_table': None,
                   'xmlids': []}
        table = model.replace('.', '_')
        if stored and _table_exists(cr, table) and _column_exists(cr, table, name):
            quarantined = _quarantine_name(name)
            cr.execute('ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
                       % (table, name, quarantined))
            payload.update(table=table, column=quarantined)
        if relation_table and _table_exists(cr, relation_table):
            # Only when no other (kept) field shares the relation table.
            cr.execute("""SELECT 1 FROM ir_model_fields
                           WHERE relation_table = %s AND id <> %s""",
                       (relation_table, field_id))
            if not cr.fetchone():
                quarantined = _quarantine_name(relation_table)
                cr.execute('ALTER TABLE "%s" RENAME TO "%s"'
                           % (relation_table, quarantined))
                payload['relation_table'] = [relation_table, quarantined]
        # xmlids of the field and of its selection values: without them,
        # _process_end leaves the rows alone (no unlink, no DROP COLUMN).
        cr.execute("""SELECT coalesce(json_agg(d), '[]'::json) FROM ir_model_data d
                       WHERE (d.model = 'ir.model.fields' AND d.res_id = %s)
                          OR (d.model = 'ir.model.fields.selection' AND d.res_id IN (
                                SELECT id FROM ir_model_fields_selection
                                 WHERE field_id = %s))""", (field_id, field_id))
        payload['xmlids'] = cr.fetchone()[0]
        if payload['xmlids']:
            cr.execute('DELETE FROM ir_model_data WHERE id IN %s',
                       (tuple(xmlid['id'] for xmlid in payload['xmlids']),))
        if not (payload['column'] or payload['relation_table'] or payload['xmlids']):
            continue  # already retired
        _journal(cr, batch=batch, kind='retired_field',
                 identifier='%s.%s' % (model, name),
                 quarantined_as=payload['column'], payload=json.dumps(payload))
        retired += 1

    names = sorted({name for _model, name in entries})
    filters = 0
    if names:
        pattern = r'\m(%s)\M' % '|'.join(names)
        cr.execute("""SELECT id, name FROM ir_filters
                       WHERE active
                         AND concat_ws(' ', domain, context, sort) ~ %s""",
                   (pattern,))
        for filter_id, filter_name in cr.fetchall():
            cr.execute('UPDATE ir_filters SET active = false WHERE id = %s',
                       (filter_id,))
            _journal(cr, batch=batch, kind='retired_filter',
                     identifier=str(filter_id),
                     payload=json.dumps({'id': filter_id, 'name': filter_name}))
            filters += 1

    stripped, archived = _retire_fields_from_views(cr, names, batch)

    if not (retired or filters or stripped or archived):
        _logger.info('field retirement: nothing to do (already done?)')
        return None
    _logger.info('field retirement, batch %s: %d fields, %d filters archived, '
                 '%d views stripped, %d views archived',
                 batch, retired, filters, stripped, archived)
    return batch


def _strip_field_nodes(arch, names):
    """Removes the plain ``<field name="...">`` nodes of ``names`` from an
    arch. Returns the new arch, or None when a name is used any other way
    and the view has to be archived instead."""
    root = etree.fromstring(arch.encode())
    for node in root.xpath('//field[@name]'):
        if node.get('name') not in names:
            continue
        parent = node.getparent()
        if (node.get('position') or parent is None
                or parent.get('position') == 'replace'):
            return None
        # Keep the surrounding whitespace in place.
        previous = node.getprevious()
        if node.tail:
            if previous is not None:
                previous.tail = (previous.tail or '') + node.tail
            else:
                parent.text = (parent.text or '') + node.tail
        parent.remove(node)
    result = etree.tostring(root, encoding='unicode')
    if re.search(r'\b(%s)\b' % '|'.join(map(re.escape, names)), result):
        return None
    return result


def _retire_fields_from_views(cr, names, batch):
    """Strips the retired fields from the active views in database, or
    archives the views that cannot be stripped. Returns (stripped, archived)."""
    if not names:
        return 0, 0
    names = set(names)
    cr.execute("""SELECT id, arch_db::text FROM ir_ui_view
                   WHERE active AND arch_db::text ~ %s""",
               (r'\m(%s)\M' % '|'.join(sorted(names)),))
    stripped = archived = 0
    for view_id, arch_text in cr.fetchall():
        translations = json.loads(arch_text)
        new = {}
        for lang, arch in translations.items():
            new[lang] = _strip_field_nodes(arch, names) if arch else arch
            if arch and new[lang] is None:
                new = None
                break
        if new is None:
            cr.execute('UPDATE ir_ui_view SET active = false WHERE id = %s',
                       (view_id,))
            archived += 1
            _logger.warning('view %s uses a retired field beyond a plain '
                            '<field> node: archived', view_id)
        else:
            cr.execute('UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s',
                       (json.dumps(new), view_id))
            stripped += 1
        _journal(cr, batch=batch, kind='retired_view', identifier=str(view_id),
                 payload=json.dumps({'id': view_id, 'arch_db': arch_text,
                                     'archived': new is None}))
    return stripped, archived


def _restore_retired_field(cr, payload):
    if payload.get('column'):
        cr.execute('ALTER TABLE "%s" RENAME COLUMN "%s" TO "%s"'
                   % (payload['table'], payload['column'], payload['name']))
    if payload.get('relation_table'):
        original, quarantined = payload['relation_table']
        cr.execute('ALTER TABLE "%s" RENAME TO "%s"' % (quarantined, original))
    for xmlid in payload.get('xmlids') or []:
        cr.execute("""INSERT INTO ir_model_data
                      SELECT (json_populate_record(null::ir_model_data, %s::json)).*
                      ON CONFLICT (id) DO NOTHING""", (json.dumps(xmlid),))


def _studio_debris_status(cr):
    """État lisible de la quarantaine, pour un contrôle en lecture seule."""
    if not _table_exists(cr, JOURNAL_TABLE):
        return {'quarantined': False, 'batch': None, 'entries': {}}
    batch = _pending_batch(cr)
    if not batch:
        return {'quarantined': False, 'batch': None, 'entries': {}}
    cr.execute("""SELECT kind, count(*) FROM %s
                   WHERE batch = %%s AND restored_on IS NULL GROUP BY kind"""
               % JOURNAL_TABLE, (batch,))
    return {'quarantined': True, 'batch': batch, 'entries': dict(cr.fetchall())}
