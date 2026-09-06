"""Vertex Test 1.0 · G4/G6 — MODES DÉGRADÉS, SYMBOLE INCONNU, FUITE DE SECRET.

Ce fichier garde `tools/mesures/mesurer_qa_degrade.py`. Les contrôles y sont
des **fonctions pures** de `(corps) -> anomalies` : on peut donc leur présenter
un corps fabriqué portant le défaut, sans serveur et sans attendre qu'un vrai
défaut apparaisse. C'est ce qui rend le gardien rapide **et** probant.

## Ce que la mesure a établi sur le produit

```text
22 surfaces (12 espaces + 10 API)   ← relevé du 6 sept. 2026, instance QA
 0  fuite de secret          0  verbe d'ordre servi
 0  anomalie de fraicheur    0  fabrication sur un ticker inexistant
 0  erreur JS cliente        mode demo declare
```

Ce relevé disait « 18 surfaces (8 espaces + 10 API) » alors que l'instrument
en énumère 22 : la liste des espaces est dérivée de la navigation du produit
(`PRIMARY_NAV`), donc elle grandit avec lui pendant que le chiffre recopié ici
reste figé. Un compte rendu de couverture qui se périme tout seul est le
premier signe qu'une garde a cessé de mesurer.

Le comportement sur symbole inconnu mérite d'être cité, parce que c'est
exactement ce que la mission demande et qu'il est rare : `verdict = null`,
`score.level = REFUS_WATCH`, six blocs sur huit en `INSUFFICIENT`,
`confidence.value = 0.0`, et une base qui écrit *« facteur plafonné à 0,50,
jamais inventé »*. Le produit refuse au lieu d'estimer.

## Le piège que ce fichier existe pour empêcher

Un contrôle de fuite qui cherche la **chaîne « VERTEX_CODE »** trouve le mot
dans un commentaire et rate la **valeur**. Un contrôle qui ne cherche que des
valeurs présentes dans l'environnement ne cherche rien du tout sur une machine
où elles sont absentes — d'où les motifs génériques (compte IBKR, clés d'API,
clé privée), qui ne dépendent d'aucun environnement.

Et le contrôle du symbole inconnu doit savoir distinguer **refuser** de
**fabriquer** : un test qui exigerait simplement « pas d'erreur » serait vert
sur un produit qui invente un verdict.
"""
import pathlib
import sys

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures import mesurer_qa_degrade as _mes  # noqa: E402

#  L'ADRESSE N'EST PLUS REFIGÉE ICI. Elle l'était (`http://127.0.0.1:5002`)
#  alors que l'instrument lit désormais `VERTEX_MESURE_BASE`, exactement comme
#  test_qa_espaces / test_couche_visuelle / test_regles_mortes qui lisent tous
#  `_mes.BASE_DEFAUT`. MESURE du défaut :
#      pytest -q -rs tests/test_qa_degrade.py                      → 9 passed, 1 skipped
#      VERTEX_MESURE_BASE=…:5003 pytest -q -rs tests/…             → 9 passed, 1 skipped
#  La variable était ignorée : sur la seule instance mesurable de la machine
#  (QA, sans code d'accès), le gardien continuait de dormir — y compris sous le
#  job CI que le dépôt prépare, qui pose pourtant cette variable sur 5003.
#  Le défaut sans variable reste 5002 : aucun poste existant ne change.
BASE = _mes.BASE_DEFAUT

#  LE MÊME CRITÈRE QUE LES TROIS MODULES FRÈRES, ET IL VIT DANS L'INSTRUMENT.
#
#  Ce banc demandait `/healthz` puis `/api/live/status` : une surface que la
#  mesure n'examine pas, pour décider du sort de 12 pages HTML qu'elle examine.
#  Deux faiblesses mesurées : le verrou n'est pas la seule raison de ne pas
#  voir le produit (page servie sans son espace, interstitiel de proxy), et
#  toute erreur non HTTP — expiration, connexion coupée — rendait « pas
#  verrouillé », donc « mesure ». L'instrument accusait alors le produit de ne
#  pas nommer un vide qu'il n'avait jamais vu.
#
#  `etat_instance` exige désormais une PAGE ouverte (`data-space="markets"`,
#  sans `name="code"` ni `type="password"`), exactement comme test_qa_espaces,
#  test_couche_visuelle et test_regles_mortes. La décision est PURE et éprouvée
#  plus bas sur des corps fabriqués ; ici on ne fait que l'appeler.
_ETAT_INSTANCE = _mes.etat_instance(BASE)


