import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CaDiffusionPreparer(models.Model):
    """Configurable lists backing the preparer Selection fields
    (transfers and MOs). Invariant: every stored value belongs to the
    choices of its list — a value outside the list makes the record
    undisplayable (blank tab in the OWL SelectionField)."""

    _name = 'ca.diffusion.preparer'
    _description = 'Preparer (configurable list)'
    _order = 'list_type, sequence, id'

    _name_type_uniq = models.Constraint(
        'unique(name, list_type)',
        "This name is already in the list.")

    name = fields.Char(string='Name', required=True)
    list_type = fields.Selection(
        selection=[
            ('transfer', 'Transfers'),
            ('kit', 'Kits'),
        ],
        string='List',
        required=True,
        default='transfer',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    # (model, field) served by each list.
    _LIST_FIELDS = {
        'transfer': [('stock.picking', 'x_studio_prparateur')],
        'kit': [('mrp.production', 'x_studio_preparateur_kit')],
    }

    # Former hardcoded lists, to seed a database with empty columns.
    _SEED_VALUES = {
        'transfer': ['CYRIL', 'MANUEL', 'ZAHIA', 'SABINE', 'DAVID',
                      'FLORIAN', 'INTERIM', 'PASCAL', 'ANCIEN SALARIE'],
        'kit': ['SABINE', 'ZAHIA', 'CYRIL', 'MANUEL', 'AUTRE'],
    }

    @api.model
    def _selection_for(self, list_type):
        return [(name, name)
                for name in self.sudo()._proposable_names(list_type)]

    @tools.ormcache('list_type')
    def _proposable_names(self, list_type):
        # Active names first, then archived ones still in use: a
        # referenced name must never leave the list, an unused archived
        # one drops out of the choices.
        records = self.with_context(active_test=False).search(
            [('list_type', '=', list_type)])
        names = [record.name for record in records if record.active]
        archived = [record.name for record in records if not record.active]
        if archived:
            used = self._used_names(list_type)
            names += [name for name in archived if name in used]
        return tuple(names)

    def _used_names(self, list_type):
        used = set()
        for model_name, field_name in self._LIST_FIELDS[list_type]:
            model = self.env[model_name]
            model.flush_model([field_name])
            self.env.cr.execute(
                'SELECT DISTINCT "%s" FROM "%s" WHERE "%s" IS NOT NULL'
                % (field_name, model._table, field_name))
            used.update(value for (value,) in self.env.cr.fetchall())
        return used

    @api.model
    def _check_field_values(self, records, field_name, list_type):
        # Since the v19 ORM refactor, a dynamic Selection is no longer
        # validated on write (_selection is None): this guard, called from
        # an @api.constrains on each backed field, takes over.
        allowed = set(self.sudo()._proposable_names(list_type))
        for record in records:
            value = record[field_name]
            if value and value not in allowed:
                raise ValidationError(_(
                    "\"%(value)s\" is not part of the preparer list "
                    "(%(field)s). Add it first in Inventory → "
                    "Configuration → Preparers.",
                    value=value,
                    field=record._fields[field_name].string))

    def _ensure_unused(self, action):
        self.ensure_one()
        usage = []
        for model_name, field_name in self._LIST_FIELDS[self.list_type]:
            model = self.env[model_name].sudo()
            model.flush_model([field_name])
            self.env.cr.execute(
                'SELECT count(*) FROM "%s" WHERE "%s" = %%s'
                % (model._table, field_name), (self.name,))
            count = self.env.cr.fetchone()[0]
            if count:
                usage.append('%s × %s' % (
                    count, self.env['ir.model']._get(model_name).name))
        if usage:
            raise UserError(_(
                "\"%(name)s\" cannot be %(action)s: still used by "
                "%(usage)s. Archive it to stop offering it, or reassign "
                "the affected records first.",
                name=self.name, action=action, usage=', '.join(usage)))

    def _propagate_rename(self, list_type, old_name, new_name):
        for model_name, field_name in self._LIST_FIELDS[list_type]:
            model = self.env[model_name].sudo()
            model.flush_model([field_name])
            self.env.cr.execute(
                'UPDATE "%s" SET "%s" = %%s WHERE "%s" = %%s'
                % (model._table, field_name, field_name),
                (new_name, old_name))
            count = self.env.cr.rowcount
            if count:
                model.invalidate_model([field_name])
            _logger.info(
                "cadiffusion_base: preparer '%s' renamed to '%s' — "
                "%s %s record(s) updated",
                old_name, new_name, count, model_name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = vals['name'].strip()
        records = super().create(vals_list)
        self.env.registry.clear_cache()
        return records

    def write(self, vals):
        if 'name' in vals:
            vals = dict(vals, name=(vals['name'] or '').strip())
        if 'list_type' in vals:
            for record in self:
                if record.list_type != vals['list_type']:
                    record._ensure_unused(_("moved to another list"))
        renames = [(record.name, record.list_type) for record in self
                   if 'name' in vals and record.name != vals['name']]
        result = super().write(vals)
        for old_name, list_type in renames:
            self._propagate_rename(list_type, old_name, vals['name'])
        self.env.registry.clear_cache()
        return result

    def unlink(self):
        for record in self:
            record._ensure_unused(_("deleted"))
        result = super().unlink()
        self.env.registry.clear_cache()
        return result

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if not default or 'name' not in default:
            for vals in vals_list:
                vals['name'] = _("%s (copy)", vals['name'])
        return vals_list

    def _drop_stale_static_selection_rows(self):
        # Purge the options of the former hardcoded lists left in
        # ir.model.fields.selection. Raw SQL on purpose: an ORM unlink
        # would go through _process_ondelete, pointless here.
        for specs in self._LIST_FIELDS.values():
            for model_name, field_name in specs:
                self.env.cr.execute("""
                    DELETE FROM ir_model_data
                     WHERE model = 'ir.model.fields.selection'
                       AND res_id IN (
                           SELECT s.id
                             FROM ir_model_fields_selection s
                             JOIN ir_model_fields f ON f.id = s.field_id
                            WHERE f.model = %s AND f.name = %s)
                """, (model_name, field_name))
                self.env.cr.execute("""
                    DELETE FROM ir_model_fields_selection s
                     USING ir_model_fields f
                     WHERE f.id = s.field_id
                       AND f.model = %s AND f.name = %s
                """, (model_name, field_name))
                if self.env.cr.rowcount:
                    _logger.info(
                        "cadiffusion_base: %s stale static option(s) purged "
                        "on %s.%s (selection now dynamic)",
                        self.env.cr.rowcount, model_name, field_name)

    @api.model
    def _seed_lists(self):
        """Seed the lists: historical values from the code + distinct
        values actually stored. Idempotent, never destructive. Shared
        between the post_init_hook (fresh install) and
        migrations/19.0.1.0.30/post-migrate.py."""
        self._drop_stale_static_selection_rows()
        Preparateur = self.sudo().with_context(active_test=False)
        for list_type, seed_names in self._SEED_VALUES.items():
            names = list(seed_names)
            for model_name, field_name in self._LIST_FIELDS[list_type]:
                model = self.env[model_name]
                self.env.cr.execute("""
                    SELECT 1 FROM information_schema.columns
                     WHERE table_name = %s AND column_name = %s
                """, (model._table, field_name))
                if not self.env.cr.fetchone():
                    continue
                self.env.cr.execute(
                    'SELECT DISTINCT "%s" FROM "%s" WHERE "%s" IS NOT NULL '
                    'ORDER BY 1' % (field_name, model._table, field_name))
                names += [value for (value,) in self.env.cr.fetchall()
                          if value not in names]
            existing = set(Preparateur.search(
                [('list_type', '=', list_type)]).mapped('name'))
            missing = [name for name in names if name not in existing]
            if not missing:
                continue
            Preparateur.create([
                {'name': name,
                 'list_type': list_type,
                 'sequence': (names.index(name) + 1) * 10}
                for name in missing])
            _logger.info(
                "cadiffusion_base: preparer list '%s' seeded — "
                "%s name(s) added: %s",
                list_type, len(missing), ', '.join(missing))
