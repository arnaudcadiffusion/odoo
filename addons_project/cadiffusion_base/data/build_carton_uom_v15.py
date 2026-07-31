#!/usr/bin/env python3
"""Générateur des CSV carton_uom_v15_*.csv (reprise des conditionnements v15).

Outil de développement — PAS chargé par Odoo (absent du manifest et des
imports). Croise les choix de conditionnement v15 (product_packaging_id des
lignes de vente/d'achat) avec les UDM v19 et produit les CSV d'écarts :
uniquement les lignes dont le choix v15 diffère du défaut « plus grand
carton » calculé par _cadiffusion_default_carton_uom (les autres n'ont pas
besoin de reprise). Appliqués par _apply_v15_carton_choices (__init__.py).

À régénérer si la bascule production repart d'un dump v15 plus récent :

1. Exporter dans WORKDIR depuis la base v15 (ici cadiffusion16) :
   \\copy (select l.id, l.product_id, btrim(p.name) as pack_name, p.qty as pack_qty
           from purchase_order_line l
           join product_packaging p on p.id=l.product_packaging_id)
        to 'v15_purchase.csv' with csv header
   (idem sale_order_line -> v15_sale.csv)
2. Exporter depuis la base v19 migrée (ici cadiffusion) :
   \\copy (select id, product_id from purchase_order_line
           where product_id is not null) to 'v19_purchase.csv' with csv header
   (idem sale_order_line -> v19_sale.csv)
   \\copy (select pp.id as product_id, u.id as uom_id,
                  btrim(u.name->>'en_US') as uom_name,
                  u.factor/b.factor as ratio
           from product_product pp
           join product_template pt on pt.id=pp.product_tmpl_id
           join uom_uom b on b.id=pt.uom_id
           join product_template_uom_uom_rel r on r.product_template_id=pt.id
           join uom_uom u on u.id=r.uom_uom_id
           where b.factor is not null and u.factor is not null)
        to 'v19_product_uoms.csv' with csv header
3. WORKDIR=/chemin python3 build_carton_uom_v15.py, puis copier
   override_purchase.csv -> carton_uom_v15_purchase_order_line.csv et
   override_sale.csv -> carton_uom_v15_sale_order_line.csv.

Dernière génération : 31/07/2026 (cadiffusion16 × cadiffusion locales,
1 101 écarts achat / 27 493 écarts vente, ~99,95 % des colis v15 résolus).
"""
import csv
import os
from collections import Counter

SP = os.environ.get('WORKDIR', '.')
TOL = 1e-6


def norm(name):
    return ' '.join((name or '').upper().split())


# --- UDM candidates par produit (v19) ---
product_uoms = {}  # product_id -> list[(uom_id, name, ratio)]
with open(f'{SP}/v19_product_uoms.csv') as f:
    for row in csv.DictReader(f):
        product_uoms.setdefault(int(row['product_id']), []).append(
            (int(row['uom_id']), norm(row['uom_name']), float(row['ratio'])))


def default_carton(pid):
    """Réplique product.template._cadiffusion_carton_uom : plus grand ratio
    > 1, CARTON préféré à ratio égal."""
    best = None  # (uom_id, name, ratio, is_carton)
    for uom_id, name, ratio in product_uoms.get(pid, []):
        if ratio <= 1 + TOL:
            continue
        is_carton = name.startswith('CARTON')
        if best is None or ratio > best[2] + TOL or (
                abs(ratio - best[2]) <= TOL and is_carton and not best[3]):
            best = (uom_id, name, ratio, is_carton)
    return best


def resolve(pid, pack_name, pack_qty):
    """Choix v15 -> UDM v19 du produit : par nom, puis par ratio."""
    cands = product_uoms.get(pid, [])
    pname = norm(pack_name)
    by_name = [c for c in cands if c[1] == pname]
    if by_name:
        exact = [c for c in by_name if abs(c[2] - pack_qty) <= TOL]
        return (exact or by_name)[0], 'name'
    by_qty = [c for c in cands if abs(c[2] - pack_qty) <= TOL]
    if by_qty:
        carton = [c for c in by_qty if c[1].startswith('CARTON')]
        return (carton or by_qty)[0], 'qty'
    return None, None


def process(kind):
    v19_products = {}
    with open(f'{SP}/v19_{kind}.csv') as f:
        for row in csv.DictReader(f):
            v19_products[int(row['id'])] = int(row['product_id'])

    stats = Counter()
    overrides = []  # (line_id, uom_name)
    samples = {'override': [], 'unmatched': [], 'product_changed': []}
    with open(f'{SP}/v15_{kind}.csv') as f:
        for row in csv.DictReader(f):
            line_id = int(row['id'])
            pid15 = int(row['product_id'])
            pack_name, pack_qty = row['pack_name'], float(row['pack_qty'])
            pid19 = v19_products.get(line_id)
            if pid19 is None:
                stats['line_absent_v19'] += 1
                continue
            if pid19 != pid15:
                stats['product_changed'] += 1
                if len(samples['product_changed']) < 5:
                    samples['product_changed'].append((line_id, pid15, pid19))
                continue
            target, how = resolve(pid19, pack_name, pack_qty)
            if target is None:
                stats['unmatched'] += 1
                if len(samples['unmatched']) < 10:
                    samples['unmatched'].append((line_id, pid19, pack_name, pack_qty))
                continue
            stats[f'matched_by_{how}'] += 1
            dflt = default_carton(pid19)
            if dflt and dflt[0] == target[0]:
                stats['same_as_default'] += 1
            else:
                stats['override'] += 1
                overrides.append((line_id, target[1]))
                if len(samples['override']) < 10:
                    samples['override'].append(
                        (line_id, pack_name, '->', target[1],
                         'défaut:', dflt[1] if dflt else None))

    overrides.sort()
    out = f'{SP}/override_{kind}.csv'
    with open(out, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['line_id', 'uom_name'])
        w.writerows(overrides)
    print(f'== {kind} ==')
    for k, v in sorted(stats.items()):
        print(f'  {k}: {v}')
    for cat, rows in samples.items():
        for r in rows[:6]:
            print(f'  ex {cat}:', *r)
    print(f'  -> {out}: {len(overrides)} lignes')


process('purchase')
process('sale')
