# -*- coding: utf-8 -*-
"""P3 — le skill maître porte la procédure de maintenance de l'alimentation
(mission §16 A), liée depuis SKILL.md ; aucun second skill actif."""
import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SKILL = os.path.join(_ROOT, '.claude', 'skills', 'vertex-2-0')


def _lire(*p):
    with open(os.path.join(_SKILL, *p), encoding='utf-8') as f:
        return f.read()


def test_la_reference_existe_et_est_liee_depuis_le_skill_maitre():
    assert os.path.exists(os.path.join(_SKILL, 'references', 'data-feed-maintenance.md'))
    assert '(references/data-feed-maintenance.md)' in _lire('SKILL.md')


def test_la_procedure_impose_les_quatre_exigences_de_la_mission():
    doc = _lire('references', 'data-feed-maintenance.md')
    for sujet in ('VERTEX_DATA_COVERAGE.md', 'observed_at', 'received_at',
                  'ibkr_session.connecter', 'reqPositions', 'EN_COURS',
                  'test_sw_cache_scope', 'test_pass_terminal', 'VERTEX_TEST_IBKR_LIVE=1'):
        assert sujet in doc, sujet


def test_un_seul_skill_actif():
    skills = [d for d in os.listdir(os.path.join(_ROOT, '.claude', 'skills'))
              if os.path.isdir(os.path.join(_ROOT, '.claude', 'skills', d))]
    assert skills == ['vertex-2-0'], skills
