from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Réintroduit pour compatibilité avec account_invoice_facturx (OCA)
    # Le champ 'mobile' a été supprimé de res.partner en Odoo 19
    mobile = fields.Char(string='Mobile', tracking=True)

    # NIC = 5 derniers chiffres du SIRET (company_registry).
    # Champ calculé non stocké, en lecture seule — identique au comportement v15.
    nic = fields.Char(
        string='NIC',
        compute='_compute_nic',
        store=False,
    )

    @api.depends('company_registry')
    def _compute_nic(self):
        for partner in self:
            cr = partner.company_registry or ''
            partner.nic = cr[-5:] if len(cr) >= 9 else False

    # Stub pour account_peppol_response (module non installé) :
    # la vue res.partner.form.account.peppol.response référence ce champ
    # dans une condition invisible — sans le champ le formulaire crash.
    peppol_response_support = fields.Boolean(
        string='Peppol Response Support',
        compute='_compute_peppol_response_support',
    )

    def _compute_peppol_response_support(self):
        for partner in self:
            partner.peppol_response_support = False

    cad_secteur = fields.Selection(
        selection=[
            ('100 - THOMAS', '100 - THOMAS'),
            ('210', '210 - DEVERGNIES'),
            ('220', '220'),
            ('230', '230'),
            ('240', '240'),
            ('260', '260'),
            ('300', '300'),
            ('310 - LESEUIL', '310 - LESEUIL'),
            ('320', '320'),
            ('330', '330 - DURAND'),
            ('340 - BARBERO', '340 - BARBERO'),
            ('350', '350'),
            ('400 - AUTRES', '400 - AUTRES'),
        ],
        string='Secteur',
    )
    # Choices managed by the users in ca.diffusion.customer.category
    # (Sales → Configuration → Customer Categories).
    cad_categorie_client = fields.Selection(
        selection=lambda self: self.env['ca.diffusion.customer.category']
            ._selection_for('customer_category'),
        string='Categorie Client',
    )
    cad_assurance = fields.Selection(
        selection=[
            ('ACCEPTEE', 'ACCEPTEE'),
            ('ANNULEE/REFUSEE', 'ANNULEE/REFUSEE'),
            ('NON DEFINI', 'NON DEFINI'),
            ('PUBLIC', 'PUBLIC'),
            ('EUROCONTACT', 'EUROCONTACT'),
            ('FOURNISSEUR', 'FOURNISSEUR'),
            ('INTERNE', 'INTERNE'),
        ],
        string='Assurance',
    )
    cad_livraison_xpo = fields.Selection(
        selection=[
            ('STANDARD', 'STANDARD'),
            ('PRENDRE RDV', 'PRENDRE RDV'),
            ('TARGET', 'TARGET'),
        ],
        string='Livraison XPO',
    )
    cad_code_service_chorus = fields.Char(string='Code Service Chorus')
    cad_credit_safe = fields.Char(string='Credit Safe', tracking=True)
    cad_notes_internes = fields.Text(string='Notes Internes')
    cad_prospect = fields.Boolean(string='Prospect', default=False)
    cad_adresse_echantillon = fields.Boolean(string='Adresse Echantillon', default=False)
    cad_interets_moratoires = fields.Boolean(string='Interets Moratoires', default=False)
    cad_livraison_vl = fields.Boolean(string='Livraison VL', default=False)
    cad_fermeture_1 = fields.Char(string='Fermeture 1')
    cad_fermeture_2 = fields.Char(string='Fermeture 2')
    cad_ouverture_1 = fields.Char(string='Ouverture 1')
    cad_ouverture_2 = fields.Char(string='Ouverture 2')

    @api.constrains('cad_categorie_client')
    def _check_cad_categorie_client(self):
        self.env['ca.diffusion.customer.category']._check_field_values(
            self, 'cad_categorie_client', 'customer_category')

    # Synchronisation v15 : invoice_sending_method était un related de
    # customer_invoice_transmit_method_id.code. En Odoo 19 c'est un champ
    # natif Selection — on le recalcule via onchange pour conserver le comportement v15.
    @api.onchange('customer_invoice_transmit_method_id')
    def _onchange_customer_invoice_transmit_method(self):
        code = self.customer_invoice_transmit_method_id.code
        if code == 'fr-chorus':
            self.invoice_sending_method = 'fr_chorus'
        elif code == 'mail':
            self.invoice_sending_method = 'email'
        else:
            self.invoice_sending_method = 'manual'

    x_order_partner_id_sale_order_line_count = fields.Integer(
        string='Vente Article',
        compute='_compute_order_partner_id_sale_order_line_count',
    )

    @api.depends()
    def _compute_order_partner_id_sale_order_line_count(self):
        for partner in self:
            results = self.env['sale.order.line'].search(
                [('order_partner_id', 'in', partner.ids)]
            )
            partner.x_order_partner_id_sale_order_line_count = len(results)
