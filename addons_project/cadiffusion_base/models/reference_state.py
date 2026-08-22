"""Point d'entrée ``<function>`` du rejeu de l'instantané de référence.

``data/reference_state.xml`` — premier fichier de données du manifest —
appelle ``apply_reference_state`` à chaque install et à chaque ``-u`` du
module. C'est ce qui manquait : un script de migrations/ ne tourne qu'au saut
de version et le post_init_hook qu'à l'install, alors qu'Odoo.sh met le module
à jour sans toucher à sa version dès qu'un de ses fichiers change, et qu'une
base restaurée peut déjà porter la dernière version. Plus rien ne rejouait
l'instantané : le build 36768993 du 21/08/2026 a fini avec les vues Studio
encore actives — cinq d'entre elles, invalides en v19 (attribut ``modifiers``
de Studio v15, ``quick_add`` devenu ``quick_create`` sur le calendrier),
remontaient en « invalid custom view(s) » en fin de chargement.

La logique (prise, comparaison, rejeu) vit dans
``cadiffusion_base/reference_state.py`` ; ce modèle n'a pas de table.
"""
from odoo import api, models

from ..reference_state import _apply_reference_state


class CadiffusionReferenceState(models.AbstractModel):
    _name = 'cadiffusion.reference.state'
    _description = "Rejeu de l'instantané de référence de la configuration"

    @api.model
    def apply_reference_state(self):
        """Réapplique les specs APPLY de l'instantané, signale les specs REPORT."""
        _apply_reference_state(self.env)
