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
import ast
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


def _js_execute(src):
    """`src` privé de ses commentaires de bloc `/* … */`.

    Même leçon que pour le garde AST côté Python : un banc qui interdit une
    chaîne dans un fichier rougit sur le COMMENTAIRE qui documente le
    correctif. Mesuré le 2026-09-06 sur `options-intel.js` — le commentaire
    citant `if (!syms.length) return;` faisait tomber le garde du fichier
    qu'il venait de réparer. On n'assertionne que sur ce qui S'EXÉCUTE."""
    return re.sub(r'/\*.*?\*/', ' ', src, flags=re.S)


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
    40 %, confiance 0,4 — sur un board qui portait le spread 96/96.

    BARÈME, pour qu'aucun chiffre de fixture ne soit re-cité comme « board
    réel » (environment.py:88, pts = (8 - moyenne) / (8 - 1) × 100) : moyenne
    6,5 % → 21,4 ; moyenne 22,9 % (celle des 96 contrats servis) → clampée à
    0,0, d'où le verdict HOSTILE 34,8 et non MITIGÉ 52,2. La fixture de ce banc
    (6,5 % et 1,0 %) vaut 3,8 % → 60,7 : c'est un banc, pas une mesure du
    marché."""
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


def _etat_lab(board):
    """`scan_state` minimal à la forme réelle, pour `options_lab.build`."""
    return {
        'options_board': board,
        'detail': {'NVDA': {'price': 230.0, 'score': 70, 'verdict': 'ACHETER',
                            'sector': 'Tech', 'vol_z': 1.5, 'mom': 60,
                            'perf_m': 5, 'perf_q': 10, 'confidence': 70,
                            'plan': {'tp2': 260.0, 'atr': 5.0}}},
        'market': {'vix': 15.0, 'roro': 'RISK-ON', 'spy_regime': 'TREND'},
        'updated': '10:00', 'scan_ts_h': '10:00',
    }


def _contrat_lab(strike, **extra):
    c = _contrat_reel(strike=strike, pop=55, tgt=260.0, pot=40, spot=230.0,
                      theta_burn=0.4, danger_n=2, swing_ok=True, swing_ret=30)
    c.update(extra)
    return c


def test_le_centre_de_recherche_options_juge_la_liquidite_du_board_reel():
    """MESURE DU 2026-09-06 — quatre surfaces d'`options_lab` étaient
    structurellement INATTEIGNABLES sur données réelles, parce que le moteur
    relisait `.get('spread_pct')` et `.get('vol')` à la main, les clés du
    board de DÉMONSTRATION, sur des contrats venus de `state['options_board']`
    (board réel : `spread` 96/96, `spread_pct` 0/96).

    Appel de `options_lab.build` sur un board À LA FORME RÉELLE (spread 6,5 %
    et 1,0 % sur 2/2 contrats, volume 675) — AVANT / APRÈS :

      comité « Meilleure liquidité »  winner « — », value null,
                                      COMMITTEE_LIQUIDITY_UNAVAILABLE
                                   →  winner nommé, « OI 3 000 »,
                                      COMMITTEE_LIQUIDITY_AVAILABLE
      fiche, ligne Liquidité          score null, « Liquidité non quantifiée »
                                   →  score 29, « OI 4 615 · volume 675 ·
                                      spread 6.5% »
      fiche de recherche              spread_pct null → 6.5
      matrice de risques              SPREAD_UNAVAILABLE → SPREAD_AVAILABLE

    …pendant que la carte « Meilleur volume » servait 675 dans la MÊME charge :
    deux lectures du même board se contredisaient dans la même réponse."""
    from vertex.engines import options_lab

    board = [_contrat_lab(230.0), _contrat_lab(245.0, quality=55, oi=3000, spread=1.0)]
    d = options_lab.build(_etat_lab(board), demo=False)

    liq = [r for r in (d.get('committee') or []) if r.get('title') == 'Meilleure liquidité'][0]
    assert liq['coverage']['status'] == 'COMMITTEE_LIQUIDITY_AVAILABLE'
    assert liq['winner'] != '—' and liq['value']
    assert d['research']['spread_pct'] == 6.5

    ligne = [r for r in (d.get('analysis') or []) if r.get('key') == 'liquidity'][0]
    assert ligne['coverage']['status'] == 'LIQUIDITY_INPUT_AVAILABLE'
    assert ligne['score'] is not None
    assert 'spread 6.5%' in ligne['text'] and 'volume 675' in ligne['text']

    spread_r = [r for r in (d.get('risks') or [])
                if r.get('coverage', {}).get('status') == 'SPREAD_AVAILABLE']
    assert spread_r, 'la matrice de risques doit voir le spread mesuré'


def test_le_centre_de_recherche_ne_sert_ni_penalite_ni_zero_impute():
    """L'autre moitié du contrat : passer par l'accesseur ne doit RIEN
    fabriquer. Un contrat non coté porte `spread 99.0` (pénalité de
    `legacy_engine.py:338`) et `vol 0` (`_i(None) -> 0`) ; les deux doivent
    rester des ABSENCES, sinon on a simplement déplacé l'invention."""
    from vertex.engines import options_lab

    muet = _contrat_lab(230.0, spread=99.0, vol=0,
                        liquidity_coverage={'quoted_bid_ask': False,
                                            'volume_present': False})
    d = options_lab.build(_etat_lab([muet]), demo=False)

    liq = [r for r in (d.get('committee') or []) if r.get('title') == 'Meilleure liquidité'][0]
    assert liq['coverage']['status'] == 'COMMITTEE_LIQUIDITY_UNAVAILABLE'
    vol = [r for r in (d.get('committee') or []) if r.get('title') == 'Meilleur volume'][0]
    assert vol['value'] is None, 'un volume imputé à 0 n’est pas une observation'
    assert d['research']['spread_pct'] is None and d['research']['vol'] is None
    assert d['overview']['vol_total'] is None
    ligne = [r for r in (d.get('analysis') or []) if r.get('key') == 'liquidity'][0]
    assert ligne['score'] is None
    assert 'aucune imputation' in ligne['text']


