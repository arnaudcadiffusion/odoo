"""
Migration 19.0.1.0.32 - pre-upgrade

Applies the "Tri champs studio v15" spreadsheet agreed with the customer
(data/field_decisions.csv), BEFORE the registry reloads on the new sources:

1. Ghost fields: the delegation mirrors (product.product, res.users) of
   Studio fields that no longer exist, marked for deletion. Not stored, no
   data; the rows are saved in the studio_debris journal and removed.
2. Retired fields: the fields removed from the sources
   (data/field_retire_map.csv). Their columns are set aside as zz_dead_*,
   their xmlids detached so that the end of the upgrade does not DROP them,
   and the favourite filters naming them archived (studio_debris.py).
3. Rename x_studio_* -> cad_* of the kept fields
   (data/field_rename_map.csv): columns, ir_model_fields, xmlids and every
   text naming them (filters, exports, views, actions...), journaled row by
   row in cadiffusion_field_rename (field_rename.py). The six tender.order
   fields were already renamed by the pre-migrate of public_tender.

Idempotent. Undone by _restore_studio_debris (1, 2) and
_rollback_field_rename_batches (3), from a pre-migrate travelling with the
revert commit - see the headers of studio_debris.py and field_rename.py.
"""
import logging

from odoo.addons.cadiffusion_base.field_rename import _apply_field_rename
from odoo.addons.cadiffusion_base.studio_debris import (
    _decided_deletions,
    _quarantine_studio_debris,
    _retire_fields,
)

_logger = logging.getLogger(__name__)

BLOQUER = ('sale.order', 'x_studio_related_field_3a8_1k1oqd81b')
BLOQUER_RELATED = 'partner_id.credit_on_hold'


def _check_bloquer(cr):
    # The Studio field only exists in production: the code now declares it
    # as cad_bloquer, related to partner_id.credit_on_hold. Say so loudly if
    # the production field turns out to point elsewhere.
    cr.execute("""SELECT related FROM ir_model_fields
                   WHERE model = %s AND name = %s""", BLOQUER)
    row = cr.fetchone()
    if row and row[0] != BLOQUER_RELATED:
        _logger.warning(
            "%s.%s is related to %r, cad_bloquer is declared as %r: check the "
            "quotation form", BLOQUER[0], BLOQUER[1], row[0], BLOQUER_RELATED)


def migrate(cr, version):
    _quarantine_studio_debris(cr, ghost_fields=True, only=_decided_deletions())
    _retire_fields(cr)
    _check_bloquer(cr)
    _apply_field_rename(cr)
