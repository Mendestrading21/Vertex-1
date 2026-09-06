"""Vertex Test 1.0 - LES DEPECHES VIENNENT DU COURTIER, PAS DU WEB.

Le compte est abonne a des fournisseurs professionnels ; le fil les
ignorait et lisait yfinance puis un repli RSS. Mesure du jour sur
U8000001 : 12 symboles servis en 8,9 s sur UNE session, fil a 45 articles,
provenance « depeches ibkr » sans aucun repli web.

Le piege que ce fichier garde surtout : `reqHistoricalNews` REJETTE la
requete entiere (erreur 321) si un seul fournisseur de la liste n est pas
abonne. Interroger les huit codes rendus par `reqNewsProviders` donnait
donc ZERO depeche alors que quatre repondaient.
"""
from __future__ import annotations

from vertex.data_sources import ibkr_news, ibkr_link


def test_seuls_les_fournisseurs_mesures_sont_interroges():
    """DJNL rend systematiquement zero, et DJ-RTA/RTE/RTG ne sont pas
    abonnes : les garder couterait un aller-retour par symbole pour rien,
    et un seul non-abonne fait tomber toute la requete."""
    assert set(ibkr_news.FOURNISSEURS) == {"BRFG", "DJ-N", "DJ-RT", "BRFUPDN"}
    for interdit in ("DJ-RTA", "DJ-RTE", "DJ-RTG", "DJNL"):
        assert interdit not in ibkr_news.FOURNISSEURS


def test_chaque_fournisseur_est_interroge_SEPAREMENT():
    """Le defaut mesure : la liste complete passee en une fois rendait
    erreur 321 et zero depeche. Un refus doit en isoler UN."""
    src = open(ibkr_news.__file__, encoding="utf-8").read()
    assert "for code in FOURNISSEURS:" in src, (
        "les fournisseurs doivent etre interroges un par un")
    deb = src.index("for code in FOURNISSEURS:")
    corps = src[deb:deb + 700]
    assert "continue" in corps, "un refus doit isoler un fournisseur, pas tous"


def test_le_prefixe_technique_est_retire_du_titre():
    """`reqHistoricalNews` prefixe ses titres — « {A:800015:L:en}Apple... ».
    Affiche tel quel, le fil commencerait par une accolade."""
    assert ibkr_news._titre("{A:800015:L:en}Apple Bites Into Record Q3") == (
        "Apple Bites Into Record Q3")
    assert ibkr_news._titre("Sans prefixe") == "Sans prefixe"


def test_le_role_news_a_son_propre_identifiant():
    """La boucle news tourne toutes les 60 s, celle du scan par salves de
    plusieurs minutes : partager un identifiant les ferait s evincer."""
    ids = ibkr_link.CLIENT_IDS
    assert "news" in ids
    assert len(set(ids.values())) == len(ids), "deux roles partagent un identifiant"


def test_un_titre_sans_depeche_est_ABSENT_du_lot():
    """Present avec une liste vide, il passerait pour servi et le repli
    n irait jamais le chercher."""
    src = open(ibkr_news.__file__, encoding="utf-8").read()
    deb = src.index("def depeches_lot")
    corps = src[deb:]
    assert "if art:" in corps, (
        "seul un symbole REELLEMENT servi doit entrer dans le lot")


def test_un_lot_vide_ne_touche_pas_au_courtier():
    assert ibkr_news.depeches_lot([]) == {}


def test_la_boucle_news_met_le_courtier_en_tete_et_garde_le_repli():
    import terminal
    src = open(terminal.__file__, encoding="utf-8").read()
    deb = src.index("def _news_loop")
    corps = src[deb:deb + 4200]
    assert "depeches_lot" in corps, "le courtier doit etre interroge en premier"
    assert "rss_news" in corps, (
        "le repli web doit rester : ce que le courtier ne sert pas doit "
        "descendre la chaine, pas disparaitre de l ecran")
    assert "source_detail" in corps, (
        "la provenance doit compter les contributeurs : un fil bascule "
        "entierement sur le web se lirait sinon comme avant")


