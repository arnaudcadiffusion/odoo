"""
Migration 19.0.1.0.27 — pre-upgrade

Premier lot du renommage x_studio_* → ca_diff_* : les 14 champs de transport
et de préparation des BL et des OF (TRANSPORT_BATCH), ceux passés en
copy=False par la 19.0.1.0.26+ (task#17998). Les sources de cette version les
déclarent déjà sous leur nouveau nom ; ce script renomme colonnes,
ir_model_fields, xmlids et références textuelles (filtres, exports, vues,
actions) AVANT que le registre ne se charge — sinon l'ORM créerait des
colonnes ca_diff_* vides à côté des x_studio_*.

Réversible : _rollback_field_rename(cr) relit le journal
cadiffusion_field_rename (voir l'en-tête de field_rename.py pour l'ordre des
opérations). Idempotent : sur une base déjà renommée, il n'y a simplement
plus rien à faire.
"""
from odoo.addons.cadiffusion_base import _apply_field_rename
from odoo.addons.cadiffusion_base.field_rename import TRANSPORT_BATCH


def migrate(cr, version):
    _apply_field_rename(cr, only=TRANSPORT_BATCH)
