"""tests/test_performance_population_par_vue.py — LOT G : l'en-tête de
Performance annonçait la MAUVAISE population sur quatre vues sur six, et sa
pastille d'échantillon restait sur « Lecture… » pour toujours.

MESURES DU 06/09/2026 (Chromium sur l'instance QA 5003, lecture du DOM après
chargement complet, desk vide) — AVANT le correctif :

  · `/performance?view=track-record` servait, dans la même page :
      barre d'en-tête → « POPULATION MESURÉE Trades réels déclarés au journal
                         du desk · NATURE Réalisé — encaissé · CALCUL
                         Arithmétique sur vos déclarations — aucun moteur »
      bannière de vue → « Population : verdicts rendus par les moteurs … Ces
                         chiffres ne se mélangent JAMAIS avec vos trades
                         déclarés »
      carte servie    → « 1026 verdict(s) enregistré(s) » depuis
                         `/api/track-record`, c'est-à-dire un MOTEUR.
    L'en-tête contredisait donc la bannière, la carte, et la règle que la page
    énonce elle-même (« un indicateur ne mélange jamais deux de ces lignes »).
    Les six vues partageaient une seule barre : 1 barre distincte pour 6 vues.

  · Pastille « Échantillon » : « Lecture… » sur journal, learnings,
    progression ET track-record — indéfiniment, `echantillon()` n'étant
    appelée que pour `overview` et `real`.

APRÈS : 3 barres distinctes pour 6 vues (déclarations / décisions / moteur) ;
track-record affiche « 1026 verdicts · 0 résolu · sous le minimum de 5 par
verdict », servi par la route, plus jamais « Lecture… ».

Ces bancs mesurent des PROPRIÉTÉS (exhaustivité de la table, pouvoir de
discrimination entre vues, position d'appel dans `boot`) et non des libellés :
reformuler un texte doit rester possible ; réunifier les six vues sous une
seule population, non. Nés ROUGES.
"""
from __future__ import annotations

import re

from vertex.ui.pages import performance_page as pp


def _barre(view: str) -> str:
    """La barre de contexte RÉELLEMENT servie pour cette sous-vue."""
    html = pp.render(view=view)
    m = re.search(r'<div class="vx2-contextbar".*?</div>\s*(?=<)', html, re.S)
    assert m, f'aucune barre de contexte servie pour la vue {view!r}'
    #  On borne au bloc complet : la regex ci-dessus s'arrête au premier
    #  fermant ; on reprend depuis l'ancre jusqu'au marqueur de fin de barre.
    debut = html.index('<div class="vx2-contextbar"')
    fin = html.index('vx2-tabs', debut) if 'vx2-tabs' in html[debut:] else len(html)
    return html[debut:fin]


def test_chaque_sous_vue_declare_sa_population():
    """Exhaustivité : aucune vue servie ne peut rester sans population déclarée.

    Ajouter un onglet à `_VIEWS` sans dire ce qu'il mesure ferait retomber la
    page dans le défaut mesuré (un en-tête qui parle d'une autre population que
    le contenu affiché)."""
    vues = set(dict(pp._VIEWS))
    assert set(pp._POPULATION_DE_VUE) == vues, (
        'toute sous-vue servie doit déclarer la population qu\'elle mesure ; '
        f'manquantes : {vues - set(pp._POPULATION_DE_VUE)} · '
        f'en trop : {set(pp._POPULATION_DE_VUE) - vues}')
    for vue, cle in pp._POPULATION_DE_VUE.items():
        assert cle in pp._CONTEXTES, f'{vue} pointe une population inconnue : {cle}'