# ── L'HORODATAGE DE LA DEPECHE N'EST PLUS TRONQUE ───────────────────────────

class _Article:
    """Ce que `reqHistoricalNews` rend : ib_async parse `time` en datetime UTC."""

    def __init__(self, headline, time, provider='DJ-N'):
        self.headline, self.time, self.providerCode = headline, time, provider


class _Contrat:
    def __init__(self, *a, **k):
        self.conId = 0


class _IB:
    def qualifyContracts(self, c):
        c.conId = 265598

    def reqHistoricalNews(self, con_id, code, deb, fin, n):
        import datetime as _dt
        if code != 'DJ-N':
            return []
        return [_Article('{A:800015:L:en}Apple Bites Into Record Q3',
                         _dt.datetime(2026, 9, 5, 13, 22, 11,
                                      tzinfo=_dt.timezone.utc))]


class _Passerelle:
    _ib = None

    def connect(self):
        return _IB()


def test_l_horodatage_de_la_depeche_garde_le_fuseau_declare(monkeypatch):
    """MESURE DU 2026-09-06 — `str(a.time)[:16]` jetait la QUEUE de
    l'horodatage, c'est-a-dire le fuseau que le courtier DECLARE.

    `ib_async` rend un datetime aware ; son `str()` vaut
    « 2026-09-05 13:22:11+00:00 ». Tronque a 16 caracteres, il devenait
    « 2026-09-05 13:22 », et `news_plus.horodatage_source` — qui n'invente
    jamais un fuseau absent — rendait « 2026-09-05T13:22 » : l'ecran affichait
    « fuseau n/d » sur une source qui, elle, le declare. Meme famille que le
    `str(t)[:16]` de yfinance releve par le controle du jour.

    Ce banc mesure les DEUX bouts : la chaine servie par le module, et ce que
    la normalisation en tire.
    """
    from vertex.services import news_plus
    monkeypatch.setattr(ibkr_news.ibkr_gateway, 'classe', lambda nom: _Contrat)
    out = ibkr_news.depeches_pour('AAPL', 4, gateway=_Passerelle())
    assert len(out) == 1
    assert out[0]['title'] == 'Apple Bites Into Record Q3'
    assert out[0]['time'] == '2026-09-05 13:22:11+00:00', (
        'la chaine du courtier est servie ENTIERE, jamais tronquee')
    assert news_plus.horodatage_source(out[0]['time']) == '2026-09-05T13:22Z'
    #  La mesure du defaut, figee : la troncature detruisait le fuseau.
    assert news_plus.horodatage_source(out[0]['time'][:16]) == '2026-09-05T13:22'


def test_une_depeche_sans_horodatage_reste_sans_horodatage(monkeypatch):
    """`getattr(a, 'time', '')` peut rendre None : `str(None)` aurait servi la
    chaine « None », c'est-a-dire une date illisible presentee comme servie.
    Une absence reste une absence — et le pipeline la rejette explicitement."""
    class _IBMuet(_IB):
        def reqHistoricalNews(self, con_id, code, deb, fin, n):
            return [_Article('Sans date', None)] if code == 'DJ-N' else []

    class _PasserelleMuette(_Passerelle):
        def connect(self):
            return _IBMuet()

    monkeypatch.setattr(ibkr_news.ibkr_gateway, 'classe', lambda nom: _Contrat)
    out = ibkr_news.depeches_pour('AAPL', 4, gateway=_PasserelleMuette())
    assert out[0]['time'] == '', 'aucune chaine « None » servie comme horodatage'


# ── L'ATTESTATION DU COURTIER EST POSEE A LA PRODUCTION ─────────────────────

