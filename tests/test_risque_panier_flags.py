# -*- coding: utf-8 -*-
"""Le risque du panier distingue un FAIT ARITHMÉTIQUE d'un RISQUE SUBI.

Mesure du 2026-09-06 (contrôle adverse du lot « valorisation ») : après la
correction du cap de poids — qui renormalise correctement à 100 % — le drapeau
`ligne_trop_grosse` s'arme pour TOUT panier de 2 à 6 lignes. C'est de
l'arithmétique : avec un plafond de 15 % par ligne, cinq lignes valent 20 %
chacune. Or `no_new_risk` valait `bool(flags)` : ce constat de taille bloquait
le « risque neuf » chez trois consommateurs (portfolio_guard, /api/command,
scanner/stages), c'est-à-dire interdisait d'AJOUTER une ligne exactement quand
ajouter est le remède à la concentration.

Le drapeau reste (il est vrai, l'écran doit le dire) ; il ne bloque plus. Seules
la corrélation moyenne et la concentration sectorielle arment `no_new_risk`.
"""
import math

from vertex.portfolio import legacy_basket_risk as r


def _detail(symbols, decalage=2.09):
    """Séries synthétiques déterministes (aucun réseau) : 60 clôtures par titre.

    MÊME amplitude et MÊME fréquence pour toutes les lignes — donc même
    volatilité, donc des poids inverse-vol ÉGAUX : le test porte alors sur les
    drapeaux, pas sur un déséquilibre fabriqué par la fixture. Seule la phase
    change (décalage de 120° par défaut → corrélations négatives, franchement
    sous le seuil de 0,65). Le secteur ne vient PAS de la fixture : le moteur le
    lit dans `vertex.market.sectors.SECTOR_MAP` — d'où des tickers réels, et un
    ticker inconnu tomberait dans « Autre » (100 % d'un seul seau, donc une
    concentration fabriquée par la fixture).
    """
    d = {}
    for i, s in enumerate(symbols):
        d[s] = {'series': {'close': [100 + 5 * math.sin(x / 4.0 + i * decalage) + x * 0.1
                                     for x in range(60)]},
                'sector': ''}
    return d


def test_le_panier_petit_signale_la_taille_sans_bloquer():
    """Trois lignes, trois secteurs distincts, corrélations faibles : le seul
    drapeau possible est structurel — le risque neuf reste autorisé."""
    syms = ['NVDA', 'JPM', 'XOM']          # Semiconducteurs · Finance · Energie
    out = r.build(syms, _detail(syms))
    assert out['n'] == 3
    assert len(out['sectors']) == 3, out['sectors']
    assert 'ligne_trop_grosse' in out['flags_structurels']
    assert out['flags_bloquants'] == [], out['flags_bloquants']
    assert out['no_new_risk'] is False, (
        'un panier de trois lignes ne peut pas tenir un plafond de 15 % : '
        'ce fait arithmétique ne doit pas interdire de diversifier')


def test_la_concentration_sectorielle_bloque_toujours():
    """La garde réelle n'est pas desserrée : deux titres sur trois dans le même
    secteur arment `no_new_risk`, et le drapeau structurel reste visible."""
    syms = ['NVDA', 'AMD', 'XOM']          # deux Semiconducteurs sur trois lignes
    out = r.build(syms, _detail(syms))
    assert 'concentration_sectorielle' in out['flags_bloquants']
    assert out['no_new_risk'] is True
    assert 'ligne_trop_grosse' in out['flags']          # toujours dit à l'écran


def test_les_deux_familles_restent_lisibles_dans_flags():
    """`flags` reste la liste complète : les consommateurs d'affichage
    (Portefeuille, Opportunités) ne perdent aucune information."""
    syms = ['NVDA', 'AMD', 'XOM']
    out = r.build(syms, _detail(syms))
    assert set(out['flags']) == set(out['flags_bloquants']) | set(out['flags_structurels'])


def test_un_grand_panier_garde_le_drapeau_bloquant():
    """Au-delà de 7 lignes le plafond de 15 % est atteignable : si une ligne le
    dépasse quand même, c'est une vraie surexposition — elle bloque."""
    syms = ['NVDA', 'AMD', 'MSFT', 'GOOGL', 'JPM', 'XOM', 'LLY', 'V']
    detail = _detail(syms)
    #  une ligne beaucoup moins volatile que les autres capte un poids > 15 %
    detail['NVDA']['series']['close'] = [100 + x * 0.01 for x in range(60)]
    out = r.build(syms, detail)
    assert out['n'] == 8
    if 'ligne_trop_grosse' in out['flags']:
        assert 'ligne_trop_grosse' in out['flags_bloquants'], (
            'sur un panier où le plafond est atteignable, une ligne trop grosse '
            'est une surexposition réelle, pas un artefact de taille')
        assert out['no_new_risk'] is True
