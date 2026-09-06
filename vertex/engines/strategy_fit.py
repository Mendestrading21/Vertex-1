"""
vertex/engines/strategy_fit.py — COUCHE STRATÉGIE (présentation, Ch. II).

Re-pondère l'analyse déjà calculée selon le profil « offensif croissance » :
choix du véhicule (ACTION vs OPTION), score stratégie, playbook, et tilt du
climat de marché. NE TOUCHE JAMAIS les moteurs quant : lit uniquement des champs déjà
présents sur les lignes (rows). Pur, sans état, sans I/O.

Extrait verbatim du monolithe, à une exception près : le climat n'est plus
recalculé ici — `_strat_tilt` délègue score et bande à son propriétaire unique
`vertex.engines.market_lens.climate` (constats 30 et 48). Analyse uniquement,
aucune exécution.
"""


def _vehicle_of(r, best):
    v = r.get('verdict')
    score = r.get('score') or 0
    if v == 'AVOID':
        return {'reco': '—', 'tone': 'mut', 'why': "signal trop faible — ni action ni option aujourd'hui"}
    if not best:
        return {'reco': 'ACTION', 'tone': 'blue',
                'why': "aucune option propre (illiquide / hors séance) — jouer le titre en action"}
    q = best.get('quality') or 0
    pop = best.get('pop') or 0
    iv = best.get('iv') or 0
    pot = best.get('pot') or 0
    if q < 45 or pop < 35:
        return {'reco': 'ACTION', 'tone': 'blue',
                'why': "option de faible qualité / liquidité — l'action est plus sûre"}
    o = 0
    o += 1 if q >= 70 else 0
    o += 1 if pop >= 50 else 0
    o += 1 if pot >= 100 else 0            # forte asymétrie (gain option ≥ +100% si cible)
    o += 1 if score >= 72 else 0           # conviction élevée
    o += 1 if 0 < iv <= 45 else 0          # IV pas chère → l'option paie
    o -= 2 if iv >= 62 else 0              # IV chère → surpayer la prime, préférer l'action
    o -= 1 if score < 62 else 0            # conviction moyenne
    if o >= 3:
        return {'reco': 'OPTION', 'tone': 'orange', 'opt': {'strike': best.get('strike'),
                'exp': best.get('exp'), 'q': q, 'pop': pop, 'pot': pot},
                'why': "levier + risque défini : qualité %d, POP %d%%, gain visé +%d%%" % (q, pop, pot)}
    if o <= 0:
        why = ("IV chère (%d%%) — l'action évite de surpayer la prime" % round(iv)) if iv >= 62 \
            else "conviction / liquidité moyenne — l'action est plus souple (ni théta ni échéance)"
        return {'reco': 'ACTION', 'tone': 'blue', 'why': why}
    return {'reco': 'AU CHOIX', 'tone': 'gold',
            'why': "les deux jouables — option pour le levier, action pour tenir sans échéance"}


def _attach_vehicle(rows, board):
    """Attache r['vehicle'] à chaque titre (meilleur CALL du board comme référence)."""
    best = {}
    for c in (board or []):
        if c.get('type') != 'CALL':
            continue
        s = c.get('sym')
        if s and (s not in best or (c.get('quality') or 0) > (best[s].get('quality') or 0)):
            best[s] = c
    for r in rows or []:
        r['vehicle'] = _vehicle_of(r, best.get(r.get('symbol')))


# ─── COUCHE STRATÉGIE (présentation) : re-pondère l'analyse selon le profil de l'utilisateur ──
# Profil : OFFENSIF CROISSANCE — action socle + CALL comme levier · R:R ≥ 2:1 · tendance propre.
# ⛔ Ne touche jamais les moteurs quant : lit uniquement les champs déjà calculés (st_*, rs, regime, plan…).
def _strat_score(r):
    """Score /100 ré-pondéré vers l'offensif croissance (momentum/force/tendance surpondérés)."""
    score = r.get('score') or 0
    def g(v, d): return v if isinstance(v, (int, float)) else d
    mom = g(r.get('st_mom'), score); tech = g(r.get('st_tech'), score)
    fund = g(r.get('st_fund'), 50); risk = g(r.get('st_risk'), 50); rs = g(r.get('rs'), 50)
    regime = r.get('regime'); pos52 = r.get('pos52'); ext = r.get('ext_atr'); rsi = r.get('rsi')
    s = (0.30 * mom + 0.16 * tech + 0.10 * fund + 0.10 * risk
         + 0.22 * max(0, min(100, rs))
         + 0.12 * (100 if regime == 'TREND' else 45 if regime == 'NEUTRAL' else 12))
    if regime == 'CHOP':
        s -= 12
    if pos52 is not None and pos52 >= 80 and regime == 'TREND':
        s += 5
    if ext is not None and abs(ext) >= 3:
        s -= 8
    if rsi is not None and rsi >= 78:
        s -= 5
    if r.get('vx_notrade'):
        s -= 10
    return int(max(0, min(100, round(s))))


