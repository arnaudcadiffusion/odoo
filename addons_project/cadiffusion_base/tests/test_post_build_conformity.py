from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.cadiffusion_base import (
    _APPLY,
    _PICKING_TYPE_BARCODES,
    _REFERENCE_SPECS,
    _configure_unece_exo_taxes,
    _reference_diff,
    _unece_categ_for_tax_name,
)


@tagged('post_install', '-at_install')
class TestPostBuildConformity(TransactionCase):
    """Post-conditions de ce que cadiffusion_base réaffirme à l'install et à
    l'upgrade (post_init_hook + migrations/).

    Ces réglages ne sont écrits qu'AU MOMENT de l'install ou de l'upgrade :
    entre deux builds, plus rien ne relit l'état. Ces tests verrouillent le
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
