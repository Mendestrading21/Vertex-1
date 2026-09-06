# -*- coding: utf-8 -*-
"""Aucun hôte de contenu des vues Options ne reste MUET dans un état dégradé.

Mesure du 2026-09-06 (contrôle adverse) : sur `/options?view=scenarios`, la
branche « aucun titre dans le tableau » ne nommait qu'UN hôte sur deux. Le
second, `vx-opt-strategies`, gardait son texte de départ — « Choisis un symbole
pour construire les stratégies depuis le board » — à l'identique dans les DEUX
états mesurés : board vide (consigne inapplicable, puisqu'il n'y a aucun
symbole à choisir) et lecture en échec HTTP 503 (panne tue). C'est la même
confusion entre absence et panne qu'un correctif venait de fermer sur le rail
voisin de la même vue.

Ce banc lit les DEUX sources et les rapproche : tout hôte de contenu déclaré
dans le gabarit d'une vue doit être nommé par la branche dégradée de cette vue.
Aucun réseau, aucun navigateur.
"""
import os
import re

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PAGE = os.path.join(_RACINE, 'vertex', 'ui', 'pages', 'options_intel_page.py')
_JS = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js', 'pages', 'options-intel.js')
_GEX = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js', 'pages', 'options-gex.js')
_STRUCT = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js', 'pages', 'options-structure.js')
_SYMBOLE_JS = os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js', 'pages', 'options-symbol.js')
_SYMBOLE_PAGE = os.path.join(_RACINE, 'vertex', 'ui', 'pages', 'options_symbol_page.py')

#: Les vues dont la branche dégradée passe par `nommerAbsenceDeTableau`.
_VUES = ('volatility', 'scenarios', 'events')
#: Un hôte de CONTENU est un conteneur rempli par le JS. Le pont local (champ
#: de saisie et bouton, `hidden`) et les sections englobantes n'en sont pas.
_PONT = re.compile(r'vx-opt-\w+-(sym|go)$')


