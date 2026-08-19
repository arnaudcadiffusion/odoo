"""
Migration 19.0.1.0.18 — post-upgrade

Reprise des personnalisations Studio faites À LA MAIN sur la base de test
après l'upgrade v15 → v19 (11 vues créées du 23/06/2026 au 16/08/2026 par
atoulemonde et le compte technique). Elles ne vivaient que dans cette base :
la bascule production repart du dump v15, elles y auraient été perdues.

Six d'entre elles portaient une vraie personnalisation, désormais en XML dans
views/studio_post_upgrade_views.xml (bouton « Envoyer Chorus » en liste de
factures, visibilité du bouton « Envoyer », mode d'envoi de facture sur les
contacts enfants, interdiction de créer un article depuis une ligne de vente,
ordre des colonnes de la liste des contacts, heure masquée sur les dates des
règles de prix). Les cinq autres ne posaient que options={"numeric": true} sur
des champs date : le module ca_date_format, passé en auto_install, couvre
maintenant TOUS les champs date de l'instance.

Ce script archive les vues Studio d'origine pour éviter que les deux jeux se
superposent. La logique vit dans
``cadiffusion_base._archive_post_upgrade_studio_views``, également exécutée par
le post_init_hook pour les installs fraîches (rebuilds Odoo.sh par upgrade
complet, bascule production) où les scripts de migrations/ ne tournent pas —
elle y est simplement sans effet, ces vues n'existant pas.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _archive_post_upgrade_studio_views


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _archive_post_upgrade_studio_views(env)
