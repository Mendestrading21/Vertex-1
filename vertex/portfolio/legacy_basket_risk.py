"""vertex/portfolio/legacy_basket_risk.py — VERTEX v4 : couche PORTEFEUILLE / RISK MANAGER.

Au-delà du signal par titre, gère le RISQUE DE PANIER : corrélations entre
positions, concentration (HHI, poids max), exposition sectorielle, et un sizing
risk-parity (inverse-vol) CAPÉ. Produit un drapeau `no_new_risk` quand la
corrélation moyenne ou la concentration secteur dépasse les limites — c'est le
« no-trade de concentration » du rapport quant.

Pur numpy (déjà dépendance), déterministe, aucun appel réseau, aucun ordre.
⛔ ANALYSE ÉDUCATIVE — indicatif, jamais un ordre.
"""
import numpy as np

from vertex.market import sectors

MAX_POS = 0.15            # poids max par ligne (profil : 10-15 %)
MAX_SECTOR = 0.40         # exposition max par secteur
TARGET_CORR = 0.65        # corrélation moyenne au-delà de laquelle on bloque le risque


def _cap_weights(w, cap, iters=6):
    """Cape les poids à `cap` puis redistribue l'excédent (itératif, somme=1).

    Cap INFAISABLE (n × cap < 1, toutes les lignes capées) : les poids sont
    RENORMALISÉS à 1, et c'est le drapeau `ligne_trop_grosse` qui dit la vérité
    (« le panier est trop petit pour tenir le plafond de 15 % par ligne »).

    MESURE d'origine, poids inverse-vol égaux, cap 0,15 : n=1 somme 0,15 ·
    n=2 somme 0,30 · n=3 0,45 · n=4 0,60 · n=5 0,75 · n=6 0,90 — la fonction
    contredisait sa propre docstring, et l'allocation tronquée descendait
    jusqu'à l'écran : 2 titres 100 % semi-conducteurs affichaient
    `sectors {Semiconducteurs: 30 %}`, `diversification 96` et la lecture
    « Panier réellement diversifié », pendant que le gate `no_new_risk` restait
    désarmé. Un panier de 7 lignes ou plus (cap faisable) est inchangé.
    """
    w = np.array(w, dtype=float)
    w = np.where(w > 0, w, 0)
    if w.sum() <= 0:
        return w
    w = w / w.sum()
    for _ in range(iters):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        room = ~over
        if not room.any():
            #  Plus aucune ligne sous le cap : servir `n × cap` serait une
            #  allocation qui ne somme pas à 100 % — donc des poids, une
            #  exposition sectorielle et une diversification tous faux à la
            #  baisse. On renormalise et on assume le dépassement du plafond,
            #  que `ligne_trop_grosse` signale explicitement.
            return w / w.sum()
        w[room] += excess * (w[room] / w[room].sum())
    return w


