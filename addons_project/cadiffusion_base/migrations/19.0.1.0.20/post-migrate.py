"""
Migration 19.0.1.0.20 — post-upgrade

Deux réglages posés à la main sur la base de test et que la plateforme
d'upgrade ne rapporte pas de la production :

  - le code-barres des types d'opération « Réceptions » et « Livraisons » de
    l'entrepôt principal, ramené par l'upgrade aux valeurs par défaut d'Odoo
    (WH-RECEIPTS / WH-DELIVERY) alors que les douchettes et les étiquettes sont
    calées sur WHIN / WHOUT ;
  - ``stock_move_email_validation`` sur CA DIFFUSION.

Ces deux écritures (17/08 et 19/08/2026) ne laissaient aucune trace
exploitable en SQL : ni ``res.company`` ni ``stock.picking.type`` ne sont
suivis par le chatter, et aucune autre écriture ne les accompagnait. Elles ont
été identifiées en comparant champ par champ la base de test de mai (build
35344202) avec l'upgrade neuf du 19/08 (build 36652311), qui porte encore les
valeurs de production.

La logique vit dans
``cadiffusion_base._apply_manual_settings_from_test_base``, également exécutée
par le post_init_hook pour les installs fraîches (rebuilds Odoo.sh par upgrade
complet, bascule production) où les scripts de migrations/ ne tournent pas.
"""
from odoo import SUPERUSER_ID, api

from odoo.addons.cadiffusion_base import _apply_manual_settings_from_test_base


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _apply_manual_settings_from_test_base(env)
