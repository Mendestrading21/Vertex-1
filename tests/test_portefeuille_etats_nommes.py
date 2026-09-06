"""LOT F — PORTEFEUILLE / SUIVI : deux tirets muets, nommés.

Ce banc garde les deux corrections du lot F, mesurées le 2026-09-06 dans
Chromium sur une instance QA (`tools/qa/run_qa_instance.py`, NO_IBKR=1,
DEMO=0) servant le portefeuille DÉCLARÉ (1 action KO, 2 CALLS MSFT/GOOG).

## Défaut 1 — « Risque événementiel » (/portfolio?view=options)

MESURE AVANT :

```text
KPI « Risque événementiel »  valeur « — »
                             sous-titre « earnings par position ci-dessous »
```

Deux fautes en une.

* La valeur ne pouvait pas être autre chose. Le test était
  `rich.some(t => t.entrySnap && t.entrySnap.earnings_dte != null)`, or
  **aucun producteur du dépôt n'écrit `earnings_dte` dans `entrySnap`** : le
  formulaire de déclaration pose `entrySnap {stop, tgt, date}`
  (`vertex/static/vertex/js/vx-entities.js:545`) et `models.py` n'y lit que
  `stop`/`tgt`. Le prédicat valait donc `false` **par construction**, sur tout
  portefeuille possible — un tiret que rien ne pouvait lever.
* Le sous-titre renvoyait à une colonne qui n'existe pas. En-têtes du tableau
  « Positions options » mesurés dans le DOM : Contrat, Qté, Coût, Marque, P&L,
  DTE, Stop sous-jacent — **aucune colonne « earnings »**.

« Aucune échéance de résultats proche » et « date de résultats inconnue »
s'écrivaient donc du même tiret, et le renvoi était faux.

MESURE APRÈS :

```text
KPI « Risque événementiel »  valeur « date inconnue »
                             sous-titre « calendrier de résultats non servi
                                          pour 2 contrat(s) »
```

La date réelle vient de `/api/positions/state` (`days_to_earnings`), déjà
consommé par la vue Positions : instantané **borné**, mesuré à ~10 ms et mis
en cache 30 s par `VX.fetch` — jamais une collecte réseau dans la requête.
La convention de chevauchement (`earningsDte <= dte`) est celle de
`vertex/engines/earnings_option_overlap.py`, pas une invention de la page.

## Défaut 2 — « Bêta » (/portfolio?view=risk)

MESURE AVANT :

```text
KPI « Bêta »  valeur « — »  sous-titre « pondéré »
```

`risk.beta` vaut `null`. Mais la **même** réponse `/api/portfolio/team` sert
`risk.beta_coverage`, que la page n'a jamais lue — mesuré ce jour :

```json
{"known_positions": 0, "total_positions": 1, "coverage_pct": 0.0,
 "missing_symbols": ["KO"], "partial": true}
```

Un bêta absent parce que le seul titre déclaré n'en publie pas n'est pas un
bêta absent parce qu'aucune position n'est déclarée, ni un bêta absent parce
que le moteur ne sert pas la couverture. Trois causes, un seul tiret.

MESURE APRÈS :

```text
KPI « Bêta »  valeur « n/d »
              sous-titre « incalculable — bêta non déclaré pour KO »
```

## Pourquoi le banc exécute le JS au lieu de le relire

Figer les phrases produites transformerait ce gardien en presse-papier : la
correction suivante (une meilleure formulation) le ferait tomber sans qu'aucun
comportement n'ait régressé. Ce banc extrait les deux fonctions **pures** du
source et les **exécute** dans Chromium avec des entrées synthétiques. Ce qu'il
impose n'est pas un texte, c'est une propriété : *des causes différentes
produisent des sorties différentes*. Les phrases restent libres.

Le seul gardien textuel porte sur une **absence** — la page ne doit plus lire
`entrySnap.earnings_dte` — et celui-là est légitime : ce chemin est mort,
mesuré sans écrivain dans tout le dépôt.
"""
from __future__ import annotations

import json
import os
import re

import pytest

PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'vertex', 'ui', 'pages', 'portfolio_page.py')


def _source_page() -> str:
    with open(PAGE, encoding='utf-8') as fh:
        return fh.read()


