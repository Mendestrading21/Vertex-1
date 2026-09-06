"""Vertex Test 1.0 · #781 — LA COUCHE VISUELLE SERVIE, ET LE FIL D'ARIANE ILLISIBLE.

Ce fichier garde `tools/mesures/mesurer_couche_visuelle.py` et les deux
corrections qu'il a trouvées. Il est écrit sous une contrainte apprise trois
fois dans cette série : **un instrument qui impose son propre barème accuse le
produit d'une décision que le produit a prise exprès.**

## Ce que la mesure a établi

```text
17 feuilles CSS · 152 Ko · TOUTES servies sur les 8 espaces
1 022 règles chargées, dont 476 jamais appariées au chargement (candidates)
prefers-reduced-motion: reduce  ->  0 animation, 0 transition > 150 ms
```

La prémisse de `#781` — « le dépôt empile plusieurs directions visuelles » — est
**vraie en volume et fausse en divergence** : les huit espaces reçoivent
exactement la même pile. Il n'y a pas de thème parallèle par page ; il y a une
seule couche, épaisse. La distinction change le travail : converger, pas
départager.

## Les deux défauts du fil d'Ariane

Le fil est le **seul repère de lieu persistant en mobile** — la sidebar y est
hors-écran.

1. **Hauteur.** Son segment d'espace est un lien, et il mesurait 19,5 px sur les
   huit espaces : la seule cible tactile du produit sous le plancher de 32 px.
2. **Largeur.** Le fil recevait **84 px pour 122-185 px** de contenu sur sept
   espaces sur huit — tous les segments tronqués, séparateur compris, réduit à
   2 px.

Le second ne se répare pas en élargissant la cible : le lien est étroit **parce
que** son conteneur l'est. Élargir la cible aurait soigné le thermomètre.

## Pourquoi masquer le nom d'espace, et pas le sous-libellé

Mesuré sur les huit : le `h1` de la page répète le nom d'espace **à
l'identique** (« Marchés » / « Marchés »). Le sous-libellé (« Vue d'ensemble »,
« Discipline », « Connexions ») n'apparaît **nulle part ailleurs**. Masquer le
nom ne perd rien ; masquer le sous-libellé aurait supprimé la seule information
que le fil porte en propre — c'est le choix que j'allais faire avant de mesurer
les `h1`.

## Le piège que `:not(:last-child)` évite

Sur `/analysis` le fil n'a **qu'un seul segment** (pas de sous-libellé). Masquer
le nom d'espace sans condition y laisserait un topbar sans aucun repère de lieu
— une correction qui casse la page qu'elle prétend servir.
"""
import pathlib
import re
import sys
import urllib.request

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures import mesurer_couche_visuelle as _mes  # noqa: E402
from tools.mesures.mesurer_qa_espaces import _chromium  # noqa: E402

_RESPONSIVE = RACINE / 'vertex' / 'static' / 'vertex' / 'css' / 'responsive.css'

#: RÉSIDU ASSUMÉ, gelé à la mesure — aujourd'hui VIDE.
#:
#: Il recensait deux sous-libellés qui dépassaient les 84 px du fil :
#:
#:     briefing  « Résumé du jour »   96 px pour 84
#:     markets   « Vue d'ensemble »   98 px pour 84
#:
#: Ni l'un ni l'autre n'est le sous-libellé de ces espaces : ils sont devenus
#: « Marchés US » (72 px) et « Synthèse » (55 px) au lot 28. Le résidu a donc
#: disparu par le RACCOURCISSEMENT DES LIBELLÉS, et non par l'arbitrage qu'il
#: décrivait — `.vx-topbar-search input{min-height:40px}` (lot 289) est
#: intact, le champ de recherche n'a pas été rogné. Mesuré au navigateur :
#: douze espaces, zéro troncature, le plus long à 72 px pour 84.
#:
#: Un recensement vide serait indiscernable d'une sonde devenue aveugle. C'est
#: pourquoi `mesurer_couche_visuelle._temoins` présente désormais à `SONDE_FIL`
#: un fil fabriqué portant un segment qui tronque et un qui tient : le vide
#: ci-dessous ne vaut que tant que ces deux témoins tiennent.
FILS_ENCORE_TRONQUES: set[str] = set()


def _navigateur_dispo():
    #  Lancement reel : voir mesurer_qa_espaces.navigateur_pret().
    from tools.mesures.mesurer_qa_espaces import navigateur_pret
    return navigateur_pret()


