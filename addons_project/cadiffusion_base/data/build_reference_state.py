#!/usr/bin/env python3
"""Générateur des instantanés de référence : état des vues et modules installés.

Outil de développement — PAS chargé par Odoo (absent du manifest et des
imports), au même titre que build_carton_uom_v15.py.

La base de recette — celle que le client a validée fonctionnalité par
fonctionnalité — fait référence. Un CSV par entrée de ``_REFERENCE_SPECS``
(__init__.py) : état actif des vues, cibles des rapports, code-barres des types
d'opération, réglages des sociétés, modules installés, paramètres système,
actions, filtres.

Ces instantanés sont rejoués à chaque install et à chaque ``-u`` du module
par ``_apply_reference_state`` (reference_state.py, appelée par
``data/reference_state.xml`` puis par le post_init_hook) et servent de base de
comparaison à ``data/check_post_build.py`` sur les autres bases — remigration
à blanc du staging, bascule de production.

C'est ce qui rend le contrôle générique : AUCUNE liste tenue à la main. Une
migration qui livre une vue, en archive une, réaffecte un rapport ou change un
réglage est couverte dès que l'instantané est régénéré — un seul geste. Le
périmètre s'élargit en ajoutant une ligne à ``_REFERENCE_SPECS``.

Usage (odoo shell, sur la base DE RÉFÉRENCE) :

    docker exec -i odoo19 odoo shell -c /etc/odoo/odoo.conf --no-http \\
      --addons-path=/mnt/enterprise,/mnt/extra-addons,/mnt/shared-addons,\\
/mnt/extra-addons/cadiffusionV19/addons_project,\\
/mnt/extra-addons/cadiffusionV19/addons_oca,\\
/mnt/extra-addons/cadiffusionV19/addons_tier \\
      -d cadiffusion_test \\
      < addons_project/cadiffusion_base/data/build_reference_state.py

À REGÉNÉRER depuis la base de recette dès qu'une fonctionnalité y est
validée. Les CSV sont relus tels quels par le hook : ce qu'ils contiennent
devient l'état attendu partout.

Les valeurs des paramètres système dont la clé évoque un secret (token, key,
password, uuid…) sont remplacées par ``<masqué>`` : seule leur présence est
comparée, rien de sensible n'entre dans le dépôt.
"""
import csv
import os

from odoo.modules.module import get_module_path

from odoo.addons.cadiffusion_base import _REFERENCE_SPECS, _reference_snapshot

DATA_DIR = os.path.join(get_module_path('cadiffusion_base'), 'data')

for name, model, key, fields, mode in _REFERENCE_SPECS:
    if model not in env:
        print("%-20s modèle %s absent de cette base — ignoré" % (name, model))
        continue
    snapshot = _reference_snapshot(env, model, key, fields)
    path = os.path.join(DATA_DIR, 'reference_%s.csv' % name)
    with open(path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, ['_key'] + list(fields))
        writer.writeheader()
        for identifier in sorted(snapshot):
            writer.writerow(dict(snapshot[identifier], _key=identifier))
    print("%-20s %-26s %5s enregistrement(s)  [%s]"
          % (name, model, len(snapshot), mode))
