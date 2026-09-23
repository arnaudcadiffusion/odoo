#!/usr/bin/env python3
"""Builds the tables of the Studio field rename (``x_studio_*`` -> ``cad_*``).

Development tool - NOT loaded by Odoo (not in the manifest nor imported). It
reads the models of ``addons_project`` with ``ast`` (no Odoo import, so it runs
outside the container), matches every declared ``x_studio_*`` field with the
customer's decision (``data/field_decisions.csv``) and writes:

* ``data/field_rename_map.csv`` - kept fields, under their new name::

      model,old_name,new_name,ttype,source

* ``data/field_retire_map.csv`` - deleted fields, removed from the sources and
  quarantined in the database (``studio_debris._retire_fields``)::

      model,name,ttype,source

``data/field_decisions.csv`` is the "Tri champs studio v15" spreadsheet agreed
with the customer (September 2026): one row per name, ``keep`` / ``delete``
and the target name. Names are not mechanical: two old names may converge on
the same target on different models (``x_studio_atradius`` on res.partner and
``x_studio_assurance_bc`` on sale.order both become ``cad_assurance``). Only
the (model, new name) pair has to stay unique.

ONE-SHOT tool: run it on sources still declaring ``x_studio_*``, BEFORE
``data/rename_source_fields.py``. Once the sources are rewritten it has nothing
left to read; both CSV files are then the reference, and
``tests/test_field_rename.py`` checks that they match the sources.

Usage (from the module root)::

    python3 data/build_field_rename_map.py
"""
import ast
import csv
import os

OLD_PREFIX = 'x_studio_'

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
# Studio fields are not all in this module: public_tender declares six on
# tender.order and report_cadiffusion uses some in its QWeb, so the tables
# cover the whole addons_project.
ADDONS_DIR = os.path.dirname(MODULE_DIR)
DECISIONS = os.path.join(HERE, 'field_decisions.csv')
RENAME_OUTPUT = os.path.join(HERE, 'field_rename_map.csv')
RETIRE_OUTPUT = os.path.join(HERE, 'field_retire_map.csv')

# Kept fields the sources do not declare yet: created with Studio in
# production AFTER the switch to v19, they only exist in the database (manual
# fields). The code declares them under their new name; the rename carries
# over their ir_model_fields row and the Studio views showing them.
DATABASE_ONLY = (
    # Related to partner_id.credit_on_hold (bi_customer_limit), shown on the
    # quotation form.
    ('sale.order', 'x_studio_related_field_3a8_1k1oqd81b', 'Boolean'),
)


def _model_name(node):
    """Model carried by a class: ``_name``, else ``_inherit``.

    ``_inherit`` may be a string or a list. When both are set ``_name`` names
    the model - public_tender writes ``_inherit = 'mail.thread'`` with
    ``_name = 'tender.order'``.
    """
    name = inherit = None
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if not isinstance(target, ast.Name):
                continue
            value = stmt.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                literal = value.value
            elif (isinstance(value, (ast.List, ast.Tuple)) and value.elts
                  and isinstance(value.elts[0], ast.Constant)):
                literal = value.elts[0].value
            else:
                continue
            if target.id == '_inherit':
                inherit = literal
            elif target.id == '_name':
                name = literal
    return name or inherit


def _field_type(value):
    """``fields.Integer(...)`` -> ``Integer``, None when it is not a field."""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id == 'fields'):
        return func.attr
    return None


def _sources():
    for dirpath, dirnames, filenames in os.walk(ADDONS_DIR):
        dirnames[:] = [name for name in dirnames if name != '__pycache__']
        for filename in sorted(filenames):
            if filename.endswith('.py'):
                yield os.path.join(dirpath, filename)


def declared_fields(prefix):
    """Fields declared in addons_project whose name starts with ``prefix``.

    [{'model', 'name', 'ttype', 'source'}, ...] - one row per (model, field):
    the six tender.order fields are declared both by public_tender and by
    cadiffusion_base/models/tender_order.py, "source" lists every file.
    """
    merged = {}
    for path in sorted(_sources()):
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        if prefix not in source:
            continue
        tree = ast.parse(source, filename=path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            model = _model_name(node)
            if not model:
                continue
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                ttype = _field_type(stmt.value)
                if not ttype:
                    continue
                for target in stmt.targets:
                    if not (isinstance(target, ast.Name)
                            and target.id.startswith(prefix)):
                        continue
                    key = (model, target.id)
                    relpath = os.path.relpath(path, ADDONS_DIR)
                    if key in merged:
                        merged[key]['source'] += ';' + relpath
                    else:
                        merged[key] = {'model': model, 'name': target.id,
                                       'ttype': ttype, 'source': relpath}
    return sorted(merged.values(), key=lambda row: (row['model'], row['name']))


def load_decisions():
    with open(DECISIONS, encoding='utf-8') as handle:
        return {row['old_name']: row for row in csv.DictReader(handle)}


def collect():
    """(rows to rename, rows to retire). Raises when a declared field has no
    decision: it would silently be left behind."""
    decisions = load_decisions()
    renames, retires, undecided = [], [], []
    for field in declared_fields(OLD_PREFIX):
        decision = decisions.get(field['name'])
        if decision is None:
            undecided.append('%s.%s' % (field['model'], field['name']))
        elif decision['decision'] == 'keep':
            renames.append({'model': field['model'], 'old_name': field['name'],
                            'new_name': decision['new_name'],
                            'ttype': field['ttype'], 'source': field['source']})
        else:
            retires.append(field)
    if undecided:
        raise SystemExit('fields without a decision in %s: %s'
                         % (DECISIONS, ', '.join(undecided)))
    for model, old, ttype in DATABASE_ONLY:
        renames.append({'model': model, 'old_name': old,
                        'new_name': decisions[old]['new_name'],
                        'ttype': ttype, 'source': ''})
    renames.sort(key=lambda row: (row['model'], row['old_name']))
    return renames, retires


def main():
    renames, retires = collect()
    # Two old names of the same model must never land on the same new name:
    # the second one would overwrite the first.
    targets = {}
    for row in renames:
        key = (row['model'], row['new_name'])
        if key in targets:
            raise SystemExit('collision on %s.%s: %s and %s'
                             % (key + (targets[key], row['old_name'])))
        targets[key] = row['old_name']
    with open(RENAME_OUTPUT, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(
            handle, fieldnames=('model', 'old_name', 'new_name', 'ttype', 'source'))
        writer.writeheader()
        writer.writerows(renames)
    with open(RETIRE_OUTPUT, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=('model', 'name', 'ttype', 'source'))
        writer.writeheader()
        writer.writerows(retires)
    print('%s: %d fields renamed' % (RENAME_OUTPUT, len(renames)))
    print('%s: %d fields retired' % (RETIRE_OUTPUT, len(retires)))


if __name__ == '__main__':
    main()
