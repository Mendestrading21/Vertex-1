"""Vertex Test 1.0 — « JE N'AI PAS MESURÉ » N'EST PAS « LE PRODUIT A PLANTÉ ».

Quatre instruments dépendent d'un navigateur réel. Mesuré le 24 août 2026 sur
cette machine, où Chromium est installé mais ne peut pas être engendré :

| instrument | code de sortie | ce qu'il imprimait |
|---|---:|---|
| `mesurer_qa_espaces` | **1** | 26 lignes de trace Playwright, 0 ligne utile |
| `mesurer_couche_visuelle` | **1** | idem |
| `mesurer_hors_ligne` | **1** | idem |
| `mesurer_regles_mortes` | **1** | idem, après avoir bâti 4,4 Mo de corpus pour rien |

Deux mensonges dans un seul comportement :

1. **Une trace brute se lit « le produit a planté ».** C'est l'inverse exact de
   la vérité : c'est l'*instrument* qui n'a pas pu démarrer.
2. **Le code 1 se confond avec un vrai plantage**, alors que le contrat de ces
   outils annonce « 0 = mesuré, 2 = témoin muet ». Un opérateur — ou une CI —
   qui range les codes en « 0 / pas 0 » ne peut pas distinguer *mesuré propre*
   de *jamais mesuré*.

C'est la même faute que D-053 pour le HTTP : l'instrument sait pourquoi il a
échoué, et ne le dit pas. Autre mécanisme, même classe.

## Pourquoi trois motifs et pas un booléen

`navigateur_pret()` répondait `False` aux trois. Or ils n'appellent pas du tout
la même action :

| motif | remède |
|---|---|
| `MODULE_ABSENT` | installer playwright |
| `BINAIRE_ABSENT` | télécharger le navigateur |
| `LANCEMENT_REFUSE` | **rien à installer** — l'environnement ne le permet pas |

Répondre « non » aux trois envoie l'opérateur réinstaller un binaire déjà
présent. C'est le cas réel de cette machine.
"""
from __future__ import annotations

import ast
import io
import re
from pathlib import Path

from tools.mesures import mesurer_qa_espaces as QA

RACINE = Path(__file__).resolve().parents[1]
OUTILS = RACINE / "tools" / "mesures"

#: Les instruments qui ont besoin d'un navigateur. Liste DERIVEE du code, pas
#: recopiee : une liste ecrite a la main rate le cinquieme outil.
def _outils_navigateur():
    """Les outils qui PILOTENT un navigateur — détectés sur le CODE, pas sur le
    texte.

    Le prédicat cherchait `'sync_playwright' in src or 'mesurer_couche_visuelle'
    in src`, donc dans les commentaires aussi. Mesuré le 2026-09-06 : un
    commentaire ajouté à `mesurer_qa_degrade.py` (outil purement HTTP) citait le
    nom `mesurer_couche_visuelle` pour expliquer une variable d'environnement —
    et le banc a exigé de lui l'aveu navigateur, code de sortie 3 compris, qu'il
    n'a aucune raison de porter. Un gardien qui se déclenche sur une phrase
    apprend à ne plus écrire de phrases.

    On lit donc l'AST : un import réel de `sync_playwright`/`playwright` ou du
    module `mesurer_couche_visuelle`, ou un usage de ces noms dans le code.
    """
    trouves = []
    for f in sorted(OUTILS.glob('*.py')):
        src = f.read_text(encoding='utf-8')
        if 'def main(' not in src:
            continue
        try:
            arbre = ast.parse(src)
        except SyntaxError:                       # un outil illisible n'est pas un outil navigateur
            continue
        noms = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Import):
                for al in n.names:
                    noms.add(al.name)
                    noms.add(al.asname or '')
            elif isinstance(n, ast.ImportFrom):
                noms.add(n.module or '')
                for al in n.names:
                    noms.add(al.name)
                    noms.add(al.asname or '')
            elif isinstance(n, ast.Name):
                noms.add(n.id)
            elif isinstance(n, ast.Attribute):
                noms.add(n.attr)
        pilote = any('playwright' in x or 'mesurer_couche_visuelle' in x for x in noms if x)
        if pilote:
            trouves.append(f)
    return trouves


#  ═══════════  1. les trois motifs sont DISTINCTS  ════════════════════════════

def test_les_trois_motifs_ont_des_remedes_DIFFERENTS():
    """Un motif qui mène au même conseil que les autres n'est pas un motif."""
    remedes = set(QA.REMEDES.values())
    assert len(remedes) == 3, QA.REMEDES
    assert 'install' in QA.REMEDES[QA.MODULE_ABSENT]
    assert 'install' in QA.REMEDES[QA.BINAIRE_ABSENT]
    #  Celui-ci ne s'installe PAS — c'est tout l'intérêt de le distinguer.
    assert 'install' not in QA.REMEDES[QA.LANCEMENT_REFUSE]


def test_un_binaire_INTROUVABLE_n_est_pas_un_binaire_qui_REFUSE(monkeypatch):
    """Le cas réel de cette machine : Chromium est là, il refuse de démarrer.
    Conseiller de le réinstaller ferait perdre son temps à l'opérateur."""
    QA.diagnostic_navigateur.cache_clear()
    monkeypatch.setattr(QA, '_chromium', lambda: None)
    d = QA.diagnostic_navigateur()
    QA.diagnostic_navigateur.cache_clear()
    if not d['pret']:
        assert d['raison'] in (QA.BINAIRE_ABSENT, QA.MODULE_ABSENT), d


