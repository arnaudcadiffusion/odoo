"""
Migration 19.0.1.0.2 — pre-upgrade

Retour arrière du renommage des six champs de tender.order que ce module
déclare (Début de Marché, Coordinateur, Contact, Téléphone, Email, Notes
Marché), appliqué par la 19.0.1.0.1 aujourd'hui supprimée.

Il doit se faire ICI et pas dans cadiffusion_base, pour la même raison qu'à
l'aller : public_tender se charge avant lui (cadiffusion_base en dépend), et
son _auto_init recréerait des colonnes x_studio_* vides à côté des ca_diff_*
pleines avant que le pre-migrate .29 de cadiffusion_base ne passe.

Le ciblage se fait par les champs, pas par le numéro de lot : celui-ci varie
d'une base à l'autre selon l'ordre des upgrades. Sur une base où ces champs
ont été renommés par le lot global de cadiffusion_base plutôt que par un lot
dédié, c'est ce lot-là qui est défait ici — plus tôt que prévu, mais dans le
bon ordre, et le pre-migrate .29 n'aura simplement plus rien à faire.

La mécanique (journal, rollback) vit dans cadiffusion_base/field_rename.py —
voir son en-tête. Idempotent.
"""
from odoo.addons.cadiffusion_base.field_rename import (
    TENDER_BATCH,
    _rollback_field_rename_batches,
)


def migrate(cr, version):
    _rollback_field_rename_batches(cr, only=TENDER_BATCH)