def _code_sans_commentaires(source: str) -> str:
    """Le source privé de ses blocs `/* … */`.

    Sans ce filtre, les gardiens d'absence tomberaient sur le commentaire qui
    EXPLIQUE le défaut — la page serait accusée de relire un champ mort parce
    qu'elle documente pourquoi elle ne le relit plus.
    """
    return re.sub(r'/\*.*?\*/', ' ', source, flags=re.S)


def extraire_fonction(source: str, nom: str) -> str:
    """Le corps complet d'une `function <nom>(…){…}` par comptage d'accolades.

    Un `split` sur la fonction suivante casserait au premier réordonnancement ;
    l'équilibrage d'accolades survit à l'ordre du fichier.
    """
    debut = source.find('function %s(' % nom)
    assert debut != -1, 'fonction %s introuvable dans %s' % (nom, PAGE)
    ouvrante = source.find('{', debut)
    profondeur, i = 0, ouvrante
    while i < len(source):
        if source[i] == '{':
            profondeur += 1
        elif source[i] == '}':
            profondeur -= 1
            if profondeur == 0:
                return source[debut:i + 1]
        i += 1
    raise AssertionError('accolades non équilibrées pour %s' % nom)


def _chromium():
    from tools.mesures.mesurer_qa_espaces import _chromium as resoudre
    return resoudre()


def _navigateur_dispo() -> bool:
    try:
        import playwright  # noqa: F401
    except Exception:
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(executable_path=_chromium(),
                              args=['--no-sandbox']).close()
        return True
    except Exception:
        return False


_SANS_NAVIGATEUR = pytest.mark.skipif(
    not _navigateur_dispo(),
    reason='playwright/chromium absent — la propriété ne serait pas mesurée')


class Bac:
    """Un Chromium qui évalue les fonctions pures de la page."""

    def __init__(self, page, fonctions: str):
        self._page = page
        self._page.goto('about:blank')
        #  `evaluate` attend une EXPRESSION : une `function f(){}` y est une
        #  erreur de syntaxe. Le script injecté les déclare dans le global.
        self._page.add_script_tag(content=fonctions)

    def appel(self, expression: str):
        return self._page.evaluate('() => %s' % expression)


@pytest.fixture(scope='module')
def bac():
    from playwright.sync_api import sync_playwright
    src = _source_page()
    fns = '\n'.join(extraire_fonction(src, nom) for nom in
                    ('pfEtatEvenementiel', 'pfEtatBeta', 'pfEtatHhi',
                     'pfEtatDrawdown'))
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=_chromium(), args=['--no-sandbox'])
        page = nav.new_page()
        try:
            yield Bac(page, fns)
        finally:
            nav.close()


def _ev(bac, contrats):
    return bac.appel('pfEtatEvenementiel(%s)' % json.dumps(contrats))


def _beta(bac, valeur, couverture):
    return bac.appel('pfEtatBeta(%s, %s)'
                     % (json.dumps(valeur), json.dumps(couverture)))


def _hhi(bac, valeur, base, poids):
    return bac.appel('pfEtatHhi(%s, %s, %s)' % (json.dumps(valeur),
                                                json.dumps(base),
                                                json.dumps(poids)))


# ═══ Défaut 1 — Risque événementiel ═══

@_SANS_NAVIGATEUR
def test_evenementiel_separe_inconnu_de_aucun_et_de_proche(bac):
    """LA propriété que le tiret muet violait.

    Trois situations qui n'appellent pas la même action tenaient dans le même
    « — » : je ne connais pas la date · je la connais, rien ne tombe · elle
    tombe dans la vie du contrat. Le banc n'impose aucun libellé, seulement
    qu'ils diffèrent deux à deux.
    """
    inconnu = _ev(bac, [{'dte': 130, 'earningsDte': None},
                        {'dte': 200, 'earningsDte': None}])
    aucun = _ev(bac, [{'dte': 30, 'earningsDte': 90}])
    proche = _ev(bac, [{'dte': 130, 'earningsDte': 12}])

    valeurs = {inconnu['valeur'], aucun['valeur'], proche['valeur']}
    assert len(valeurs) == 3, (
        'deux causes distinctes rendent la même valeur : %r' % (valeurs,))
    sous = {inconnu['sous'], aucun['sous'], proche['sous']}
    assert len(sous) == 3, 'sous-titres non distincts : %r' % (sous,)

    #  Le défaut d'origine, nommément : plus aucune de ces causes ne rend le
    #  tiret cadratin muet.
    for etat in (inconnu, aucun, proche):
        assert etat['valeur'] != '—', etat