#  ------------------------------------------------------- les contrôles purs

def test_le_controle_de_fuite_voit_un_secret_planté():
    """Trois formes qui ne dépendent d'aucun environnement : un compte IBKR,
    une clé d'API, une adresse e-mail."""
    a = _mes.controler_fuite(_mes.CORPS_AVEC_SECRET, {})
    assert a, ('un corps portant « U1234567 », une cle « sk-ant-… » et une '
               'adresse e-mail ne declenche rien : le controle de fuite ne '
               'cherche que des valeurs d\'environnement, absentes ici')
    assert len(a) >= 3, 'un seul motif sur trois mord : %s' % a


def test_le_controle_de_fuite_cherche_la_VALEUR_pas_le_NOM():
    """Ce qui fuit n'est jamais le nom de la variable."""
    faux = {'VERTEX_CODE': 'valeur-secrete-fabriquee-123456'}
    assert _mes.controler_fuite('page ' + faux['VERTEX_CODE'] + ' fin', faux)
    assert not _mes.controler_fuite('page qui parle de VERTEX_CODE', faux), (
        'le simple NOM « VERTEX_CODE » declenche une fuite : le controle '
        'signalerait chaque commentaire de la base')


def test_le_controle_de_fuite_ne_crie_pas_sur_un_corps_sain():
    """Un détecteur qui crie sur tout est aussi inutilisable qu'un aveugle —
    et celui-ci voit passer des nombres, des plages, des cours."""
    assert not _mes.controler_fuite(_mes.CORPS_PROPRE, {})


def test_le_controle_des_verbes_d_ordre_mord_et_se_tait():
    """L'invariant absolu du produit : aucun ordre. Vérifié sur les octets
    SERVIS, pas seulement sur les sources."""
    assert _mes.controler_verbe_ordre(_mes.CORPS_AVEC_ORDRE)
    assert not _mes.controler_verbe_ordre(_mes.CORPS_PROPRE)
    #  Les verbes sont assembles a l'execution : les ecrire ici en entier
    #  ferait echouer `test_no_orders.py`, qui les interdit dans tout `.py`.
    #  Ce gardien-la a raison — on ne loge pas un outil dans ses exceptions.
    assert ('transmit' + 'Order') in _mes.VERBES_ORDRE
    assert len(_mes.VERBES_ORDRE) >= 6, (
        'le vocabulaire d\'ordre a maigri : %s' % (_mes.VERBES_ORDRE,))


def test_le_controle_du_symbole_inconnu_distingue_refuser_de_fabriquer():
    """LE TEST QUI COMPTE LE PLUS DE CE FICHIER.

    Un contrôle qui exigerait seulement « pas d'erreur » serait vert sur un
    produit qui invente un verdict ACHAT à 82 % de confiance."""
    invente = _mes.controler_symbole_inconnu(_mes.PAQUET_INVENTE)
    assert invente, ('un verdict ACHAT a 82 %% de confiance pour un titre '
                     'inexistant passe le controle')
    honnete = _mes.controler_symbole_inconnu(_mes.PAQUET_HONNETE)
    assert not honnete, ('le comportement ATTENDU — REFUS_WATCH, confiance '
                         'nulle, « jamais estimés » — ressort en anomalie : %s'
                         % honnete)


def test_un_vide_non_nomme_est_une_anomalie():
    """Refuser sans le dire laisse l'écran vide et muet : l'utilisateur ne peut
    pas distinguer « rien à voir » de « le calcul a échoué »."""
    #  Le paquet doit etre VRAIMENT muet : « REFUS_WATCH » est deja un aveu
    #  (il contient « REFUS »), donc un paquet qui le porte ne teste pas cette
    #  branche-la. Le silence complet, c'est un refus qui ne se nomme meme pas.
    muet = {'decision': {'verdict': None, 'confidence': {'value': 0.0}}}
    a = _mes.controler_symbole_inconnu(muet)
    assert any('aveu' in x for x in a), (
        'un refus qui ne contient AUCUN mot d\'aveu passe : %s' % a)


