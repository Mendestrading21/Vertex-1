"""vertex.positions.detector — détection au démarrage + rapport (§6).

Compare l'état courant au dernier inventaire connu (fichier de snapshots)
et produit le Startup Position Report. Sans comparaison au courtier
(`ibkr_online=False`, seule valeur passée en production depuis la frontière
« données de marché uniquement ») ⇒ AUCUNE position déclarée n'est clôturée,
et les compteurs de disparition restent `None` : jamais comparé n'est pas
zéro (test_ibkr_offline_does_not_close_positions).
"""
from __future__ import annotations

import time

from vertex.positions.repository import load_positions
from vertex.positions.reconciler import reconcile
from vertex.services import persist

_INVENTORY_FILE = 'position_inventory.json'


def _identity_set(positions: list[dict]) -> dict:
    return {p['position_id']: {'quantity': p.get('quantity'),
                               'average_cost': p.get('average_cost'),
                               'symbol': p.get('symbol')}
            for p in positions}


def startup_position_report(desk_blob: dict | None,
                            ibkr_online: bool) -> dict:
    positions = load_positions(desk_blob)
    open_pos = [p for p in positions if p.get('status') != 'CLOSED']
    prev = persist.load_json(_INVENTORY_FILE, {}) or {}
    prev_ids = prev.get('ids') or {}
    cur_ids = _identity_set(open_pos)

    new = [pid for pid in cur_ids if pid not in prev_ids]
    missing = [pid for pid in prev_ids if pid not in cur_ids]
    modified = [pid for pid in cur_ids
                if pid in prev_ids and (
                    cur_ids[pid]['quantity'] != prev_ids[pid].get('quantity')
                    or cur_ids[pid]['average_cost'] != prev_ids[pid].get('average_cost'))]

    rec = reconcile([p for p in open_pos if p['source'] != 'IBKR'],
                    [p for p in open_pos if p['source'] == 'IBKR'],
                    ibkr_online=ibkr_online)
    report = {
        'positions_detected': len(open_pos),
        'new_positions': len(new),
        'modified_positions': len(modified),
        #  Une DÉTECTION qui n'a pas eu lieu ne vaut pas zéro (invariant 5).
        #  `0` se lit « vérifié, rien ne manque » ; seul `None` dit « jamais
        #  comparé ». La route le corrigeait à la frontière ; le moteur
        #  fabriquait toujours le zéro en amont — sortie servie inchangée.
        'missing_positions': len(missing) if ibkr_online else None,
        'closed_positions_detected': len(missing) if ibkr_online else None,
        'duplicates': sum(1 for i in rec['issues'] if i['code'] == 'POSITION_DUPLICATE'),
        'conflicts': rec['conflicts'],
        'repairs_required': rec['repairs_required'],
        'errors': [],
        'ibkr_online': ibkr_online,
        #  La CAUSE réelle, pas une panne supposée. Ce moteur écrivait « IBKR
        #  hors ligne » : le même processus pouvait alors annoncer
        #  `ibkr_connected=True, ibkr_live=True` sur /healthz et une panne
        #  courtier ici. `ibkr_online=False` n'est pas un état de session
        #  mesuré, c'est le CHOIX de produit « IBKR = données de marché
        #  uniquement » (invariant 3). La route corrigeait déjà la phrase
        #  servie ; le moteur cesse de la fabriquer. Aucune valeur ne change.
        'note': (None if ibkr_online else
                 'Aucune comparaison au courtier — positions déclarées '
                 'conservées, aucune clôture automatique'),
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }
    try:
        persist.save_json(_INVENTORY_FILE, {'ids': cur_ids, 'ts': time.time()})
    except Exception as e:                       # jamais bloquant
        report['errors'].append(f'inventaire non persisté: {e}')
    return report


__all__ = ['startup_position_report']
