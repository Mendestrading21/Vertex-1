# -*- coding: utf-8 -*-
"""Composants jamais alimentés (docs/VERTEX_DATA_COVERAGE.md §13 #9, reste).

- Aujourd'hui › « Ce qui a changé » lisait `scan.market_ctx.changes_since_prev` :
  le contexte BRUT du scan ne porte jamais de diff → carte « pas de base » à vie.
  Le propriétaire est `/api/market/context` (moteur + base persistée), qui dit
  désormais s'il a une base (`changes_base`) et de quand (`prev_as_of`).
- Portefeuille › Performance : la courbe d'équité lisait le stock
  `myTradesEquity`, alimenté par personne ; elle est dérivée des clôtures
  déclarées. La contribution attendait `t.plAbs`, jamais produit par `enrich`.
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(*parts):
    with open(os.path.join(_ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def test_le_contexte_marche_nomme_sa_base_de_comparaison():
    from vertex.engines import market_context as mc
    sans = mc.build({}, prev=None)
    assert sans['changes_base'] is False and sans['prev_as_of'] is None
    assert sans['changes_since_prev'] == []
    prev = {'as_of': '2026-09-05 22:00', 'dimensions': {}, 'regime': {'label': None}}
    avec = mc.build({}, prev=prev)
    assert avec['changes_base'] is True and avec['prev_as_of'] == '2026-09-05 22:00'


def test_ce_qui_a_change_lit_le_proprietaire_du_diff():
    src = _src('vertex', 'ui', 'pages', 'briefing.py')
    assert "VX.fetch('/api/market/context'" in src
    assert 'ctx.changes_base' in src and 'ctx.prev_as_of' in src
    assert "const m=((scan||{}).market_ctx)||{};\n  const ch=m.changes_since_prev;" not in src
    # les trois états restent distincts : pas de base / rien de notable / liste
    assert 'Pas de base de comparaison' in src and 'Aucun changement notable' in src


def test_l_equite_portefeuille_derive_des_clotures_declarees():
    src = _src('vertex', 'ui', 'pages', 'portfolio_page.py')
    assert 'function pfEquiteDerivee(' in src
    assert 'const eq=pfEquiteDerivee(closed);' in src
    assert "E().equity()" not in src, 'le stock myTradesEquity n’est alimenté par personne'
    assert 'Number(t.exit)-Number(t.cost)' in src


def test_le_brief_porte_le_diff_du_contexte_marche(monkeypatch):
    """`daily_changes` n'était produit par personne : le brief lit le diff de
    market_context (base persistée) — jamais inventé, vide sans base."""
    from vertex.ui.pages import briefing
    from vertex.services import persist
    scan = {'market': {'spy_regime': 'UP'}, 'market_ctx': {'vix': 25.0, 'vix_band': 'ELEVE'},
            'scan_ts_h': '2026-09-06T07:00:00Z', 'rows': [], 'indices': []}
    monkeypatch.setattr(persist, 'load_json', lambda name, default=None: None)
    assert briefing.build_editorial(scan)['changed_since_yesterday'] == []
    prev = {'as_of': '2026-09-05T22:00:00Z', 'regime': {'label': None},
            'dimensions': {'vix': {'value': 15.0, 'band': 'BAS'}}}
    monkeypatch.setattr(persist, 'load_json', lambda name, default=None: prev)
    chg = briefing.build_editorial(scan)['changed_since_yesterday']
    assert any('VIX' in c for c in chg), chg


def test_la_contribution_recoit_un_pl_absolu():
    src = _src('vertex', 'ui', 'pages', 'portfolio_page.py')
    assert 'const plAbs=value!==null?(value-invested):null;' in src
    assert 'pl,plAbs,delayed' in src