def test_un_volume_observe_a_zero_reste_un_zero_dans_le_centre_de_recherche():
    """La contrepartie du refus : un ZÉRO RÉELLEMENT OBSERVÉ (séance fermée,
    contrat sans échange, `volume_present: true`) est une MESURE, pas une
    absence. Les deux formulations du moteur testaient la VÉRACITÉ
    (`if _vol else '—'`), donc rendaient « — » et `None` sur un zéro mesuré —
    la conflation même que l'accesseur venait de fermer en amont, réintroduite
    à la sortie. Mesure sur le board servi le 2026-09-06 : les 3 contrats de
    `/api/options/chain/NVDA` portent `vol: 0` avec `volume_present: true`."""
    from vertex.engines import options_lab

    zero_observe = _contrat_lab(230.0, vol=0,
                                liquidity_coverage={'quoted_bid_ask': True,
                                                    'volume_present': True})
    d = options_lab.build(_etat_lab([zero_observe]), demo=False)
    ligne = [r for r in (d.get('analysis') or []) if r.get('key') == 'liquidity'][0]
    assert 'volume 0' in ligne['text'], ligne['text']
    vol = [r for r in (d.get('committee') or []) if r.get('title') == 'Meilleur volume'][0]
    assert vol['value'] == '0'
    assert d['research']['vol'] == 0
    assert d['overview']['vol_total'] == 0


# ── Le garde qui manquait : un seul lecteur de ce champ ───────────────────────

_CLES_LIQUIDITE = ('spread_pct', 'volume')


