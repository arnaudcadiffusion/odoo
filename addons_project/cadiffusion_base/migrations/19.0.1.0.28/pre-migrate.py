"""
Migration 19.0.1.0.28 — pre-upgrade

Second et dernier lot du renommage x_studio_* → ca_diff_* : tous les champs
restants de la table de correspondance (data/field_rename_map.csv), soit tout
ce que les sources déclarent hors le lot transport (.27) et les six champs de
tender.order (pre-migrate de public_tender, chargé avant ce module).

Idempotent : les champs déjà renommés par ces deux passages sont absents de
ir_model_fields sous leur ancien nom, donc ignorés. Réversible lot par lot via
_rollback_field_rename(cr) — en-tête de field_rename.py.
"""
from odoo.addons.cadiffusion_base import _apply_field_rename


def migrate(cr, version):
    _apply_field_rename(cr)