def test_l_en_tete_discrimine_les_populations():
    """AVANT : 1 barre distincte pour 6 vues. La barre ne discriminait rien.

    On mesure le POUVOIR DE DISCRIMINATION, pas les mots : il doit exister
    autant de barres distinctes que de populations réellement servies."""
    barres = {vue: _barre(vue) for vue, _ in pp._VIEWS}
    distinctes = set(barres.values())
    attendues = len({pp._POPULATION_DE_VUE[v] for v, _ in pp._VIEWS})
    assert len(distinctes) == attendues, (
        f'{len(distinctes)} barre(s) distincte(s) pour {len(barres)} vues, '
        f'{attendues} population(s) attendue(s) — une barre unique annonce '
        'la même population sur des vues qui ne mesurent pas la même chose')
    assert barres['track-record'] != barres['overview'], (
        'les verdicts moteur et les trades déclarés ne peuvent pas partager '
        'le même en-tête : la page interdit de mélanger ces deux populations')


def test_la_vue_des_signaux_ne_nie_pas_le_moteur_qui_la_sert():
    """`track-record` est servie par `/api/track-record`. Elle annonçait
    « Arithmétique sur vos déclarations — aucun moteur ».

    La phrase interdite est LUE dans `_CONTEXTES` au lieu d'être recopiée ici :
    reformuler le texte des déclarations garde le banc valide."""
    barre = _barre('track-record')
    calcul_declare = pp._CONTEXTES['reels']['calcul']
    assert calcul_declare not in barre, (
        'la vue servie par un moteur affichait le libellé de calcul réservé '
        f'aux déclarations : {calcul_declare!r}')
    assert '/api/track-record' in barre, (
        'une valeur critique porte sa source : la vue doit nommer la route '
        'qui la sert')


def test_l_echantillon_est_rempli_sur_toutes_les_vues():
    """AVANT : `echantillon()` n'était appelée que dans les branches
    `overview` et `real` de `boot()`. Les quatre autres vues gardaient la
    pastille « Lecture… » servie par le module — pour toujours.

    On mesure la POSITION D'APPEL : `echantillon()` doit être invoquée dans
    `boot()` AVANT le premier aiguillage `if(VIEW`, donc sans condition de vue.
    Un appel replacé dans une branche fait retomber le défaut."""
    js = pp._JS
    debut = js.index('function boot(){')
    #  corps de boot() par comptage d'accolades — pas de découpe au jugé
    i, profondeur = js.index('{', debut), 0
    for fin in range(i, len(js)):
        if js[fin] == '{':
            profondeur += 1
        elif js[fin] == '}':
            profondeur -= 1
            if profondeur == 0:
                break
    corps = js[i:fin]
    assert 'echantillon()' in corps, 'boot() ne remplit plus la pastille'
    premier_aiguillage = corps.index('if(VIEW')
    assert corps.index('echantillon()') < premier_aiguillage, (
        'echantillon() est appelée dans une branche de vue : les vues qui ne '
        'passent pas par cette branche garderont « Lecture… » indéfiniment')


def test_les_verdicts_moteur_recoivent_leur_echantillon_servi():
    """`track-record` ne compte pas des clôtures : son échantillon appartient
    au moteur. Il doit être posé depuis la réponse de la route — succès ET
    panne —, jamais deviné par la page."""
    js = pp._JS
    debut = js.index('async function loadTrack()')
    fin = js.index('function loadReal()', debut)
    corps = js[debut:fin]
    assert corps.count('marquerEchantillon(') >= 2, (
        'loadTrack doit renseigner l\'échantillon dans le cas servi ET dans '
        'le cas injoignable — sinon la pastille reste sur « Lecture… » quand '
        'la route tombe')
    assert 'tr.entries' in corps and 'tr.resolved' in corps, (
        'le décompte doit venir des champs servis, pas d\'une estimation')


