"""
vertex/engines/market_lens.py — PRISME MARCHÉ & SECTEUR (Ch. IX/XI).

Un titre ne se négocie pas dans le vide. Ce moteur situe une décision aux TROIS
niveaux — marché, secteur, titre — pour dire si le vent est dans le dos ou de
face : climat de marché, position du secteur, force du titre, et leur alignement.

Pur, sans état. Analyse uniquement.
"""


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# Borne unique de la bande FAVORABLE du climat. Elle vivait en TROIS exemplaires
# divergents : market_lens (62), feeds.py (65) et strategy_fit (65) — trois
# propriétaires d'une seule métrique. Mesuré : mc={'spy_regime':'TREND',
# 'roro':'RISK-ON','vix_band':'stress'} avec above50 ∈ {0,4,8} donne des scores
# 62/63/64 étiquetés FAVORABLE par le moteur et NEUTRE par /api/market/summary,
# au même instant sur la même donnée. On retient 65, la borne des deux
# propriétaires réellement servis à l'écran : le comportement affiché ne bouge
# pas, seule la bande 62-64 du JSON /api/decision s'aligne.
CLIMAT_FAVORABLE_MIN = 65
CLIMAT_NEUTRE_MIN = 40


def climate(market):
    """Score de climat 0-100 (régime + risk-on/off + largeur + VIX) → label + couleur.

    Propriétaire UNIQUE du couple score+label du climat : aucun consommateur ne
    doit re-dériver le label depuis le score (feeds.py le faisait avec une borne
    différente).

    Couverture : quand la largeur de marché (`breadth.above50`) manque, le score
    reste calculable mais il est PARTIEL. Mesuré avant correctif :
    breadth={} , above50=None et above50=50 rendaient tous
    {'score': 70, 'label': 'FAVORABLE'} — identiques au bit près, alors que la
    composante participation pèse 25 points sur 100 (58 à 0 %, 83 à 100 %) et
    peut faire basculer le label. Le même dictionnaire disait pourtant honnêtement
    « participation ?% » dans le verdict (vertex/market/context.py:99). Les
    marqueurs ne sont posés QUE dans le cas dégradé : un score à couverture
    complète garde exactement la forme historique {score, label, col}.
    """
    if not market:
        return None
    br = market.get('breadth') or {}
    reg, ro, vb = market.get('spy_regime'), market.get('roro'), market.get('vix_band')
    s = (35 if reg == 'TREND' else 18 if reg == 'NEUTRAL' else 6 if reg == 'CHOP' else 14)
    s += (25 if ro == 'RISK-ON' else 2 if ro == 'RISK-OFF' else 12)
    a50 = br.get('above50')
    breadth_connue = a50 is not None
    s += round((a50 if breadth_connue else 50) / 100 * 25)
    s += (15 if vb == 'calme' else 2 if vb == 'stress' else 8)
    s = max(0, min(100, round(s)))
    label, col = (('FAVORABLE', '#22C55E') if s >= CLIMAT_FAVORABLE_MIN else
                  ('NEUTRE', '#FFB23F') if s >= CLIMAT_NEUTRE_MIN else ('DANGEREUX', '#EF4444'))
    out = {'score': s, 'label': label, 'col': col}
    if not breadth_connue:
        out['breadth_status'] = 'MISSING'
        out['partiel'] = True
        out['note'] = ('Largeur de marché indisponible — score partiel : la '
                       'composante participation (25 pts sur 100) n’est pas mesurée.')
    return out


def sector_standing(sectors, sector_name):
    """Rang du secteur du titre parmi les secteurs scannés (par score moyen)."""
    if not sectors or not sector_name:
        return None
    ranked = sorted(sectors, key=lambda x: (_num(x.get('avg_score')) or -1), reverse=True)
    for i, s in enumerate(ranked):
        if s.get('sector') == sector_name:
            n = len(ranked)
            return {'name': sector_name, 'rank': i + 1, 'n': n,
                    'avg_score': _num(s.get('avg_score')), 'avg_change': _num(s.get('avg_change')),
                    'in_favor': (i + 1) <= max(1, n // 3)}          # tiers supérieur = porteur
    return None


def build(*, market, sectors, sector_name, stock_pct):
    """Prisme aux trois niveaux + lecture d'alignement (vent dans le dos / de face)."""
    cl = climate(market)
    sec = sector_standing(sectors, sector_name)
    stock_strong = stock_pct is not None and stock_pct >= 70
    lights = {
        # même borne que le label du climat : sans cela le feu « marché » du
        # prisme redevient un quatrième propriétaire de la même métrique.
        'market': bool(cl and cl['score'] >= CLIMAT_FAVORABLE_MIN),
        'sector': bool(sec and sec['in_favor']),
        'stock': bool(stock_strong),
    }
    n_green = sum(1 for v in lights.values() if v)
    if n_green == 3:
        alignment, tone = 'aligné', 'green'
        head = 'Vent dans le dos : titre fort, secteur porteur, marché favorable.'
    elif lights['stock'] and n_green == 1:
        alignment, tone = 'à contre-courant', 'amber'
        head = 'Titre fort mais à contre-courant de son secteur / du marché — prudence.'
    elif n_green >= 2:
        alignment, tone = 'partiellement aligné', 'blue'
        head = 'Alignement partiel entre le titre, son secteur et le marché.'
    else:
        alignment, tone = 'défavorable', 'red'
        head = 'Contexte défavorable aux trois niveaux — le dossier rame à contre-courant.'
    return {'climate': cl, 'sector': sec, 'stock_strong': stock_strong,
            'lights': lights, 'alignment': alignment, 'tone': tone, 'headline': head}


__all__ = ['build', 'climate', 'sector_standing',
           'CLIMAT_FAVORABLE_MIN', 'CLIMAT_NEUTRE_MIN']
