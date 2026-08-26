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

Les noms cités dans ce fichier sont ceux que ces objets portent EN BASE. Ils ne
suivent pas le renommage ``x_studio_*`` → ``ca_diff_*`` — un objet que plus
aucun code ne déclare n'a rien qui puisse le renommer — et ``field_rename.py``
laisse donc ce fichier de côté quand il réécrit les sources.
"""
import json
import logging

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
                              dead_tables=False):
    """Met de côté les séquelles demandées. Sans argument : ne fait rien.

    Chaque catégorie est explicite parce qu'elles n'ont ni le même poids ni le
    même risque : supprimer 23 lignes de métadonnées inertes n'engage rien,
    écarter 340 000 lignes de facturation v15 se décide.
    """
    if not (ghost_fields or orphan_columns or dead_tables):
        _logger.info('aucune catégorie demandée — rien à faire')
        return None

    _ensure_journal(cr)
    batch = _next_batch(cr)
    debris = _studio_debris(cr)
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
