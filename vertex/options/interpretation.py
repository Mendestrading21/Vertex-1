"""vertex.options.interpretation — verdicts de graphiques options (§6/§18).

Transforme les mesures pures (volatilité, expected move, event risk) en
interprétations canoniques (contrat vertex.visualization.schemas). Chaque
fonction répond à UNE question et rend FAVORABLE/NEUTRE/DEFAVORABLE/
BLOQUANT/INCONNU avec ses preuves. Aucun ordre, lecture seule.
"""
from __future__ import annotations

from vertex.visualization.schemas import (
    interpretation, unknown, ST_FAVORABLE, ST_NEUTRE, ST_DEFAVORABLE,
    ST_INCONNU,
)
from . import volatility as vol
from . import event_risk as ev

_VOL_LIMITS = [
    'IV rank/percentile dépendent de la profondeur d\'historique disponible',
    'vol réalisée close-to-close : ne capture pas le risque intra-journalier',
]

#  UN SEUL propriétaire de la phrase de prime IV/RV : les deux chemins (verdict
#  classable et cherté non classable) la formulent ici, sinon ils redivergent.
#  Mais la phrase a DEUX moitiés de nature différente — une MESURE et sa
#  QUALIFICATION — et les deux chemins n'ont pas droit à la même.
def _mesure_prime(prem):
    """La prime IV/RV telle qu'elle est MESURÉE, sans aucune qualification.

    Ne dit QUE ce que le calcul rend : le sens de l'écart et sa taille. Aucun
    mot de cherté, aucun verdict — c'est la forme servie par le chemin où
    précisément aucun verdict de cherté n'est possible."""
    if prem is None:
        return None
    return ('IV au-dessus de la vol réalisée : prime +%.2f' % prem if prem > 0
            else 'IV sous la vol réalisée : prime %.2f' % prem)


def _phrase_prime(prem):
    """La mesure ET sa qualification de cherté — réservée au chemin CLASSABLE.

    RÉGRESSION INTRODUITE AU TOUR 2, MESURÉE ET CORRIGÉE ICI (2026-09-06).
    En donnant un propriétaire unique à la phrase, la queue normative
    (« premium payé cher » / « premium relativement bon marché ») a été
    transportée telle quelle sur le chemin INCONNU. Mesure de l'appel
    (IV 0,415, 21 clôtures, vol réalisée 0,2237, prime +0,1913) :

      dominant_reading  « Cherté non classable : ni IV rank ni IV percentile
                          ne sont mesurés ici… »
      negative_evidence ['IV au-dessus de la vol réalisée (prime +0.19) :
                          premium payé cher']

    La carte niait tout verdict de cherté dans sa lecture dominante et en
    rendait un dans son unique preuve. La prime, elle, est bien mesurée
    (aucun chiffre inventé) : c'est la QUALIFICATION qui était de trop, parce
    que « cher » se lit sur le rank — la grandeur justement absente.

    La queue reste ici, sur le chemin où le rank la porte."""
    mesure = _mesure_prime(prem)
    if mesure is None:
        return None
    return mesure + (' — premium payé cher' if prem > 0
                     else ' — premium relativement bon marché')


