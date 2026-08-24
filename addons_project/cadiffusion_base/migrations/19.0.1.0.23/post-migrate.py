"""
Migration 19.0.1.0.23 — post-upgrade

Supprime les vues dont le type n'existe plus dans Odoo 19 : deux vues Studio
de type « dashboard » (v15, web_dashboard) que la plateforme d'upgrade a
recopiées telles quelles. La valeur reste en base alors qu'aucun module ne la
déclare plus, et le champ « Type » de Paramètres → Technique → Vues plante à
l'affichage — SelectionField cherche le libellé, ne le trouve pas et lit
``undefined[1]``. C'est le « An error occured in the owl lifecycle » remonté
en production le 24/08/2026 à 08:05 GMT.

L'instantané de référence archive déjà ces deux vues
(data/reference_views.csv), ce qui les sort de la liste filtrée « actives » —
mais pas du filtre « Archivé », ni de leur propre formulaire. D'où la
suppression, définitive et sans effet de bord : plus aucun moteur de rendu ne
connaît ce type de vue, et rien ne les référence (héritage, action, vue de
recherche).

La logique vit dans ``cadiffusion_base._delete_views_with_unknown_type``,
également exécutée par le post_init_hook pour les installs fraîches (rebuilds
Odoo.sh par upgrade complet, bascule production) où les scripts de migrations/
ne tournent pas.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _delete_views_with_unknown_type


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _delete_views_with_unknown_type(env)
