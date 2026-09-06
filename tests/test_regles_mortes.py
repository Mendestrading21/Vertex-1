"""Vertex Test 1.0 · #781 — LA PREUVE DE NON-USAGE, ET SES TROIS TROUS.

`CLEANUP_POLICY.md` interdit de supprimer sans **preuve de non-usage**.
`mesurer_couche_visuelle.py` rend 476 règles « jamais appariées au chargement » ;
ce sont des **candidates**, pas une preuve. Cet outil produit la preuve — et ce
fichier garde le fait que la preuve en soit une.

## Le résultat

```text
476 candidates
 63 PROUVÉES inatteignables   (aucune de leurs classes n'est écrite nulle part)
401 atteignables              (une classe existe quelque part dans les octets)
 12 indécidables              (sélecteur sans classe, ou préfixe assemblé)
corpus : 99 documents servis · 4,34 Mo
```

## Les trois trous, trouvés avant d'agir

Une preuve trouée est **pire qu'une absence de preuve** : elle autorise l'acte.
Chacun de ces trois défauts aurait fait supprimer du CSS vivant.

**1. Le corpus ne couvrait que les huit espaces.** `.ds-note` — écrite deux fois
dans la page `/design-system` servie — ressortait « prouvée inatteignable ». Le
produit sert bien plus que huit routes HTML : `/widget-lab`, `/intelligence`,
`/tracking`, `/design-system`… Corpus 35 → 88 documents, **preuves 92 → 63** :
**29 fausses preuves**, soit près d'un tiers.

**2. Les routes paramétrées manquaient.** `/analysis/<sym>`, `/company/<sym>`,
`/options/<sym>` rendent un balisage que les pages d'index n'ont pas. Corpus
88 → 99 ; le compte est resté à 63, ce qui rend la preuve d'autant plus solide :
elle a résisté à l'élargissement.

**3. Les noms de classe assemblés à l'exécution.** `'vx-chart-size-' +` en
construit un : le nom complet n'existe **nulle part** dans les octets, et c'est
précisément parce qu'il est fabriqué. Les règles qui en dérivent sont écartées
vers `INDÉCIDABLE`, jamais vers les preuves.

Un quatrième piège a été évité de justesse : la première version cherchait toute
interpolation `${…}` pour détecter les noms construits. Elle aurait trouvé
chaque gabarit de texte du produit et déclaré la preuve non fiable partout — un
détecteur qui crie sur tout ne guide rien.

## Le principe qui gouverne le critère

**Le doute profite à la règle.** Une seule classe présente quelque part suffit à
classer le sélecteur `ATTEIGNABLE`, même s'il ne s'apparie jamais au
chargement. C'est ce qui protège le CSS des **états** — `.vx-drawer.open`,
`.vx-row.is-selected` — celui qu'on voit le moins et dont on a le plus besoin.
"""
import pathlib
import sys
import urllib.request

import pytest

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.mesures import mesurer_regles_mortes as _mes  # noqa: E402

#: Recensement GELÉ. `CLEANUP_POLICY.md` interdit « tout empilement de CSS
#: temporaire sans date de retrait » : ce plafond est la date de retrait. Il
#: peut BAISSER librement (on a nettoyé) ; il ne doit pas monter en silence.
PROUVEES_INATTEIGNABLES = 63

#: Le corpus doit rester large. S'il se rétrécit, des preuves apparaissent —
#: et ce sont de fausses preuves, comme les 29 du premier passage.
CORPUS_MINIMAL = 90


def _navigateur_dispo():
    """Meme garde que les autres gardiens navigateur (qa_espaces, couche_visuelle).

    Elle manquait ICI : le skipif ne regardait que le serveur, donc sur une
    machine ou le serveur tourne SANS playwright installe, le test ne
    s'abstenait pas — il levait ModuleNotFoundError au milieu de la mesure. Un
    gardien qui plante ne dit pas « je n'ai pas pu mesurer », il dit « c'est
    casse », et les deux ne se lisent pas pareil.
    """
    from tools.mesures.mesurer_qa_espaces import navigateur_pret
    return navigateur_pret()


def _serveur_repond():
    try:
        with urllib.request.urlopen(_mes.BASE_DEFAUT + '/healthz', timeout=3) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


#  ------------------------------------------- le critère, éprouvé sans serveur

def test_une_classe_ecrite_nulle_part_est_prouvee_inatteignable():
    r = {x['selecteur']: x['classe']
         for x in _mes.classer(['.vx-nulle-part-xyz'], _mes.CORPUS_TEMOIN)}
    assert r['.vx-nulle-part-xyz'] == 'PROUVEE_INATTEIGNABLE'


def test_une_classe_posee_par_JS_n_est_PAS_prouvee_morte():
    """CONTRE-EXEMPLE. Sans cela, tout le CSS des ÉTATS serait déclaré mort :
    il ne s'apparie jamais au chargement, par construction."""
    r = {x['selecteur']: x['classe']
         for x in _mes.classer(['.vx-pose-par-js'], _mes.CORPUS_TEMOIN)}
    assert r['.vx-pose-par-js'] == 'ATTEIGNABLE', (
        'une classe posee par `classList.add` ressort morte — le CSS des '
        'etats serait supprime')