# ──────────────────────────────────────────────────────────────────────────
#  CONTRÔLE ADVERSE du 06/09/2026 — le correctif ci-dessus avait rendu
#  `track-record` honnête et laissé la MÊME faute sur `overview`, la vue
#  d'entrée de la page.
#
#  MESURE AVANT (Chromium sur 5003, journal réseau de
#  `/performance?view=overview`) : la vue appelle `/api/journal/postmortem`,
#  `/api/skyler/calibration` et `/api/skyler/memory` — soit trois moteurs —
#  pendant que sa barre affiche « CALCUL Arithmétique sur vos déclarations —
#  aucun moteur », chaîne strictement identique à celle de `real`, qui
#  n'appelle aucune route. Mesuré côté source : 4 routes `/api/` atteignables
#  depuis la branche `overview` de `boot()`, 0 depuis `real`.
#  APRÈS : `overview` déclare la population `mixte` et nomme les trois moteurs.
# ──────────────────────────────────────────────────────────────────────────

_MOTS_JS = {'if', 'for', 'while', 'switch', 'catch', 'function', 'return',
            'typeof', 'await', 'Number', 'String', 'Boolean', 'Math', 'Object'}


def _corps_accolades(js: str, depuis: int) -> str:
    """Bloc `{…}` complet à partir de `depuis`, par comptage d'accolades."""
    i, prof = js.index('{', depuis), 0
    for fin in range(i, len(js)):
        if js[fin] == '{':
            prof += 1
        elif js[fin] == '}':
            prof -= 1
            if prof == 0:
                return js[i:fin + 1]
    raise AssertionError('bloc non refermé')


def _corps_fonction(js: str, nom: str) -> str | None:
    m = re.search(r'(?:async\s+)?function\s+' + re.escape(nom) + r'\s*\(', js)
    return _corps_accolades(js, m.start()) if m else None


def _routes(js: str, bloc: str, vus: set | None = None, prof: int = 0) -> set:
    """Routes `/api/…` atteignables depuis `bloc`, en suivant les appels."""
    vus = set() if vus is None else vus
    trouvees = set(re.findall(r"['\"](/api/[\w/\-]+)", bloc))
    if prof > 3:
        return trouvees
    for nom in set(re.findall(r'\b([a-zA-Z_]\w*)\s*\(', bloc)):
        if nom in vus or nom in _MOTS_JS:
            continue
        vus.add(nom)
        corps = _corps_fonction(js, nom)
        if corps:
            trouvees |= _routes(js, corps, vus, prof + 1)
    return trouvees


def _routes_par_vue() -> dict:
    js = pp._JS
    boot = _corps_accolades(js, js.index('function boot(){'))
    commun = boot[:boot.index('if(VIEW')]
    par_vue = {}
    for m in re.finditer(r"VIEW===\'([\w-]+)\'\)\{", boot):
        branche = _corps_accolades(boot, m.end() - 1)
        par_vue[m.group(1)] = _routes(js, branche + commun)
    return par_vue


def test_une_vue_qui_interroge_un_moteur_ne_declare_pas_le_contraire():
    """Le libellé « Calcul » d'une vue qui appelle une route de moteur ne peut
    pas être celui d'une vue qui n'en appelle aucune.

    On ne fige aucune phrase : on mesure les routes réellement atteignables
    depuis chaque branche de `boot()`, puis on exige que les deux familles
    portent des libellés DIFFÉRENTS. Reformuler reste libre ; réunifier les
    deux, non."""
    par_vue = _routes_par_vue()
    vues = [v for v, _ in pp._VIEWS]
    avec = {v for v in vues if par_vue.get(v)}
    sans = {v for v in vues if not par_vue.get(v)}
    assert avec and sans, (
        'mesure impossible : il faut au moins une vue qui appelle un moteur et '
        f'une qui n\'en appelle aucun — mesuré {par_vue}')

    def calcul(vue):
        return pp._CONTEXTES[pp._POPULATION_DE_VUE[vue]]['calcul']

    for v1 in sorted(avec):
        for v2 in sorted(sans):
            assert calcul(v1) != calcul(v2), (
                f'{v1} atteint {sorted(par_vue[v1])} et {v2} aucune route, '
                'mais les deux annoncent le même calcul : la vue servie par '
                'des moteurs prétend n\'en utiliser aucun')