def lectures_directes(src):
    """Les LECTURES RÉELLES de `spread_pct`/`volume` dans `src` : [(clé, ligne)].

    Lit l'ARBRE SYNTAXIQUE, pas le texte. La version d'origine était une regex
    (`(?:\\.get\\(\\s*|\\[\\s*)['\"](spread_pct|volume)['\"]`) et portait deux
    faux positifs mesurés :

      · un COMMENTAIRE ou une DOCSTRING qui CITE la faille corrigée la
        déclenche. Mesuré le 2026-09-06 : le commentaire d'en-tête
        d'`options_lab.py` (« ce moteur lisait `.get('spread_pct')` à la
        main »), écrit pour documenter le correctif, faisait tomber le garde
        sur le fichier qu'il venait de réparer ;
      · un simple littéral de liste — `COLONNES = ['volume']` — était compté
        comme une lecture (doute nommé au second tour, alors sans occurrence).

    Un garde qui rougit sur sa propre documentation finit par être désarmé.
    L'AST ne voit que ce qui S'EXÉCUTE : `x.get('spread_pct')`,
    `x.get("volume")`, `x['spread_pct']`. Il ignore par construction le texte
    des commentaires, des docstrings et des listes de noms."""
    lectures = []
    arbre = ast.parse(src)
    for n in ast.walk(arbre):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == 'get' and n.args
                and isinstance(n.args[0], ast.Constant)
                and n.args[0].value in _CLES_LIQUIDITE):
            lectures.append((n.args[0].value, n.lineno))
        elif (isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)
                and n.slice.value in _CLES_LIQUIDITE):
            lectures.append((n.slice.value, n.lineno))
    return lectures


