"""vertex/ui/pages/options_symbol_page.py — DOSSIER OPTIONS d'un titre (§18+).

La « machine d'analyse options » d'un sous-jacent : bascule Action|Options,
scorecard de chaîne (calls vs puts, qualité, PoP, IV), volatilité (structure
par terme, cône de mouvement, open interest par strike, smile), chaîne complète
du titre, scénarios × horizon, décote temps, sensibilité IV et stratégies
multi-jambes. Toutes les données viennent de /api/options/* et /scan (moteurs
purs, READONLY) — jamais un chiffre inventé, « — » honnête si absent.
"""
from __future__ import annotations

import re

from vertex.ui.shell import render_shell

_CONTENT = """
<div id="vx-osym-root" data-sym="%%SYM%%">

<!-- Hero : titre + bascule Action | Options -->
<section class="vx-card vx-card--premium" id="vx-osym-hero">
  <div class="vx-flex vx-wrap" style="gap:.7rem;align-items:center">
    <span class="vx-ticker" style="font-size:22px">%%SYM%%</span>
    <span class="vx-mono" id="vx-osym-spot" style="font-size:20px;font-weight:700">—</span>
    <span class="vx-badge" id="vx-osym-envbadge">chaîne d'options</span>
    <span class="vx-right vx-flex" style="gap:.4rem" role="group" aria-label="Mode d'analyse">
      <a class="vx-btn vx-btn-sm" href="/analysis/%%SYM%%">Dossier action</a>
      <span class="vx2-badge" data-state="option" title="Mode actuel : dossier options">Mode : options</span>
      <a class="vx-btn vx-btn-sm vx-btn-ghost" href="/options">Espace Options →</a>
    </span>
  </div>
  <div id="vx-osym-scorecard" class="vx-mt3">%%LOADING%%</div>
</section>

<!-- Verdict volatilité -->
<section class="vx-card vx-mt4" id="vx-osym-verdict">
  <div class="vx-card-header"><span class="vx-card-title">Les options de %%SYM%% sont-elles chères ?</span></div>
  <div data-body>%%LOADING%%</div>
</section>

<!-- Volatilité : 4 graphiques -->
<div class="vx-grid vx-mt4">
  <div class="vx-col-6" id="vx-osym-term"></div>
  <div class="vx-col-6" id="vx-osym-cone"></div>
</div>
<div class="vx-grid vx-mt4">
  <div class="vx-col-6" id="vx-osym-oi"></div>
  <div class="vx-col-6" id="vx-osym-smile"></div>
</div>

<!-- Max pain / murs d'OI : chaîne LARGE réelle IBKR (open interest par strike, avant filtrage board) -->
<section class="vx-card vx-mt4 vx-card--premium" id="vx-osym-maxpain">
  <div class="vx-card-header"><span class="vx-card-title">Aimant d'expiration — max pain &amp; murs d'open interest</span>
    <span class="vx-chart-question">Vers quel strike la mécanique de l'open interest tire-t-elle %%SYM%% à l'échéance ?</span>
    <span class="vx-actions vx-meta" id="vx-osym-mp-meta"></span></div>
  <div data-body>%%LOADING%%</div>
</section>

<!-- Grille de chaîne : strikes × échéances, greeks courtier IBKR -->
<div class="vx-mt4" id="vx-osym-grid"></div>

<!-- Surface de volatilité + skew (strikes × échéances) -->
<div class="vx-grid vx-mt4">
  <div class="vx-col-7" id="vx-osym-surface"></div>
  <div class="vx-col-5" id="vx-osym-skew"></div>
</div>

<!-- Chaîne complète du titre -->
<section class="vx-card vx-mt4 vx-card--premium" id="vx-osym-chain">
  <div class="vx-card-header"><span class="vx-card-title">Chaîne — contrats de %%SYM%% au tableau</span>
    <span class="vx-chart-question">Quels contrats le moteur juge-t-il exploitables ?</span>
    <span class="vx-actions vx-meta" id="vx-osym-chain-meta"></span></div>
  <div data-body>%%LOADING%%</div>
</section>

<!-- Scénarios du meilleur contrat -->
<section class="vx-card vx-mt4" id="vx-osym-scenarios">
  <div class="vx-card-header"><span class="vx-card-title">Scénarios — que vaudra le meilleur contrat ?</span>
    <span class="vx-actions vx-meta" id="vx-osym-sc-meta"></span></div>
  <div data-body>%%LOADING%%</div>
</section>
<div class="vx-grid vx-mt4">
  <div class="vx-col-6" id="vx-osym-decay"></div>
  <div class="vx-col-6" id="vx-osym-ivsens"></div>
</div>

<!-- Stratégies multi-jambes -->
<section class="vx-card vx-mt4" id="vx-osym-strats">
  <div class="vx-card-header"><span class="vx-card-title">Stratégies multi-jambes sur %%SYM%%</span>
    <span class="vx-chart-question">Payoff, probabilité de profit, gain/perte max — depuis le board réel, aucun ordre</span></div>
  <div data-body>%%LOADING%%</div>
</section>

</div>
"""

_LOADING = '<div class="vx-skeleton" style="height:64px"></div>'

_PAGE_JS = (
    '<script src="/static/vertex/js/charts/bar-chart.js" defer></script>'
    '<script src="/static/vertex/js/charts/heatmap.js" defer></script>'
    '<script src="/static/vertex/js/charts/option-chain-grid.js" defer></script>'
    '<script src="/static/vertex/js/charts/vol-surface.js" defer></script>'
    '<script src="/static/vertex/js/pages/options-symbol.js" defer></script>'
)


def render(sym: str) -> str:
    safe = re.sub(r'[^A-Z0-9.\-]', '', (sym or '').upper())[:12] or 'SPY'
    content = _CONTENT.replace('%%SYM%%', safe).replace('%%LOADING%%', _LOADING)
    return render_shell(
        title=f'{safe} · Options',
        active='options',
        space_label='Options',
        sub_label=safe,
        page_label='options:symbol',
        content=content,
        page_js=_PAGE_JS)


__all__ = ['render']