# playbooks = mêmes règles que la page Stratégie, priorisés pour l'offensif (momentum/levier d'abord)
_PLAYBOOKS_PY = [
    ('🚀', 'Momentum Breakout', '#22C55E', 'Acheter la force qui casse ses plus-hauts.',
     lambda r: r.get('regime') == 'TREND' and (r.get('rs') or 0) >= 70 and (r.get('pos52') or 0) >= 80),
    ('⚡', 'Levier LEAPS', '#FF7A18', 'CALL long terme sur forte conviction — levier, perte max = la prime.',
     lambda r: (r.get('vx_edge') or 0) >= 60 and r.get('regime') == 'TREND'),
    ('🎯', 'Repli sur tendance', '#38BDF8', 'Entrer sur un creux dans une tendance saine — meilleur R:R.',
     lambda r: r.get('regime') == 'TREND' and 40 <= (r.get('rsi') or 0) <= 58 and (r.get('pos52') or 0) >= 40),
    ('💎', 'Qualité forte', '#A78BFA', 'Meilleurs scores validés ACHAT — le socle du portefeuille.',
     lambda r: (r.get('score') or 0) >= 72 and r.get('verdict') == 'BUY'),
    ('🔄', 'Retournement de bas', '#FFB23F', 'Rebond depuis le bas du range — à CONFIRMER.',
     lambda r: (r.get('pos52') or 0) <= 25 and (r.get('change') or 0) > 0),
    ('🛡️', 'Socle défensif', '#34D399', 'Titres solides peu volatils — amortir les chocs.',
     lambda r: (r.get('score') or 0) >= 58 and (abs(r['ext_atr']) if r.get('ext_atr') is not None else 2) <= 1 and r.get('regime') != 'CHOP'),
]


def _playbook_of(r):
    for ic, name, col, desc, f in _PLAYBOOKS_PY:
        try:
            if f(r):
                return {'ic': ic, 'name': name, 'col': col, 'desc': desc}
        except Exception:
            pass
    return None


def _attach_strategy(rows, detail):
    """Attache par titre : strat_score (profil offensif), playbook, R:R et rr_ok (≥ 2:1)."""
    for r in rows or []:
        r['strat_score'] = _strat_score(r)
        r['playbook'] = _playbook_of(r)
        sym = r.get('symbol')
        plan = ((detail or {}).get(sym) or {}).get('plan') or {}
        #  ERREUR D'UNITÉ, MESURÉE. Le repli `rr = r.get('vx_rr')` lisait
        #  `vertex['rr']`, qui n'est PAS un ratio : `quant_engine.rr_score`
        #  renvoie une NOTE /100 (`_clamp(rr_real * 32, 0, 100)`, son propre
        #  commentaire dit « 2:1→64, 3:1→96 »). Mesuré le 6 sept. 2026 sur
        #  /api/vertex/<sym> (5003) : NVDA 8, MSFT 22, AAPL 41, TSLA 44,
        #  AMD 55, META 44, GOOGL 64, AMZN 55. Passées dans le repli, ces notes
        #  donnaient `rr_ok = (note >= 2)` — VRAI sur 8/8, donc un drapeau
        #  « R:R ≥ 2:1 respecté » allumé en permanence, y compris pour la note 8
        #  qui encode le pire ratio réel (~0,25:1). Une garde toujours vraie ne
        #  distingue plus rien.
        #  Sans ratio MESURÉ (`plan['rr_res']`, seul rapport gain/risque du
        #  produit), le champ reste None et le drapeau reste faux : une absence,
        #  jamais un feu vert emprunté à une autre échelle.
        rr = plan.get('rr_res')
        r['rr'] = rr
        r['rr_ok'] = bool(rr is not None and rr >= 2)


