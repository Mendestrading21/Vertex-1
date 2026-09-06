"""Vertex Test 1.0 · G4 — LES HUIT ESPACES : DESKTOP / MOBILE / CLAVIER / CONTRASTE.

Ce fichier garde `tools/mesures/mesurer_qa_espaces.py` et le défaut qu'il a
trouvé. Il est bâti sur une leçon coûteuse de cette série : **l'instrument a été
faux deux fois avant le produit**.

## Les deux erreurs de l'instrument, et pourquoi elles se ressemblent

1. **Débordement.** La première version comparait chaque élément à
   `window.innerWidth` : 136 « débordements » sur un produit qui n'en avait
   aucun. Les panneaux garés hors-écran par `transform: translateX(…)` — sidebar
   mobile, drawer fermé (`aria-hidden`, `inert`) — sont le bon motif, pas un
   défaut. Mesuré : `document.scrollWidth == clientWidth` partout.
2. **Contraste.** La deuxième version ne lisait que `backgroundColor`, nul sur un
   bouton peint par `linear-gradient`. Elle sautait le fond réellement peint,
   atterrissait sur la page sombre, et condamnait l'encre du bouton primaire —
   à ~7:1 sur son dégradé — à 1,04:1. 34 faux positifs.

Les deux fois, le détecteur **accusait à tort**, et les deux fois il aurait été
plus facile de « corriger » le produit. C'est pourquoi ce fichier tient autant
aux témoins **négatifs** qu'aux positifs.

## Le défaut RÉEL, celui qui restait dessous

Sur `/markets` à 390 px : `.vx-mk-idx-top` portait 198 px de contenu dans une
boîte de 143, sous le `overflow-x:hidden` de la carte. Rien dans cette rangée ne
pouvait céder — monogramme figé à 34 px, pastille en `white-space:nowrap`, nom
sans `min-width:0` — donc « milieu de plage » était **coupé sans points de
suspension ni barre de défilement**, sur Nasdaq et Dow. Une donnée présente,
rendue illisible en silence : la même famille que « masquer une donnée
manquante », vue de l'autre côté.

## Ce que la campagne de mutation a trouvé

Onze affaiblissements appliqués sur disque ; cinq passaient. Le plus instructif :
**« ne plus écouter `pageerror` »**. Les témoins avaient leur *propre* écouteur,
donc ils restaient verts pendant que le balayage devenait aveugle. Les témoins
passent désormais par `_sonder`, la fonction qu'emploie la mesure.

Deux autres méritent d'être notées, parce qu'elles disent quelque chose de
général : abaisser le seuil AA à 1,5:1 et retenir le *meilleur* stop d'un
dégradé passaient tous les deux — parce que mes témoins étaient **trop
mauvais**. `#888` sur `#777`, c'est 1,3:1 : ça survit à n'importe quel seuil
plus permissif. Un témoin doit vivre **au bord** du seuil qu'il défend, pas au
fond du gouffre. D'où `#636363` sur `#000`, soit exactement 3,50:1.
"""
import glob
import pathlib
import re
import sys
import urllib.request

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures import mesurer_qa_espaces as _mes  # noqa: E402

#  Lot 24 : neon-glass.css (jamais servie) est supprimée ; les règles
#  contractuelles gardées ici sont RAPATRIÉES dans la couche servie.
CSS = RACINE / 'vertex' / 'static' / 'vertex' / 'css' / 'vertex-2-0.css'


def _navigateur_dispo():
    #  Un LANCEMENT reel, pas la presence d'un fichier : un binaire present mais
    #  impossible a engendrer faisait planter la mesure au lieu de l'abstenir.
    return _mes.navigateur_pret()


