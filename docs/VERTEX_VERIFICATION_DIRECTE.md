# VERTEX_VERIFICATION_DIRECTE — vérification de l'application en fonctionnement

Méthode : onze domaines contrôlés EN PARALLÈLE par onze agents indépendants, en lecture
seule, sur l'instance de travail (live, IBKR réel, seule `/healthz` publique) et sur
l'instance de contrôle QA (sans IBKR, sans code d'accès, même code source). Chaque
problème rapporté a ensuite été soumis à un agent chargé de le RÉFUTER : seuls ceux
qu'il n'a pas pu réfuter, en reproduisant la mesure, sont retenus ici.

Bilan : 114 agents, 103 contrôles adverses, **52 défauts confirmés**, 51 écartés.

## Domaines

| Domaine | Statut | Vérifications | Problèmes retenus |
|---|---|---|---|
| Frontière IBKR — données de marché uniquement (invariant n°3) | OK | 14 | 5 |
| Automatisations et registre des jobs (vertex/scheduler/registry.py, /a | PARTIEL | 8 | 7 |
| Honnêteté des verdicts et du cerveau Claude (instance QA 127.0.0.1:500 | PARTIEL | 11 | 7 |
| Actualités et publications officielles (fil /news-feed, communiqués BC | PARTIEL | 13 | 11 |
| options (board, chaîne, structures, verdict serveur) — instance QA htt | ECHEC | 9 | 13 |
| Diffusion temps réel (SSE) et fraîcheur servie | PARTIEL | 12 | 11 |
| Portefeuille déclaré, risque, cotations de positions (instance QA 127. | PARTIEL | 11 | 15 |
| Rendu de toutes les pages et cartes dans un vrai navigateur (Chromium/ | OK | 16 | 4 |
| Chaîne de données de marché — scan, régime, contexte, macro officielle | PARTIEL | 8 | 15 |
| Santé de l'instance de travail Vertex (live, IBKR réel via TWS, pid 32 | PARTIEL | 15 | 4 |
| Suite de tests et gardiens du contrat | PARTIEL | 12 | 11 |

## Défauts confirmés (52)

1. **[bloquant]** reproduit intégralement sur l'instance de contrôle (127.0.0.1:5003, ibkr_enabled=false, data_source=yfinance, DEMO_MODE=false : board RÉEL, pas de démo). 1) La clé lue n'existe pas dans le board réel. `vertex/options/legacy_engine
2. **[bloquant]** reproduit à l'identique, trois fois, avec arithmétique exacte. La mesure d'origine a été faite sur l'instance de contrôle avec le desk RÉEL du poste : `/api/portfolio/context` valorisait chaque contrat d'options en multipliant le nombre de CONTRATS par le prix du SOUS-JACENT, puis servait `valuation_note: null` — donc l'API affirmait avoir tout valorisé au marché. Les montants observés ne sont pas reproduits ici : ils décriraient le portefeuille de l'utilisateur, et ce document est public (invariant 5). Le banc qui fige la correction, `tests/test_portfolio_asset_mix.py`, rejoue la même propriété sur un desk synthétique et rond : 4 contrats MSFT à 6 000 $ engagés, 3 GOOG à 3 000 $, 10 actions KO cotées 50 $ — attendu 9 500, fabriqué 3 000.
3. **[bloquant]** et le défaut est plus large que celui annoncé. La ligne fautive est `vertex/engines/portfolio_context.py:86-92`, qui valorise TOUTE position sans distinguer le type d'actif. 1) BRANCHE « cote absente » — exactement la mesure annon
4. **[majeur]** reproduit à l'identique, et la cause racine est plus large que celle annoncée. 1) Code confirmé (numéros mesurés, léger décalage avec le rapport) `vertex/ui/pages/system_page.py:1424` : `if(v&&v!=='OK'&&v!=='LIVE')pannes.push(['So
5. **[majeur]** le problème est reproduit intégralement, et son impact est plus large qu'annoncé. 1) PREUVE CODE — les clés lues n'ont aucun producteur. `grep -rn "st_fund|fund_score|st_timing" --include=*.py --include=*.js --include=*.html .` (h
6. **[majeur]** reproduit intégralement, du flux brut jusqu'au DOM. Mes tentatives de réfutation échouent toutes. 1) La source publie bien la date, et le parseur ne la lit pas. Téléchargement direct du flux réel : `requests.get('https://www.snb.c
7. **[majeur]** j'ai tenté de le réfuter et j'ai échoué : la chaîne causale est reproduite de bout en bout, sur la même instance, le même processus, le même objet `scan_state` et le même instant. 1) LE PRODUCTEUR. `/api/market/summary` (feeds.py:
8. **[majeur]** et le rapport est plutôt SOUS-ESTIMÉ. J'ai tenté de le réfuter sur trois angles (comptage naïf trop strict ? attribution défendable comme « pertinence sectorielle » ? impact seulement décoratif ?) — aucun ne tient. 1) MÉCANISME (l
9. **[majeur]** sur l'instance QA 127.0.0.1:5003, en lecture seule. 1) La valeur EST bien en UTC (mesure à la source, pas une hypothèse) `.venv/Scripts/python.exe -c "import yfinance...; tk=yf.Ticker('NVDA'); print(repr(c.get('pubDate')))"` → pub
10. **[majeur]** le problème est reproduit et le motif de refus est bien faux. 1) Reproduction du refus (instance de contrôle 5003, demo=false) `curl -s http://127.0.0.1:5003/api/options/scanner/LEAPS` → sur les 5 meilleurs : NVDA CALL strike 230.
11. **[majeur]** CONTRADICTION REPRODUITE, MAIS DIAGNOSTIC INVERSÉ. Le rapport accuse environment.py ; la mesure montre que la carte fautive est /api/options/volatility. 1) Faits du rapport confirmés. `grep -rn "score_environment(" vertex/` -> opt
12. **[majeur]** non réfutable, et plus grave que rapporté. 1) La donnée est présente et c'est bien un pourcentage. `curl http://127.0.0.1:5003/api/options` (HTTP 200, demo=False) rend 96 contrats : `spread` présent 96/96, `spread_pct` présent 0/9
13. **[majeur]** Reproduit de bout en bout, je n'ai pas pu le refuter. 1. PAYLOAD. curl http://127.0.0.1:5003/api/options/chain/KHC, parse avec .venv/Scripts/python.exe : les 8 contrats portent `spread` (8/8 : 149.0, 177.6, None, 28.6, 17.1, 22.6,
14. **[majeur]** mais pas pour la raison annoncée. CE QUE JE RÉFUTE. Le sous-claim « contradiction avec l'en-tête du même fichier » est faux : l'en-tête (options-structure.js:26-35) est explicitement borné à cinq fonctions nommées (liqState, strat
15. **[majeur]** Le scanner déclare « indisponible » des valeurs que le board qu'il parcourt détient réellement. 1) Mesure servie (instance QA 5003) curl /api/options/scanner/LEAPS -> n=33, Counter({'OUT_OF_MANDATE': 33}), raisons [('delta hors ma
16. **[majeur]** et plus grave qu'annoncé. Le décalage de clés est confirmé sur l'application vivante, pas seulement dans les tests. PREUVE 1 — le producteur et les consommateurs ne parlent pas la même langue. `curl http://127.0.0.1:5003/api/optio
17. **[majeur]** reproduit intégralement, et le défaut est plus large que l'annonce. 1) La donnée porte bien la dégradation, côté serveur. `vertex/options/legacy_engine.py:329-337` : `stale = True` si l'IV a dû être RECALCULÉE depuis le prix (`_iv
18. **[majeur]** le problème est reproduit trois fois, et il contredit l'invariant 5 du contrat produit (« Absence, zéro, estimation… restent distincts »). 1) Preuve HTTP (instance QA 5003, lecture seule) POST http://127.0.0.1:5003/api/portfolio/t
19. **[majeur]** et de surcroit atteignable par les chemins natifs de l'application (pas seulement par un localStorage bricole par le QA). 1) CODE — vertex/ui/pages/portfolio_page.py:1121-1123 const e=+r.entry_spot,s=+r.stop,t=+r.tgt; if([e,s,t].e
20. **[majeur]** le problème est reproduit intégralement, à trois niveaux indépendants. 1) Unité — `_cap_weights` ne somme pas à 1 sous 7 lignes Commande : `.venv/Scripts/python.exe -c "from vertex.portfolio.legacy_basket_risk import _cap_weights;
21. **[majeur]** dans sa conclusion, mais le mécanisme et la localisation annoncés sont partiellement faux. Le défaut réel est PLUS LARGE que rapporté. == 1. Rendu reproduit à l'identique (instance QA 5003) == Navigation http://127.0.0.1:5003/port
22. **[majeur]** et ma tentative de réfutation échoue sur le point central. 1) Mesure API (instance de contrôle 5003, POST /api/pos-quotes) : {"NVDA|2026-10-23|245|C":{"delayed":true,"mark":6.2,"mark_source":"DERNIER_ECHANGE","spot":230.36,"spread
23. **[majeur]** le problème est réel, reproduit de bout en bout, et sa conséquence mesurée dépasse celle annoncée. Toutes les mesures ci-dessous sont faites sur l'instance de contrôle 5003 (l'instance live 5002 n'a jamais été sollicitée au-delà d
24. **[majeur]** et confirmé au-delà de ce qui était annoncé. J'ai cherché à réfuter ; je n'y suis pas parvenu. 1) FORMULE — vertex/portfolio/risk_engine.py:28-33 `stock_weights = {s: w for s, w in weights.items() if s != '_CASH'}` puis `hhi = rou
25. **[majeur]** La tentative de réfutation échoue : la cause fausse est bien affichée alors que la socket IBKR est vivante. 1) CODE CONFIRMÉ VERBATIM — vertex/ui/pages/portfolio_page.py:382 `${tile('P&L latent',pl!==null?((pl>=0?'+':'')+VX.fmt.pr
26. **[majeur]** sur l'instance de contrôle, API + page rendue. Je n'ai pas pu le réfuter ; j'ai même trouvé une preuve plus dure que celle avancée. Le HHI du compartiment actions rendait 0,0 sur un compartiment composé d'UN SEUL titre, et la jauge lisait « bien dispersé » en bande verte sur une concentration maximale. Comme ci-dessus, les montants du desk réel ne sont pas reproduits : `tests/test_risk_engine.py` rejoue la propriété sur 10 actions à 50 $ et 20 000 $ de cash — HHI du compartiment 1,0, part investie 2,44 %, et l'ancien chiffre conservé sous son vrai nom `hhi_total_equity`.
27. **[majeur]** et pire que ce qui est décrit. J'ai tenté de le réfuter sur quatre angles (voir « tentatives de réfutation ») ; aucun ne tient. 1) LE PAYLOAD SERVEUR — asymétrie confirmée sur l'instance de contrôle Commande : curl -s -X POST http
28. **[majeur]** mais la cause avancée par le contrôle automatisé est FAUSSE, et le défaut réel est plus large que « mineur ». 1) Reproduction du symptôme (instance de contrôle 5003) Commande : curl -s -X POST http://127.0.0.1:5003/api/portfolio/t
29. **[majeur]** et plus large que decrit. Je remonte la gravite de « mineur » a « majeur ». 1) Format reellement stocke par le desk (lecture seule de desk_data.json, .venv python) : 3 trades, dont 2 options `type=CALL, right='C', exp='2027.01.15'
30. **[majeur]** J'ai tenté de réfuter et je n'y suis pas parvenu : la mesure se reproduit, le chemin est atteignable en scan réel, et le comportement contredit un invariant absolu du produit. 1) REPRODUCTION EXACTE (commande + sortie) `.venv/Scri
31. **[majeur]** et plus grave que rapporte. Cause : `_download_universe` publie la provenance de facon INCONDITIONNELLE (terminal.py:440-466) alors qu'il a deux appelants — le scan (terminal.py:528, univers complet) et le backtest d'edge (termina
32. **[majeur]** sur l'instance de contrôle 5003, et le problème est plus grave que l'annonce « mineur ». Je n'ai pas réussi à le réfuter. 1) LE PAYLOAD CONTIENT BIEN LA VRAIE SÉRIE S&P 500, IGNORÉE `python -c "json.loads(urlopen('http://127.0.0.1
33. **[majeur]** y compris la contre-épreuve. J'ai cherché à réfuter et je n'y suis pas parvenu. 1) Le défaut de source est exact, et il est double : - tests/test_qa_degrade.py:49 → `BASE = 'http://127.0.0.1:5002'` (constante nue). - Cause racine 
34. **[majeur]** mais le mécanisme avancé par le rapport est FAUX — et le vrai est plus grave. 1) Réfutation partielle du rapport. « Les compteurs par source se rapportent au dernier lot téléchargé » est inexact. `_download_universe` accumule sur 
35. **[mineur]** je n'ai pas réussi à le réfuter. 1) Le littéral est bien inconditionnel. `vertex/app/routes/positions_api.py:95-96` (`return jsonify(startup_position_report(_desk_blob(), ibkr_online=False))`) et `:113-114` (`reconcile(local, [], 
36. **[mineur]** mais la gravité annoncée est surévaluée : le mécanisme est bien celui décrit, aucune donnée n'est pour autant inventée et la configuration de travail de l'utilisateur n'est pas touchée. Ce que j'ai mesuré moi-même : 1. Point de dé
37. **[mineur]** J'ai tenté de réfuter et je n'y suis pas parvenu : le mécanisme est reproductible, mais son impact est LATENT (aucune fausseté visible dans l'application telle qu'elle tourne aujourd'hui). CE QUI EST SAIN — MESURÉ SUR L'INSTANCE Q
38. **[mineur]** mais pas pour la raison annoncee — et l'impact reel est plus etroit que decrit. CE QUE J'AI MESURE MOI-MEME 1) Aucun ordonnanceur n'existe. `ls vertex/scheduler/` -> `__init__.py`, `registry.py` seulement. `grep -rn "interval_s" -
39. **[mineur]** et le défaut est plus large que rapporté. J'ai tenté de le réfuter sur trois axes (consommateur réel, chiffres inventés, spécificité NVDA) — aucun n'a tenu. 1) Incohérence Central — structurelle, 5/5 symboles réels. `curl -s http:
40. **[mineur]** intégralement sur l'instance de contrôle (5003), code + API + DOM. 1) API (source du décompte) — `curl http://127.0.0.1:5003/api/macro/officiel` puis comptage : total communiques = 24 ; erreurs = {} ; par source = Counter({'BCE': 
41. **[mineur]** je n'ai pas pu réfuter. Confirmé par lecture de code, sonde directe et appel de la vraie route HTTP. 1) Code. Le motif existe à DEUX endroits, pas un seul (l'audit en a manqué un) : - vertex/strategy/decision_packet.py:114 → 'cata
42. **[mineur]** reproduit intégralement, et le problème est plus large que rapporté. 1) L'item exact est reproduit. `curl -s http://127.0.0.1:5003/news-feed` sert littéralement : {"title":"Oil Surged, Then Slumped, Year to Date in 2026. Here&#39;
43. **[mineur]** reproduit sur les trois axes, plus un facteur aggravant non relevé par le rapport. 1) Zéro tampon dans la carte (mesuré, pas déduit) - `awk 'NR>=1936 && NR<=1990' vertex/ui/pages/briefing.py | grep -c "updateIndicator"` -> `0`. - 
44. **[mineur]** sur l'instance de contrôle 5003 (lecture seule, aucune modification). 1) Le board porte bien bid ET ask partout. `curl /api/options` -> 96 lignes ; script de comptage : "board rows 96 / bid&ask present: 96 / 96". Le contrat exact 
45. **[mineur]** et le défaut est plus large que ne le dit le rapport. 1) Mesure navigateur sur l'instance QA (127.0.0.1:5003), lecture DOM après chargement complet : - /options?view=structure&sym=NVDA → `#vx-opt-ctx-fresh`.innerText = « Aucune do
46. **[mineur]** et pire que rapporté — mais dans l'outillage de preuve, pas dans l'application. REPRODUCTION 1 (forme de l'endpoint, blueprint isolé, aucune des deux instances touchée) : python -c "from flask import Flask; from vertex.app.routes.
47. **[mineur]** au niveau de la charge servie, mais l'impact annoncé est FAUX. Le rapport mérite d'être retenu en mineur, pas en majeur. 1) Le mécanisme est exact. `vertex/engines/market_lens.py:19-22` : `def climate(market): if not market: retur
48. **[mineur]** mais gravité annoncée surévaluée. Je confirme la divergence arithmétique et j'en trouve une aggravation ET une atténuation. REPRODUCTION (.venv/Scripts/python.exe, mc={'spy_regime':'TREND','roro':'RISK-ON','vix_band':'stress'}) : 
49. **[mineur]** de bout en bout, et le problème est PLUS large que rapporté (12 entrées BNS concernées, pas 4 — seules 4 sont visibles car le rendu tronque à `liste.slice(0,16)`). 1) Preuve navigateur (instance de contrôle 5003, /markets?view=mac
50. **[mineur]** avec une correction importante sur une des preuves avancées. 1) L'absence de verdict de fraîcheur est confirmée par mesure. `curl http://127.0.0.1:5003/api/macro/officiel` → chaque série porte exactement 16 clés : error, fournisse
51. **[mineur]** mais plus étroit et mieux argumenté que l'énoncé initial. 1) Fait mesuré (DOM réel, instance QA 5003, vue Macro) Navigation http://127.0.0.1:5003/markets?view=macro puis exécution DOM : {"url":"http://127.0.0.1:5003/markets?view=m
52. **[mineur]** mais gravité surévaluée. Correction de localisation : la ligne est tests/test_journal_system_07.py:95, pas :98. 1) L'assertion est bien tautologique. Balayage AST du fichier (.venv/Scripts/python.exe, module ast) : « TAUTO test_jo

## Ce que la vérification a confirmé comme SAIN

- Frontière IBKR : preuve sur socket réelle (TWS ouvert, rôle dédié) — aucune position,
  aucune valeur de compte, aucun ordre ; 42 méthodes sensibles verrouillées sur 133,
  zéro méthode sensible encore appelable ; 16 méthodes réellement appelées, toutes de marché.
- Rendu : 59 pages et sous-vues, aucune erreur console, aucune exception, aucune requête
  en échec, aucun squelette perpétuel ; 630 clics sans incident.
- Instance de travail : scans complets (513/517), `ibkr_live: true`, aucun traceback.

