# Skills de design installés (lecture, pas autorité)

Ces quatre skills sont des **expertises consultatives** utilisées pour la refonte
des dashboards. L'autorité unique reste `.claude/skills/vertex-2-0/SKILL.md`
(CLAUDE.md, « aucun second skill actif ») : c'est pourquoi ils vivent dans
`.claude/design-skills/` et non dans `.claude/skills/` — ils ne sont pas chargés
automatiquement ; Claude les lit explicitement. Aucun hook n'a été activé.

| Skill | Origine | Commit / version | Licence | Fichiers conservés |
|---|---|---|---|---|
| kpi-dashboard-design | https://github.com/wshobson/agents — `plugins/business-analytics/skills/kpi-dashboard-design` | `a30778f` (2026-09-01) | MIT (Seth Hobson) | SKILL.md, references/details.md, LICENSE |
| interface-design | https://github.com/Dammyjay93/interface-design — `.claude/skills/interface-design` + `reference/` | `2f9be32` (2026-06-20) | MIT | SKILL.md, agents/openai.yaml, reference/system-template.md, reference/examples/*, LICENSE |
| ui-ux-pro-max | https://github.com/nextlevelbuilder/ui-ux-pro-max-skill — `.claude/skills/ui-ux-pro-max` | `f3ac195` (2026-09-03), skill.json 2.13.0 | MIT | SKILL.md, data/*.csv, references/*.md, scripts/*.py (tests exclus), LICENSE |
| impeccable | https://github.com/pbakaus/impeccable — `plugin/skills/impeccable` (fichiers distribués, pas `skill/SKILL.src.md`) | `4bee58d` (2026-09-05), skill 4.2.0, ENGINE_VERSION 0.1.1 | Apache 2.0 | SKILL.md, reference/*.md, scripts/ (lanceur inerte), LICENSE, NOTICE.md |

## Décisions d'installation

- Seul le dossier `kpi-dashboard-design` a été extrait de `wshobson/agents`
  (checkout sparse) ; le catalogue complet n'est pas installé.
- `impeccable` : le manifeste `plugin/hooks/hooks.json` (PostToolUse/Stop)
  n'est **pas** installé. Le lanceur `scripts/impeccable` télécharge et exécute
  un binaire moteur au premier appel : il n'a pas été exécuté. Les commandes
  `critique`, `audit`, `layout`, `adapt`, `clarify`, `harden` et `polish` sont
  appliquées par lecture de leurs références (`reference/*.md`), ce qui est une
  lecture méthodologique et non une invocation native du moteur.
- `ui-ux-pro-max` : le moteur de recherche local fonctionne sans dépendance
  (`python .claude/design-skills/ui-ux-pro-max/scripts/search.py "<requête>" --domain ux`).
  Les stacks proposées (React, Next, Vue…) ne correspondent pas à Vertex
  (Flask + HTML rendu côté serveur + JS vanilla + CSS custom) ; seules les
  règles génériques UX/tables/charts/accessibilité sont retenues.
- `interface-design` : la mémoire de projet existe déjà dans
  `.interface-design/system.md` ; elle n'a pas été régénérée.
- Aucun réglage global, permission ou hook modifié.
