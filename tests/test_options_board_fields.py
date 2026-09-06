# -*- coding: utf-8 -*-
"""Frontière de forme du board options : un seul accesseur, aucun nom mort.

MESURE DU 2026-09-06 (instance de contrôle, board RÉEL yfinance, DEMO_MODE
false) qui a produit ce banc. Le producteur canonique
`legacy_engine.build_board` (l. 383) publie `spread` (déjà en %, l. 338) et
`vol` ; le board de DÉMONSTRATION (`vertex/data/demo.py`:111) et les fixtures
publient `spread_pct` et `volume`. Comptage sur le board servi : `spread`
96/96 contrats, `spread_pct` 0/96 ; sur `options_cache.json` : 481 contrats,
`spread_pct` 0/481, `volume` 0/481.

Conséquences mesurées, toutes sur données réelles et aucune en démonstration :
  - `/api/options/environment` : liquidity score null, « liquidité (spread)
    indisponible », couverture 40 %, confiance 0,4, score 52,2 MITIGÉ — alors
    que la dimension manquante valait 0/100 (spread moyen 22,9 %) et faisait
    tomber le verdict à 34,8 HOSTILE, couverture 60 %, confiance 0,6.
    L'exclusion FLATTAIT le verdict, ce que `data_coverage.note` promet
    explicitement de ne jamais faire ;
  - `/api/options/overview` : `avg_spread_pct: null` et radar muet sur 6 lignes,
    pendant que la page Opportunités imprimait « 6,5 % » pour le même contrat ;
  - `/api/options/scanner/LEAPS` : 33/33 lignes motivées « spread indisponible »,
    `IN_MANDATE` structurellement inatteignable ; SWING_3_6M 74/74 « volume
    indisponible », et 22 des 31 candidats étiquetés PARTIAL_MANDATE étaient
    mesurablement HORS mandat — une fausse absence PROMEUT (rank PARTIAL=1 <
    OUT=2), donc un contrat illiquide prenait la tête du mandat 3–6 mois ;
  - colonnes clientes muettes : `/options/dossier/<sym>` rendait « — » sur 8/8
    lignes KHC (spreads réels 17 % à 178 %) et 30/30 cartes LEAPS affichaient
    « Spread n/d · 0/15 » (NVDA 61/100 ambre au lieu de 76/100 vert).

Aucun test n'appelait `build_board` pour comparer les clés émises aux clés
consommées : c'est le garde qui manquait, il est ici.
"""
import io
import os
import re

from vertex.options import board_fields as bf
from vertex.options import environment as env
from vertex.options import horizon_scanners as hs
from vertex.options import overview as ov
from vertex.strategy import constitution as C

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_JS = os.path.join(_ROOT, 'vertex', 'static', 'vertex', 'js', 'pages')


def _lire(*bouts):
    return io.open(os.path.join(*bouts), encoding='utf-8').read()


def _contrat_reel(**extra):
    """Forme RÉELLE d'une ligne de `build_board` (clés `spread` et `vol`)."""
    c = {'sym': 'NVDA', 'type': 'CALL', 'bucket': 'long', 'exp': '2027-03-19',
         'dte': 193, 'strike': 230.0, 'delta': 0.75, 'iv': 42.7, 'cost': 2860,
         'oi': 4615, 'vol': 675, 'spread': 6.5, 'bid': 6.0, 'ask': 6.4,
         'quality': 61, 'stale': False,
         'liquidity_coverage': {'quoted_bid_ask': True, 'volume_present': True}}
    c.update(extra)
    return c


def _contrat_demo(**extra):
    """Forme du board de DÉMONSTRATION (`spread_pct`, `vol`)."""
    c = {'sym': 'DMO', 'type': 'CALL', 'bucket': 'long', 'exp': '2027-03-19',
         'dte': 193, 'strike': 100.0, 'delta': 0.75, 'iv': 40.0, 'cost': 500,
         'oi': 2000, 'vol': 300, 'spread_pct': 2.0, 'quality': 70, 'spot': 100.0}
    c.update(extra)
    return c


# ── L'accesseur lui-même ──────────────────────────────────────────────────────

def test_accesseur_lit_les_deux_boards_et_n_invente_aucune_des_deux_cles():
    assert bf.spread_pct(_contrat_reel()) == 6.5
    assert bf.spread_pct(_contrat_demo()) == 2.0
    assert bf.volume(_contrat_reel()) == 675
    assert isinstance(bf.volume(_contrat_reel()), int)   # un compte, pas « 675.0 »
    assert bf.volume(_contrat_demo()) == 300
    assert bf.volume({'volume': 42}) == 42            # forme des fixtures
    #  Aucune des deux clés → ABSENCE, jamais un zéro ni une pénalité.
    assert bf.spread_pct({'oi': 4615}) is None
    assert bf.volume({'oi': 4615}) is None
    assert bf.spread_pct(None) is None and bf.volume('pas un contrat') is None