def _serveur_repond():
    try:
        with urllib.request.urlopen(_mes.BASE_DEFAUT + '/healthz', timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


#  ---------------------------------------------- le défaut réel, sur la source
#  Ces trois tests ne demandent NI navigateur NI serveur : ils gardent la
#  correction elle-même, donc ils tournent partout, tout le temps.

def _regle(selecteur):
    src = CSS.read_text(encoding='utf-8')
    m = re.search(re.escape(selecteur) + r'\s*\{([^}]*)\}', src)
    return m.group(1) if m else None


def test_la_rangee_d_entete_des_cartes_d_indices_peut_passer_a_la_ligne():
    """LA CORRECTION. Sans `flex-wrap`, rien dans cette rangée ne peut céder et
    le `overflow-x:hidden` de la carte coupe le surplus **en silence**."""
    r = _regle('#vx-content[data-space="markets"] .vx-mk-idx-top')
    assert r is not None, 'la regle .vx-mk-idx-top a disparu'
    assert 'flex-wrap:wrap' in r.replace(' ', ''), (
        'la rangee d\'en-tete des cartes d\'indices ne peut plus passer a la '
        'ligne : a 390 px elle porte 198 px de contenu dans 143 px, et la '
        'carte COUPE le surplus sans points de suspension ni barre')


def test_le_nom_de_l_indice_tronque_en_l_avouant():
    """`min-width:0` lève le plancher implicite des éléments flex ; l'ellipse
    dit au lecteur qu'il manque du texte, au lieu de le couper sans le dire."""
    r = _regle('#vx-content[data-space="markets"] .vx-mk-idx-name')
    assert r is not None
    compact = r.replace(' ', '').replace('\n', '')
    assert 'min-width:0' in compact, (
        'sans `min-width:0`, un element flex ne descend pas sous la taille de '
        'son contenu : le nom ne peut pas retrecir et la rangee deborde')
    assert 'text-overflow:ellipsis' in compact, (
        'le nom est coupe sans rien dire — l\'ellipse est l\'aveu')


def test_la_pastille_reste_a_droite_quand_elle_passe_a_la_ligne():
    """Le `margin-left:auto` est ce qui fait tenir la mise en page une fois la
    rangée passée en `wrap` : sans lui, la pastille se colle au nom."""
    r = _regle('#vx-content[data-space="markets"] .vx-mk-idx-rel')
    assert r is not None
    assert 'margin-left:auto' in r.replace(' ', ''), (
        'la pastille de position relative n\'est plus poussee a droite')


#  ------------------------------------------------------------- les témoins
#  Ils ne demandent que le navigateur : c'est la garde de l'INSTRUMENT, et
#  c'est elle qui a le plus de valeur — un detecteur faux est pire qu'aucun.

@pytest.mark.skipif(not _navigateur_dispo(),
                    reason='playwright/chromium absent de cet environnement')
def test_les_onze_temoins_de_l_instrument_mordent():
    """LE TEST CENTRAL DU FICHIER.

    Onze témoins, positifs et négatifs, sur trois pages fabriquées — dont le
    dégradé EXACT du bouton primaire servi, qui est le cas ayant pris
    l'instrument en défaut. Ils passent par `_sonder`, la fonction qu'emploie
    le balayage : une copie locale des écouteurs les rendrait verts pendant que
    la mesure devient aveugle."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=_mes._chromium(),
                                args=['--no-sandbox'])
        try:
            echecs = _mes._temoins(nav)
        finally:
            nav.close()
    assert echecs == [], '\n'.join(echecs)


def test_le_temoin_de_contraste_vit_AU_BORD_du_seuil():
    """CONTRE-EXEMPLE MESURÉ, contre un réflexe très naturel.

    Un témoin de contraste « bien mauvais » (1,3:1) ne défend pas le seuil :
    abaisser 4,5 à 1,5 le laissait vert. Le témoin de bord (3,50:1) est le seul
    qui fasse échouer cette mutation."""
    assert _mes.GRIS_3_50 == '#636363', (
        'le gris de bord a change : recalculer son ratio sur #000 et verifier '
        'qu\'il reste entre 3,0 (seuil grand texte) et 4,5 (seuil normal), '
        'sinon il ne discrimine plus rien')
    assert 'au bord du seuil' in _mes.PAGE_TEMOIN_DEFAUTS
    assert 'grand texte' in _mes.PAGE_TEMOIN_PROPRE, (
        'le temoin NEGATIF du grand texte a disparu : plus rien n\'empeche '
        'd\'aligner le seuil du grand texte sur celui du texte courant')


def test_les_temoins_passent_par_la_fonction_de_mesure():
    """Le trou le plus grave qu'ait trouvé la mutation : des témoins qui
    éprouvent une COPIE du code mesuré ne prouvent rien sur le code mesuré."""
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    corps = src.split('def _temoins(')[1].split('\ndef ')[0]
    #  UNE page temoin = UN appel. Se contenter de « `_sonder` apparait quelque
    #  part » ne suffit pas : la mutation qui a survecu ne remplacait QUE le
    #  premier des trois appels, et les deux autres suffisaient a satisfaire un
    #  simple `in`. C'est le dernier trou de la campagne, et il est ici.
    assert corps.count('_sonder(') == 3, (
        'les trois pages temoins ne passent plus toutes par `_sonder` (%d appel(s)) '
        ': celle qui s\'en ecarte eprouve une COPIE du code mesure, et restera '
        'verte quand la mesure deviendra aveugle' % corps.count('_sonder('))
    assert 'page.evaluate(' not in corps, (
        'un temoin appelle une sonde directement au lieu de passer par '
        '`_sonder` : il n\'eprouve plus le chemin que suit la mesure')
    assert 'page.on(' not in corps, (
        'les temoins reposent un ecouteur local : c\'est exactement la copie '
        'qui a laisse passer « ne plus ecouter pageerror »')
    assert 'set_content' not in corps, (
        'un temoin charge son document lui-meme : `_sonder(contenu=…)` existe '
        'pour que le chargement suive le meme chemin que la mesure')


def test_l_instrument_ne_confond_pas_un_panneau_GARE_avec_un_debordement():
    """La première erreur, épinglée. `.vx-drawer` fermé vit à droite du cadre,
    `aria-hidden` et `inert` : c'est le bon motif, pas un défaut."""
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    sonde = src.split('SONDE_DEBORDEMENT = r"""')[1].split('"""')[0]
    assert 'window.innerWidth' not in sonde, (
        'la sonde compare de nouveau les elements a la fenetre : tout panneau '
        'hors-ecran garé par transform ressortira en debordement (136 faux '
        'positifs a la premiere version)')
    assert 'scrollWidth' in sonde and 'clientWidth' in sonde


def test_l_instrument_lit_les_fonds_peints_par_degrade():
    """La deuxième erreur, épinglée."""
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    assert 'backgroundImage' in src, (
        'la remontee du fond ne regarde plus les degrades : elle sautera le '
        'fond REELLEMENT peint des boutons pour atterrir sur la page sombre')
    assert _mes.DEGRADE_PRIMAIRE.startswith('linear-gradient('), (
        'le degrade du bouton primaire n\'est plus un temoin')


#  ------------------------------------------------ la mesure sur le produit

@pytest.mark.skipif(not (_navigateur_dispo() and _serveur_repond()),
                    reason='navigateur ou serveur absent — la mesure porterait '
                           'sur rien')
def test_les_huit_espaces_sont_propres_a_390_px():
    """390 px est la largeur où le défaut vivait, et celle qui contraint le
    plus. Une seule largeur ici : un gardien lent finit désactivé, et un
    gardien désactivé ne garde rien. Le balayage complet (390/768/1440) reste
    dans le rapport."""
    r = _mes.mesurer(largeurs=(390,))
    assert r['echecs_temoins'] == [], '\n'.join(r['echecs_temoins'])
    assert not r['statuts_non_200'], r['statuts_non_200']
    assert r['total_debordements'] == 0, [
        (x['espace'], x['debordement']) for x in r['releves']
        if x['debordement']['elements'] or x['debordement']['document']]
    assert r['total_erreurs'] == 0, [
        (x['espace'], x['erreurs']) for x in r['releves'] if x['erreurs']]
    assert r['total_sans_anneau'] == 0, [
        (x['espace'], x['clavier']['sans_anneau']) for x in r['releves']
        if x['clavier']['sans_anneau']]
    assert r['total_contraste'] == 0, [
        (x['espace'], x['contraste']['faibles']) for x in r['releves']
        if x['contraste']['faibles']]


@pytest.mark.skipif(not (_navigateur_dispo() and _serveur_repond()),
                    reason='navigateur ou serveur absent')
def test_le_balayage_porte_bien_sur_TOUS_les_espaces_du_registre():
    """Une mesure qui porterait sur 3 pages et rendrait « 0 defaut » serait
    verte et vide. Le registre est lu depuis `PRIMARY_NAV`, jamais recopié.

    LE NOMBRE N'EST PLUS FIGÉ. Il valait `== 8`, et la refonte 2.0 a porté la
    navigation à douze espaces : l'assertion était fausse depuis, sans que
    personne le voie — ce banc s'abstient dès qu'il manque un navigateur ou un
    serveur sur 127.0.0.1:5002, et il ne s'était jamais exécuté.
    `.claude/rules/vertex-tests.md` l'interdit d'ailleurs explicitement :
    « ne jamais figer un nombre comme vérité permanente ; mesurer le SHA
    courant ».

    Ce qui compte est l'ÉGALITÉ entre ce que la sonde balaie et ce que la coque
    déclare — plus un plancher anti-vide, pour qu'un registre tombé à trois
    pages ne rende pas ce banc silencieux."""
    from vertex.ui.shell import PRIMARY_NAV
    assert len(_mes.espaces()) == len(PRIMARY_NAV), (
        'la sonde balaie %d espaces, la coque en déclare %d'
        % (len(_mes.espaces()), len(PRIMARY_NAV)))
    assert len(PRIMARY_NAV) >= 8, (
        'seulement %d espaces déclarés — plancher anti-vide franchi'
        % len(PRIMARY_NAV))
