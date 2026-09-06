"""vertex.ai.tool_registry — outils Claude AUTORISÉS (lecture) et INTERDITS (§28).

Claude lit, analyse, explique, propose. Il ne calcule pas les indicateurs
(les moteurs déterministes s'en chargent) et ne peut JAMAIS toucher un ordre :
tout outil interdit est rejeté à l'enregistrement, et les tests de sécurité
inspectent ce registre.

## ⚠ AUCUN CHEMIN DE PRODUCTION N'ENREGISTRE D'OUTIL — NON_IMPLÉMENTÉ

Mesuré le 2026-09-06, fermeture transitive des imports depuis les points
d'entrée réels (`terminal.py`, `vertex/runtime.py`, `vertex/app/factory.py`) :
ce module n'est atteint que par ses propres bancs. Aucun appelant n'instancie
`ToolRegistry`, et le seul `tools=` transmis à l'API Anthropic est le
`web_search` HÉBERGÉ côté fournisseur (`vertex/ai/web_provider.py`) — pas un
outil local de Vertex.

Autrement dit : Claude ne reçoit aujourd'hui AUCUN outil de ce dépôt. Il reçoit
un prompt et un paquet de données, et sa réponse est validée
(`response_validator`, qui rejette tout chiffre absent du paquet).

Il faut l'écrire ici, en tête, parce que la phrase ci-dessus — « tout outil
interdit est rejeté à l'enregistrement » — est vraie et pourtant trompeuse :
elle décrit une garde qui ne garde rien, faute de quelque chose à garder. Ce
n'est PAS un trou de sécurité (aucun outil exposé, donc aucun outil interdit
atteignable) ; c'est une capacité annoncée et non branchée, ce que l'invariant 8
demande de nommer.

Le module est conservé : il porte la liste blanche, la liste noire et la
distinction proposition/lecture, qui restent le contrat à respecter le jour où
des outils seront exposés. `ETAT` et `MANQUE` le disent à un programme autant
qu'à un lecteur.
"""
from __future__ import annotations

from typing import Callable

#: État réel de la capacité, lisible par un programme autant que par un humain.
ETAT = 'NON_IMPLÉMENTÉ'
#: Ce qui manque pour l'activer, mesuré et non supposé.
MANQUE = (
    'aucun appelant de production n’instancie ToolRegistry',
    'le seul `tools=` transmis à l’API est le web_search hébergé du fournisseur, '
    'pas un outil local de Vertex',
)

ALLOWED_TOOLS = (
    'get_strategy', 'get_market_regime', 'get_market_breadth', 'get_portfolio',
    'get_positions', 'get_stock_packet', 'get_fundamentals', 'get_catalysts',
    'get_technicals', 'get_sentiment', 'get_anomalies', 'get_institutional_context',
    'get_tradingview_signals', 'get_option_chain', 'get_vol_surface',
    'simulate_option', 'get_thesis', 'get_track_record', 'get_validation_results',
    'save_analysis_note', 'propose_alert', 'propose_rule',
)

FORBIDDEN_TOOLS = (
    'place_order', 'modify_order', 'cancel_order', 'exercise_option',
    'transfer_cash', 'change_constitution', 'activate_rule', 'delete_history',
    'submit_order', 'transmit_order', 'withdraw_cash', 'rebalance_automatically',
    'auto_execute',

    'auto_close_position', 'auto_rebalance', 'one_click_trade',
)

# Outils d'écriture tolérés : ils créent des PROPOSITIONS (statut PROPOSED),
# jamais des actions actives — la confirmation humaine reste obligatoire.
PROPOSAL_TOOLS = ('save_analysis_note', 'propose_alert', 'propose_rule')


class ForbiddenToolError(ValueError):
    """Tentative d'enregistrer un outil d'exécution — refusée par conception."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable, description: str = '') -> None:
        if name in FORBIDDEN_TOOLS:
            raise ForbiddenToolError(f'outil interdit: {name}')
        if name not in ALLOWED_TOOLS:
            raise ForbiddenToolError(f'outil hors liste blanche: {name}')
        self._tools[name] = fn

    def names(self) -> list[str]:
        return sorted(self._tools)

    def call(self, name: str, **kwargs):
        if name not in self._tools:
            raise KeyError(f'outil non enregistré: {name}')
        return self._tools[name](**kwargs)

    def specs(self) -> list[dict]:
        return [{'name': n, 'read_only': n not in PROPOSAL_TOOLS} for n in self.names()]
