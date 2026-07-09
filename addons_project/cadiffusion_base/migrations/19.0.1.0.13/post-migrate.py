"""
Migration 19.0.1.0.13 — post-upgrade

(Recréée : la version originale, écrite sous 19.0.1.0.12, a été perdue avant
d'être commitée. Les bases déjà passées en .12 — dont la branche Test — n'ont
donc jamais été réparées : conversions d'UDM à 0, d'où les colonnes COLIS /
CONDITIONNEMENT vides et le Total Colis absent sur les bons de livraison.)

Deux réparations de données laissées par la plateforme d'upgrade v15 → v19 :

1. UDM sans facteur calculé : les UDM créées depuis les product.packaging
   v15 (« CARTON DE 10 », « BOITE »…) arrivent avec le champ calculé stocké
   ``factor`` à NULL (89 UDM sur 222 sur la base migrée). Toute conversion
   passant par elles renvoie alors 0 (colis des BL, prix à la pièce,
   quantités MRP…). On force le recalcul.

2. Réservations perdues : plus aucune stock.move.line sur les transferts
   non terminés, moves « confirmed » avec quantity = 0, alors que les
   pickings restent affichés « assigned » (état hérité, non recalculé).
   Conséquence visible : le « Bon de livraison - Rupture »
   (report_cadiffusion), dont la colonne COLIS n'affiche que le réservé,
   sort sans aucun colis. On ré-exécute la réservation standard
   (action_assign, l'équivalent du bouton « Vérifier la disponibilité »)
   sur les transferts ouverts. En v19, action_assign trie lui-même les
   moves par priorité / échéance / date, donc le stock est attribué dans le
   même ordre que le planificateur. L'appel se fait picking par picking
   sous savepoint : un transfert corrompu ne doit pas faire échouer tout
   l'upgrade.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # ------------------------------------------------------------------
    # 1. Recalcul des facteurs UDM stockés à NULL
    # ------------------------------------------------------------------
    cr.execute("SELECT count(*) FROM uom_uom WHERE factor IS NULL")
    nb_null = cr.fetchone()[0]
    uoms = env['uom.uom'].with_context(active_test=False).search([])
    env.add_to_compute(uoms._fields['factor'], uoms)
    uoms.flush_recordset(['factor'])
    _logger.info(
        "cadiffusion_base: facteurs UDM recalculés (%s NULL sur %s avant migration)",
        nb_null, len(uoms))

    # ------------------------------------------------------------------
    # 2. Conditionnement des moves ouverts : la plateforme d'upgrade a mis
    #    packaging_uom_id à l'UDM pièce (perte du product_packaging_id v15).
    #    On force le recalcul — la surcharge cadiffusion de
    #    _compute_packaging_uom_id le remet sur l'UDM carton.
    # ------------------------------------------------------------------
    moves = env['stock.move'].search([('state', 'not in', ('done', 'cancel'))])
    env.add_to_compute(moves._fields['packaging_uom_id'], moves)
    moves.flush_recordset(['packaging_uom_id'])
    # la quantité doit être recalculée APRÈS l'écriture du nouveau
    # conditionnement, sinon elle est convertie avec l'ancien (la pièce)
    env.add_to_compute(moves._fields['packaging_uom_qty'], moves)
    moves.flush_recordset(['packaging_uom_qty'])
    _logger.info(
        "cadiffusion_base: conditionnement recalculé sur %s moves ouverts", len(moves))

    # ------------------------------------------------------------------
    # 3. Re-réservation des transferts ouverts
    # ------------------------------------------------------------------
    pickings = env['stock.picking'].search([
        ('state', 'in', ('confirmed', 'waiting', 'assigned')),
    ])
    ok = ko = 0
    for picking in pickings:
        try:
            with env.cr.savepoint():
                picking.action_assign()
            ok += 1
        except Exception:
            ko += 1
            _logger.warning(
                "cadiffusion_base: action_assign en échec sur %s (ignoré)",
                picking.name, exc_info=True)
    _logger.info(
        "cadiffusion_base: re-réservation terminée — %s transferts traités, %s en échec",
        ok, ko)
