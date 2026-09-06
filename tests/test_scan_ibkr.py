"""Vertex Test 1.0 — IBKR EN TETE DE LA CHAINE DE DONNEES DU SCAN.

Mesure du jour (compte U8000001, TWS reel port 7496) : sur 533 symboles,
IBKR en sert **515** et yfinance **18** — ceux dont IBKR ne connait aucune
definition de titre. Ce fichier garde les deux moities de cette promesse :

- ce qu'IBKR sait servir ne doit PLUS venir du web ;
- ce qu'il ne sait pas servir doit rester une ABSENCE ici, jamais un trou
  rempli, pour que le repli le ramasse et que la provenance le dise.
"""
from __future__ import annotations

import pytest

from vertex.data_sources import ibkr_historical as hist
from vertex.data_sources import ibkr_link


#  ---------------------------------------------------------------- la forme

def test_la_forme_yfinance_est_traduite_pour_ibkr():
    """`BRK-B` chez Yahoo est `BRK B` chez IBKR. Sans traduction, la classe B
    disparaissait du scan sans qu'aucune erreur ne soit levee."""
    assert hist._forme_ibkr('BRK-B') == 'BRK B'
    assert hist._forme_ibkr(' aapl ') == 'AAPL'


def test_le_role_historique_ne_partage_l_identifiant_d_aucun_autre():
    """IBKR refuse deux sessions de meme identifiant, et le refus ne nomme
    jamais sa cause : la collision se lirait comme une panne de cotations."""
    ids = ibkr_link.CLIENT_IDS
    assert 'historique' in ids, 'le scan doit avoir son propre role'
    assert len(set(ids.values())) == len(ids), 'deux roles partagent un identifiant'


#  ------------------------------------------------- l'absence reste absente

class _IbFactice:
    """Un IBKR qui ne connait que ce qu'on lui declare."""

    def __init__(self, connus):
        self.connus = connus

    def qualifyContracts(self, contrat):
        if contrat.symbol in self.connus:
            contrat.conId = 1
        return [contrat]

    def reqHistoricalData(self, contrat, **_):
        class _B:
            date, open, high, low, close, volume = '2026-08-20', 1.0, 2.0, 0.5, 1.5, 10
        return [_B()] if contrat.symbol in self.connus else []


class _PasserelleFactice:
    def __init__(self, ib):
        self._ib = ib

    def connect(self):
        return self._ib


def test_un_symbole_inconnu_est_absent_et_non_rempli():
    """Rendre une trame vide le ferait passer pour SERVI : le titre sortirait
    du scan en silence, et le repli n'irait jamais le chercher."""
    g = _PasserelleFactice(_IbFactice({'AAPL'}))
    frames, rapport = hist.fetch_universe_bars(['AAPL', 'INCONNU'], gateway=g)
    assert list(frames) == ['AAPL'], 'seul le symbole servi doit etre present'
    assert 'INCONNU' in rapport['inconnus']
    assert rapport['servis'] == 1


def test_la_trame_porte_la_forme_attendue_par_le_scan():
    """C'est cette forme — et elle seule — qui permet de mettre IBKR en tete
    de la chaine sans reecrire le scan."""
    g = _PasserelleFactice(_IbFactice({'AAPL'}))
    frames, _ = hist.fetch_universe_bars(['AAPL'], gateway=g)
    df = frames['AAPL']
    assert list(df.columns) == ['Open', 'High', 'Low', 'Close', 'Volume']
    assert len(df) == 1 and float(df['Close'].iloc[-1]) == 1.5


def test_un_univers_vide_ne_touche_pas_au_courtier():
    """Ouvrir une session pour ne rien demander couterait une connexion et un
    identifiant, sur un chemin ou il n'y a rien a mesurer."""
    class _Interdit:
        def connect(self):
            raise AssertionError('aucune connexion ne doit etre ouverte')
    frames, rapport = hist.fetch_universe_bars([], gateway=_Interdit())
    assert frames == {} and rapport['servis'] == 0


#  ------------------------------------------------ la provenance le dit

def test_la_provenance_du_scan_nomme_chaque_contributeur():
    """« ibkr+yfinance » n'est pas « ibkr ». Un repli invisible est un mensonge
    de source : l'ecran doit pouvoir dire qu'une part de l'univers a ete servie
    par le web."""
    import terminal
    src = open(terminal.__file__, encoding='utf-8').read()
    assert "scan_state['source_detail']" in src, (
        'le detail par contributeur doit exister — sans lui, un repli passant '
        'de 3 a 200 symboles se lirait exactement pareil')
    assert "'+'.join(contributeurs)" in src, (
        "la source doit etre composee, pas choisie : ecrire 'ibkr' quand "
        'yfinance a servi 18 titres masquerait le repli')


#  'univers' -> 'symboles_demandes' : le compte des symboles DEMANDÉS à la
#  file (533) n'est ni `universe_n` (517) ni `scanned_n` (513) — le nom
#  invitait à comparer trois dénominateurs différents.
@pytest.mark.parametrize('champ', ['ibkr', 'yfinance', 'stooq',
                                   'symboles_demandes'])
def test_le_detail_de_provenance_compte_les_trois_sources(champ):
    import terminal
    src = open(terminal.__file__, encoding='utf-8').read()
    deb = src.index("scan_state['source_detail']")
    assert "'%s'" % champ in src[deb:deb + 260], (
        'le detail doit compter %s — sinon la part servie par cette source '
        "n'est pas mesurable" % champ)