def interpret_volatility(symbol, current_iv, iv_low, iv_high, iv_history=None,
                         closes=None, source='', as_of=None):
    """« Les options sont-elles chères ou bon marché ici ? »"""
    cid = 'options.volatility'
    q = 'Les options de %s sont-elles chères ou bon marché ?' % symbol
    rank = vol.iv_rank(current_iv, iv_low, iv_high)
    pctl = vol.iv_percentile(current_iv, iv_history) if iv_history else None
    rv = vol.realized_vol(closes) if closes else None
    prem = vol.iv_rv_premium(current_iv, rv)
    regime = vol.vol_regime(rank)
    if rank is None and pctl is None:
        #  RÉGRESSION CORRIGÉE (mesure du 2026-09-06) : la sortie anticipée
        #  jetait la prime IV/RV AVANT de l'avoir regardée. Sur NVDA
        #  (IV médiane 41,5 %, 21 clôtures réelles du scan, vol réalisée
        #  44,7 %) l'appel rendait positive_evidence [] et negative_evidence []
        #  — la SEULE grandeur réellement mesurée de la carte disparaissait de
        #  l'écran parce qu'une AUTRE grandeur (l'IV rank, sans historique d'IV
        #  câblé) manquait. Le verdict de cherté reste INCONNU (il se lit sur le
        #  rank, pas sur la prime) ; la mesure, elle, est servie et nommée.
        #  La MESURE NUE, jamais sa qualification : cette carte déclare qu'aucun
        #  verdict de cherté n'est possible ici (cf. `_phrase_prime`).
        phrase = _mesure_prime(prem)
        if phrase is None:
            return unknown(cid, q, reason='IV rank/percentile indisponibles',
                           source=source, limitations=_VOL_LIMITS)
        return interpretation(
            cid, q,
            'Cherté non classable : ni IV rank ni IV percentile ne sont mesurés '
            'ici. Seule la prime IV/RV, calculée sur les clôtures réelles, est '
            'disponible.',
            ST_INCONNU,
            confidence=None,                     # non mesurable : jamais gonflée
            positive_evidence=([phrase] if prem <= 0 else []),
            negative_evidence=([phrase] if prem > 0 else []),
            uncertainties=['IV rank/percentile indisponibles — aucune série d\'IV '
                           'historique n\'est câblée : le verdict cher/bon marché '
                           'reste inconnu'],
            strategy_impact='Aucun verdict de cherté : la prime IV/RV est la seule '
                            'mesure disponible, elle ne suffit pas à trancher seule.',
            source=source, as_of=as_of, limitations=_VOL_LIMITS)
    pos, neg, unc = [], [], []
    ref = rank if rank is not None else pctl
    label = 'IV rank' if rank is not None else 'IV percentile'
    if regime:
        pos.append('Régime de volatilité : %s (%s %.0f)' % (regime, label, ref))
    phrase = _phrase_prime(prem)
    if phrase is not None:
        (neg if prem > 0 else pos).append(phrase)
    else:
        unc.append('Vol réalisée indisponible — prime IV/RV non calculable')
    # Verdict pour un ACHETEUR d'options (le desk n'achète que) : IV basse = favorable.
    if ref >= 70:
        status, reading = ST_DEFAVORABLE, 'Volatilité élevée : acheter des primes coûte cher, risque de crush.'
    elif ref <= 35:
        status, reading = ST_FAVORABLE, 'Volatilité basse : primes relativement abordables pour un achat.'
    else:
        status, reading = ST_NEUTRE, 'Volatilité médiane : ni aubaine ni piège sur le prix des primes.'
    conf = 0.6 if (rank is not None and prem is not None) else 0.4
    return interpretation(
        cid, q, reading, status, confidence=conf,
        positive_evidence=pos, negative_evidence=neg, uncertainties=unc,
        strategy_impact=('Favorise l\'achat de convexité.' if status == ST_FAVORABLE
                         else 'Privilégier des structures moins exposées au vega / attendre une détente.'
                         if status == ST_DEFAVORABLE else 'Sélection au cas par cas.'),
        source=source, as_of=as_of, limitations=_VOL_LIMITS)


def interpret_event_risk(symbol, earnings_in_days, ex_dividend_days, right, dte,
                         source='', as_of=None):
    """« Un événement menace-t-il cette position d'ici l'échéance ? »"""
    cid = 'options.event_risk'
    q = 'Un événement menace-t-il l\'option %s d\'ici l\'échéance ?' % symbol
    c = ev.combined(earnings_in_days, ex_dividend_days, right, dte)
    lvl = c['level']
    notes = c['notes']
    if lvl == ev.RISK_UNKNOWN:
        return unknown(cid, q, reason='Dates d\'événement inconnues',
                       source=source)
    pos, neg = [], []
    if lvl in (ev.RISK_HIGH, ev.RISK_MODERATE):
        neg.extend(notes)
    else:
        pos.extend(notes or ['Aucun événement majeur identifié sur la fenêtre.'])
    status = {ev.RISK_HIGH: ST_DEFAVORABLE, ev.RISK_MODERATE: ST_DEFAVORABLE,
              ev.RISK_LOW: ST_NEUTRE, ev.RISK_NONE: ST_FAVORABLE}[lvl]
    reading = {
        ev.RISK_HIGH: 'Événement imminent : risque de crush/gap élevé sur la prime.',
        ev.RISK_MODERATE: 'Événement dans la fenêtre : exposition à surveiller.',
        ev.RISK_LOW: 'Événement lointain : impact limité.',
        ev.RISK_NONE: 'Aucun événement porté d\'ici l\'échéance.',
    }[lvl]
    return interpretation(
        cid, q, reading, status, confidence=0.55,
        positive_evidence=pos, negative_evidence=neg,
        uncertainties=([] if notes else ['Vérifier les dates officielles avant décision']),
        strategy_impact=('Dimensionner en conscience du crush / envisager une échéance qui évite l\'événement.'
                         if status == ST_DEFAVORABLE else 'Pas de contrainte d\'événement particulière.'),
        source=source, as_of=as_of)


__all__ = ['interpret_volatility', 'interpret_event_risk']