#  Prescriptions par bande de climat. La BANDE vient du moteur canonique
#  (`market_lens.climate`) ; ce module ne fait plus que choisir le ton.
_TILT_BANDES = {
    'FAVORABLE': {'call_size': 'normale → agressive',
                  'emphasis': ['Momentum Breakout', 'Levier LEAPS', 'Repli sur tendance'],
                  'note': "Marché porteur : ton profil offensif est dans son élément. "
                          "Privilégie le momentum et le levier CALL long (LEAPS)."},
    'NEUTRE': {'call_size': 'réduite (½ taille)',
               'emphasis': ['Repli sur tendance', 'Qualité forte'],
               'note': "Marché mitigé : sois sélectif. Repli sur tendance + qualité forte ; "
                       "CALL en taille réduite et échéances plus longues."},
    'DANGEREUX': {'call_size': 'minime / cash',
                  'emphasis': ['Socle défensif', 'Qualité forte'],
                  'note': "Marché dangereux : défense. Réduis le levier CALL, garde du cash, "
                          "socle défensif seulement. Discipline > FOMO."},
}


def _strat_tilt(mctx):
    """Oriente l'analyse selon le climat : quels playbooks pousser + taille de levier CALL.

    CONSTATS 30 et 48, second moteur. Ce corps RECOPIAIT verbatim la formule de
    `market_lens.climate` (poids 35/18/6/14, 25/2/12, /100*25, 15/2/8) puis
    ré-étiquetait la bande sur un `65` littéral : troisième propriétaire d'une
    métrique qui n'en admet qu'un, et divergence prête à se rouvrir en silence à
    la première modification de `CLIMAT_FAVORABLE_MIN`. Il portait surtout la
    SUBSTITUTION non marquée du constat 30 : ``(a50 if a50 is not None else 50)``.
    Mesuré avant correctif, mctx = {'spy_regime':'TREND','roro':'RISK-ON',
    'vix_band':'stress'} : breadth {'above50': 50}, {} et {'above50': None}
    rendaient tous ``score 74 / FAVORABLE / call_size « normale → agressive »``,
    identiques au bit près — une participation JAMAIS mesurée poussait donc le
    ton le plus offensif du produit (taille de CALL « agressive » contre
    « réduite (½ taille) » au palier voisin), sans aucune marque.

    Correctif : la bande et le score viennent du moteur canonique, qui marque
    déjà la couverture (`partiel`, `breadth_status`, `note`). Tant que la largeur
    manque, la PRESCRIPTION est plafonnée au palier NEUTRE — jamais plus
    offensive qu'une donnée mesurée ne l'autorise — et le plafonnement est dit
    (`call_size_plafonne`, `couverture_note`). Aucun seuil ne bouge : la formule,
    les bornes (65/40) et les trois bandes restent celles du moteur.
    """
    if not mctx:
        return None
    from vertex.engines import market_lens
    cl = market_lens.climate(mctx)
    if not cl:                                   # aucun climat calculable : rien d'inventé
        return None
    label = cl['label']
    prescription = label
    out = {'score': cl['score'], 'regime': label, 'col': cl['col']}
    if cl.get('partiel'):
        out['partiel'] = True
        out['breadth_status'] = cl.get('breadth_status')
        out['couverture_note'] = cl.get('note')
        if label == 'FAVORABLE':
            prescription = 'NEUTRE'
            out['call_size_plafonne'] = True
    bande = _TILT_BANDES[prescription]
    out['call_size'] = bande['call_size']
    out['emphasis'] = list(bande['emphasis'])
    out['note'] = bande['note']
    if prescription != label:
        out['note'] += (' Largeur de marché non mesurée : le ton reste plafonné au '
                        'palier NEUTRE tant que la participation n’est pas connue.')
    return out


__all__ = ['vehicle_of', 'attach_vehicle', 'strat_score', 'playbook_of', 'attach_strategy', 'strat_tilt']

# Alias publics (API du module) vers les fonctions extraites verbatim.
vehicle_of = _vehicle_of
attach_vehicle = _attach_vehicle
strat_score = _strat_score
playbook_of = _playbook_of
attach_strategy = _attach_strategy
strat_tilt = _strat_tilt