def _serveur_repond():
    try:
        with urllib.request.urlopen(_mes.BASE_DEFAUT + '/healthz', timeout=3) as r:
            if r.status != 200:
                return False
        #  Une instance derrière un code d'accès (VERTEX_CODE) servirait sa page
        #  de connexion à la mesure : ce serait mesurer la mauvaise page en
        #  silence (mesuré le 2026-09-06 : deux gardiens ont « mesuré » l'écran
        #  de connexion de l'instance de travail). On exige une PAGE ouverte :
        #  l'espace Marchés servi avec son attribut `data-space`, sans champ
        #  de code. `VERTEX_MESURE_BASE` désigne l'instance QA (sans code).
        with urllib.request.urlopen(_mes.BASE_DEFAUT + '/markets', timeout=5) as r:
            corps = r.read().decode('utf-8', 'replace')
        return (r.status == 200 and 'data-space="markets"' in corps
                and 'name="code"' not in corps and 'type="password"' not in corps)
    except Exception:  # noqa: BLE001
        return False


def _regle(selecteur):
    src = _RESPONSIVE.read_text(encoding='utf-8')
    m = re.search(re.escape(selecteur) + r'\s*\{([^}]*)\}', src)
    return m.group(1) if m else None


#  --------------------------------------------- les corrections, sur la source
#  Ni navigateur ni serveur : elles sont gardées partout, toujours.

def test_le_lien_du_fil_d_ariane_est_une_cible_tactile_atteignable():
    """CORRECTION 1. 19,5 px sur les huit espaces, sous le plancher de 32."""
    r = _regle('.vx-breadcrumb a')
    assert r is not None, ('la regle de hauteur du fil d\'Ariane a disparu : '
                           'le segment d\'espace retombe a 19,5 px')
    assert 'padding-block' in r, r


def test_la_correction_de_hauteur_n_emploie_PAS_display_flex():
    """CONTRE-EXEMPLE. `min-height` + `display:flex` est le réflexe, et il
    casserait l'ellipse du lot 222 — `text-overflow` ne s'applique pas au
    contenu d'un conteneur flex, et un fil long repasserait sous les boutons du
    topbar. Le padding agrandit la boîte d'un élément déjà blocifié par le flex
    parent, sans toucher au rendu du texte."""
    r = _regle('.vx-breadcrumb a')
    assert r is not None
    assert 'display:flex' not in r.replace(' ', ''), (
        'le fil passe en `display:flex` : l\'ellipse du lot 222 ne s\'applique '
        'plus et un libelle long repassera sous les boutons')
    src = _RESPONSIVE.read_text(encoding='utf-8').replace(' ', '')
    assert 'text-overflow:ellipsis' in src, 'l\'ellipse du lot 222 a disparu'


def test_le_nom_d_espace_est_masque_SEULEMENT_s_il_n_est_pas_seul():
    """CORRECTION 2, et le piège qu'elle évite.

    Sur `/analysis` le fil n'a qu'un segment. Sans `:not(:last-child)`, le
    topbar y perdrait tout repère de lieu — une correction qui casse la page
    qu'elle prétend servir."""
    src = _RESPONSIVE.read_text(encoding='utf-8').replace('\n', ' ')
    m = re.search(r'\.vx-breadcrumb \.vx-crumb-space([^{]*)\{([^}]*)\}', src)
    assert m, ('la regle qui masque le nom d\'espace en mobile a disparu : le '
               'fil redevient illisible (84 px pour 122-185 px de contenu)')
    assert ':not(:last-child)' in m.group(0), (
        'le nom d\'espace est masque SANS CONDITION : sur /analysis, seul '
        'segment du fil, le topbar n\'a plus aucun repere de lieu')
    assert 'display:none' in m.group(2).replace(' ', '')


def test_le_separateur_orphelin_est_masque_avec_le_segment():
    """Même leçon qu'au lot 56 : masquer un segment sans son séparateur laisse
    un slash orphelin en tête de fil."""
    src = _RESPONSIVE.read_text(encoding='utf-8').replace('\n', ' ')
    assert re.search(r'\.vx-crumb-space:not\(:last-child\) \+ span', src), (
        'le separateur adjacent n\'est plus masque : le fil commencera par un '
        'slash orphelin')


#  ----------------------------------------------- les garde-fous d'instrument

