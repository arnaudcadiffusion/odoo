#!/usr/bin/env python3
"""Renames the Studio fields in the SOURCES (x_studio_* -> cad_*).

Development tool - NOT loaded by Odoo (not in the manifest nor imported). It
rewrites every .py / .xml / .js / .csv of ``addons_project`` with the mapping
table ``data/field_rename_map.csv``, on word boundaries only. The logic lives
in ``field_rename.py`` (module root): this script is only a command line, and
the Odoo import is optional there, so it runs outside the container.

    python3 data/rename_source_fields.py             # x_studio_ -> cad_
    python3 data/rename_source_fields.py --dry-run   # list without writing

``--rollback`` (cad_ -> x_studio_) skips the converging names (cad_assurance,
cad_type_container): revert the sources with git instead.

It touches neither the database nor git: review the ``git diff`` before
committing. The order of the forward/backward operations (sources and
database) is documented at the top of ``field_rename.py``.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
ADDONS_DIR = os.path.dirname(MODULE_DIR)

sys.path.insert(0, MODULE_DIR)
from field_rename import TENDER_BATCH, _rewrite_sources  # noqa: E402

# Named batches.
BATCHES = {'tender': TENDER_BATCH}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--rollback', action='store_true',
                        help='reverse direction: cad_* -> x_studio_*')
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
             'cad_ -> x_studio_' if options.rollback else 'x_studio_ -> cad_',
             'lot de %d champs' % len(only) if only else 'tous les champs'))


if __name__ == '__main__':
    main()
