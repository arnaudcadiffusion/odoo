"""
Migration 19.0.1.0.19 — post-upgrade

Installe ``ca_date_format`` sur les bases où cadiffusion_base est DÉJÀ installé.

``ca_date_format`` (format de date numérique jj/mm/aaaa sur tous les champs date
de l'instance) est passé en ``auto_install`` : sa seule dépendance étant
cadiffusion_base, Odoo l'installe tout seul lors d'une installation fraîche —
c'est le cas de la bascule production et des rebuilds Odoo.sh par upgrade
complet.

Mais ``ir.module.module.button_install`` n'installe un module auto_install que
si au moins une de ses dépendances est à l'état ``to install`` (voir
``must_install``). Sur une base où cadiffusion_base est déjà ``installed``, la
condition n'est jamais remplie et le module resterait indéfiniment
désinstallé : d'où cette installation explicite.

``button_install`` place le module en ``to install`` ; la boucle STEP 3 de
``odoo.modules.loading.load_modules`` le charge dans le même run, après ce
script.

Idempotent : ne fait rien si le module est déjà installé ou absent du dépôt.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    module = env['ir.module.module'].search(
        [('name', '=', 'ca_date_format'), ('state', '=', 'uninstalled')], limit=1)
    if module:
        module.button_install()
