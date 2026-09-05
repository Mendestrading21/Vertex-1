"""Gardiens finaux Strategy OS (§38) — noms canoniques exigés par le cahier.

Certains invariants sont déjà testés sous d'autres noms ; ces tests portent
les noms canoniques et vérifient l'invariant directement (pas de simple alias).
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_EXECUTION_NAMES = (
    'place_order', 'placeOrder', 'submit_order', 'submitOrder', 'transmit_order',
    'modify_order', 'cancel_order', 'exercise_option', 'transfer_cash',
    'withdraw_cash', 'rebalance_automatically', 'auto_execute', 'whatIfOrder',
    'bracketOrder', 'MarketOrder(', 'LimitOrder(',
)


def _python_sources():
    out = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT,
                         capture_output=True, text=True, encoding='utf-8', check=True).stdout
    for rel in out.splitlines():
        p = ROOT / rel
        if p.is_file() and 'tests' not in Path(rel).parts:
            yield p


# Ces deux fichiers citent les noms pour les refuser ou les auditer ; ils ne
# les appellent jamais. Le test comportemental IBKR reste chargé de vérifier
# que le scanner lui-même ne confond pas une chaîne avec un appel AST.
DENY_LIST_FILES = (
    'vertex/ai/tool_registry.py',
    '.claude/skills/vertex-2-0/scripts/check_ibkr_boundary.py',
)


def test_no_order_execution_path():
    """AUCUN chemin d'exécution d'ordre dans tout le code applicatif."""
    offenders = []
    for path in _python_sources():
        rel = path.relative_to(ROOT).as_posix()  # forward-slash sur tout OS (Windows inclus)
        if rel in DENY_LIST_FILES:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        for needle in FORBIDDEN_EXECUTION_NAMES:
            for i, line in enumerate(text.splitlines(), 1):
                if needle in line and not line.strip().startswith('#') \
                        and 'interdit' not in line and 'FORBIDDEN' not in line \
                        and 'forbidden' not in line:
                    offenders.append(f'{rel}:{i}: {needle}')
    assert not offenders, 'chemins d’exécution détectés:\n' + '\n'.join(offenders[:20])


def test_ibkr_readonly():
    """Toute connexion IBKR du dépôt force readonly=True."""
    connect_sites = []
    for path in _python_sources():
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
        for i, line in enumerate(lines, 1):
            #  Depuis la session « marché seulement », la porte canonique est
            #  `ibkr_session.connecter(` ; `IB.connect(` n'a plus de site.
            if ('.connect(' in line or '.connecter(' in line) and ('clientId' in line or 'client_id' in line):
                window = ' '.join(lines[i - 1:i + 2])  # l'appel peut être multi-lignes
                connect_sites.append((path, i, window))
    for path, i, window in connect_sites:
        assert 'readonly=True' in window, \
            f'{path.relative_to(ROOT)}:{i}: connexion IBKR sans readonly=True'
    assert connect_sites, 'aucun site de connexion IBKR trouvé (test devenu aveugle ?)'


def test_all_sync_keys_match():
    """Le contrat de sync desk vit dans le JS SERVI (règle critique n°1).

    vx_kit.py et journal.py — anciennes « sources de vérité » jamais servies —
    sont retirés (lot 37). La liste servie est celle de vx-entities.js ;
    l'égalité avec le repli inline de system_page est gardée par le lot 381,
    l'ancre littérale complète par test_production.
    """
    ent = (ROOT / 'vertex/static/vertex/js/vx-entities.js').read_text(
        encoding='utf-8', errors='ignore')
    m3 = re.search(r"DESK_KEYS\s*=\s*\[([^\]]+)\]", ent)
    assert m3, 'DESK_KEYS absent de vx-entities.js'
    ent_keys = set(re.findall(r"'([^']+)'", m3.group(1)))
    assert 'vxWatchlist' in ent_keys and 'vxAlerts' in ent_keys




def test_no_temporary_migration_adapters_left():
    """Les adaptateurs temporaires de migration ont tous disparu."""
    for path in _python_sources():
        text = path.read_text(encoding='utf-8', errors='ignore')
        assert 'DeprecationWarning' not in text or 'adapter' not in text.lower(), \
            f'{path}: adaptateur de migration résiduel'
