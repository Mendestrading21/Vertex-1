"""
vertex/engines/reasoning.py — LE MOTEUR DE RAISONNEMENT (Ch. XVIII).

La décision n'est pas une prédiction. Ce module transforme un plan chiffré en
SCÉNARIOS conditionnels (haussier / central / baissier), chacun avec son
déclencheur, sa cible, son invalidation. Il rend explicite ce qui doit se
passer pour que chaque futur se réalise — et ce qui le tuerait.

Règle : la conviction mesure la solidité du dossier AUJOURD'HUI, jamais la
probabilité d'un gain futur. On expose les conditions, on ne promet rien.

Analyse uniquement. Aucune exécution.
"""


def _num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _pct(a, b):
    """Variation en % de b vers a, arrondie — None si base absente."""
    b = _num(b)
    if not b:
        return None
    return round((_num(a) / b - 1) * 100, 1)


# Aucune probabilité n'est calibrée dans le dépôt : le standard déjà posé par
# `skyler_core.scenarios` (probability None + note + model.calibrated False) est
# la référence. Ce module l'adopte au lieu d'émettre un second vocabulaire.
PROBABILITY_NOTE = ('modèle de probabilité non calibré — aucune probabilité '
                    'affichée (lot 9 : calibration)')
MODEL = {'type': 'plan_levels_deterministic', 'calibrated': False}


def scenarios(detail, committee, decision):
    """Trois futurs conditionnels, avec déclencheur, cible et invalidation.

    CONSTAT 39. Trois défauts MESURÉS ont été retirés ici ; aucun niveau du plan
    moteur n'a changé.

    1. Vocabulaire probabiliste non calibré. Le champ s'appelait `likelihood`
       (« plausible / possible / peu probable ») et les `weight` sommaient à 100,
       tous dérivés du seul `committee.lean` — aucune source, aucune calibration,
       aucun marqueur. Mesuré par appel direct : lean=10 → 15/25/60,
       lean=50 → 45/**9**/45, lean=90 → 60/25/15. Au comité PARFAITEMENT partagé
       (incertitude maximale), le scénario Central recevait le poids le plus
       FAIBLE possible pendant que les deux extrêmes recevaient 45 chacun : le
       résidu ``base = max(0.1, 1 - bull - bear)`` inversait le sens du mot
       « central ». L'invariant 7 interdit d'inventer une probabilité, pas
       seulement de l'afficher.
    2. Scénario Central contredit par sa propre cible. Le déclencheur annonçait
       « Maintien de la zone $stop–$resistance » et la cible valait `tp2`, une
       grandeur INDÉPENDANTE (`entry + 2×risque`, analysis.py:264) de la
       résistance (plus-haut 40 séances, analysis.py:267). Mesuré 5/5 sur
       /api/decision : NVDA zone 211.91–234.76 → cible 267.26 ; AAPL
       300.89–344.27 → 358.14 ; MSFT 473.3–517.78 → 552.51 ; TSLA
       315.91–406.59 → 430.42 ; AMD 421.3–574.2 → 590.12. La cible était donc
       au-dessus du plafond de la zone que la condition déclarait tenue :
       inatteignable sous son propre déclencheur. La condition est désormais
       énoncée en deux temps (maintien du stop PUIS dépassement de la
       résistance) — le texte suit la cible, la cible ne bouge pas.
    3. Scénario Baissier tautologique. `trigger = 'Clôture sous $stop'` et
       `target = stop` : atteindre la cible ÉTAIT le déclencheur (vérifié 5/5 en
       réel, NVDA 211.91/211.91, AAPL 300.89/300.89, MSFT 473.3/473.3, TSLA
       315.91/315.91, AMD 421.3/421.3). Le plan moteur ne contient AUCUN
       objectif sous le stop : l'absence est déclarée au lieu d'être comblée par
       le niveau d'invalidation déguisé en cible.
    """
    d = detail or {}
    plan = d.get('plan') or {}
    price = _num(d.get('price')) or _num(plan.get('entry'))
    entry, stop = plan.get('entry'), plan.get('stop')
    tp2, tp3 = plan.get('tp2'), plan.get('tp3')
    resistance = plan.get('resistance') or tp2
    return [
        {'name': 'Haussier', 'tone': 'green',
         'probability': None, 'probability_note': PROBABILITY_NOTE,
         'trigger': f'Cassure de ${resistance} confirmée par le volume' if resistance
                    else 'Reprise de la tendance avec volume',
         'target': tp3 or tp2, 'move_pct': _pct(tp3 or tp2, price),
         'invalidation': f'Repli sous ${entry}' if entry else 'Perte de la zone d\'entrée'},
        {'name': 'Central', 'tone': 'amber',
         'probability': None, 'probability_note': PROBABILITY_NOTE,
         'trigger': (f'Maintien au-dessus de ${stop}, puis dépassement de ${resistance}'
                     if stop and resistance else 'Consolidation dans le range'),
         'target': tp2 or resistance, 'move_pct': _pct(tp2 or resistance, price),
         'invalidation': f'Sortie franche du range (sous ${stop})' if stop else 'Sortie de range'},
        {'name': 'Baissier', 'tone': 'red',
         'probability': None, 'probability_note': PROBABILITY_NOTE,
         'trigger': f'Clôture sous ${stop}' if stop else 'Perte du support',
         'target': None, 'move_pct': None,
         'target_note': (f'aucun objectif baissier dans le plan moteur — ${stop} est '
                         f'l’invalidation, pas une cible' if stop else
                         'aucun objectif baissier dans le plan moteur'),
         'invalidation': f'Reprise au-dessus de ${entry}' if entry else 'Reprise de l\'entrée'},
    ]


def invalidations(detail):
    """Ce qui tuerait la thèse — conditions explicites, testables (Ch. XVIII)."""
    d = detail or {}
    plan = d.get('plan') or {}
    out = []
    if plan.get('stop') is not None:
        out.append(f'Clôture journalière sous ${plan["stop"]} (stop de la thèse)')
    if not (d.get('signals') or {}).get('above200', True):
        out.append('Le titre repasse durablement sous la MM200')
    if d.get('distribution'):
        out.append('La distribution s\'accentue (OBV continue de diverger)')
    out.append('Un changement de régime de marché (RISK-ON → RISK-OFF)')
    return out[:4]


def build(detail, committee, decision):
    """Bloc de raisonnement complet attaché à la décision.

    `model` dit ce que ces scénarios SONT : des niveaux déterministes du plan
    moteur, non calibrés. Sans ce marqueur, un consommateur pouvait lire trois
    futurs pondérés comme un modèle probabiliste (constat 39).
    """
    return {
        'scenarios': scenarios(detail, committee, decision),
        'invalidations': invalidations(detail),
        'model': dict(MODEL),
        'conviction_note': ('La conviction reflète la solidité du dossier aujourd\'hui, '
                            'pas la probabilité d\'un gain. Ce sont des scénarios '
                            'conditionnels, pas des prédictions.'),
    }


__all__ = ['build', 'scenarios', 'invalidations', 'PROBABILITY_NOTE', 'MODEL']
