from odoo import api, fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    # Même conditionnement que les lignes de vente / d'achat : le plus grand
    # carton du produit (product.template._cadiffusion_carton_uom), et non le
    # premier élément de uom_ids, dont l'ordre suit le tri de uom.uom (la
    # pièce sortait donc devant « CARTON DE 20 »).
    # Many2one et non Char : le nom des UDM est traduit, et plusieurs cartons
    # s'appellent « SACHET DE 20 » en anglais mais « CARTON DE 20 » en
    # français — un Char figé au calcul (migration sans langue) affichait le
    # libellé anglais aux utilisateurs francophones.
    x_studio_conditionnement = fields.Many2one(
        'uom.uom',
        string='Conditionnement',
        compute='_compute_x_studio_conditionnement',
        store=True,
        readonly=False,
        precompute=True,
    )

    @api.depends('product_id.product_tmpl_id.uom_ids')
    def _compute_x_studio_conditionnement(self):
        for production in self:
            template = production.product_id.product_tmpl_id
            production.x_studio_conditionnement = (
                template._cadiffusion_carton_uom() if template else False)

    x_studio_impression_mo = fields.Boolean(
        string='Impression MO',
        default=False,
        copy=False,
        tracking=True,
    )
    x_studio_notes = fields.Text(
        string='Notes',
    )
    x_studio_preparateur_kit = fields.Selection(
        selection=[
            ('SABINE', 'SABINE'),
            ('ZAHIA', 'ZAHIA'),
            ('CYRIL', 'CYRIL'),
            ('MANUEL', 'MANUEL'),
            ('AUTRE', 'AUTRE'),
        ],
        string='Preparateur_Kit',
        copy=False,
    )

    def action_open_project(self):
        return True