@_SANS_NAVIGATEUR
def test_evenementiel_compte_les_contrats_sans_date(bac):
    """« Inconnu » doit dire COMBIEN — sinon il ne se distingue pas d'un vide."""
    etat = _ev(bac, [{'dte': 130, 'earningsDte': None},
                     {'dte': 200, 'earningsDte': None}])
    assert '2' in etat['sous'], etat


@_SANS_NAVIGATEUR
def test_evenementiel_signale_le_chevauchement_et_son_echeance(bac):
    """Convention de `engines/earnings_option_overlap` : résultats ≤ DTE."""
    etat = _ev(bac, [{'dte': 130, 'earningsDte': 12},
                     {'dte': 40, 'earningsDte': 300}])
    assert etat['cls'] == 'vx-warn', etat
    assert '1' in etat['sous'] and '12' in etat['sous'], etat


@_SANS_NAVIGATEUR
def test_evenementiel_melange_connu_et_inconnu_sans_les_confondre(bac):
    """Un contrat daté + un contrat sans date : la part non sue reste dite."""
    etat = _ev(bac, [{'dte': 130, 'earningsDte': 12},
                     {'dte': 200, 'earningsDte': None}])
    assert 'sans date' in etat['sous'], etat


@_SANS_NAVIGATEUR
def test_evenementiel_distingue_injoignable_de_inconnu(bac):
    """Route muette ≠ calendrier vide. La première est une panne de lecture."""
    panne = _ev(bac, [{'indisponible': True}, {'indisponible': True}])
    vide = _ev(bac, [{'dte': 130, 'earningsDte': None}])
    assert panne['valeur'] != vide['valeur'], (panne, vide)
    assert panne['valeur'] != '—'


@_SANS_NAVIGATEUR
def test_evenementiel_sans_contrat_ne_ment_pas(bac):
    """Aucun contrat ouvert n'est pas « aucun risque »."""
    etat = _ev(bac, [])
    assert etat['valeur'] != '—'
    assert 'contrat' in etat['sous']


def test_le_champ_mort_n_est_plus_lu():
    """Gardien d'ABSENCE, seul cas où figer un texte se justifie.

    `entrySnap.earnings_dte` n'a aucun écrivain dans le dépôt : le formulaire
    de déclaration (`vx-entities.js:545`) pose `{stop, tgt, date}`. Relire ce
    champ, c'est réintroduire un prédicat toujours faux.
    """
    src = _code_sans_commentaires(_source_page())
    assert 'entrySnap.earnings_dte' not in src, (
        'la page relit un champ que personne n’écrit — le KPI redeviendrait '
        'muet sur 100 % des portefeuilles')


def test_la_promesse_de_colonne_absente_ne_revient_pas():
    """Le sous-titre renvoyait « ci-dessous » à une colonne inexistante.

    Mesuré dans le DOM : le tableau des positions options porte Contrat, Qté,
    Coût, Marque, P&L, DTE, Stop sous-jacent — pas d'earnings. Tant que la
    colonne n'existe pas, le KPI ne doit pas y renvoyer.
    """
    src = _code_sans_commentaires(_source_page())
    entetes = re.search(r'<th>Contrat</th>.*?<th></th>', src, re.S)
    assert entetes, 'en-têtes du tableau options introuvables'
    assert 'earnings' not in entetes.group(0).lower(), (
        'une colonne earnings existe désormais : ce gardien doit être relu, '
        'le renvoi « ci-dessous » redevient légitime')
    assert 'earnings par position ci-dessous' not in src, (
        'le KPI renvoie à une colonne que le tableau n’a pas')


# ═══ Défaut 2 — Bêta ═══

@_SANS_NAVIGATEUR
def test_beta_separe_non_declare_de_aucune_position_et_de_moteur_muet(bac):
    """Trois causes d'absence, trois sorties. C'est le défaut mesuré."""
    non_declare = _beta(bac, None, {'known_positions': 0, 'total_positions': 1,
                                    'missing_symbols': ['KO'], 'partial': True})
    aucune = _beta(bac, None, {'known_positions': 0, 'total_positions': 0,
                               'missing_symbols': [], 'partial': False})
    muet = _beta(bac, None, None)

    sous = {non_declare['sous'], aucune['sous'], muet['sous']}
    assert len(sous) == 3, 'trois causes, %d explication(s) : %r' % (len(sous), sous)
    for etat in (non_declare, aucune, muet):
        assert etat['valeur'] != '—', etat


