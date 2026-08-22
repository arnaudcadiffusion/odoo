import csv

from lxml import etree

from odoo.exceptions import ValidationError
from odoo.modules.module import get_manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open

from odoo.addons.cadiffusion_base import (
    _APPLY,
    _PICKING_TYPE_BARCODES,
    _REFERENCE_SPECS,
    _configure_unece_exo_taxes,
    _reference_diff,
    _reference_snapshot,
    _unece_categ_for_tax_name,
)
from odoo.addons.cadiffusion_base.reference_state import _VOLATILE_PARAMS


@tagged('post_install', '-at_install')
class TestPostBuildConformity(TransactionCase):
    """Post-conditions de ce que cadiffusion_base réaffirme à l'install et à
    l'upgrade (post_init_hook, migrations/, data/reference_state.xml).

    Ces réglages ne sont écrits qu'AU MOMENT de l'install ou d'un ``-u`` du
    module : entre deux builds, plus rien ne relit l'état. Ces tests verrouillent le
    code ; l'état réel d'une base de staging ou de production se contrôle avec
    ``data/check_post_build.py`` (odoo shell, lecture seule), qui rejoue les
    mêmes attentes.
    """

    def test_manual_settings_from_test_base(self):
        """Réglages posés à la main sur la base de test et que la plateforme
        d'upgrade ne rapporte pas de la production (19.0.1.0.20)."""
        company = self.env.ref('base.main_company')
        self.assertTrue(
            company.stock_move_email_validation,
            "confirmation par e-mail des mouvements de stock désactivée sur %s"
            % company.display_name)
        for xmlid, barcode in _PICKING_TYPE_BARCODES:
            picking_type = self.env.ref(xmlid)
            self.assertEqual(
                picking_type.barcode, barcode,
                "les douchettes et les étiquettes sont calées sur %s" % barcode)

    def test_reference_state_applied(self):
        """La configuration suit l'instantané de la base de recette
        (data/reference_*.csv) pour tout ce que le hook réapplique : état actif
        des vues, cibles des rapports, code-barres, réglages des sociétés.

        Une vue archivée par la plateforme d'upgrade reste muette tant que le
        hook ne l'a pas rallumée : un ``-u`` ne le fait pas, ``active`` n'étant
        pas un champ que les ``<record>`` écrivent.

        Aucune liste en dur : le test couvre d'office ce qu'apportent les
        migrations suivantes, dès que l'instantané est régénéré.
        """
        for spec in _REFERENCE_SPECS:
            name, model, key, fields, mode = spec
            if mode != _APPLY:
                continue
            differences, __, __ = _reference_diff(self.env, spec)
            self.assertFalse(
                differences[:10],
                "%s : %s écart(s) avec la recette" % (name, len(differences)))

    def test_reference_state_replayed_on_update(self):
        """data/reference_state.xml rejoue l'instantané à chaque ``-u``, pas
        seulement au saut de version : une vue Studio revenue active (base
        restaurée, plateforme d'upgrade — build 36768993 du 21/08/2026) est
        re-archivée sans migration ni post_init_hook.

        La vue simulée est INVALIDE en v19 (attribut ``modifiers`` de Studio
        v15) : depuis la 19, write() revalide l'arch à l'archivage et refuse —
        c'est ce qui avait laissé quatre vues actives sur ce build. Le rejeu
        doit passer outre (reference_state._archive_view).
        """
        with file_open('cadiffusion_base/data/reference_views.csv') as csvfile:
            xmlid = next(row['_key'] for row in csv.DictReader(csvfile)
                         if row['_key'].startswith('studio_customization.')
                         and row['active'] == 'False')
        # Une vue de recherche : c'est le type de trois des cinq vues du build,
        # et l'un de ceux qu'Odoo valide par schéma RNG (search, list, graph,
        # calendar, pivot, activity) — le formulaire, lui, n'y passe pas.
        view = self.env['ir.ui.view'].create({
            'name': 'Vue Studio v15 de test',
            'model': 'res.partner',
            'type': 'search',
            'arch': '<search><field name="name"/></search>',
        })
        # Arch invalide posée en SQL, telle que la plateforme d'upgrade la
        # livre — l'ORM refuserait de la créer. Flush d'abord : create() laisse
        # arch_db en attente d'écriture, et ce flush écraserait l'UPDATE.
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE ir_ui_view
               SET arch_db = jsonb_build_object('en_US', %s)
             WHERE id = %s
        """, ('<search><field name="name" modifiers="{}"/></search>', view.id))
        module, name = xmlid.split('.', 1)
        data = self.env['ir.model.data'].search(
            [('module', '=', module), ('name', '=', name)])
        if data:
            # Base restaurée : le xmlid existe déjà, on le pointe sur la vue
            # simulée (annulé avec la transaction du test).
            data.write({'res_id': view.id})
        else:
            self.env['ir.model.data'].create({
                'module': module, 'name': name,
                'model': 'ir.ui.view', 'res_id': view.id,
            })
        self.env.registry.clear_cache()
        view.invalidate_recordset()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            # Prémisse du contournement SQL : si Odoo cesse de revalider à
            # l'archivage, _archive_view n'a plus de raison d'être.
            view.write({'active': False})
        view.invalidate_recordset()
        self.assertTrue(view.active)

        self.env['cadiffusion.reference.state'].apply_reference_state()

        self.assertFalse(view.active, "%s non re-archivée par le rejeu" % xmlid)

    def test_volatile_params_ignored(self):
        """Les paramètres propres à chaque base (URL, domaine catchall,
        expiration, cloc…) ne sont ni pris dans l'instantané ni comparés : ils
        resignaleraient des écarts à chaque build sans que rien n'ait dérivé."""
        spec = next(s for s in _REFERENCE_SPECS if s[1] == 'ir.config_parameter')
        name, model, key, fields, __ = spec
        self.assertFalse(
            set(_reference_snapshot(self.env, model, key, fields))
            & set(_VOLATILE_PARAMS))
        self.env['ir.config_parameter'].sudo().set_param(
            'web.base.url', 'http://ailleurs.example')
        differences, missing, __ = _reference_diff(self.env, spec)
        self.assertNotIn('web.base.url', [d[0] for d in differences])
        self.assertNotIn('web.base.url', missing)

    def test_reference_state_runs_before_views(self):
        """Le rejeu doit précéder nos vues : un xpath ne résout que si la vue
        qu'il cible est active (migrations/19.0.1.0.21/pre-migrate.py). Le
        fichier reste donc le PREMIER du manifest."""
        self.assertEqual(
            get_manifest('cadiffusion_base')['data'][0],
            'data/reference_state.xml')

    def test_studio_views_archived(self):
        """Le contenu Studio est repris en XML : les deux jeux ne doivent pas
        se superposer (19.0.1.0.3 / .8 / .9 / .18)."""
        self.env.cr.execute("""
            SELECT d.name FROM ir_ui_view v
              JOIN ir_model_data d ON d.res_id = v.id
             WHERE d.model = 'ir.ui.view'
               AND d.module = 'studio_customization'
               AND v.active
        """)
        still_active = [row[0] for row in self.env.cr.fetchall()]
        self.assertFalse(
            still_active, "vues Studio encore actives : %s" % still_active)

    def test_chorus_conditions_applied(self):
        """Les conditions Chorus (customer_invoice_transmit_method_code, OCA)
        remplacent bien les conditions natives d'Odoo 19 sur le formulaire
        partenaire — toute la chaîne d'héritage doit être active."""
        arch = etree.fromstring(
            self.env['res.partner'].get_view(view_type='form')['arch'])
        fields = arch.xpath(
            "//field[@name='fr_chorus_service_id']"
            "[not(ancestor::field[@name='child_ids'])]")
        self.assertTrue(
            fields, "fr_chorus_service_id absent du formulaire partenaire : "
                    "la chaîne d'héritage Chorus est-elle active ?")
        self.assertIn(
            'customer_invoice_transmit_method_code',
            fields[0].get('invisible', ''),
            "condition native d'Odoo 19 non remplacée par celle de l'OCA")
        # Repris de Studio : le mode d'envoi de facture à côté du code service,
        # sur les contacts enfants. La vue qui le pose doit hériter de la vue
        # Chorus de l'OCA — ancrée sur base.view_partner_form, elle ne se
        # charge que si la vue Chorus est active, et le module casse au
        # chargement sur une base fraîchement remigrée.
        self.assertTrue(
            arch.xpath("//field[@name='child_ids']"
                       "//group[@name='fr_chorus_service']"
                       "/field[@name='invoice_sending_method']"),
            "mode d'envoi absent du sous-formulaire contact")

    def test_unece_categ_for_tax_name(self):
        """E = exonéré, G = export hors UE, K = intracommunautaire. L'ordre des
        tests compte : « EXPORT » ne doit pas retomber sur l'exonération."""
        for name, expected in (
                ('TVA 0% EXO', 'E'),
                ('TVA 0% EXPORT', 'G'),
                ('TVA 0% export (vente)', 'G'),
                ('TVA 0% EU M', 'K'),
                ('0% Non EU', 'G'),
                ('TVA 0% livraisons intracommunautaires (vente)', 'K'),
                ('TVA 20%', None),
        ):
            self.assertEqual(_unece_categ_for_tax_name(name), expected, name)

    def _unece(self, code_type, code):
        return self.env['unece.code.list'].search(
            [('type', '=', code_type), ('code', '=', code)], limit=1)

    def test_unece_repairs_wrong_category(self):
        """Une catégorie fausse est pire qu'absente : le XML CII passe la
        validation en déclarant un régime de TVA qui n'est pas celui de la
        facture. La première version de la fonction (ilike « EXO », qui matche
        par sous-séquence en v19) a posé E sur des taxes export.

        La réparation reste volontairement étroite : elle corrige ce que le
        ilike a cassé, sans décider à la place de la comptabilité pour les
        taxes restées sans code ni écraser un code assumé (AE).
        """
        common = {
            'amount': 0,
            'amount_type': 'percent',
            'type_tax_use': 'sale',
            'country_id': (self.env.company.account_fiscal_country_id
                           or self.env.ref('base.fr')).id,
        }
        vat = self._unece('tax_type', 'VAT')
        exo = self.env['account.tax'].create(dict(common, name='TVA 0% EXO'))
        mislabelled = self.env['account.tax'].create(dict(
            common, name='TVA 0% EXPORT', unece_type_id=vat.id,
            unece_categ_id=self._unece('tax_categ', 'E').id))
        undecided = self.env['account.tax'].create(dict(
            common, name='TVA 0% EU M'))
        reverse_charge = self.env['account.tax'].create(dict(
            common, name='0% EU M.', unece_type_id=vat.id,
            unece_categ_id=self._unece('tax_categ', 'AE').id))
        standard = self.env['account.tax'].create(dict(
            common, name='TVA 20% collectée', amount=20))

        _configure_unece_exo_taxes(self.env)

        self.assertEqual(exo.unece_categ_id.code, 'E')
        self.assertEqual(exo.unece_type_id.code, 'VAT')
        self.assertEqual(mislabelled.unece_categ_id.code, 'G',
                         "catégorie fautive non corrigée")
        self.assertFalse(
            undecided.unece_categ_id,
            "une taxe export/intracom sans code relève d'un arbitrage "
            "comptable, pas de ce hook")
        self.assertEqual(reverse_charge.unece_categ_id.code, 'AE',
                         "un code déjà posé est un choix assumé")
        self.assertFalse(standard.unece_type_id,
                         "seules les taxes 0% de vente sont concernées")

    def test_unece_codes_are_durable(self):
        """unece_type_code / unece_categ_code sont des related stockés : une
        colonne remplie sans son many2one source retombe à vide au premier
        recalcul, et le bloc ApplicableTradeTax disparaît du XML sans bruit."""
        self.env.cr.execute("""
            SELECT id FROM account_tax
             WHERE type_tax_use = 'sale' AND amount = 0
               AND ((unece_type_code IS NOT NULL AND unece_type_id IS NULL)
                 OR (unece_categ_code IS NOT NULL AND unece_categ_id IS NULL))
        """)
        orphans = [row[0] for row in self.env.cr.fetchall()]
        self.assertFalse(
            orphans, "codes UNECE sans many2one source sur les taxes %s"
                     % orphans)
