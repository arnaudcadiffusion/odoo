"""
Migration 19.0.1.0.14 — post-upgrade

Réparation des données laissées par la plateforme d'upgrade v15 → v19 :
facteurs UDM à NULL, conditionnements des moves remis à la pièce,
réservations perdues. La logique vit dans
``cadiffusion_base._repair_upgrade_data`` (idempotente), également exécutée
par le post_init_hook pour les installations fraîches (rebuilds Odoo.sh par
upgrade complet, migration prod) où les scripts de migrations/ ne tournent
pas.

Historique : la réparation était initialement prévue en 19.0.1.0.12 mais le
script a été perdu avant commit ; la base Test est ensuite passée en .13 par
une installation fraîche (donc sans réparation). Ce script en .14 rattrape
les bases déjà installées en .12/.13.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _repair_upgrade_data


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _repair_upgrade_data(env)