def test_le_controle_de_fraicheur_refuse_un_age_nul_sur_un_domaine_hors_ligne():
    """LE DÉFAUT LE PLUS MÉCANIQUE DU PRODUIT (lots 62-64) : `age_s = 0` sur un
    domaine mort s'affiche « à l'instant ». Zéro et « inconnu » sont deux
    choses, et l'étiquette de fraîcheur est le seul endroit où le produit
    puisse mentir sans que rien ne plante."""
    a = _mes.controler_fraicheur_domaines(_mes.STATUT_MENTEUR)
    assert a and any('age_s=0' in x for x in a), (
        'un domaine « offline » avec age_s=0 passe le controle : il s\'affichera '
        '« a l\'instant » sur du vide')
    assert not _mes.controler_fraicheur_domaines(_mes.STATUT_HONNETE), (
        'un domaine hors ligne qui AVOUE (age null, « jamais synchronise ») '
        'ressort en anomalie')


def test_le_critere_d_instance_refuse_l_ecran_de_connexion_et_le_silence():
    """MESURÉ le 6 sept. 2026 : deux gardiens ont mesuré l'ÉCRAN DE CONNEXION
    de l'instance de travail en le prenant pour le produit.

    Les quatre cas, sans serveur, avec un lecteur fabriqué :

    ```text
    /healthz muet                        → ABSENTE  (rien à mesurer)
    /healthz 200 + page de connexion     → FERMEE   (on s'abstient)
    /healthz 200 + /markets sans réponse → FERMEE   (l'ancien critere disait
                                                     « pas verrouille » → mesure)
    /healthz 200 + espace Marchés servi  → OUVERTE  (on mesure)
    ```
    """
    def lecteur(reponses):
        return lambda base, chemin, defaut='': reponses[chemin]

    absente = lecteur({'/healthz': (None, 'connexion refusee')})
    assert _mes.etat_instance('http://x', lire=absente) == 'ABSENTE'

    verrou = lecteur({'/healthz': (200, '{"ok":true}'),
                      '/markets': (200, _mes.CORPS_ECRAN_DE_CODE)})
    assert _mes.etat_instance('http://x', lire=verrou) == 'FERMEE', (
        'un ecran de connexion est pris pour le produit : c\'est lui qui sera '
        'mesure, et le produit sera accuse de ne rien nommer')

    muette = lecteur({'/healthz': (200, '{"ok":true}'),
                      '/markets': (None, 'expiree apres 60 s')})
    assert _mes.etat_instance('http://x', lire=muette) == 'FERMEE', (
        'une page qui ne repond pas vaut « instance ouverte » : la mesure part '
        'sur une instance qu\'on n\'a pas vue')

    ouverte = lecteur({'/healthz': (200, '{"ok":true}'),
                       '/markets': (200, _mes.CORPS_ESPACE_OUVERT)})
    assert _mes.etat_instance('http://x', lire=ouverte) == 'OUVERTE', (
        'la page Marches du produit ne suffit plus a declarer l\'instance '
        'mesurable : le controle produit dormira pour toujours')


def test_les_temoins_de_l_instrument_sont_tous_eprouves():
    """Le jeu de témoins complet, tel que l'outil l'exécute."""
    faux_releve = {'statuts': {'/': 200}}
    assert _mes._temoins(faux_releve) == []


def test_l_instrument_ne_recopie_jamais_le_secret_qu_il_trouve():
    """Un rapport de fuite qui imprime le secret est lui-même une fuite — et il
    finit dans un fichier de validation versionné."""
    a = _mes.controler_fuite('compte U9876543 ici', {})
    assert a
    assert 'U9876543' not in ' '.join(a), (
        'le rapport recopie le secret trouve : le rapport devient la fuite')


#  ------------------------------------------------ la mesure sur le produit

@pytest.mark.skipif(_ETAT_INSTANCE == 'ABSENTE',
                    reason='aucun serveur sur %s — la mesure porterait sur '
                           'rien' % BASE)
@pytest.mark.skipif(_ETAT_INSTANCE == 'FERMEE',
                    reason="le produit ne se montre pas sur %s (verrou "
                           "VERTEX_CODE, ou page servie sans son espace) : "
                           "l'instrument ne verrait que cet ecran. Mesurer ici "
                           'accuserait le produit de ne pas nommer un vide que '
                           'personne ne lui a montre.' % BASE)