@_SANS_NAVIGATEUR
def test_beta_absent_nomme_le_titre_qui_manque(bac):
    """Sans le symbole, l'utilisateur ne sait pas quoi corriger."""
    etat = _beta(bac, None, {'known_positions': 0, 'total_positions': 1,
                             'missing_symbols': ['KO'], 'partial': True})
    assert 'KO' in etat['sous'], etat


@_SANS_NAVIGATEUR
def test_beta_connu_dit_sa_couverture(bac):
    """Un bêta pondéré sur 1 titre sur 4 n'est pas le bêta du portefeuille."""
    complet = _beta(bac, 1.1, {'known_positions': 3, 'total_positions': 3,
                               'missing_symbols': [], 'partial': False})
    partiel = _beta(bac, 1.1, {'known_positions': 1, 'total_positions': 4,
                               'missing_symbols': ['KO', 'MSFT', 'GOOG'],
                               'partial': True})
    assert complet['valeur'] == 1.1 and partiel['valeur'] == 1.1
    assert complet['sous'] != partiel['sous'], (complet, partiel)
    assert partiel['cls'] == 'vx-warn', partiel
    assert 'KO' in partiel['sous'], partiel


def test_la_couverture_servie_est_effectivement_lue():
    """`beta_coverage` était servi par risk_engine et ignoré par la page.

    Gardien de PRÉSENCE d'une lecture, pas d'une phrase : si la page cesse de
    lire la couverture, le KPI ne peut plus expliquer l'absence.
    """
    src = _code_sans_commentaires(_source_page())
    assert 'risk.beta_coverage' in src, (
        'la page a cessé de lire beta_coverage — le tiret redevient muet')


def test_les_deux_fonctions_sont_pures():
    """Aucun accès réseau ni DOM : le banc peut donc les exécuter isolément.

    Une de ces fonctions qui se mettrait à `fetch` ferait rentrer une collecte
    dans le rendu d'un KPI — exactement ce que la doctrine des instantanés
    bornés interdit.
    """
    src = _source_page()
    for nom in ('pfEtatEvenementiel', 'pfEtatBeta', 'pfEtatHhi', 'pfEtatDrawdown'):
        corps = _code_sans_commentaires(extraire_fonction(src, nom))
        for interdit in ('fetch(', 'document.', 'window.', 'await ', 'XMLHttpRequest'):
            assert interdit not in corps, (
                '%s n’est plus pure : elle contient %r' % (nom, interdit))


# ═══ Défaut 3 — HHI ═══

BASE = 'compartiment actions, poids renormalisés à 100 % — cash exclu du calcul'


@_SANS_NAVIGATEUR
def test_hhi_absent_ne_recite_pas_la_base_du_calcul(bac):
    """MESURE — `weights` = {KO: 0.0, _CASH: 100.0}, `invested_pct` 0.0, donc
    `hhi: null`. Le KPI rendait « — » sous « indice · compartiment actions,
    poids renormalisés à 100 % » : une méthode affirmée pour un calcul qui n'a
    pas eu lieu. Sans indice, c'est la cause qui doit être servie.
    """
    vide = _hhi(bac, None, BASE, {'KO': 0.0, '_CASH': 100.0})
    assert vide['valeur'] != '—', vide
    assert BASE not in vide['sous'], (
        'la base du calcul est récitée alors qu’aucun indice n’a été calculé')


@_SANS_NAVIGATEUR
def test_hhi_distingue_ses_causes_d_absence(bac):
    """Aucune action déclarée · actions à poids nul · moteur muet."""
    aucune = _hhi(bac, None, BASE, {'_CASH': 100.0})
    poids_nul = _hhi(bac, None, BASE, {'KO': 0.0, '_CASH': 100.0})
    muet = _hhi(bac, None, BASE, {'KO': 60.0, 'MSFT': 40.0})
    sous = {aucune['sous'], poids_nul['sous'], muet['sous']}
    assert len(sous) == 3, 'trois causes, %d explication(s) : %r' % (len(sous), sous)


@_SANS_NAVIGATEUR
def test_hhi_connu_garde_sa_base(bac):
    """Témoin négatif : quand l'indice existe, la base RESTE — elle est alors
    la seule chose qui rend « 1 » lisible (1 sur le compartiment actions n'est
    pas 1 sur le capital total)."""
    connu = _hhi(bac, 1.0, BASE, {'KO': 100.0, '_CASH': 0.0})
    assert connu['valeur'] == 1.0
    assert BASE in connu['sous'], connu