def _marquage_du_producteur():
    """La boucle de marquage REELLE de `_news_loop`, extraite par AST.

    `_news_loop` est une boucle infinie qui ouvre une session TWS : on ne peut
    pas l'appeler ici. On extrait donc le `for it in its:` de son corps et on
    le compile tel quel — ce qui est mesure est la SORTIE du producteur servi,
    pas une chaine de caracteres trouvee dans le fichier.
    """
    import ast
    import terminal
    from vertex.services import news_plus
    arbre = ast.parse(open(terminal.__file__, encoding='utf-8').read())
    fn = next(n for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == '_news_loop')
    boucle = next(n for n in ast.walk(fn)
                  if isinstance(n, ast.For) and isinstance(n.target, ast.Name)
                  and n.target.id == 'it' and isinstance(n.iter, ast.Name)
                  and n.iter.id == 'its')
    mod = ast.Module(body=[boucle], type_ignores=[])
    ast.fix_missing_locations(mod)
    code = compile(mod, terminal.__file__, 'exec')

    def _marque(items, sym, atteste):
        espace = {'its': [dict(i) for i in items], 'sym': sym,
                  'atteste': atteste, 'feed': [], '_news_plus': news_plus}
        exec(code, espace)
        return espace['feed']
    return _marque


def test_la_depeche_du_courtier_est_ATTESTEE_le_repli_web_ne_l_est_pas():
    """LE FIL A UN SEUL PRODUCTEUR, ET C'EST LUI QUI SAIT.

    `sym` est le FIL INTERROGE, pas le sujet : mesure du 2026-09-06, 22 titres
    sur les 45 items servis ne nomment ni le ticker ni la societe. Mais la
    branche courtier, elle, SAIT : `depeches_lot` interroge
    `reqHistoricalNews` sur le `conId` QUALIFIE du contrat — c'est IBKR qui
    rattache la depeche au titre. Le repli web, lui, est une recherche de
    mots-cles (`'%s stock'`) : rien ne l'y attache.

    Le producteur pose donc `sym_atteste` sur la SEULE branche courtier, et
    `sym_role` sur tous les items — pour que la route, le brief et le pipeline
    lisent un verdict au lieu de le rejuger chacun de leur cote (ou, pire, de
    prendre la provenance pour un sujet).
    """
    marque = _marquage_du_producteur()
    #  Depeche du courtier : le titre ne nomme pas la societe, et le sujet est
    #  pourtant ETABLI — l'attestation vient du vendeur, pas du texte.
    depeche = marque([{'title': 'Analyst raises target'}], 'NVDA', True)[0]
    assert depeche['sym_atteste'] is True
    assert depeche['sym_role'] == 'sujet'
    assert depeche['sym'] == 'NVDA'
    #  MEME titre arrive par le repli web : rien ne l'attache au titre.
    web = marque([{'title': 'Analyst raises target'}], 'NVDA', False)[0]
    assert 'sym_atteste' not in web, 'le repli web n est jamais atteste'
    assert web['sym_role'] == 'fil'
    #  Le repli qui NOMME la societe reste etabli par le nom, comme avant.
    nomme = marque([{'title': 'Nvidia beats estimates'}], 'NVDA', False)[0]
    assert nomme['sym_role'] == 'sujet' and 'sym_atteste' not in nomme
    #  Le marquage est ADDITIF : rien de l'item d'origine n'est perdu.
    assert nomme['title'] == 'Nvidia beats estimates' and nomme['senti'] == 1


def test_l_attestation_vient_de_la_branche_courtier_pas_du_repli(monkeypatch):
    """Le drapeau doit etre calcule AVANT que le repli ne remplace `its`.

    Si `atteste` etait evalue apres, tout le fil serait declare atteste des
    que le repli rend quelque chose — l'inverse exact de la regle.
    """
    import ast
    import terminal
    src = open(terminal.__file__, encoding='utf-8').read()
    arbre = ast.parse(src)
    fn = next(n for n in ast.walk(arbre)
              if isinstance(n, ast.FunctionDef) and n.name == '_news_loop')
    poses = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
             for c in n.targets
             if isinstance(c, ast.Name) and c.id == 'atteste']
    replis = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and n.func.attr == 'rss_news']
    assert poses and replis, (poses, replis)
    assert max(poses) < min(replis), (
        'le drapeau d attestation est pose apres le repli web : il declarerait '
        'atteste ce que le courtier n a jamais servi')