def test_accesseur_refuse_de_servir_une_penalite_pour_une_mesure():
    """MESURE : `legacy_engine.py:338` pose `spread = 99.0` quand le bid/ask
    n'est pas exploitable, et `_i(None) -> 0` transforme un volume absent en
    zéro. Rendre l'un ou l'autre comme observé, c'est fabriquer un chiffre."""
    non_cote = _contrat_reel(spread=99.0,
                             liquidity_coverage={'quoted_bid_ask': False,
                                                 'volume_present': True})
    assert bf.spread_pct(non_cote) is None
    croise = _contrat_reel(spread=99.0, bid=6.4, ask=6.4)   # marché verrouillé
    assert bf.spread_pct(croise) is None
    sans_volume = _contrat_reel(vol=0,
                                liquidity_coverage={'quoted_bid_ask': True,
                                                    'volume_present': False})
    assert bf.volume(sans_volume) is None
    #  Un zéro RÉELLEMENT observé reste un zéro observé.
    zero_observe = _contrat_reel(vol=0,
                                 liquidity_coverage={'quoted_bid_ask': True,
                                                     'volume_present': True})
    assert bf.volume(zero_observe) == 0.0


# ── Consommateurs serveur ─────────────────────────────────────────────────────

def test_environnement_note_le_spread_detenu_au_lieu_de_le_declarer_indisponible():
    """MESURE : liquidity (None, « liquidité (spread) indisponible »), couverture
    40 %, confiance 0,4 — sur un board qui portait le spread 96/96."""
    board = [_contrat_reel(spread=6.5), _contrat_reel(strike=245.0, spread=1.0)]
    score, note = env._score_liquidity(board)
    assert score is not None and 'indisponible' not in note
    assert note == 'spread moyen 3.8 %'
    d = env.score_environment(board, detail_by_sym={}, as_of='10:00', source='SCAN')
    assert 'liquidity' not in (d['data_coverage']['unknown_dimensions'])
    #  L'absence RÉELLE continue d'être dite honnêtement.
    muet = [{'sym': 'NVDA', 'type': 'CALL', 'oi': 10}]
    assert env._score_liquidity(muet) == (None, 'liquidité (spread) indisponible')


def test_overview_sert_le_spread_moyen_et_le_radar():
    """MESURE : `counters.avg_spread_pct = null` et radar `spread_pct` null sur
    les 6 lignes ; la carte « SPREAD MOY. » annonçait « non disponible sur ce
    scan » pendant qu'Opportunités imprimait « 6,5 % » pour le même contrat."""
    d = ov.summarize([_contrat_reel()], as_of='10:00', source='SCAN')
    assert d['counters']['avg_spread_pct'] == 6.5
    assert d['radar'][0]['spread_pct'] == 6.5
    vide = ov.summarize([{'sym': 'NVDA', 'type': 'CALL', 'quality': 10}])
    assert vide['counters']['avg_spread_pct'] is None    # absence réelle préservée


def test_scanner_leaps_juge_la_liquidite_reelle_au_lieu_de_la_dire_indisponible():
    """MESURE : Scanner LEAPS, 33/33 lignes « spread indisponible », spread_pct
    servi non nul 0/33 alors que la ligne de board portait la mesure 33/33."""
    conforme = _contrat_reel(delta=0.80, spread=1.0, oi=12050)
    res = hs.scan([conforme], 'LEAPS', profile=C.load_profile())
    c0 = res['candidates'][0]
    assert c0['spread_pct'] == 1.0                       # servi, pas vide
    assert c0['mandate']['spread_ok'] is True
    assert c0['mandate_status'] == 'IN_MANDATE'          # inatteignable avant
    assert c0['mandate_reasons'] == []
    #  Un spread mesuré HORS mandat est refusé pour le bon motif.
    large = _contrat_reel(delta=0.80, spread=14.2, oi=12050)
    r2 = hs.scan([large], 'LEAPS', profile=C.load_profile())
    assert r2['candidates'][0]['mandate']['spread_ok'] is False
    assert 'spread hors mandat' in r2['candidates'][0]['mandate_reasons']