def test_les_seuils_tactiles_sont_LUS_dans_le_produit_jamais_recopies():
    """LE TEST QUI COMPTE LE PLUS DE CE FICHIER.

    Un instrument qui recopie un barème diverge du produit au premier
    ajustement, puis l'accuse. Mesurer contre le seul seuil de 40 px rendait
    113 « défauts » dont la quasi-totalité étaient la règle secondaire du
    lot 612."""
    s = _mes.seuils_tactiles()
    assert s['primaire'] == 40 and s['secondaire'] == 32, (
        'les seuils du produit ont change (%s) — la mesure suit, mais le lot '
        '612 demande une re-mesure documentee' % s)
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    assert 'responsive.css' in src and 're.search' in src, (
        'les seuils ne sont plus lus dans le CSS servi')


def test_l_instrument_separe_la_hauteur_de_la_largeur():
    """Elles ne se réparent pas pareil : la hauteur ne dépend que du CSS, la
    largeur dépend du texte ET de la place laissée. Les confondre fait
    « corriger » un symptôme."""
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    assert 'trop_bas' in src and 'trop_etroits' in src, (
        'l\'instrument confond de nouveau hauteur et largeur')


def test_l_instrument_ignore_les_elements_GARES_hors_du_cadre():
    """Le lien d'évitement clavier vit à `translateY(-160%)` jusqu'au focus :
    ce n'est pas une cible tactile. Même erreur que compter un drawer fermé
    comme un débordement — déjà commise une fois dans cette série."""
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    sonde = src.split('SONDE_TACTILE = r"""')[1].split('"""')[0]
    assert 'window.innerHeight' in sonde and 'r.bottom <= 0' in sonde, (
        'la sonde ne verifie plus que l\'element est DANS le cadre : le lien '
        'd\'evitement clavier sera signale sur les 8 espaces')


def test_l_outil_ne_supprime_rien():
    """476 règles jamais appariées est une liste de CANDIDATES. La preuve de
    non-usage demande davantage, et la suppression demande un humain."""
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    for verbe in ('os.remove', 'unlink', 'shutil.rm', 'write_text', 'os.rmdir'):
        assert verbe not in src, (
            'l\'instrument sait desormais ecrire ou supprimer (« %s ») : la '
            'preuve et l\'acte doivent rester separes' % verbe)


@pytest.mark.skipif(not _navigateur_dispo(),
                    reason='playwright/chromium absent de cet environnement')
def test_les_temoins_de_l_instrument_mordent():
    """Positifs et négatifs. Le plus instructif est le négatif « garé » : sans
    lui, l'instrument signale un élément que personne ne peut toucher."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=_chromium(), args=['--no-sandbox'])
        try:
            echecs = _mes._temoins(nav)
        finally:
            nav.close()
    assert echecs == [], '\n'.join(echecs)


#  ------------------------------------------------ la mesure sur le produit

@pytest.mark.skipif(not (_navigateur_dispo() and _serveur_repond()),
                    reason='navigateur ou serveur absent — la mesure porterait '
                           'sur rien')
def test_le_produit_a_390px_tient_ses_propres_regles():
    r = _mes.mesurer(largeur=390)
    assert r['echecs_temoins'] == [], '\n'.join(r['echecs_temoins'])
    assert r['tactile_trop_bas'] == 0, [
        (x['espace'], x['tactile']['trop_bas']) for x in r['releves']
        if x['tactile']['trop_bas']]
    assert r['mouvement_total'] == 0, [
        (x['espace'], x['mouvement_reduit']['uniques']) for x in r['releves']
        if x['mouvement_reduit']['uniques']]
    #  Recensement GELÉ du résidu assumé (voir FILS_ENCORE_TRONQUES).
    encore = set(r['fils_tronques']) - FILS_ENCORE_TRONQUES
    assert not encore, (
        'le fil d\'Ariane tronque sur des espaces NOUVEAUX : %s — c\'est le '
        'seul repere de lieu quand la sidebar est hors-ecran' % sorted(encore))
    disparus = FILS_ENCORE_TRONQUES - set(r['fils_tronques'])
    assert not disparus, (
        'ces espaces ne tronquent plus — les retirer du recensement : %s'
        % sorted(disparus))
    assert not r['feuilles_partielles'], (
        'une feuille n\'est plus servie partout — une couche visuelle diverge '
        'selon la page : %s' % r['feuilles_partielles'])
