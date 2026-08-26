"""
Migration 19.0.1.0.1 — pre-upgrade

Renommage x_studio_* → ca_diff_* des six champs de tender.order que ce module
déclare (Début de Marché, Coordinateur, Contact, Téléphone, Email, Notes
Marché). Il doit se faire ICI et pas dans cadiffusion_base : public_tender se
charge avant lui (dépendance), et son _auto_init créerait sinon des colonnes
ca_diff_* vides à côté des x_studio_* pleines.

La mécanique (table de correspondance, journal, rollback) vit dans
cadiffusion_base/field_rename.py — voir son en-tête. Idempotent.
"""
from odoo.addons.cadiffusion_base import _apply_field_rename
from odoo.addons.cadiffusion_base.field_rename import TENDER_BATCH


def migrate(cr, version):
    _apply_field_rename(cr, only=TENDER_BATCH)
