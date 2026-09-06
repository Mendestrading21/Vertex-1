"""LOT H — SYSTÈME ET VERTEX IA : CE QUE LES DEUX PAGES DISAIENT DE FAUX.

Trois défauts, tous MESURÉS au navigateur sur l'instance de mesure (copie QA,
`NO_IBKR=1`, `DEMO=0`, sans code) le 6 septembre 2026, service worker
neutralisé — sans quoi le relevé porte sur une coque mise en cache et non sur
ce que le serveur sert aujourd'hui.

## 1. La bande de confiance annonçait quatre tuiles et n'en dimensionnait aucune

`.vx-kpi-strip` est une grille de DOUZE colonnes ; ses tuiles doivent porter
une classe de portée. Celles que `_kp()` produit n'en portaient aucune : une
colonne sur douze chacune.

    largeur   tuile   descendants en débordement horizontal
    1920 px    68 px   11
    1600 px    52 px   14
    1440 px    44 px   16
    1280 px    37 px   16
    1024 px   143 px    0     <- le défaut ne se voyait qu'au grand écran

« 8/8 », « opérationnels », « aucun ordre » sortaient de leur boîte : les
quatre indicateurs de confiance de la page de vérité étaient illisibles sur
toute la plage bureau. Après : 136 à 227 px, **zéro débordement** aux seize
largeurs relevées, et le repli mobile à deux tuiles par rangée est intact.

## 2. Six sous-vues de Vertex IA sur huit annonçaient une lecture qui n'arrivait jamais

La barre de contexte déclare « Fraîcheur » et part sur `Lecture…`.
`peindreFraicheurIA` n'était appelée que par `initBrief` et `initDecisions` :

    Assistant Comité Recherche Mémoire Doctrine Impacts  ->  « Lecture… », figé
    Brief                                                ->  « Horodatage illisible »
    Décisions                                            ->  puce réelle

Même défaut, même remède que `peindreSante()` sur la page Système — « déclarée
et remplie par personne ». Il est pire ici : le badge qui ment porte le mot
« fraîcheur ». Après : les huit vues disent quelque chose de vérifiable, et
celles dont le paquet n'a aucune date le DISENT avec la raison
(`/api/validator` rend ses métriques sans date de calcul,
`/api/strategy/profile` une constitution versionnée et non datée).

## 3. Un `/healthz` muet était déclaré sain

La carte « Stockage & santé » testait :

    hz.ok!==false && (hz.status==='ok' || hz.ok===true || hz.status===undefined)

Le dernier terme déclare SAIN un corps qui ne dit rien de sa santé. Mesuré,
`/healthz` intercepté :

    corps servi              badge     ligne « Santé serveur »
    {}                       sain      OK          <- faux
    {"build":"X"}            sain      OK          <- faux
    {"status":"degraded"}    dégradé   dégradé     <- juste
    {"ok":false}             dégradé   dégradé     <- juste

Le défaut n'était pas la panne : c'était le silence, compté du côté
rassurant, sur l'écran même où l'on vient vérifier que le reste ne ment pas.

## 3 bis. Les deux bords du même partage (contrôle adverse)

Le premier partage corrigeait le silence rassurant mais gardait deux façons de
dire faux, mesurées après coup :

    corps servi     rendu
    {"status":""}   « dégradé — code serveur :  »   <- verdict, pièce vide
    {"ok":0}        « ne porte ni status ni ok »    <- il porte `ok`

Une chaîne vide n'affirme rien : la ranger du côté défavorable est l'erreur
symétrique de celle du défaut 3. Et l'explication du silence ne peut pas nier
une clé reçue. Après : les deux rejoignent « état non rapporté », et la carte
montre ce que le corps portait (`status=""`, `ok=0`).

## Ce que ces bancs mesurent — et ce qu'ils ne figent pas

Aucune assertion ne gèle un libellé. Le banc 1 compare `scrollWidth` à
`clientWidth` : c'est le débordement lui-même, pas une largeur convenue. Le
banc 2 relit le texte que le SERVEUR pose dans le badge et vérifie qu'il n'y
est plus après chargement : le jour où « Lecture… » devient autre chose, la
mesure suit. Le banc 3 compare deux rendus entre eux — un serveur qui se tait
ne doit pas être indiscernable d'un serveur qui se déclare sain.

## Ce qu'ils NE gardent PAS

Sans Chromium ou sans instance de mesure, ils s'abstiennent. Les trois
corrections vivent dans du JavaScript de page : les éprouver hors navigateur
demanderait un moteur JS que le dépôt n'a pas. Une abstention est dite, jamais
comptée comme un succès.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

import pytest

_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SONDE = os.path.join(_RACINE, 'tests', 'aides', 'sonde_h_systeme_intelligence.py')

#: L'instance de MESURE. 5002 est l'instance réelle, branchée sur le courtier :
#: une sonde n'a rien à y faire, et le défaut ne l'y envoie jamais.
BASE = os.environ.get('VERTEX_MESURE_BASE', 'http://127.0.0.1:5003')

#: Les huit sous-vues de Vertex IA (l'ordre canonique de `intelligence_page`).
VUES_IA = ('analyst', 'brief', 'committee', 'decisions',
           'research', 'memory', 'strategy', 'impacts')


def _navigateur_dispo() -> bool:
    from tools.mesures.mesurer_qa_espaces import navigateur_pret
    return navigateur_pret()


def _serveur_ouvert() -> bool:
    """Une instance qui RÉPOND et qui sert une page OUVERTE.

    Une instance derrière un code servirait son écran de connexion à la
    sonde : ce serait mesurer la mauvaise page en silence. On exige la page
    Système elle-même, avec son attribut d'espace et sans champ de code.
    """
    try:
        with urllib.request.urlopen(BASE + '/system?view=connections', timeout=5) as r:
            corps = r.read().decode('utf-8', 'replace')
            return (r.status == 200 and 'data-space="system"' in corps
                    and 'name="code"' not in corps
                    and 'type="password"' not in corps)
    except Exception:  # noqa: BLE001
        return False


#: Ce que les corrections posent dans le JS SERVI. L'instance de mesure sert une
#: COPIE du dépôt, figée à son démarrage : tant qu'elle n'est pas relancée, elle
#: sert le code d'AVANT, et un relevé pris là-dessus est faux sans le dire.
#: C'est arrivé pendant l'écriture de ce lot (deux relevés sur un serveur
#: résiduel) et de son contrôle (un port occupé par une autre instance, qui a
#: rendu des marqueurs d'une tout autre version). On refuse de mesurer plutôt
#: que de mesurer la mauvaise page.
_MARQUEURS = (
    ('/system?view=connections', 'vx-sys-kpis-css'),
    ('/system?view=connections', 'aucun verdict lisible'),
    ('/intelligence?view=memory', 'fraicheurIAAbsente'),
)

_SOURCES = ('vertex/ui/pages/system_page.py', 'vertex/ui/pages/system_page.py',
            'vertex/ui/pages/intelligence_page.py')


def _version_servie_manquante() -> list:
    """Les marqueurs absents de ce que l'instance SERT.

    Chaque marqueur est d'abord cherché dans le code LOCAL : s'il n'y est plus
    (un lot l'a renommé), le témoin ne vaut rien et on le dit ici plutôt que de
    laisser le banc conclure « instance périmée » à tort.
    """
    manquants = []
    for (chemin, jeton), source in zip(_MARQUEURS, _SOURCES):
        with open(os.path.join(_RACINE, source), encoding='utf-8') as f:
            if jeton not in f.read():
                manquants.append('%s : le témoin « %s » n’existe plus dans %s '
                                 '— le mettre à jour' % (chemin, jeton, source))
                continue
        try:
            with urllib.request.urlopen(BASE + chemin, timeout=10) as r:
                if jeton not in r.read().decode('utf-8', 'replace'):
                    manquants.append('%s ne contient pas « %s »' % (chemin, jeton))
        except Exception as e:  # noqa: BLE001
            manquants.append('%s injoignable (%s)' % (chemin, e))
    return manquants


@pytest.fixture(scope='module')
def releve() -> dict:
    if not _navigateur_dispo():
        pytest.skip('Chromium absent — la mesure porterait sur rien')
    if not _serveur_ouvert():
        pytest.skip('aucune instance de mesure ouverte sur %s '
                    '(VERTEX_MESURE_BASE) — rien à mesurer' % BASE)
    perimes = _version_servie_manquante()
    if perimes:
        pytest.skip(
            'l’instance de mesure %s sert une version ANTÉRIEURE des pages '
            '(%s) : la relancer sur l’arbre courant avant de mesurer — un '
            'relevé pris ici porterait sur le code d’hier'
            % (BASE, ' ; '.join(perimes)))
    r = subprocess.run([sys.executable, _SONDE], capture_output=True,
                       text=True, encoding='utf-8', timeout=900)
    assert r.returncode == 0, 'la sonde a échoué :\n%s' % (r.stderr or '')[-1200:]
    lignes = [l for l in r.stdout.splitlines() if l.strip().startswith('{')]
    assert lignes, 'la sonde n’a rien rendu :\n%s' % r.stdout[-600:]
    return json.loads(lignes[-1])


# ── 1. La bande de confiance ────────────────────────────────────────────────

def test_la_bande_de_confiance_ne_deborde_a_aucune_largeur(releve):
    """DÉFAUT 1. 14 débordements à 1600 px, 16 à 1440, 0 après.

    On ne fixe pas une largeur minimale convenue : on mesure le débordement
    lui-même (`scrollWidth > clientWidth`). Un chiffre tronqué est un chiffre
    faux, et c'est la seule chose que la tuile a à dire.
    """
    for largeur, m in sorted(releve['bande'].items(), key=lambda kv: int(kv[0])):
        assert m, 'la bande #vx-sys-kpis est absente à %s px' % largeur
        assert not m['debordements'], (
            'à %s px, %d élément(s) de la bande de confiance débordent '
            'horizontalement — les indicateurs sont tronqués : %s'
            % (largeur, len(m['debordements']), m['debordements'][:4]))


def test_les_quatre_tuiles_de_confiance_tiennent_la_meme_grandeur(releve):
    """La bande annonce `data-max-kpis="4"` : quatre tuiles, jamais une seule
    écrasée à côté de trois autres. Mesure de forme, pas de largeur imposée.
    """
    for largeur, m in releve['bande'].items():
        assert len(m['tuiles']) == 4, (
            'à %s px la bande porte %d tuiles au lieu des 4 annoncées'
            % (largeur, len(m['tuiles'])))
        assert max(m['tuiles']) - min(m['tuiles']) <= 2, (
            'à %s px les quatre tuiles n’ont pas la même grandeur : %s'
            % (largeur, m['tuiles']))


def test_la_page_systeme_ne_defile_pas_horizontalement(releve):
    """Aux trois largeurs de la doctrine, plus 1440."""
    for largeur, m in releve['bande'].items():
        assert not m['page_deborde'], (
            'la page Système défile horizontalement à %s px' % largeur)


# ── 2. La fraîcheur de Vertex IA ────────────────────────────────────────────

def test_aucune_vue_ne_reste_sur_le_badge_pose_par_le_serveur(releve):
    """DÉFAUT 2. Six vues sur huit affichaient encore, deux secondes et demie
    après le chargement, EXACTEMENT le texte que le serveur avait posé dans le
    badge — donc personne ne l'avait peint.

    Le témoin est relu sur la page servie, jamais figé ici : si le libellé de
    départ change, la comparaison reste juste.
    """
    figees = []
    for vue in VUES_IA:
        pose = releve['temoin_fraicheur_servi'].get(vue)
        rendu = releve['fraicheur'].get(vue)
        assert rendu, 'la vue %s n’a aucun badge de fraîcheur' % vue
        if pose and rendu == pose:
            figees.append(vue)
    assert not figees, (
        '%d sous-vue(s) de Vertex IA affichent encore le badge de départ '
        '« %s » : la fraîcheur y est annoncée et jamais peinte — %s'
        % (len(figees), releve['temoin_fraicheur_servi'].get(figees[0]),
           ', '.join(figees)))


def test_chaque_vue_de_vertex_ia_dit_quelque_chose_de_sa_fraicheur(releve):
    """Une vue muette vaut la vue figée : le badge doit porter un texte."""
    for vue in VUES_IA:
        rendu = (releve['fraicheur'].get(vue) or '').strip()
        assert rendu, 'la vue %s laisse son badge de fraîcheur vide' % vue


# ── 3. Le silence de /healthz ───────────────────────────────────────────────

def test_un_healthz_muet_n_est_pas_rendu_comme_un_healthz_sain(releve):
    """DÉFAUT 3. `{}` et `{"status":"ok"}` produisaient le MÊME écran.

    On ne compare pas à un libellé attendu : on compare les deux rendus entre
    eux. Tant qu'ils sont identiques, l'absence de verdict se lit comme un
    verdict favorable — quel que soit le mot choisi pour le dire.
    """
    sain = releve['stockage']['affirme_sain']
    for muet in ('muet_vide', 'muet_sans_verdict'):
        m = releve['stockage'][muet]
        assert m['badge'] != sain['badge'], (
            'un /healthz qui ne dit rien (%s) rend le même badge « %s » qu’un '
            'serveur qui se déclare sain : le silence est compté comme un '
            'verdict favorable' % (muet, sain['badge']))
        assert m['corps'] != sain['corps'], (
            'un /healthz qui ne dit rien (%s) rend la même carte qu’un serveur '
            'sain' % muet)


def test_un_status_vide_n_est_pas_une_declaration_de_panne(releve):
    """CONTRÔLE ADVERSE. L'erreur SYMÉTRIQUE de celle du défaut 3.

    Le premier partage rendait `{"status":""}` comme `dégradé — code serveur :`
    (mesuré au navigateur le 6 sept. 2026), c'est-à-dire un verdict de panne
    suivi d'une pièce vide. Une chaîne vide n'affirme pas plus qu'un corps
    absent : compter le silence du côté défavorable est la même faute que le
    compter du côté rassurant, et l'écran montrait une accusation sans preuve.

    On ne fige aucun libellé : on exige que `{"status":""}` se range avec les
    corps muets, et pas avec ceux qui déclarent une panne.
    """
    s = releve['stockage']
    assert s['status_vide']['badge'] == s['muet_vide']['badge'], (
        'un `status` vide rend « %s » là où un corps muet rend « %s » : une '
        'chaîne vide est traitée comme une affirmation'
        % (s['status_vide']['badge'], s['muet_vide']['badge']))
    assert s['status_vide']['badge'] != s['affirme_degrade']['badge'], (
        'un `status` vide est rendu comme une panne déclarée (« %s ») alors '
        'que le serveur n’a rien affirmé' % s['status_vide']['badge'])


def test_l_explication_du_silence_ne_nie_pas_une_cle_presente(releve):
    """CONTRÔLE ADVERSE. La carte affirmait une absence qui était fausse.

    Pour `{"ok":0}` — une clé de verdict PRÉSENTE, mais dont la valeur n'est ni
    vraie ni fausse — la carte servait mot pour mot l'explication du corps
    réellement muet : « son corps ne porte ni status ni ok ». Mesuré : les deux
    rendus étaient identiques. Sur la page où l'on vient vérifier que le reste
    ne ment pas, l'explication du silence mentait sur ce qu'elle avait reçu.

    Comparaison entre rendus, pas à un libellé : un corps qui porte une clé et
    un corps qui n'en porte aucune ne peuvent pas s'expliquer de la même façon.
    """
    s = releve['stockage']
    assert s['ok_non_booleen']['badge'] == s['muet_vide']['badge'], (
        'préalable : `{"ok":0}` doit rester un état non rapporté, or son badge '
        'est « %s » contre « %s »'
        % (s['ok_non_booleen']['badge'], s['muet_vide']['badge']))
    assert s['ok_non_booleen']['corps'] != s['muet_vide']['corps'], (
        'un corps qui porte `ok` reçoit la MÊME explication qu’un corps qui ne '
        'porte ni `status` ni `ok` : la carte nie une clé qu’elle a reçue')


def test_un_healthz_qui_se_declare_en_panne_reste_distingue_des_deux(releve):
    """Trois états DISTINCTS : affirmé sain, affirmé dégradé, non rapporté.
    Les replier à deux perdrait justement ce que la correction sépare.
    """
    badges = {k: releve['stockage'][k]['badge'] for k in releve['stockage']}
    assert badges['affirme_degrade'] == badges['affirme_ko'], (
        'deux façons de déclarer la panne rendent deux badges différents : %s'
        % badges)
    trois = {badges['affirme_sain'], badges['affirme_degrade'],
             badges['muet_vide']}
    assert len(trois) == 3, (
        'sain, dégradé et non rapporté ne font plus trois états distincts : %s'
        % badges)


# ── 4. Aucune des deux pages ne casse la console ────────────────────────────

def test_les_deux_pages_se_chargent_sans_erreur_de_console(releve):
    fautives = {k: v for k, v in releve['console'].items() if v}
    assert not fautives, 'erreurs JavaScript au chargement : %s' % fautives