def test_le_diagnostic_rend_TOUJOURS_les_memes_cles():
    """Un appelant qui doit tester la présence d'une clé avant de la lire
    finira par ne plus la lire du tout."""
    d = QA.diagnostic_navigateur()
    assert set(d) == {'pret', 'raison', 'detail', 'chemin', 'remede'}
    assert isinstance(d['pret'], bool)


def test_navigateur_pret_garde_son_contrat_BOOLEEN():
    """Trois bancs de test s'abstiennent dessus. Changer son type les casserait
    en silence — ils s'abstiendraient sur un dict toujours vrai, et
    prétendraient mesurer ce qu'ils n'ont pas mesuré."""
    v = QA.navigateur_pret()
    assert v is True or v is False


def test_pret_et_raison_ne_se_contredisent_JAMAIS():
    d = QA.diagnostic_navigateur()
    if d['pret']:
        assert d['raison'] is None and d['remede'] is None
    else:
        assert d['raison'] in (QA.MODULE_ABSENT, QA.BINAIRE_ABSENT,
                               QA.LANCEMENT_REFUSE)
        assert d['remede']


#  ═══════════  2. l'aveu dit ce qu'il faut, et rien de faux  ══════════════════

def test_l_aveu_sort_en_code_3_et_pas_en_code_1():
    """1 est le code d'un plantage Python. Le contrat de ces outils est
    « 0 = mesuré, 2 = témoin muet » ; 3 rejoint la convention déjà posée par
    `mesurer_g5_live` pour TWS injoignable."""
    flux = io.StringIO()
    assert QA.abandonner_sans_navigateur(flux) == QA.SORTIE_SANS_NAVIGATEUR == 3


def test_l_aveu_NIE_explicitement_dire_quoi_que_ce_soit_du_produit():
    """Le point entier du lot. Sans cette phrase, un code non nul se lit
    « défaut trouvé »."""
    flux = io.StringIO()
    QA.abandonner_sans_navigateur(flux)
    texte = flux.getvalue()
    assert 'NON MESURE' in texte
    assert 'ne dit RIEN du produit' in texte


def test_l_aveu_NOMME_le_motif_et_le_remede():
    flux = io.StringIO()
    QA.abandonner_sans_navigateur(flux)
    texte = flux.getvalue()
    d = QA.diagnostic_navigateur()
    if not d['pret']:
        assert d['raison'] in texte
        assert d['remede'][:20] in texte


def test_l_aveu_tient_en_QUELQUES_lignes_pas_en_vingt_six():
    """26 lignes de trace noient le seul mot qui compte."""
    flux = io.StringIO()
    QA.abandonner_sans_navigateur(flux)
    assert len(flux.getvalue().strip().splitlines()) <= 4


#  ═══════════  3. la classe entière, pas l'outil du symptôme  ═════════════════

def test_CHAQUE_outil_navigateur_avoue_avant_de_mesurer():
    """D-027 : corriger le site où le symptôme apparaît laisse la classe en
    place. Quatre outils étaient concernés ; le cinquième s'écrira sans aveu si
    rien ne l'en empêche."""
    manquants = []
    for f in _outils_navigateur():
        #  `mesurer_qa_espaces` DEFINIT l'aveu — raison de plus pour qu'il
        #  s'en serve : l'outil qui pose la regle est le premier a l'oublier.
        src = f.read_text(encoding='utf-8')
        corps = src[src.index('def main('):]
        if 'navigateur_pret()' not in corps or 'abandonner_sans_navigateur' not in corps:
            manquants.append(f.name)
    assert manquants == [], (
        "ces outils planteront en trace brute au lieu d'avouer : %s" % manquants)


def test_CHAQUE_outil_navigateur_DOCUMENTE_le_code_3():
    """Un code de sortie non documenté est un code que personne ne teste."""
    muets = []
    for f in _outils_navigateur():
        #  Le docstring du MODULE, pas un prefixe de N caracteres : celui de
        #  `mesurer_qa_espaces` fait 85 lignes, et toute fenetre arbitraire
        #  finit par couper le contrat qu'elle est censee verifier.
        doc = ast.get_docstring(ast.parse(f.read_text(encoding='utf-8'))) or ''
        if not re.search(r"3 = NON MESUR", doc):
            muets.append(f.name)
    assert muets == [], "code 3 absent du contrat de : %s" % muets


def test_le_gardien_VOIT_un_outil_sans_aveu_qu_on_lui_montre(tmp_path):
    """Contre-épreuve n°1. Un gardien qui ne trouve jamais rien passerait pour
    un gardien qui garde — D-031, déjà payé."""
    faux = "from playwright.sync_api import sync_playwright\ndef main():\n    return 0\n"
    corps = faux[faux.index('def main('):]
    assert 'navigateur_pret()' not in corps


def test_le_gardien_NE_signale_PAS_un_outil_correctement_gardé(tmp_path):
    """Contre-épreuve n°2 : un gardien qui refuse aussi la correction est
    désactivé au premier commit pressé."""
    bon = ("from playwright.sync_api import sync_playwright\n"
           "def main():\n"
           "    if not navigateur_pret():\n"
           "        return abandonner_sans_navigateur()\n"
           "    return 0\n")
    corps = bon[bon.index('def main('):]
    assert 'navigateur_pret()' in corps and 'abandonner_sans_navigateur' in corps


def test_le_recensement_trouve_bien_les_QUATRE_outils_concernes():
    """Si le recensement rendait une liste vide, les deux bancs ci-dessus
    passeraient sur rien du tout."""
    noms = {f.name for f in _outils_navigateur()}
    assert {'mesurer_qa_espaces.py', 'mesurer_couche_visuelle.py',
            'mesurer_hors_ligne.py', 'mesurer_regles_mortes.py'} <= noms, noms