def test_aucun_module_options_ne_relit_spread_pct_a_la_main():
    """Sans ce garde, n'importe quel renommage futur rouvre la même faille en
    silence : c'est exactement ainsi que six consommateurs ont divergé du
    producteur sans qu'une suite verte de 407 bancs ne le voie.

    Ce garde épingle les CONSOMMATEURS entre eux ; le contrat
    producteur↔consommateur est épinglé plus bas, à partir de la sortie réelle
    de `build_board` (`legacy_engine`, exempté ici parce qu'il lit la ligne
    yfinance BRUTE `row.get('volume')`, pas une ligne de board).

    PÉRIMÈTRE ÉLARGI le 2026-09-06 à `vertex/engines/` : le premier tour avait
    délibérément laissé ce répertoire hors champ parce que
    `vertex/engines/options_lab.py` y lisait encore `.get('spread_pct')` sur
    des contrats de `state['options_board']` (l. 194, 351, 951, 955, 1001) et
    n'appartenait au périmètre d'aucun lot — étendre le garde l'aurait rendu
    rouge sans pouvoir fermer la cause. La cause est fermée : le garde
    surveille désormais aussi ce répertoire, sinon rien n'empêche la faille
    de s'y rouvrir en silence. Seuls les fichiers `options*` y sont balayés :
    `vertex/engines/` héberge des moteurs qui ne lisent aucun board."""
    cibles = [os.path.join(_ROOT, 'vertex', 'options'),
              os.path.join(_ROOT, 'vertex', 'engines'),
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
            if racine.endswith('engines') and not nom.startswith('options'):
                continue
            for cle, ligne in lectures_directes(_lire(racine, nom)):
                fautifs.append('%s:%s (%s)' % (nom, ligne, cle))
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
    #  La dégradation des cellules IV et Coût ne tenait qu'à un attribut
    #  `title` : aucun lecteur d'écran ne l'annonce de façon fiable et il
    #  n'existe pas au tactile. Elle entre dans le flux du texte via le jeton
    #  muet DÉJÀ présent (`vx2-sr-only`, vertex-2-0.css:756) — aucune couleur
    #  nouvelle, le badge « Hors séance » restant la marque visible.
    assert 'var indicSr' in src
    assert "'<span class=\"vx2-sr-only\"> (valeur indicative, hors s" in src
    #  DOUTE MESURÉ du recontrôle, fermé le 2026-09-06 : la marque était posée
    #  INCONDITIONNELLEMENT dès que `c.stale`, y compris sur une cellule valant
    #  « — ». Un contrat hors séance sans IV se lisait donc
    #  « — (valeur indicative, hors séance) » au lecteur d'écran : une ABSENCE
    #  annoncée comme une ESTIMATION, soit les deux états que cette marque
    #  existe pour séparer. Le banc épingle maintenant la CONDITION, pas
    #  seulement la présence — les deux cellules, IV et Coût.
    assert src.count("+ indicSr(c.iv != null) + '</td>'") == 1
    assert src.count("+ indicSr(c.cost != null) + '</td>'") == 1
    assert "+ indicSr + '</td>'" not in src            # la pose inconditionnelle


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


def test_la_chaine_partagee_separe_retard_estimation_et_absence_de_cotation():
    """LA SECONDE SURFACE — `charts/option-chain.js`, servie par `/analysis/<sym>`
    depuis la MÊME charge `/api/options/chain/<sym>` que le dossier Options.

    Trois défauts mesurés le 2026-09-06 dans un moteur Chromium, sur trois
    contrats à la forme réelle :

      · colonne Vol : le tableau lisait `c.vol` NU. Un contrat dont la source
        ne reporte AUCUN volume porte `vol: 0` (`legacy_engine._i(None) -> 0`,
        `volume_present: false`) → la cellule imprimait « 0 », un zéro imputé
        rendu comme une observation. Et un contrat portant l'alias `volume`
        (fixtures, chemins de cotation) rendait « — », une absence FAUSSE ;
      · aucune marque de `stale` ni de `quoted_bid_ask` sur la ligne : rien ne
        distinguait une IV back-solvée d'une cotation ;
      · le pied résumait tout à « 3 contrat(s) · CALL & PUT » sous l'unique
        étiquette de mode « Différé », fondant RETARD, ESTIMATION et ABSENCE
        DE COTATION — trois états que le board sert séparément et que
        l'invariant 5 exige de garder distincts.

    Mesure APRÈS, mêmes entrées : Vol « — » / 675 / 1234, badges « Hors
    séance » et « Non coté », pied « … dont 1 hors séance (valeur indicative)
    · 1 sans carnet coté · 1 sans volume reporté »."""
    src = _lire(_ROOT, 'vertex', 'static', 'vertex', 'js', 'charts', 'option-chain.js')
    #  L'accesseur de volume suit le contrat de `board_fields.volume`.
    assert 'function volObserve(c)' in src
    assert "couverture(c).volume_present === false" in src
    assert "(c.volume != null) ? c.volume : c.vol" in src
    assert "{ k: 'vol', label: 'Vol', num: true, d: 0 }," not in src   # défaut d'origine
    #  Les deux états de ligne portent un mot, pas seulement un `title`.
    assert 'function estEstimation(c)' in src and 'function estNonCote(c)' in src
    assert "quoted_bid_ask === false" in src
    assert 'data-state="stale"' in src and 'Hors séance' in src
    assert 'data-state="missing"' in src and 'Non coté' in src
    assert 'vx2-sr-only' in src
    #  Le pied COMPTE les états au lieu de les fondre dans le mode.
    for compte in ('hors séance (valeur indicative)', 'sans carnet coté',
                   'sans volume reporté'):
        assert compte in src, compte
    assert 'ne dit que l’âge de l’instantané' in src


def test_les_vues_options_nomment_un_tableau_vide_au_lieu_de_se_taire():
    """MESURE DU 2026-09-06 (instance de contrôle, sans IBKR, desk quasi vide) :
    `/options?view=volatility` rendait **16 valeurs creuses sur 16**.

    Cause : `autoSym` faisait `if (!syms.length) return;` — un retour
    SILENCIEUX. Les quatre hôtes de graphiques (`vx-opt-term`, `vx-opt-cone`,
    `vx-opt-oi`, `vx-opt-smile`) restaient littéralement vides, sous un rail
    qui gardait sa consigne serveur « Choisis un symbole présent dans le
    tableau d'options » — inapplicable, puisqu'il n'y en avait aucun.

    Et `boardSyms` faisait `.catch(function () { cb([]); })` : une PANNE de
    lecture du tableau devenait indistinguable d'un tableau vide.

    Mesuré en moteur Chromium sur le fichier servi, APRÈS : tableau vide →
    « Aucun titre dans le tableau d'options pour l'instant… » sur les quatre
    hôtes ET le rail ; lecture en échec → « Le tableau d'options n'a pas pu
    être lu (502 board indisponible) : ce n'est pas une absence de données,
    c'est une lecture en échec. »"""
    src = _lire(_JS, 'options-intel.js')
    execute = _js_execute(src)
    assert 'if (!syms.length) return;' not in execute    # le retour muet d'origine
    assert 'function nommerAbsenceDeTableau(' in src
    assert 'cb(syms, null);' in src and 'cb([], e ||' in src
    assert 'Aucun titre dans le tableau' in src
    assert 'c’est une lecture en échec' in src
    #  Les quatre hôtes de la vue Volatilité sont nommés, pas seulement le rail.
    for hote in ('vx-opt-term', 'vx-opt-cone', 'vx-opt-oi', 'vx-opt-smile'):
        assert "'" + hote + "'" in src, hote
    #  Les deux autres vues qui pré-sélectionnent un symbole disent aussi leur vide.
    assert "nommerAbsenceDeTableau('vx-opt-ev-out-body'" in src
    assert "nommerAbsenceDeTableau('vx-opt-sc-out-body'" in src


def test_la_vue_structure_ne_laisse_aucun_hote_muet():
    """MESURE : sur `/options?view=structure`, quand aucune structure n'est
    constructible, `vx-os-greeks` restait à `''` (vidé au chargement, jamais
    rempli) et `vx-os-payoff` affichait un TIRET NU — deux hôtes muets alors
    que la carte verdict, elle, nomme la cause. Un tiret sans motif ne
    distingue pas l'absence de la panne. Les deux hôtes répètent désormais le
    motif que possède la carte verdict, sans inventer un second vocabulaire."""
    src = _lire(_JS, 'options-structure.js')
    tiret_nu = """innerHTML = '<div class="vx-empty">—</div>'"""
    assert tiret_nu not in _js_execute(src)
    #  Ce garde comptait deux occurrences de chaque phrase, une par branche
    #  dégradée. Mesure du 2026-09-06 : compter les phrases a laissé passer
    #  DEUX hôtes de plus — `vx-os-scenarios` et `vx-os-compare`, vidés au
    #  chargement et jamais remplis dans aucun état, y compris la panne
    #  réseau où seul l'hôte du verdict était servi. Le nom du garde promettait
    #  « aucun hôte muet » ; il ne vérifiait que deux hôtes sur quatre.
    #  Les quatre hôtes sont désormais nommés en UN seul endroit, et chaque
    #  chemin dégradé y passe : on vérifie la LISTE et la COUVERTURE, pas le
    #  nombre de répétitions d'une phrase.
    import re as _re
    liste = _re.search(r'var HOTES_STRUCTURE = \[(.*?)\];', src, _re.S)
    assert liste, 'la liste des hôtes de la vue Structure a disparu'
    hotes = set(_re.findall(r"\['([\w-]+)'", liste.group(1)))
    assert hotes == {'vx-os-scenarios', 'vx-os-compare', 'vx-os-payoff', 'vx-os-greeks'}, hotes
    #  TROIS causes distinctes, plus la définition : board muet, analyse
    #  serveur absente, lecture en échec. Aucune ne doit être oubliée.
    assert src.count('nommerAbsenceStructure(') == 4, (
        'un chemin dégradé ne passe pas par le nommage commun des hôtes')
    assert "esc(motif)" in src and "esc(motifA)" in src
    #  Une PANNE ne se dit pas comme une absence.
    assert 'la lecture a échoué' in src and 'VX.states.error' in src


# ── Le garde PRODUCTEUR ↔ CONSOMMATEUR (celui qui manquait vraiment) ──────────

def _cles_lues_par(nom_accesseur):
    """Noms de clés littérales que l'accesseur `board_fields.<nom>` lit.

    Extraits de la SOURCE, jamais recopiés : si l'accesseur cesse de lire un
    alias, ce banc le voit ; si le producteur cesse de l'émettre, il le voit
    aussi. C'est le contrat producteur↔consommateur, pas un accord entre
    consommateurs."""
    import inspect
    src = inspect.getsource(getattr(bf, nom_accesseur))
    return set(re.findall(r"contract\.get\(\s*['\"]([a-z_]+)['\"]", src))


def _board_reel_produit():
    """Sort UN board du PRODUCTEUR CANONIQUE `legacy_engine.build_board`.

    La chaîne yfinance est remplacée par une chaîne FIGÉE (aucun réseau), mais
    tout le reste — noms de clés, arrondis, unités, pénalités — est le code de
    production. Les fixtures des autres bancs écrivent `spread`/`vol` À LA MAIN :
    elles ne prouvent RIEN sur ce que le producteur émet réellement."""
    import types
    from datetime import timedelta

    from vertex.options import legacy_engine as le

    class _DF(object):
        def __init__(self, rows):
            self._rows = rows

        def iterrows(self):
            for i, r in enumerate(self._rows):
                yield i, r

    class _Chain(object):
        def __init__(self, rows):
            self.calls = _DF(rows)
            self.puts = _DF(rows)

    exp = (le._ny_now() + timedelta(days=210)).strftime('%Y-%m-%d')
    #  Carnet COTÉ : bid 6,00 / ask 6,40 / mid 6,20 → spread (6,40-6,00)/6,20
    #  = 6,45 % arrondi à 6,5 % ; volume du jour 675 ; OI 4 615.
    row = {'strike': 230.0, 'impliedVolatility': 0.427, 'openInterest': 4615,
           'volume': 675, 'bid': 6.0, 'ask': 6.4, 'lastPrice': 6.2,
           'lastTradeDate': '2026-09-04 20:00:00'}

    class _Ticker(object):
        def __init__(self, sym):
            self.options = [exp]

        def option_chain(self, e):
            return _Chain([dict(row)])

    vrai_yf = le.yf
    le.yf = types.SimpleNamespace(Ticker=_Ticker)
    try:
        return le.build_board(
            {'NVDA': {'price': 230.0, 'plan': {'tp2': 250.0, 'atr': 5.0}}},
            [{'symbol': 'NVDA', 'verdict': 'BUY'}])
    finally:
        le.yf = vrai_yf


def test_les_cles_emises_par_build_board_couvrent_les_cles_lues_par_l_accesseur():
    """LE GARDE QUI MANQUAIT. Aucun banc n'appelait `build_board` : les cinq
    mentions dans tests/ étaient des DOCSTRINGS. Les fixtures écrivant `spread`
    et `vol` à la main, un renommage côté producteur (legacy_engine.py:383)
    rendrait `board_fields.spread_pct()` None sur 100 % du board RÉEL — et la
    suite resterait VERTE, exactement le trou par lequel six consommateurs ont
    divergé du producteur sans qu'une suite de 407 bancs ne le voie.

    Ici on part de la SORTIE RÉELLE du producteur (chaîne figée, zéro réseau)
    et on vérifie que les clés émises couvrent les clés lues, PUIS que la
    valeur lue est bien la mesure calculée par le producteur (6,5 % depuis
    bid 6,00 / ask 6,40 / mid 6,20 ; volume 675)."""
    board = _board_reel_produit()
    assert board, 'le producteur doit rendre au moins un contrat'
    for c in board:
        emises = set(c)
        for accesseur in ('spread_pct', 'volume'):
            lues = _cles_lues_par(accesseur)
            assert lues, 'aucune clé littérale extraite de %s' % accesseur
            assert emises & lues, (
                '%s lit %s ; le producteur émet %s — aucune intersection : '
                'la mesure serait ABSENTE sur 100 %% du board réel'
                % (accesseur, sorted(lues), sorted(emises)))
        assert bf.spread_pct(c) == 6.5      # (6,40-6,00)/6,20 → 6,45 → 6,5
        assert bf.volume(c) == 675
        assert isinstance(bf.volume(c), int)


def test_le_garde_voit_les_quatre_formes_et_ignore_ce_qui_ne_s_execute_pas():
    """Le garde doit voir TOUTES les formes de lecture réelle — apostrophes,
    guillemets doubles, indexation — et AUCUNE citation.

    Les deux faux positifs mesurés de la version regex sont épinglés ici :
    un commentaire qui documente la faille corrigée, et un littéral de liste
    de noms de colonnes. Vérifié sur du texte synthétique, pas sur l'arbre
    (qui doit rester propre)."""
    faux = ('a = c.get("spread_pct")\n'
            'b = c["volume"]\n'
            "d = c.get('spread_pct')\n")
    assert [k for k, _ in lectures_directes(faux)] == ['spread_pct', 'volume', 'spread_pct']

    innocent = ('#  Ce moteur lisait `.get(\'spread_pct\')` a la main.\n'
                '"""Docstring citant c["volume"] comme defaut ferme."""\n'
                "COLONNES = ['volume', 'spread_pct']\n"
                "e = c.get('spread')\n")
    assert lectures_directes(innocent) == []


def test_l_ordre_des_alias_ne_decide_jamais_a_la_place_du_refus_d_imputation():
    """DOUTE MESURÉ du contrôle : `flow._vol` lisait `vol` PUIS `volume`,
    l'accesseur lit `volume` PUIS `vol` — l'ordre a changé en silence. Aucun
    producteur n'émet les deux clés aujourd'hui (board réel `spread`/`vol`
    96/96, démo et fixtures `spread_pct`), donc l'ordre est inobservable EN
    PRODUCTION. Mais il décidait quand même : le témoin d'imputation
    (`quoted_bid_ask`, `volume_present`) n'était consulté que sur la branche
    de repli.

    Mesure du 2026-09-06, contrat portant les deux noms :
    `{'spread_pct': 99.0, 'spread': 6.5, quoted_bid_ask: false}` → l'accesseur
    rendait **99.0**, la pénalité servie comme une mesure ;
    `{'vol': 675, 'volume': 0, volume_present: false}` → il rendait **0**, le
    zéro imputé servi comme une observation. Les deux cas sont exactement ce
    que le module existe pour interdire, arrivés par l'autre nom. Le refus
    passe désormais AVANT l'ordre de lecture, donc l'ordre ne décide de rien."""
    penalise = {'sym': 'X', 'spread_pct': 99.0, 'spread': 6.5,
                'liquidity_coverage': {'quoted_bid_ask': False, 'volume_present': True}}
    assert bf.spread_pct(penalise) is None

    impute = {'sym': 'X', 'vol': 675, 'volume': 0,
              'liquidity_coverage': {'quoted_bid_ask': True, 'volume_present': False}}
    assert bf.volume(impute) is None

    #  Sans témoin d'imputation, les deux alias restent lus, dans l'ordre documenté.
    assert bf.spread_pct({'spread_pct': 2.0, 'spread': 6.5}) == 2.0
    assert bf.volume({'volume': 42, 'vol': 675}) == 42
