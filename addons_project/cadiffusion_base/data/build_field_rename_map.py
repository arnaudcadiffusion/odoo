#!/usr/bin/env python3
"""Générateur de data/field_rename_map.csv (renommage x_studio_* → ca_diff_*).

Outil de développement — PAS chargé par Odoo (absent du manifest et des
imports). Il lit les modèles du module avec ``ast`` (aucun import d'Odoo, donc
exécutable hors conteneur) et écrit la table de correspondance que
``field_rename.py`` rejoue ensuite, dans un sens comme dans l'autre :

    model,old_name,new_name,ttype,source

La règle de nommage est mécanique — ``x_studio_`` devient ``ca_diff_`` et le
reste du nom est conservé tel quel, y compris les suffixes illisibles hérités
de Studio (``x_studio_field_GzsJK`` → ``ca_diff_field_GzsJK``). Rien ici ne
touche à la base ni aux sources : c'est le CSV produit qui fait autorité pour
les deux opérations réversibles.

Usage (depuis la racine du module) :

    python3 data/build_field_rename_map.py

À relancer après tout ajout ou retrait d'un champ ``x_studio_*`` dans
``models/`` — ``tests/test_field_rename.py`` échoue si le CSV a dérivé.
"""
import ast
import csv
import os

OLD_PREFIX = 'x_studio_'
NEW_PREFIX = 'ca_diff_'

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
# Les champs Studio ne sont pas tous dans ce module : public_tender en déclare
# six sur tender.tender, et report_cadiffusion en référence dans ses QWeb. La
# table de correspondance couvre donc tout addons_project — un renommage
# partiel casserait les rapports.
ADDONS_DIR = os.path.dirname(MODULE_DIR)
OUTPUT = os.path.join(HERE, 'field_rename_map.csv')


def _model_name(node):
    """Nom du modèle porté par une classe : ``_name`` sinon ``_inherit``.

    ``_inherit`` peut être une chaîne ou une liste. Quand les deux sont
    présents c'est ``_name`` qui nomme le modèle — public_tender écrit
    ``_inherit = 'mail.thread'`` avec ``_name = 'tender.order'``.
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
    """``fields.Integer(...)`` → ``Integer``, sinon None si ce n'est pas un champ."""
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


def collect():
    rows = []
    for path in sorted(_sources()):
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        if OLD_PREFIX not in source:
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
                    if (isinstance(target, ast.Name)
                            and target.id.startswith(OLD_PREFIX)):
                        rows.append({
                            'model': model,
                            'old_name': target.id,
                            'new_name': NEW_PREFIX + target.id[len(OLD_PREFIX):],
                            'ttype': ttype,
                            'source': os.path.relpath(path, ADDONS_DIR),
                        })
    # Un même champ peut être déclaré par deux modules — les six champs de
    # tender.order le sont à la fois par public_tender et par
    # cadiffusion_base/models/tender_order.py. Une seule ligne par (modèle,
    # champ), les fichiers concernés listés dans « source ».
    merged = {}
    for row in rows:
        key = (row['model'], row['old_name'])
        if key in merged:
            merged[key]['source'] += ';' + row['source']
        else:
            merged[key] = row
    return sorted(merged.values(), key=lambda row: (row['model'], row['old_name']))


def main():
    rows = collect()
    # Deux anciens noms différents ne doivent jamais tomber sur le même
    # nouveau nom : la bijection est ce qui rend le retour arrière possible.
    collisions = sorted({
        (row['model'], row['new_name'])
        for row in rows
        if sum(1 for other in rows
               if (other['model'], other['new_name'])
               == (row['model'], row['new_name'])) > 1
    })
    if collisions:
        raise SystemExit('collision de nouveaux noms : %s' % collisions)
    with open(OUTPUT, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(
            handle, fieldnames=('model', 'old_name', 'new_name', 'ttype', 'source'))
        writer.writeheader()
        writer.writerows(rows)
    models = sorted({row['model'] for row in rows})
    print('%s : %d champs sur %d modèles' % (OUTPUT, len(rows), len(models)))
    for model in models:
        print('  %-24s %d' % (model, sum(1 for r in rows if r['model'] == model)))


if __name__ == '__main__':
    main()
