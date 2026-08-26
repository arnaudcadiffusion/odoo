#!/usr/bin/env python3
"""Inventaire des séquelles Studio / v15 (test / staging / production).

Outil de développement — PAS chargé par Odoo (absent du manifest et des
imports), au même titre que check_post_build.py.

EN LECTURE SEULE : aucune écriture, aucun commit. Il affiche ce que
``studio_debris.py`` sait reconnaître — champs fantômes, colonnes orphelines,
tables mortes — pour que la décision de mise en quarantaine se prenne sur des
chiffres relevés sur LA base concernée, et pas sur ceux d'une autre.

Usage (odoo shell, script sur stdin) :

  local :
    docker exec -i odoo19 odoo shell -c /etc/odoo/odoo.conf --no-http \
      --addons-path=/mnt/enterprise,/mnt/extra-addons,/mnt/shared-addons,\
/mnt/extra-addons/cadiffusionV19/addons_project,\
/mnt/extra-addons/cadiffusionV19/addons_oca,\
/mnt/extra-addons/cadiffusionV19/addons_tier \
      -d cadiffusion \
      < addons_project/cadiffusion_base/data/check_studio_debris.py

  Odoo.sh (shell du build) :
    odoo-bin shell -d $PGDATABASE < check_studio_debris.py

La mise en quarantaine, elle, se lance à la main et catégorie par catégorie —
voir l'en-tête de studio_debris.py.
"""
from odoo.addons.cadiffusion_base import _studio_debris, _studio_debris_status


def report(env):
    debris = _studio_debris(env.cr)
    status = _studio_debris_status(env.cr)

    ghosts = debris['ghost_fields']
    print('\n== Champs fantômes (%d) ==' % len(ghosts))
    print('Lignes de ir_model_fields sans champ derrière. Non stockés, donc')
    print('aucune donnée en jeu ; invisibles dans l\'interface, qui lit le')
    print('registre Python et non ir_model_fields.')
    for ghost in ghosts:
        print('  %-14s %-34s %s' % (ghost['model'], ghost['name'], ghost['reason']))

    columns = debris['orphan_columns']
    print('\n== Colonnes orphelines (%d) ==' % len(columns))
    print('Colonnes stockées qu\'aucun champ n\'expose : la donnée est là, plus')
    print('rien ne la lit ni ne l\'écrit.')
    for column in columns:
        print('  %-22s %-30s %8d valeurs'
              % (column['table'], column['column'], column['values']))

    tables = debris['dead_tables']
    print('\n== Tables mortes (%d) ==' % len(tables))
    print('Tables dont le modèle n\'est plus enregistré — reliques de la')
    print('bascule v15, jamais supprimées par la plateforme d\'upgrade.')
    for table in tables:
        print('  %-30s %10d lignes' % (table['table'], table['rows']))

    print('\n== Quarantaine ==')
    if status['quarantined']:
        print('  lot %s en cours : %s' % (status['batch'], status['entries']))
        print('  restauration : _restore_studio_debris(env.cr) puis env.cr.commit()')
    else:
        print('  aucune quarantaine en cours')

    total = len(ghosts) + len(columns) + len(tables)
    print('\n%d objet(s) recensé(s). Rien n\'a été modifié.' % total)


report(env)  # noqa: F821 - fourni par odoo shell
