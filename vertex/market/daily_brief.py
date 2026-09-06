"""vertex.market.daily_brief — le Brief Vertex quotidien (§15).

Types : PRE_MARKET / INTRADAY / CLOSE / WEEKLY (choisi par l'horloge de
New York). Composition déterministe depuis les DONNÉES RÉELLES : scan
(indices, secteurs, VIX, breadth), comité, actualités validées/sourcées
(news_pipeline), positions déclarées. Structure §15 en 10 sections,
150-280 mots + version compacte 8-12 lignes. AUCUN événement inventé :
si le flux d'actualités est vide, la section le DIT au lieu de broder.
"""
from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from vertex.market import news_pipeline
from vertex.market.news_impact import potential_impact


def brief_kind(now=None) -> str:
    ny = now or datetime.now(ZoneInfo('America/New_York'))
    if ny.weekday() >= 5:
        return 'WEEKLY'
    mins = ny.hour * 60 + ny.minute
    if mins < 570:            # avant 9h30
        return 'PRE_MARKET'
    if mins < 955:            # avant ~15h55
        return 'INTRADAY'
    return 'CLOSE'


def _idx(scan_state):
    idx = scan_state.get('indices') or []
    return {i.get('name'): i for i in idx if isinstance(i, dict)}


_REGIME_FR = {'TREND': 'TENDANCE', 'TREND_UP': 'TENDANCE HAUSSIÈRE',
              'TREND_DOWN': 'TENDANCE BAISSIÈRE', 'NEUTRAL': 'NEUTRE',
              'CHOP': 'SANS DIRECTION', 'DOWN': 'BAISSIER', 'UP': 'HAUSSIER',
              'UNKNOWN': 'INDÉTERMINÉ', 'RISK_ON': 'APPÉTIT POUR LE RISQUE',
              'RISK_OFF': 'AVERSION AU RISQUE', 'PANIC': 'PANIQUE',
              'MEAN_REVERSION': 'RETOUR À LA MOYENNE', 'TRANSITION': 'TRANSITION'}


def _regime_fr(code):
    return _REGIME_FR.get(str(code or '').upper(), code)


def _sans_actualite(fil_transmis: bool, news: dict) -> str:
    """Ce que le brief SAIT quand aucun événement ne sort du pipeline.

    ## La cause était inventée — mesure du 2026-09-06

    Le texte servi affirmait « Flux d'actualités hors ligne dans cet
    environnement ». Ce module ne mesure AUCUNE connectivité : il reçoit un
    `news_state` déjà collecté et compte ce qui en sort. « Hors ligne » est
    donc une cause fabriquée, et elle recouvrait trois états que l'invariant 5
    exige de garder distincts :

    * le fil n'a pas été transmis au brief (`news_state=None` — le cas de tous
      les appels qui ne branchent pas le fil, dont les bancs) ;
    * le fil a été transmis et il est VIDE (0 dépêche reçue : la boucle n'a pas
      encore tourné, ou aucune source n'a rien rendu) ;
    * des dépêches sont arrivées et le pipeline les a TOUTES écartées, parce
      qu'il leur manque un titre, un publieur ou une date — un défaut de
      collecte, pas une absence d'actualité, et le brief peut le nommer
      puisque `collect()` rend le compte par cause.

    Aucun des trois n'autorise à conclure sur la connexion : la phrase décrit
    ce qui est compté, et rien de plus.
    """
    fin = ' — aucun événement affiché plutôt qu’un événement inventé.'
    if not fil_transmis:
        return ('Fil d’actualités non transmis à ce brief : ni flux ni cause '
                'mesurés à cet endroit') + fin
    brut = int(news.get('raw_count') or 0)
    rejetes = int(news.get('rejected') or 0)
    if brut <= 0:
        return 'Fil d’actualités transmis mais vide : 0 dépêche reçue' + fin
    marque = 's' if brut > 1 else ''
    if rejetes >= brut:
        causes = {c: n for c, n in (news.get('rejets_par_cause') or {}).items() if n}
        detail = (' (' + ', '.join('%s : %d' % (c.replace('_', ' '), n)
                                   for c, n in sorted(causes.items())) + ')') if causes else ''
        return ('%d dépêche%s reçue%s, toutes écartées faute de titre, de '
                'publieur ou de date%s' % (brut, marque, marque, detail)) + fin
    return ('%d dépêche%s reçue%s, aucune retenue comme événement après '
            'validation et déduplication' % (brut, marque, marque)) + fin


