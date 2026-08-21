"""
Migration 19.0.1.0.21 — post-upgrade

Deux dérives relevées sur la base de test le 19/08/2026, invisibles jusque-là
parce que rien ne relit ces états entre deux builds :

  - huit vues de nos modules archivées par la plateforme d'upgrade v15 → v19.
    Un ``-u`` ne les rallume pas (un ``<record>`` n'écrit que les champs qu'il
    déclare, et ``active`` n'en fait pas partie) : la personnalisation reste
    muette. La plus visible est le pied de page des PDF
    (``report_cadiffusion.report_external_layout_boxed``), alors que
    CA DIFFUSION imprime justement avec le layout « boxed ». L'alignement ne
    porte pas que sur ces huit-là : il rejoue l'instantané de la base de
    référence (data/reference_view_state.csv), dans les deux sens, ce qui
    couvre aussi les vues Studio à garder archivées et, sans rien à écrire de
    plus, les vues des migrations suivantes ;

  - quatre taxes 0% de vente de CA DIFFUSION portant la catégorie UNECE E
    (exonéré) alors que leur nom dit export ou livraison intracommunautaire
    (G et K). Séquelle de la première version de
    ``_configure_unece_exo_taxes``, qui cherchait « EXO » en ilike : en v19 le
    ilike matche par sous-séquence de caractères et attrapait « EXPORT ». La
    version suivante ne posait plus de code fautif mais ne réparait pas ceux
    déjà écrits — c'est fait ici. Au passage, la fonction écrit désormais les
    many2one ``unece_type_id`` / ``unece_categ_id`` au lieu des related
    stockés ``unece_*_code``, dont la valeur ne survit pas au premier recalcul
    (deux taxes « TVA 0% EXO » étaient dans ce cas sur la base de test).

Ce qui n'est PAS fait ici : poser un code sur les taxes export /
intracommunautaires qui n'en ont jamais eu (59 sur la base de test, toutes
sociétés confondues). C'est un arbitrage comptable, pas une régression ;
``data/check_post_build.py`` les liste pour décision.

Les deux fonctions vivent dans ``cadiffusion_base`` et sont également
exécutées par le post_init_hook pour les installs fraîches (rebuilds Odoo.sh
par upgrade complet, bascule production), où les scripts de migrations/ ne
tournent pas.

L'état attendu après ce script est contrôlable à tout moment avec
``data/check_post_build.py`` (odoo shell, lecture seule).
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import (
    _apply_reference_state,
    _configure_unece_exo_taxes,
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_reference_state(env)
    _configure_unece_exo_taxes(env)
