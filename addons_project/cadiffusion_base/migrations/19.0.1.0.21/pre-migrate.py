"""
Migration 19.0.1.0.21 — pre-upgrade

Installe ``ca_date_format`` sur les bases déjà créées.

Le module est pourtant en ``auto_install`` et sa seule dépendance
(``cadiffusion_base``) est installée — mais auto_install n'est évalué qu'à la
CRÉATION de la base : la boucle qui marque les modules auto-installables vit
dans ``odoo/modules/db.py::initialize``, appelée seulement quand la base n'est
pas encore initialisée. Sur une base existante — le staging remigré, ou toute
base déjà installée — le module n'est jamais rattrapé, sans le moindre message.
C'est ce qui explique son absence du build du 19/08/2026.

Le marquer « to install » suffit : ``load_modules`` reboucle tant qu'il reste
des modules dans cet état, il sera donc installé dans le même cycle d'upgrade.
C'est la mécanique qu'utilise ``util.force_install_module`` des scripts
d'upgrade d'Odoo.

Sans effet sur une bascule de production par upgrade complet (base neuve), où
auto_install fait déjà le travail, ni si le module a été désinstallé
volontairement (état 'to remove' / 'uninstallable' non touché).
"""
import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _apply_reference_state

_logger = logging.getLogger(__name__)

# Modules du dépôt à poser sur les bases existantes. Une ligne de plus suffit
# pour le prochain : la liste vit ici plutôt que dans __init__.py parce qu'un
# pre-migrate tourne avant le chargement du paquet Python du module.
_FORCE_INSTALL_MODULES = ('ca_date_format',)


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_module_module
           SET state = 'to install'
         WHERE name IN %s
           AND state = 'uninstalled'
        RETURNING name
    """, (_FORCE_INSTALL_MODULES,))
    forced = [row[0] for row in cr.fetchall()]
    if forced:
        _logger.info(
            "cadiffusion_base: %s marqué(s) « to install » — auto_install ne "
            "rattrape pas les bases existantes", forced)

    # L'état des vues est aligné ICI, avant le chargement des fichiers data :
    # une de nos vues peut cibler un champ apporté par la vue d'un autre module
    # (invoice_sending_method à côté de fr_chorus_service_id, par exemple), et
    # un xpath ne résout que si cette vue-là est active. Le faire en
    # post-migrate est trop tard — le chargement a déjà échoué.
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_reference_state(env, only=('views',))
