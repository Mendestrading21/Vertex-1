# -*- coding: utf-8 -*-
"""Chien de garde local (tools/ops/veille_vertex.ps1) : présent, documenté,
et borné par ses garde-fous — jamais un processus qui écoute encore, jamais
un secret, journal borné. Non installé par ce dépôt (décision humaine)."""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, 'tools', 'ops', 'veille_vertex.ps1')


def _src():
    with open(_SCRIPT, encoding='utf-8') as f:
        return f.read()


def test_le_script_existe_et_ne_relance_que_sur_port_libre():
    s = _src()
    assert 'Invoke-RestMethod' in s and '/healthz' in s
    assert '-and -not $pid' in s, "relance seulement quand plus rien n'écoute"
    assert 'Stop-Process' not in s and 'taskkill' not in s, 'il ne tue jamais un processus'
    assert 'ne touche jamais TWS' in s


def test_aucun_secret_ni_installation_automatique():
    s = _src()
    assert 'VERTEX_CODE' not in s.replace("le code\nd'accès vit dans .env", '')
    assert 'VERTEX_SECRET' not in s
    assert 'schtasks' not in s, "l'installation en tâche planifiée est une décision humaine"
    assert re.search(r'-gt 2000', s), 'journal borné'


def test_le_runbook_le_documente():
    with open(os.path.join(_ROOT, 'docs', 'VERTEX_RUNBOOK.md'), encoding='utf-8') as f:
        rb = f.read()
    assert 'veille_vertex.ps1' in rb and 'décision humaine' in rb


def test_la_proposition_de_job_ci_navigateur_est_complete():
    """Le jeton de la session n'a pas le droit `workflow` : le job est livré
    en proposition (docs/propositions/), ci.yml reste inchangé jusqu'à ce que
    l'humain l'applique."""
    with open(os.path.join(_ROOT, 'docs', 'propositions', 'ci_navigateur_job.yml'), encoding='utf-8') as f:
        prop = f.read()
    assert 'navigateur:' in prop and 'playwright install --with-deps chromium' in prop
    assert 'VERTEX_MESURE_BASE: http://127.0.0.1:5003' in prop
    assert 'run_qa_instance.py --port 5003' in prop


def test_le_journal_est_relu_dans_l_encodage_ou_il_a_ete_ecrit():
    """La troncature ne doit pas corrompre le seul fichier lu après incident.

    Mesuré le 2026-09-06 : `Add-Content -Encoding utf8` écrit en UTF-8, mais
    `Get-Content` SANS `-Encoding` relit avec la page de codes ANSI de Windows.
    Au 2001e passage, la troncature relisait « démarrée » comme « dÃ©marrÃ©e »
    et le réécrivait ainsi. Le journal se corrompait tout seul, une fois, tard,
    et précisément sur le fichier qu'un humain vient consulter après une panne.
    """
    src = _src()
    assert 'Get-Content $Journal -Encoding utf8' in src, (
        'la relecture du journal est repassée en page de codes ANSI : la '
        'troncature réécrira des accents corrompus')
    #  Les DEUX sens doivent employer le même encodage, sinon le défaut revient
    #  par l'autre bout.
    assert src.count('-Encoding utf8') >= 3, src.count('-Encoding utf8')