def test_le_doute_profite_a_la_regle():
    """LE PRINCIPE. Une seule classe présente suffit à épargner le sélecteur.
    `.vx-carte.est-ouverte` ne doit pas mourir parce que `est-ouverte` n'est
    écrit nulle part."""
    r = {x['selecteur']: x['classe'] for x in _mes.classer(
        ['.vx-existe.vx-nulle-part-xyz'], _mes.CORPUS_TEMOIN)}
    assert r['.vx-existe.vx-nulle-part-xyz'] == 'ATTEIGNABLE'


def test_une_classe_derivee_d_un_prefixe_assemble_n_est_jamais_prouvee():
    """TROU N°3. `'vx-chart-size-' +` fabrique un nom à l'exécution : son
    absence des octets ne prouve rien, elle s'explique."""
    r = {x['selecteur']: x['classe'] for x in _mes.classer(
        ['.vx-taille-lg'], {'page:t': ''}, prefixes=['vx-taille-'])}
    assert r['.vx-taille-lg'] == 'INDECIDABLE'


def test_le_detecteur_de_noms_assembles_reste_ETROIT():
    """Le quatrième piège, évité. Chercher toute interpolation `${…}` aurait
    trouvé chaque gabarit de texte du produit et rendu la preuve « non
    fiable » partout — un détecteur qui crie sur tout ne guide rien."""
    assert _mes.classes_construites({'js:/t.js': "c='vx-taille-'+n"}), (
        'une concatenation depuis un prefixe `vx-` n\'est plus detectee')
    assert not _mes.classes_construites(
        {'js:/t.js': "html=`<p>Il y a ${n} minutes</p>`"}), (
        'un gabarit de TEXTE est pris pour une construction de classe : la '
        'preuve sera declaree non fiable partout')


#  --------------------------------------------- le corpus, source de la preuve

def test_le_corpus_vient_de_la_TABLE_DE_ROUTAGE_pas_des_huit_espaces():
    """TROU N°1, celui qui a produit 29 fausses preuves."""
    routes = _mes.routes_html()
    espaces = {'/', '/markets', '/opportunities', '/analysis',
               '/portfolio', '/options', '/journal', '/system'}
    hors = [r for r in routes if r not in espaces]
    assert len(hors) >= 20, (
        'le corpus ne compte que %d page(s) hors des huit espaces : il est '
        'retombe sur PRIMARY_NAV, et une classe servie ailleurs sera declaree '
        'morte a tort (c\'est ce qui est arrive a `.ds-note`)' % len(hors))


def test_les_routes_PARAMETREES_sont_dans_le_corpus():
    """TROU N°2. Les fiches rendent un balisage que les index n'ont pas."""
    routes = _mes.routes_html()
    assert any(r.startswith('/analysis/') for r in routes), (
        'aucune fiche instanciee : tout leur balisage est hors du corpus')
    assert '/analysis/<sym>' not in routes, 'les gabarits ne sont pas instancies'


def test_les_routes_qui_DECLENCHENT_sont_exclues():
    """Mesurer ne doit rien provoquer. `/weekly-regen` et `/scan` lancent du
    travail : les visiter pour bâtir un corpus serait payer une mesure d'un
    effet de bord."""
    routes = _mes.routes_html()
    for action in ('/weekly-regen', '/scan'):
        assert action not in routes, (
            '« %s » est dans le corpus : la mesure declenche du travail' % action)


def test_l_outil_ne_supprime_rien():
    src = pathlib.Path(_mes.__file__).read_text(encoding='utf-8')
    for verbe in ('os.remove', 'unlink', 'write_text', 'shutil.rm'):
        assert verbe not in src, (
            'l\'instrument sait desormais ecrire ou supprimer (« %s ») : la '
            'preuve et l\'acte doivent rester separes' % verbe)


def test_les_temoins_mordent_tous():
    assert _mes._temoins() == []


#  ------------------------------------------------ la mesure sur le produit

@pytest.mark.skipif(not (_serveur_repond() and _navigateur_dispo()),
                    reason='serveur ou navigateur absent — la preuve porterait '
                           'sur rien')
def test_le_recensement_des_regles_prouvees_ne_grossit_pas():
    """`CLEANUP_POLICY.md` : « aucun empilement de CSS temporaire sans date de
    retrait ». Ce plafond EST la date de retrait. Il peut baisser (on a
    nettoyé) ; il ne doit pas monter en silence."""
    r = _mes.mesurer()
    assert len(r['octets_servis']) >= CORPUS_MINIMAL, (
        'le corpus est tombe a %d documents (< %d) : des preuves vont '
        'apparaitre, et ce seront de FAUSSES preuves'
        % (len(r['octets_servis']), CORPUS_MINIMAL))
    assert r['prouvees_inatteignables'] <= PROUVEES_INATTEIGNABLES, (
        'le CSS inatteignable a grossi : %d regles prouvees contre %d gelees. '
        'Du style a ete ajoute sans consommateur.'
        % (r['prouvees_inatteignables'], PROUVEES_INATTEIGNABLES))