def build_daily_brief(scan_state: dict, news_state: dict | None = None,
                      portfolio_syms: list[str] | None = None,
                      kind: str | None = None) -> dict:
    """Brief complet : sections, texte principal, compact, sources, méta."""
    kind = kind or brief_kind()
    # market = horloge de séance ; le contexte (régime/vix/breadth) vit dans
    # market_ctx — un simple `or` le masquait (régime 'n/d' permanent).
    m = {**(scan_state.get('market') or {}), **(scan_state.get('market_ctx') or {})}
    _b = m.get('breadth')
    if isinstance(_b, dict):                     # market_ctx.breadth = objet
        m = {**m, 'breadth': _b.get('above50', _b.get('above200'))}
    by = _idx(scan_state)
    sectors = scan_state.get('sectors') or []
    committee = (scan_state.get('committee') or {})
    counts = committee.get('counts') or {}
    source = scan_state.get('source') or 'aucune'
    demo = source == 'demo'
    syms = portfolio_syms or []

    fil_transmis = news_state is not None
    news = news_pipeline.collect(news_state or {}, syms) if fil_transmis \
        else {'events': [], 'rejected': 0, 'raw_count': 0}
    top_events = news['events'][:4]

    sections: list[tuple[str, str]] = []

    # 1. Situation générale
    regime = _regime_fr(m.get('spy_regime') or m.get('regime')) or 'n/d'
    roro = m.get('roro') or ''
    sections.append(('Situation générale',
                     f"Le marché évolue en régime {regime}{', climat ' + roro if roro else ''} ; "
                     + ('la participation large autorise une exposition normale.'
                        if (m.get('breadth') or 0) >= 55
                        else 'la participation étroite impose la sélectivité.')))
    # 2. Indices
    parts = []
    for name in ('S&P 500', 'Nasdaq', 'Dow Jones', 'Russell 2000'):
        e = by.get(name) or {}
        if e.get('change') is not None:
            parts.append(f"{name} {e['change']:+.1f} %")
    sections.append(('Indices', 'Sur la séance, ' + ' · '.join(parts) + '.' if parts
                     else 'Indices indisponibles dans le dernier scan.'))
    # 3. Taux et volatilité
    vix = m.get('vix')
    tnx = (by.get('Taux 10 ans') or {}).get('price')
    vol_txt = []
    if vix is not None:
        vol_txt.append(f"VIX à {vix}{' (' + m.get('vix_band', '') + ')' if m.get('vix_band') else ''}")
    if tnx is not None:
        vol_txt.append(f'taux 10 ans à {tnx}')
    sections.append(('Taux et volatilité', ' · '.join(vol_txt) + '.' if vol_txt
                     else 'Taux et volatilité non fournis par le scan.'))
    # 4. Actualité dominante — UNIQUEMENT des événements réels et sourcés
    if top_events:
        lead = top_events[0]
        imp = potential_impact(lead)
        sections.append(('Actualité dominante',
                         f"{lead.get('title_fr') or lead['title']} "
                         f"({lead['source']}, impact {imp['direction'].lower().replace('_', ' ')})."))
    else:
        #  CAUSE NON MESURÉE (corrigé) : voir `_sans_actualite`. Le brief dit
        #  ce qu'il COMPTE, il ne conclut pas sur la connexion.
        sections.append(('Actualité dominante', _sans_actualite(fil_transmis, news)))
    # 5-6. Secteurs
    if sectors and isinstance(sectors[0], dict):
        sections.append(('Secteurs leaders',
                         f"{sectors[0].get('sector', 'n/d')} mène la cote "
                         f"(score {sectors[0].get('avg_score', 'n/d')})."))
        if len(sectors) > 1:
            sections.append(('Secteurs faibles', f"{sectors[-1].get('sector', 'n/d')} reste à la traîne."))
    else:
        sections.append(('Secteurs', 'Rotation sectorielle non calculée par le dernier scan.'))
    # 7. Entreprises importantes (comité + événements entreprises réels)
    decisions = committee.get('decisions') or []
    prio = next((d for d in decisions if d.get('verdict') in ('ACHETER', 'RENFORCER')), None)
    ent = []
    if prio:
        ent.append(f"{prio.get('symbol')} ressort du comité — dossier complet à valider avant décision")
    for ev in top_events:
        if ev['category'] in ('RESULTATS', 'GUIDANCE') and ev.get('entities'):
            ent.append(f"{ev['entities'][0]} : {ev.get('title_fr') or ev['title']} ({ev['source']})")
            break
    _na, _nw = counts.get('ACHETER', 0), counts.get('ATTENDRE', 0)
    sections.append(('Entreprises', ' · '.join(ent) + '.' if ent
                     else f"Le comité retient {_na} dossier{'s' if _na != 1 else ''} d'achat "
                          f"et {_nw} en surveillance."))
    # 8. Options et volatilité
    board = scan_state.get('options_board') or []
    _nb = len(board)
    sections.append(('Options', f"{_nb} contrat{'s' if _nb != 1 else ''} au board Vertex Dynamic Options — "
                     'priorité aux CALL, R:R minimal de 2:1.' if board
                     else 'Board options vide — aucun contrat ne satisfait le R:R 2:1.'))
    # 9. Portefeuille
    _ns = len(syms)
    sections.append(('Portefeuille', f"{_ns} position{'s' if _ns != 1 else ''} déclarée{'s' if _ns != 1 else ''} sous surveillance."
                     if syms else 'Aucune position déclarée — surveillance générale du marché.'))
    # 10. Plan et discipline
    sections.append(('Plan et discipline',
                     'Aucune improvisation : le fondamental prime sur le technique, décision finale '
                     'unique, R:R minimum de 2:1 et stops dérivés du sous-jacent.'))

    text = ' '.join(f'{label} : {body}' for label, body in sections)
    words = len(text.split())
    compact = [f'{label} : {body}' for label, body in sections][:12]
    sources = sorted({ev['source'] for ev in top_events} | {source})

    return {
        'kind': kind,
        'sections': [{'label': l, 'text': b} for l, b in sections],
        'text': text,
        'word_count': words,
        'compact': compact[:12],
        'what_changed': [f"{ev.get('title_fr') or ev['title']} ({ev['source']})"
                         for ev in top_events[:3]],
        'watching': [s.get('symbol') for s in decisions[:3] if s.get('symbol')],
        'main_risk': ('Régime indéterminé — risque neuf bloqué'
                      if regime in ('UNKNOWN', 'INDÉTERMINÉ', 'n/d')
                      else f'Invalidation du régime {regime}'),
        'main_opportunity': (prio.get('symbol') if prio else None),
        'sources': sources,
        'news_rejected': news['rejected'],
        'as_of': scan_state.get('updated') or time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'generator': 'deterministic',
        'demo': demo,
    }


__all__ = ['build_daily_brief', 'brief_kind']