def _lire(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def _gabarit(vue: str) -> str:
    src = _lire(_PAGE)
    debut = src.index("    '%s': \"\"\"" % vue)
    fin = src.index('\n"""', debut)
    return src[debut:fin]


def _hotes_de_contenu(vue: str, prefixe: str = 'vx-opt-') -> set[str]:
    """Les `<div id="…">` que le JS doit remplir, hors pont et hors sections."""
    gab = _gabarit(vue)
    #  Un hôte porte souvent une classe de grille AVANT son identifiant
    #  (`<div class="vx-col-4" id="vx-opt-cone">`) : chercher `<div id=` seul
    #  n'en voyait qu'un sur cinq — une garde qui ne mesure presque rien.
    ids = set(re.findall(r'<div[^>]*\bid="(%s[\w-]+)"' % re.escape(prefixe), gab))
    return {i for i in ids if not _PONT.search(i)}


def _contenu_de_depart(vue: str, hote: str) -> str:
    """Ce que le GABARIT met dans un hôte avant que le JS n'ait parlé.

    Un hôte qui part vide n'a que le JS pour dire sa cause ; un hôte qui part
    avec un motif est déjà honnête si le script ne se charge pas."""
    gab = _gabarit(vue)
    m = re.search(r'<div[^>]*\bid="%s"[^>]*>(.*?)</div>\s*(?:</|<div|<section|<aside|<details|$)'
                  % re.escape(hote), gab, re.S)
    return (m.group(1) if m else '').strip()


def _hotes_nommes(vue: str) -> set[str]:
    """Les identifiants passés à `nommerAbsenceDeTableau` pour cette vue."""
    js = _lire(_JS)
    charnieres = {'volatility': 'vx-opt-vol-out-body',
                  'scenarios': 'vx-opt-sc-out-body',
                  'events': 'vx-opt-ev-out-body'}
    rail = charnieres[vue]
    m = re.search(r"nommerAbsenceDeTableau\(\s*'%s'\s*,\s*\[([^\]]*)\]" % re.escape(rail), js)
    assert m, 'la vue %s n’appelle plus nommerAbsenceDeTableau' % vue
    return {rail} | set(re.findall(r"'([^']+)'", m.group(1)))


def test_le_banc_mesure_bien_quelque_chose():
    """Une garde qui n'inspecte rien est une garde qui ment."""
    for vue in _VUES:
        assert _hotes_de_contenu(vue), vue
    assert 'vx-opt-strategies' in _hotes_de_contenu('scenarios')
    assert len(_hotes_de_contenu('volatility')) >= 4


def test_chaque_hote_de_contenu_est_nomme_dans_l_etat_degrade():
    manquants = {}
    for vue in _VUES:
        oublies = _hotes_de_contenu(vue) - _hotes_nommes(vue)
        if oublies:
            manquants[vue] = sorted(oublies)
    assert not manquants, (
        'ces hôtes gardent leur texte de départ dans les DEUX états dégradés — '
        'une consigne inapplicable quand le tableau est vide, une panne muette '
        'quand la lecture échoue : %s' % manquants)


def test_l_etat_de_PANNE_est_distinct_de_l_etat_d_ABSENCE():
    """Un hôte qui dit la même chose dans les deux états ne dit rien."""
    js = _lire(_JS)
    m = re.search(r'function nommerAbsenceDeTableau\([^)]*\)\s*\{(.*?)\n  \}', js, re.S)
    assert m, 'nommerAbsenceDeTableau introuvable'
    corps = m.group(1)
    assert 'lecture en échec' in corps, 'la panne doit être nommée comme telle'
    assert 'VX.states.error' in corps and 'VX.states.empty' in corps, (
        'les deux états doivent employer deux rendus DISTINCTS')


def test_la_vue_structure_nomme_ses_quatre_hotes():
    """Même défaut, autre fichier : `options-structure.js` en vidait deux."""
    src = _lire(os.path.join(_RACINE, 'vertex', 'static', 'vertex', 'js',
                             'pages', 'options-structure.js'))
    m = re.search(r'var HOTES_STRUCTURE = \[(.*?)\];', src, re.S)
    assert m, 'la liste des hôtes de la vue Structure a disparu'
    hotes = set(re.findall(r"\['([\w-]+)'", m.group(1)))
    assert hotes == {'vx-os-scenarios', 'vx-os-compare', 'vx-os-payoff', 'vx-os-greeks'}, hotes
    #  Les trois chemins dégradés (aucune structure, analyse absente, panne)
    #  passent tous par le même endroit : aucun ne peut en oublier un.
    assert src.count('nommerAbsenceStructure(') >= 4, (
        'un chemin dégradé ne passe pas par le nommage commun')


# ─────────────────────────────────────────────────────────────────────────────
#  VUE POSITIONNEMENT — même défaut, troisième fichier.
#
#  MESURE du 2026-09-06 (Chromium 151, instance de contrôle sans IBKR,
#  `/options?view=positioning`, 1600 px) : sur les sept hôtes déclarés par le
#  gabarit, DEUX rendaient 0 octet et 0 px à l'ouverture — `vx-gx-thesis` et
#  `vx-gx-tiles` — parce que `options-gex.js` n'appelle `load()` que si un
#  ticker actif traîne dans le store ; un troisième, `vx-cp-out`, partait vide
#  lui aussi. Un quatrième, `vx-gx-flow`, affichait « — » : un tiret NU, qui
#  n'est pas un motif. Et après une lecture rendant `gex.empty`, `renderTiles`
#  remettait explicitement `innerHTML = ''` pendant que la thèse et les barres
#  nommaient l'absence : deux hôtes muets pour un état que trois autres
#  savaient dire. Enfin, le `.catch` de `load()` ne rafraîchissait que la
#  thèse : les quatre autres gardaient les chiffres du symbole PRÉCÉDENT sous
#  le titre du nouveau — une valeur fausse, pas une absence.
# ─────────────────────────────────────────────────────────────────────────────
_VUES_ETENDUES = {
    'volatility': 'vx-opt-', 'scenarios': 'vx-opt-', 'events': 'vx-opt-',
    'structure': 'vx-os-', 'positioning': 'vx-gx-', 'leaps': 'vx-lp-',
    'overview': 'vx-opt-', 'radar': 'vx-opt-', 'positions': 'vx-op-',
}
#: Un RAIL DE RACCOURCIS (`…-chips`) ne porte aucune mesure : il aligne les
#: symboles du tableau. Son absence est déjà dite par l'hôte de contenu qu'il
#: surmonte ; lui réclamer un motif ajouterait du bruit, pas de l'honnêteté.
_RAIL = re.compile(r'-chips$')


def _texte_rendu(js: str) -> str:
    """Le texte tel que l'écran l'affiche : les `\\uXXXX` redeviennent lettres."""
    return re.sub(r'\\u([0-9a-fA-F]{4})',
                  lambda m: chr(int(m.group(1), 16)), js)


def _hotes_deja_en_carte(gabarit: str) -> set[str]:
    """Les identifiants dont un ANCÊTRE porte déjà la classe `vx-card`.

    Lecture de l'arbre, pas comptage de `<section>` : le gabarit encadre selon
    le cas avec `<section>`, `<aside>` ou `<div>`, et une garde qui ne
    connaîtrait qu'une de ces trois balises se tromperait en silence."""
    from html.parser import HTMLParser

    VIDES = {'input', 'br', 'img', 'hr', 'meta', 'link'}

    class Arbre(HTMLParser):
        def __init__(self):
            super().__init__()
            self.pile, self.dedans = [], set()

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            carte = 'vx-card' in (a.get('class') or '').split()
            if a.get('id') and any(self.pile):
                self.dedans.add(a['id'])
            if tag not in VIDES:
                self.pile.append(carte)

        def handle_startendtag(self, tag, attrs):
            a = dict(attrs)
            if a.get('id') and any(self.pile):
                self.dedans.add(a['id'])

        def handle_endtag(self, tag):
            if self.pile:
                self.pile.pop()

    p = Arbre()
    p.feed(gabarit)
    return p.dedans


def _liste_js(chemin: str, nom: str) -> set[str]:
    """Les identifiants d'une liste `var NOM = [['id', '…'], …];`."""
    src = _lire(chemin)
    m = re.search(r'var %s = \[(.*?)\];' % re.escape(nom), src, re.S)
    assert m, 'la liste %s a disparu de %s' % (nom, os.path.basename(chemin))
    return set(re.findall(r"\['([\w-]+)'", m.group(1)))


def test_la_vue_positionnement_nomme_ses_hotes():
    """HOTES_GEX doit couvrir les hôtes `vx-gx-*` du gabarit, radar excepté.

    Le radar n'est pas une exemption gratuite : il porte son propre chargeur et
    son propre `.catch`, tous deux vérifiés ici."""
    gabarit = _hotes_de_contenu('positioning', 'vx-gx-')
    assert 'vx-gx-thesis' in gabarit and 'vx-gx-tiles' in gabarit, gabarit
    nommes = _liste_js(_GEX, 'HOTES_GEX')
    oublies = gabarit - nommes - {'vx-gx-radar'}
    assert not oublies, (
        'ces hôtes de la vue Positionnement ne sont nommés dans aucun état '
        'dégradé — mesurés à 0 octet le 2026-09-06 : %s' % sorted(oublies))
    gex = _lire(_GEX)
    bloc = re.search(r'function loadRadar\(\)\s*\{(.*?)\n  \}', gex, re.S)
    assert bloc, 'loadRadar a disparu : le radar ne peut plus être exempté'
    assert '.catch(' in bloc.group(1) and 'vx-error-banner' in bloc.group(1), (
        'le radar n’a plus de branche de panne : il ne peut plus être exempté')


def test_un_hote_sans_carte_dans_le_gabarit_fabrique_la_sienne():
    """Le motif d'absence tient le même rang visuel que le rendu nominal.

    MESURE (capture Chromium 1600 px du 2026-09-06) : sur les cinq hôtes de la
    vue Positionnement, `vx-gx-thesis` et `vx-gx-tiles` sont les seuls que le
    gabarit ne place PAS dans une `<section class=\"vx-card\">` ; leur motif
    d'absence flottait donc en texte nu entre deux cartes encadrées. Leur rendu
    NOMINAL, lui, fabrique bien sa carte. Le banc rapproche les deux sources :
    l'encadrement déclaré dans HOTES_GEX doit être l'exact complément de
    l'encadrement fourni par le gabarit — pas une liste à maintenir à la main.

    CONTRE-MESURE du 2026-09-06 : la règle ne valait que pour la vue
    Positionnement, et la vue Structure la violait de la même façon —
    `vx-os-scenarios` mesuré à 44,75 px et `vx-os-compare` à 76,75 px, tous
    deux `closest('.vx-card')` nul et zéro carte à l'intérieur, quand leurs
    rendus nominaux (`renderScenarios`, `renderCompare`) fabriquent la leur et
    que le verdict voisin tient 84,5 px dans une carte. Le banc s'applique
    donc aux DEUX listes ; une troisième vue qui adopterait le motif viendra
    s'y ajouter en une ligne."""
    cas = [('positioning', _GEX, 'HOTES_GEX'),
           ('structure', _STRUCT, 'HOTES_STRUCTURE')]
    for vue, chemin, nom in cas:
        gab = _gabarit(vue)
        src = _lire(chemin)
        m = re.search(r'var %s = \[(.*?)\];' % re.escape(nom), src, re.S)
        assert m, '%s a disparu' % nom
        entrees = re.findall(r"\['([\w-]+)',[^\]]*?,\s*(true|false)\]", m.group(1))
        assert len(entrees) == len(re.findall(r"\['[\w-]+'", m.group(1))), (
            'chaque hôte de %s doit dire s’il fabrique sa carte' % nom)
        encadres = _hotes_deja_en_carte(gab)
        for hote, fabrique in entrees:
            encadre = hote in encadres
            assert (fabrique == 'true') != encadre, (
                '%s : le gabarit %s l’encadre, %s dit fabrique=%s — le motif '
                'flotte hors carte, ou la carte est doublée'
                % (hote, '' if encadre else 'n’', nom, fabrique))
        #  Un point d'encadrement UNIQUE : si un chemin écrivait encore
        #  `innerHTML` en direct sur un hôte qui doit fabriquer sa carte, la
        #  règle ci-dessus serait vraie sur le papier et fausse à l'écran.
        fabriquants = [h for h, f in entrees if f == 'true']
        for hote in fabriquants:
            direct = re.findall(r"\$\('%s'\)[^\n]*\.innerHTML\s*=" % re.escape(hote), src)
            assert not direct, (
                '%s doit fabriquer sa carte, mais %s lui écrit en direct '
                '(%d occurrence(s)) : le motif repart hors carte'
                % (hote, os.path.basename(chemin), len(direct)))


def test_les_trois_chemins_degrades_du_positionnement_passent_par_le_nommage():
    """Aucune absence, aucune panne, aucun `gex.empty` ne peut oublier un hôte."""
    gex = _lire(_GEX)
    assert gex.count('nommerAbsenceGex(') >= 3, (
        'un chemin dégradé de la vue Positionnement ne passe pas par le '
        'nommage commun (attendus : aucun sous-jacent choisi, lecture en '
        'échec, et le rendu de chargement)')
    #  La PANNE doit être un rendu DISTINCT de l'absence, comme sur les autres
    #  vues : un hôte qui dit la même chose dans les deux états ne dit rien.
    corps = re.search(r'function nommerAbsenceGex\([^)]*\)\s*\{(.*?)\n  \}', gex, re.S)
    assert corps, 'nommerAbsenceGex introuvable'
    assert 'VX.states.error' in corps.group(1), 'la panne doit avoir son propre rendu'
    assert 'la lecture a échoué' in gex, 'la panne doit être nommée comme telle'


def test_le_dossier_options_nomme_ses_graphiques_derives():
    """`vx-osym-decay` et `vx-osym-ivsens` : mesurés à 0 octet / 0 px.

    MESURE du 2026-09-06 sur `/options/dossier/SPY` : ces deux emplacements,
    déclarés par `options_symbol_page.py`, restaient littéralement vides dans
    les trois chemins (scénarios absents, moins de deux points, lecture en
    échec) alors que les quatre cartes voisines nommaient leur cause."""
    gab = _lire(_SYMBOLE_PAGE)
    declares = set(re.findall(r'<div[^>]*\bid="(vx-osym-(?:decay|ivsens))"', gab))
    assert declares == {'vx-osym-decay', 'vx-osym-ivsens'}, declares
    nommes = _liste_js(_SYMBOLE_JS, 'HOTES_SIM')
    assert declares <= nommes, sorted(declares - nommes)
    js = _lire(_SYMBOLE_JS)
    assert js.count('nommerAbsenceSim(') >= 3, (
        'les trois chemins (scénarios absents, lecture en échec, et le nommage '
        'lui-même) doivent passer par le point unique')
    #  Le cas « moins de deux points » ne peut plus être un silence : il doit
    #  écrire le compte réel de points reçus.
    for hote in ('vx-osym-decay', 'vx-osym-ivsens'):
        assert re.search(r"emptyChart\('%s'" % hote, js), (
            '%s n’a pas de branche « pas assez de points »' % hote)


#: Un `innerHTML = ''` suivi d'un `return` est TERMINAL : l'hôte reste vide et
#: le script rend la main. Le même geste suivi d'une repeinte (`clearChart`,
#: effacer juste avant `VC.card`) est légitime — la garde mesure la FORME
#: terminale, pas le mot-clé, sinon elle interdirait la repeinte.
_VIDAGE_TERMINAL = re.compile(r"\.innerHTML\s*=\s*''\s*;\s*return\s*;")


def test_aucun_hote_options_ne_reste_vide_en_silence():
    """Aucun vidage TERMINAL dans les scripts de page Options.

    C'était le geste exact des défauts mesurés le 2026-09-06 dans Chromium :
    `renderCompare` (options-structure.js), `renderTiles` (options-gex.js), le
    nuage du radar (options-intel.js) et le mini-payoff d'une stratégie
    (options-symbol.js) vidaient un hôte au lieu de dire pourquoi. Un hôte vide
    est indiscernable de « le script n'est jamais passé »."""
    fautifs = {}
    for chemin in (_JS, _GEX, _STRUCT, _SYMBOLE_JS):
        src = _lire(chemin)
        for m in _VIDAGE_TERMINAL.finditer(src):
            ligne = src[:m.start()].count('\n') + 1
            fautifs.setdefault(os.path.basename(chemin), []).append(ligne)
    assert not fautifs, (
        'ces lignes laissent un hôte vide et rendent la main — le vide ne '
        'distingue pas « rien à montrer » de « la lecture a échoué » : %s'
        % fautifs)


def test_chaque_hote_de_vue_part_avec_un_motif_ou_est_nomme_par_le_js():
    """La mesure générale : un hôte n'est jamais vide SANS motif.

    Un hôte satisfait le contrat de deux façons — le gabarit lui donne un
    contenu de départ (motif, squelette, état), ou le JS de sa vue le nomme
    dans son état dégradé. Ni l'un ni l'autre = l'écran mesuré le 2026-09-06 :
    des rectangles de 0 px sous des titres qui promettaient une lecture."""
    nommes_par_vue = {
        'structure': _liste_js(_STRUCT, 'HOTES_STRUCTURE'),
        'positioning': _liste_js(_GEX, 'HOTES_GEX') | {'vx-gx-radar'},
        'volatility': _hotes_nommes('volatility'),
        'scenarios': _hotes_nommes('scenarios'),
        'events': _hotes_nommes('events'),
    }
    muets = {}
    for vue, prefixe in _VUES_ETENDUES.items():
        for hote in _hotes_de_contenu(vue, prefixe) | _hotes_de_contenu(vue, 'vx-cp-'):
            if _RAIL.search(hote):
                continue
            if _contenu_de_depart(vue, hote):
                continue
            if hote in nommes_par_vue.get(vue, set()):
                continue
            muets.setdefault(vue, []).append(hote)
    assert not muets, (
        'ces hôtes partent vides et aucun état dégradé ne les nomme : %s'
        % {k: sorted(v) for k, v in muets.items()})


def test_la_table_d_open_interest_ne_fabrique_pas_de_zero():
    """« zéro observé » ≠ « zéro imputé » — la table ne doit pas les confondre.

    MESURE du 2026-09-06 sur `/api/options/vol-charts/NVDA` (instance de
    contrôle) : les trois lignes rendues portent « put : 0 » alors que le
    tableau d'options ne contient AUCUN contrat PUT sur NVDA — trois zéros
    IMPUTÉS par l'agrégateur, zéro observé. La table les écrivait « 0 » via
    `r.put || 0` (donc l'interface en fabriquait un de plus pour une valeur
    absente) sous une note qui AFFIRMAIT « 0 est un zéro mesuré, pas une
    absence » : faux sur 3 cellules sur 3."""
    js = _lire(_JS)
    bloc = re.search(r"tableEquivalente\('vx-opt-oi'(.*?)\n    \}\);", js, re.S)
    assert bloc, 'la table équivalente de l’open interest a disparu'
    corps = bloc.group(1)
    #  Les commentaires CITENT l'ancien code pour porter la mesure : les retirer,
    #  sinon la garde se déclencherait sur sa propre explication.
    code = re.sub(r'/\*.*?\*/', '', corps, flags=re.S)
    assert 'r.call || 0' not in code and 'r.put || 0' not in code, (
        'un côté ABSENT redevient « 0 » : l’interface fabrique un zéro')
    assert "r.call == null ? '—'" in code and "r.put == null ? '—'" in code, (
        'un côté absent doit rendre un tiret, pas un zéro')
    #  Ce que l'utilisateur LIT : la source mélange les `\\uXXXX` et les accents
    #  réels ; la garde mesure le texte rendu, pas la façon de l'écrire.
    lu = _texte_rendu(code)
    assert 'est un zéro mesuré, pas une absence' not in _texte_rendu(js), (
        'la note affirme une distinction que la source ne fait pas')
    assert 'zéro observé' in lu and 'zéro imputé' in lu, (
        'la note doit nommer la limite au lieu de la nier')


def test_la_conclusion_de_l_open_interest_ne_compte_pas_les_absences():
    """Le compte de strikes « à zéro » ne doit pas compter les strikes ABSENTS.

    CONTRE-MESURE du 2026-09-06 (Chromium sur l'instance de contrôle,
    `/options?view=volatility`, réponse de `/api/options/vol-charts/NVDA`
    substituée pour porter les trois cas d'un coup) : les CELLULES de la table
    équivalente avaient appris à séparer l'absence du zéro, mais la CONCLUSION
    de la même carte comptait encore `!r.call && !r.put` — vrai pour `0` comme
    pour `null`. Sur les lignes servies [226 : call 2959 / put absent],
    [230 : call 0 / put 12] et [235 : les deux absents], la carte affichait
    « 1 à zéro des deux côtés » : l'unique ligne comptée ne portait AUCUNE
    valeur d'aucun côté. Après correction, même charge : « 0 à zéro reçu des
    deux côtés · 2 sans valeur d'un côté au moins ».

    Le banc mesure la PROPRIÉTÉ du prédicat — un champ numérique ne se teste
    pas par sa véracité JavaScript — et non la phrase, pour qu'un reformulage
    du texte reste possible."""
    js = _lire(_JS)
    bloc = re.search(r'function chartOI\(VC, d\)\s*\{(.*?)\n    _charts\.push\(c\);',
                     js, re.S)
    assert bloc, 'chartOI a disparu : le compte de strikes n’est plus mesurable'
    code = re.sub(r'/\*.*?\*/', '', bloc.group(1), flags=re.S)
    code = re.sub(r'//[^\n]*', '', code)
    #  Le prédicat fautif, sous ses deux ordres d'écriture.
    for faute in ('!r.call && !r.put', '!r.put && !r.call'):
        assert faute not in code, (
            'le compte de strikes emploie `%s` : `!null` vaut `true` comme '
            '`!0`, donc une absence est comptée comme un zéro observé' % faute)
    #  Et il doit tester explicitement les deux cas, séparément.
    assert re.search(r'r\.call === 0', code) and re.search(r'r\.put === 0', code), (
        'le zéro doit être testé par identité (`=== 0`), sinon il englobe '
        'l’absence')
    assert re.search(r'r\.call == null', code) and re.search(r'r\.put == null', code), (
        'l’absence doit avoir son propre compte, distinct du zéro reçu')