def test_le_produit_servi_ne_fuit_rien_et_ne_sait_pas_passer_d_ordre():
    r = _mes.mesurer(BASE)
    assert _mes._temoins(r) == []
    assert not r['fuites'], 'secret servi : %s' % r['fuites']
    assert not r['verbes_ordre'], (
        'un verbe d\'ordre est SERVI au navigateur : %s' % r['verbes_ordre'])
    assert not r['anomalies_fraicheur'], r['anomalies_fraicheur']
    assert not r['anomalies_symbole_inconnu'], r['anomalies_symbole_inconnu']
    assert r['erreurs_client'] == 0, (
        '/api/client-log n\'est pas propre : %s' % r['detail_erreurs_client'])
    assert not [k for k, v in r['statuts'].items() if v != 200], r['statuts']


def _recharger_instrument(valeur):
    """Pose (ou retire) VERTEX_MESURE_BASE PUIS recharge l'instrument.

    L'ordre est le correctif. La version précédente utilisait `monkeypatch`,
    dont la restauration de l'environnement n'a lieu qu'APRÈS le test : le
    `finally` rechargeait donc le module pendant que la variable était encore
    retirée. MESURE, sur un poste qui pose la variable :

    ```text
    VERTEX_MESURE_BASE=http://127.0.0.1:5003 pytest tests/test_qa_degrade.py
      avant : environnement restauré à …:5003, _mes.BASE_DEFAUT figé à …:5002
      après : environnement restauré à …:5003, _mes.BASE_DEFAUT = …:5003
    ```

    Sans effet sur la suite actuelle (aucun autre module ne lit
    `BASE_DEFAUT`), mais c'est un état global laissé faux — et le prochain
    banc qui le lira mesurera l'instance que personne n'a demandée.
    """
    import importlib
    import os

    if valeur is None:
        os.environ.pop('VERTEX_MESURE_BASE', None)
    else:
        os.environ['VERTEX_MESURE_BASE'] = valeur
    return importlib.reload(_mes).BASE_DEFAUT


def test_le_banc_vise_l_instance_que_l_instrument_vise():
    """Le gardien ne refige plus son adresse — c'est ce qui l'endormait.

    MESURE (6 sept. 2026) : l'instance de travail est verrouillée par
    `VERTEX_CODE` (`/api/live/status` → `{"error":"auth"}`), donc le contrôle
    produit se sautait, à juste titre. Mais en pointant `VERTEX_MESURE_BASE`
    sur l'instance QA ouverte, le résultat était RIGOUREUSEMENT identique —
    `9 passed, 1 skipped`, même raison — alors qu'à la main l'instrument y
    mesure 22 surfaces sans une seule anomalie. Le skip ne disait donc pas la
    vérité sur sa cause : la mesure était possible, l'adresse était figée.

    Ce banc-ci ne mesure rien du produit : il vérifie que le contrôle qui, lui,
    le mesure, regarde bien la même instance que son instrument.
    """
    import os

    assert BASE == _mes.BASE_DEFAUT, (
        'l’adresse du banc est refigée : le contrôle produit dormira sur toute '
        'machine dont l’instance mesurable n’est pas celle par défaut')
    poste = os.environ.get('VERTEX_MESURE_BASE')
    try:
        assert _recharger_instrument('http://127.0.0.1:5003') == 'http://127.0.0.1:5003', (
            'l’instrument ignore VERTEX_MESURE_BASE, contrairement à ses trois '
            'modules frères')
        assert _recharger_instrument(None) == 'http://127.0.0.1:5002', (
            'le défaut a changé : un poste existant se met à mesurer une autre '
            'instance sans l’avoir demandé')
    finally:
        #  L'ENVIRONNEMENT DU POSTE D'ABORD, LE MODULE ENSUITE.
        _recharger_instrument(poste)


def test_l_instrument_reste_accorde_a_l_environnement_du_poste():
    """Le banc précédent manipule un module global : il doit le rendre INTACT.

    MESURE : `VERTEX_MESURE_BASE=http://127.0.0.1:5003 pytest -q
    tests/test_qa_degrade.py` laissait `_mes.BASE_DEFAUT` à `…:5002` alors que
    la variable, elle, était bien restaurée à `…:5003` — l'instrument et son
    environnement racontaient deux instances différentes pour le reste de la
    session pytest."""
    import os

    attendu = os.environ.get('VERTEX_MESURE_BASE') or 'http://127.0.0.1:5002'
    assert _mes.BASE_DEFAUT == attendu, (
        'l’instrument vise %s alors que l’environnement dit %s : un banc l’a '
        'rechargé au mauvais moment' % (_mes.BASE_DEFAUT, attendu))