# ═══════════════════════════════════════════════════════════════════════════
# CONTRÔLE ADVERSE DU 06/09/2026 — ce que la première réparation a supposé,
# et ce qu'elle a laissé derrière elle.
#
# 1. FAUSSE PRÉMISSE. Le « Risque événementiel » a troqué un champ mort
#    (`entrySnap.earnings_dte`) contre une LECTURE morte : `/api/positions/state`
#    ne publie pas `days_to_earnings` pour un CONTRAT. Mesure — `recalculate_all`
#    sur un desk AAPL {1 CALL, 10 actions} avec un scan qui sert
#    `earnings_dte: 5` rend `days_to_earnings 5` sur l'ACTION et `None` sur le
#    CONTRAT ; sur l'instance QA, 2 contrats sur 2 rendent `None`. Les branches
#    « à vérifier » et « aucun chevauchement » étaient donc inatteignables en
#    production, et l'écran affichait « calendrier non servi » — une donnée en
#    attente — pour une capacité qui n'existe pas (invariant 6).
#
# 2. COÛT. Cette lecture faisait coter TOUT le desk par le worker `posq`
#    (`positions_api._quotes`, `timeout=45`), sur un panier différent de celui
#    de `/api/pos-quotes` déjà demandé par la même vue : un SECOND aller-retour
#    courtier, hors du memo de 15 s. Le « ~10 ms » certifié venait d'une
#    instance NO_IBKR=1, la seule configuration où `_quotes` rend `{}` sans rien
#    demander (positions_api.py le dit lui-même, lignes 103-108).
#
# 3. MANQUÉ, DANS LA MÊME INSTRUCTION. `_rk('Drawdown', …, 'pic')` récitait la
#    base d'un calcul jamais fait — la faute nommée deux lignes plus haut pour
#    le HHI. Mesure sur le payload EXACT de la page : `drawdown_pct: null`, et
#    la page n'envoie jamais `peak_equity` : absence structurelle, 100 % des
#    rendus.
#
# 4. MANQUÉ, DANS LA COLONNE MÊME QU'ELLE A RELEVÉE. « Stop sous-jacent »
#    rendait « — » sur 2 lignes sur 2 (relevé DOM), via `VX.fmt.nd`.
# ═══════════════════════════════════════════════════════════════════════════

import ast

CALCULATEUR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'vertex', 'positions', 'calculator.py')


def _fonctions_qui_ecrivent(champ):
    """Les fonctions de `calculator.py` qui affectent `p['<champ>']`.

    AST, pas texte : un renommage de variable ou un réordonnancement ne doit pas
    faire tomber ce banc ; seule l'écriture réelle du champ compte.
    """
    with open(CALCULATEUR, encoding='utf-8') as fh:
        arbre = ast.parse(fh.read())
    ecrivains = set()
    for fonction in ast.walk(arbre):
        if not isinstance(fonction, ast.FunctionDef):
            continue
        for noeud in ast.walk(fonction):
            if (isinstance(noeud, ast.Subscript)
                    and isinstance(noeud.ctx, ast.Store)
                    and isinstance(noeud.slice, ast.Constant)
                    and noeud.slice.value == champ):
                ecrivains.add(fonction.name)
    return ecrivains


def test_le_desk_ne_publie_pas_la_date_de_resultats_d_un_contrat():
    """LE banc qui prouve la fausse prémisse — et qui rend la main.

    Il TOMBERA le jour où `enrich_option` publiera `days_to_earnings`. Ce jour-là
    la capacité existera, `NON_IMPLÉMENTÉ` deviendra faux, et il faudra
    rebrancher la lecture de `/api/positions/state` dans `renderOptions` : les
    branches « à vérifier » / « aucun chevauchement » de `pfEtatEvenementiel`
    sont déjà écrites et déjà gardées pour ce moment-là.
    """
    ecrivains = _fonctions_qui_ecrivent('days_to_earnings')
    assert 'enrich_stock' in ecrivains, (
        'le producteur du champ a changé : ce banc doit être relu')
    assert 'enrich_option' not in ecrivains, (
        'CAPACITÉ DEVENUE RÉELLE : `enrich_option` publie désormais '
        '`days_to_earnings`. Le KPI « Risque événementiel » ne doit plus dire '
        'NON_IMPLÉMENTÉ — rebrancher la lecture de /api/positions/state dans '
        'renderOptions et repasser `{dte, earningsDte}` à pfEtatEvenementiel.')