def test_scanner_swing_ne_convertit_ni_absence_ni_penalite_en_verdict():
    """MESURE : SWING_3_6M, 74/74 « volume indisponible » ; et la tête du mandat
    (CPAY, vol 1 et spread 14,2 % sur sa ligne) était PARTIAL_MANDATE alors
    qu'elle est mesurablement hors mandat — la fausse absence PROMOUVAIT."""
    cpay = _contrat_reel(sym='CPAY', dte=135, delta=0.45, vol=1, spread=14.2)
    res = hs.scan([cpay], 'SWING_3_6M', profile=C.load_profile())
    c0 = res['candidates'][0]
    assert c0['volume'] == 1 and c0['spread_pct'] == 14.2
    assert c0['mandate']['volume_ok'] is False and c0['mandate']['spread_ok'] is False
    assert c0['mandate_status'] == 'OUT_OF_MANDATE'
    #  Volume ABSENT (et non zéro observé) : reste inconnu, jamais « conforme ».
    aveugle = _contrat_reel(sym='AVG', dte=135, delta=0.45, vol=0, spread=2.0,
                            liquidity_coverage={'quoted_bid_ask': True,
                                                'volume_present': False})
    r2 = hs.scan([aveugle], 'SWING_3_6M', profile=C.load_profile())
    m = r2['candidates'][0]['mandate']
    assert m['volume_ok'] is None and m['spread_ok'] is True
    assert 'volume indisponible' in r2['candidates'][0]['mandate_reasons']
    #  Pénalité 99.0 : ni conformité, ni rejet — une absence.
    penalise = _contrat_reel(sym='PEN', dte=135, delta=0.45, spread=99.0,
                             liquidity_coverage={'quoted_bid_ask': False,
                                                 'volume_present': True})
    r3 = hs.scan([penalise], 'SWING_3_6M', profile=C.load_profile())
    assert r3['candidates'][0]['mandate']['spread_ok'] is None
    assert r3['candidates'][0]['spread_pct'] is None


# ── Le garde qui manquait : un seul lecteur de ce champ ───────────────────────

def test_aucun_module_options_ne_relit_spread_pct_a_la_main():
    """Sans ce garde, n'importe quel renommage futur rouvre la même faille en
    silence : c'est exactement ainsi que six consommateurs ont divergé du
    producteur sans qu'une suite verte de 407 bancs ne le voie."""
    cibles = [os.path.join(_ROOT, 'vertex', 'options'),
              os.path.join(_ROOT, 'vertex', 'app', 'routes')]
    #  `board_fields` EST l'accesseur ; `legacy_engine` est le PRODUCTEUR et lit
    #  la ligne brute yfinance (`row.get('volume')`), pas une ligne de board.
    exempts = {'board_fields.py', 'legacy_engine.py'}
    fautifs = []
    for racine in cibles:
        for nom in sorted(os.listdir(racine)):
            if not nom.endswith('.py') or nom in exempts:
                continue
            if racine.endswith('routes') and not nom.startswith('options_'):
                continue
            src = _lire(racine, nom)
            for m in re.finditer(r"\.get\(\s*'(spread_pct|volume)'", src):
                fautifs.append('%s:%s' % (nom, src[:m.start()].count('\n') + 1))
    assert fautifs == [], 'lecture directe au lieu de board_fields : %s' % fautifs


# ── Contrat de rendu : les colonnes clientes ne peuvent plus être muettes ─────

def test_la_colonne_spread_du_dossier_lit_le_champ_servi_et_marque_le_hors_seance():
    """MESURE : `/options/dossier/KHC`, colonne Spread, 8/8 cellules « — » et
    0 cellule ambre, alors que la même réponse JSON portait 149,0 / 177,6 /
    28,6 / 17,1 / 22,6 / 70,1 / 79,5 % ; le pied de table promettait pourtant
    « spread ambre = liquidité coûteuse ». Et `stale` (2/96 lignes du board,
    IV recalculée depuis le prix, mid issu du dernier échange) n'était rendu
    nulle part : 0 occurrence dans l'actif servi."""
    src = _lire(_JS, 'options-symbol.js')
    assert "(c.spread_pct != null) ? c.spread_pct : c.spread" in src
    assert "c.spread_pct != null ? VXf.num(c.spread_pct" not in src   # défaut d'origine
    assert "(spr > 5 ? ' vx-warn' : '')" in src                       # le seuil peut s'allumer
    assert 'data-state="stale"' in src and 'Hors s' in src
    assert "mine.filter(function (c) { return c && c.stale; }).length" in src


def test_le_score_leaps_lit_le_spread_servi():
    """MESURE : 30/30 cartes LEAPS affichaient « Spread n/d · 0/15 » alors que
    /api/options portait `spread: 1.0` pour le même contrat ; NVDA 61/100
    (ambre) au lieu de 76/100 (vert), sous un pied de carte qui promet « Score
    explicable = somme des composantes réelles ci-dessus »."""
    src = _lire(_JS, 'options-structure.js')
    assert "var sp = (c.spread_pct != null) ? c.spread_pct : c.spread;" in src
    assert "c.spread_pct == null ? 0" not in src                      # défaut d'origine
    assert "'Spread ' + (sp != null ? num(sp, 1) + ' %' : 'n/d')" in src


def test_le_tiroir_scanner_dit_d_ou_vient_le_cours():
    """Le cours du scan n'est pas horodaté sur la cotation du contrat : le repli
    qui débloque la probabilité de doublement doit se nommer à l'écran."""
    src = _lire(_JS, 'options-scanner.js')
    assert "c.spot_source === 'scan.detail.price'" in src
    assert 'cours du scan, pas de la cotation du contrat' in src