def build(symbols, detail, max_pos=MAX_POS, max_sector=MAX_SECTOR, target_corr=TARGET_CORR):
    """Analyse le risque d'un panier. `symbols` = tickers candidats (actionnables).

    `weights` somme toujours à 100 %, y compris quand le plafond par ligne est
    INFAISABLE (n × max_pos < 1). Sur un tel panier, `max_weight > max_pos`
    n'est pas un bug : c'est l'énoncé du plafond infaisable — 2 lignes ne
    peuvent pas peser 15 % chacune et représenter le panier entier. Le
    dépassement est signalé par `ligne_trop_grosse`, et l'exposition
    sectorielle devient exacte (100 % au lieu de 30 %) donc
    `concentration_sectorielle` peut enfin s'armer.
    """
    try:
        series = {}
        for s in symbols or []:
            c = ((detail.get(s) or {}).get('series') or {}).get('close')
            if c and len(c) >= 40:
                series[s] = np.asarray(c, dtype=float)
        syms = list(series)
        if len(syms) < 2:
            return {'n': len(syms), 'symbols': syms, 'flags': [],
                    'no_new_risk': False, 'note': 'panier trop petit pour une analyse de corrélation'}
        L = min(len(v) for v in series.values())
        R = np.array([np.diff(np.log(np.clip(series[s][-L:], 1e-9, None))) for s in syms])
        vol = R.std(axis=1) * np.sqrt(252)
        corr = np.corrcoef(R)
        iu = np.triu_indices(len(syms), 1)
        avg_corr = float(np.nanmean(corr[iu])) if len(iu[0]) else 0.0
        max_corr = float(np.nanmax(corr[iu])) if len(iu[0]) else 0.0
        # sizing risk-parity (inverse-vol) capé
        inv = np.where(vol > 0, 1.0 / vol, 0.0)
        w = _cap_weights(inv, max_pos)
        hhi = float(np.sum(w ** 2))
        # exposition sectorielle
        sec = {}
        for s, wi in zip(syms, w):
            k = sectors.SECTOR_MAP.get(s) or 'Autre'
            sec[k] = sec.get(k, 0.0) + float(wi)
        max_sec_name = max(sec, key=sec.get) if sec else None
        max_sec = float(sec.get(max_sec_name, 0.0)) if max_sec_name else 0.0
        # paire la plus corrélée (pour l'explication)
        top_pair = None
        if len(iu[0]):
            j = int(np.nanargmax(corr[iu]))
            a, b = iu[0][j], iu[1][j]
            top_pair = [syms[a], syms[b], round(float(corr[a, b]), 2)]
        #  DEUX familles de drapeaux, et une seule bloque.
        #
        #  `no_new_risk` valait `bool(flags)` : depuis que le cap de poids est
        #  correct, `ligne_trop_grosse` s'arme pour TOUT panier de 2 a 6 lignes
        #  (plafond 15 % : cinq lignes valent 20 % chacune — c'est de
        #  l'arithmetique, pas un risque decouvert). Bloquer le risque neuf sur
        #  ce constat interdisait d'AJOUTER une ligne exactement quand ajouter
        #  est le remede. Mesure du contro le adverse : no_new_risk passait a
        #  True pour tout panier de 2 a 6 symboles, et trois consommateurs le
        #  lisent comme une interdiction (portfolio_guard, command, scanner).
        #
        #  Le drapeau RESTE — il est vrai, et l'ecran doit le dire — mais il est
        #  STRUCTUREL : il decrit la taille du panier, pas une concentration
        #  subie. Seules la correlation et la concentration sectorielle bloquent.
        flags, flags_structurels = [], []
        if avg_corr > target_corr:
            flags.append('correlation_panier_elevee')
        if max_sec > max_sector:
            flags.append('concentration_sectorielle')
        if float(w.max()) > max_pos + 1e-6:
            structurel = len(syms) * max_pos < 1.0 - 1e-9
            (flags_structurels if structurel else flags).append('ligne_trop_grosse')
        return {
            'n': len(syms), 'symbols': syms,
            'weights': {s: round(float(x) * 100, 1) for s, x in zip(syms, w)},
            'vol': {s: round(float(x) * 100, 1) for s, x in zip(syms, vol)},
            'avg_corr': round(avg_corr, 2), 'max_corr': round(max_corr, 2), 'top_pair': top_pair,
            'hhi': round(hhi, 3), 'diversification': round((1 - hhi) * 100),
            'max_weight': round(float(w.max()) * 100, 1),
            'sectors': {k: round(v * 100, 1) for k, v in sorted(sec.items(), key=lambda x: -x[1])},
            'max_sector': round(max_sec * 100, 1), 'max_sector_name': max_sec_name,
            #  `flags` porte les deux familles (les consommateurs d'affichage
            #  les listent), `no_new_risk` ne suit que les drapeaux bloquants.
            'flags': flags + flags_structurels,
            'flags_bloquants': flags, 'flags_structurels': flags_structurels,
            'no_new_risk': bool(flags),
            'limits': {'max_pos': round(max_pos * 100), 'max_sector': round(max_sector * 100),
                       'target_corr': target_corr},
        }
    except Exception as e:
        return {'n': 0, 'symbols': [], 'flags': [], 'no_new_risk': False,
                'error': f'{type(e).__name__}: {e}'}