@_SANS_NAVIGATEUR
def test_evenementiel_nomme_la_capacite_absente_au_lieu_d_une_attente(bac):
    """« Calendrier non servi » se lit comme une donnée qui va arriver.

    Elle n'arrivera pas : aucun producteur ne l'écrit. L'état doit se distinguer
    d'une simple absence de date ET d'une route injoignable (invariant 6).
    """
    non_implemente = _ev(bac, [{'nonPublie': True}, {'nonPublie': True}])
    sans_date = _ev(bac, [{'dte': 130, 'earningsDte': None}])
    injoignable = _ev(bac, [{'indisponible': True}])

    valeurs = {non_implemente['valeur'], sans_date['valeur'], injoignable['valeur']}
    assert len(valeurs) == 3, 'trois causes, %r' % (valeurs,)
    assert 'NON_IMPL' in non_implemente['valeur'].upper(), non_implemente
    assert '2' in non_implemente['sous'], non_implemente


def test_la_vue_options_ne_paie_plus_un_aller_retour_pour_rien():
    """Un appel réseau dont la réponse est nulle par construction reste un appel.

    MESURE : la page comptait DEUX lectures de `/api/positions/state` — celle de
    la vue Positions (légitime : elle en lit source, statut et action) et celle
    du KPI événementiel (rien à en tirer). La seconde ajoutait au rendu de la
    vue Options un second travail `posq` (`timeout=45`) sur un panier différent
    de `/api/pos-quotes`, donc hors du memo de 15 s.

    Ce banc COMPTE les lectures ; il ne fige aucune phrase.
    """
    src = _code_sans_commentaires(_source_page())
    assert src.count('/api/positions/state') == 1, (
        'la vue Options relit l’état des positions pour un champ que le desk '
        'ne publie pas sur un contrat — %d lecture(s) trouvée(s)'
        % src.count('/api/positions/state'))


# ═══ Défaut 4 — Drawdown : la base récitée sans le calcul ═══

@_SANS_NAVIGATEUR
def test_drawdown_absent_ne_recite_plus_sa_base(bac):
    """MESURE — sur le payload exact de la page (`{positions, option_positions,
    cash, simulated}`), `/api/portfolio/team` rend `drawdown_pct: null`, et le
    KPI affichait « n/d » sous « pic ». La page n'envoie jamais `peak_equity` :
    l'absence est structurelle, pas en retard. Trois situations, trois sorties.
    """
    connu = bac.appel('pfEtatDrawdown(-12.4, true)')
    sans_pic = bac.appel('pfEtatDrawdown(null, false)')
    moteur_muet = bac.appel('pfEtatDrawdown(null, true)')

    sous = {connu['sous'], sans_pic['sous'], moteur_muet['sous']}
    assert len(sous) == 3, 'trois causes, %d explication(s) : %r' % (len(sous), sous)
    assert sans_pic['sous'].strip() != 'pic', sans_pic
    assert 'pic' in sans_pic['sous'], (
        'la cause doit nommer ce qui manque, pas seulement dire « n/d »')
    #  Témoin négatif : nommer l'absence ne doit pas manger la valeur connue.
    assert '12.4' in str(connu['valeur']) or '12,4' in str(connu['valeur']), connu


# ═══ Défaut 5 — « Stop sous-jacent » : deux tirets muets sur deux lignes ═══

def test_le_stop_sous_jacent_absent_dit_qu_il_n_est_pas_declare():
    """Relevé DOM du 06/09/2026, /portfolio?view=options : la colonne « Stop
    sous-jacent » rendait « — » sur 2 lignes sur 2, via `VX.fmt.nd`, dans le
    tableau dont la première réparation a lu les en-têtes pour prouver qu'aucune
    colonne « earnings » n'existait.

    Ce banc mesure une PROPRIÉTÉ de la cellule — elle porte une branche
    d'absence nommée — et n'impose aucun libellé.
    """
    src = _code_sans_commentaires(_source_page())
    cellule = re.search(r'<td data-label="Stop">(.*?)</td>', src, re.S)
    assert cellule, 'la cellule du stop sous-jacent est introuvable'
    corps = cellule.group(1)
    assert '?' in corps and 'vx-muted' in corps, (
        'la cellule délègue son absence au formateur muet : « stop non déclaré » '
        'et « donnée perdue » s’écrivent du même tiret — %r' % corps)
