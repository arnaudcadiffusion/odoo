#!/usr/bin/env python3
"""Renomme les champs Studio dans les SOURCES (x_studio_* ↔ ca_diff_*).

Outil de développement — PAS chargé par Odoo (absent du manifest et des
imports). Il réécrit tous les .py / .xml / .js / .csv de ``addons_project``
avec la table de correspondance ``data/field_rename_map.csv``, sur frontière de
mot uniquement, dans un sens ou dans l'autre. La logique vit dans
``field_rename.py`` (racine du module) : ce script n'est qu'une ligne de
commande, et l'import d'Odoo y est facultatif, donc il tourne hors conteneur.

    python3 data/rename_source_fields.py             # x_studio_ → ca_diff_
    python3 data/rename_source_fields.py --rollback  # ca_diff_ → x_studio_
    python3 data/rename_source_fields.py --dry-run   # liste sans écrire

Il ne touche ni à la base ni à git : relire le ``git diff`` avant de committer.
L'ordre des opérations aller/retour (sources et base) est documenté en tête de
``field_rename.py`` — s'en écarter laisse la base et le code désaccordés.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
ADDONS_DIR = os.path.dirname(MODULE_DIR)

sys.path.insert(0, MODULE_DIR)
from field_rename import TRANSPORT_BATCH, _rewrite_sources  # noqa: E402

# Lots nommés : renommer par groupes fonctionnels plutôt qu'en une fois.
BATCHES = {'transport': TRANSPORT_BATCH}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--rollback', action='store_true',
                        help='sens inverse : ca_diff_* → x_studio_*')
    parser.add_argument('--dry-run', action='store_true',
                        help='affiche les fichiers concernés sans les écrire')
    parser.add_argument('--root', default=ADDONS_DIR,
                        help='racine à réécrire (défaut : %(default)s)')
    parser.add_argument('--batch', choices=sorted(BATCHES),
                        help='ne renommer que ce lot (défaut : tous les champs)')
    parser.add_argument('--only',
                        help='ne renommer que ces anciens noms, séparés par des virgules')
    options = parser.parse_args()

    only = BATCHES[options.batch] if options.batch else None
    if options.only:
        only = tuple(name.strip() for name in options.only.split(',') if name.strip())

    touched = _rewrite_sources(options.root, reverse=options.rollback,
                               dry_run=options.dry_run, only=only)
    total = sum(count for _path, count in touched)
    for path, count in touched:
        print('%4d  %s' % (count, os.path.relpath(path, options.root)))
    print('%s%d occurrences dans %d fichiers (%s, %s)'
          % ('[dry-run] ' if options.dry_run else '',
             total, len(touched),
             'ca_diff_ → x_studio_' if options.rollback else 'x_studio_ → ca_diff_',
             'lot de %d champs' % len(only) if only else 'tous les champs'))


if __name__ == '__main__':
    main()
