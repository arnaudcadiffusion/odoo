"""
Migration 19.0.1.0.17 — post-upgrade

Conditionnements achats + reprise des choix v15.

Cette version ajoute carton_uom_id / nb_carton sur purchase.order.line
(mêmes colonnes Conditionnement / Nb Carton que côté vente) ; le champ stocké
carton_uom_id vient d'être initialisé par l'ORM avec le défaut « plus grand
carton du produit » sur toutes les lignes (vente : déjà fait par une version
précédente).

On applique ensuite les choix v15 explicites qui diffèrent de ce défaut
(product_packaging_id des lignes v15, perdu par la plateforme d'upgrade),
embarqués dans data/carton_uom_v15_*.csv, puis on recalcule le
conditionnement des moves ouverts qui en dépendent. La logique vit dans
``cadiffusion_base._apply_v15_carton_choices``, également exécutée par le
post_init_hook pour les installs fraîches (rebuilds Odoo.sh par upgrade
complet) où les scripts de migrations/ ne tournent pas.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _apply_v15_carton_choices


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_v15_carton_choices(env)
