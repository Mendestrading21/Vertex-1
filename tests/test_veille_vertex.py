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


def test_la_ci_fait_mesurer_les_gardiens_navigateur():
    with open(os.path.join(_ROOT, '.github', 'workflows', 'ci.yml'), encoding='utf-8') as f:
        ci = f.read()
    assert 'navigateur:' in ci and 'playwright install --with-deps chromium' in ci
    assert 'VERTEX_MESURE_BASE: http://127.0.0.1:5003' in ci
    assert 'run_qa_instance.py --port 5003' in ci
