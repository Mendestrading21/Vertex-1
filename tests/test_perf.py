"""tests/test_perf.py — SKYLER LOT 72 : audit PERFORMANCE (programme 100 %).

Mesures réelles (Playwright, cache froid, serveur démo) : DCL 224-1021 ms
(max = premier lancement navigateur), poids total par page 515-1116 kB,
0 doublon de chargement, 0 ressource en erreur, 16 CSS (118 kB) + 8-17 JS
(336-435 kB) par page, vendor lightweight-charts (160 kB) chargé UNIQUEMENT
sur /analysis. Verdict : SAIN — lot documentaire.

Gardiens PROSPECTIFS (nés verts, dits) : ils ferment la classe « dérive
de poids » — un fichier JS/CSS première partie qui enfle au-delà du budget
ou le vendor qui fuit dans le shell casseront ces tests.
"""
import gzip
import os

#  CE QUI PART SUR LE RÉSEAU, mesuré le 2026-09-06 : jusqu'à ce jour, RIEN
#  n'était compressé. Le filtre de `app/factory.py` ne retenait que JSON et
#  HTML, et sortait d'emblée sur `direct_passthrough`, toujours vrai pour un
#  fichier servi en flux. Total première partie : 791 ko servis pour 265 ko
#  compressés — les deux tiers payés à chaque chargement froid.
#
#  Le budget d'OCTETS TRANSFÉRÉS est donc le vrai contrat réseau, et il est
#  ajouté ici. Mesuré après correction : le plus gros est options-intel.js à
#  19,5 ko compressés.
BUDGET_JS_GZIP_KB = 24
BUDGET_CSS_GZIP_KB = 32     # bundle.css : 155 ko servis, 27,9 ko compressés

#  Le budget d'octets BRUTS ne disparaît pas pour autant : il ne mesure plus le
#  réseau, il mesure le temps d'ANALYSE du moteur JavaScript, qui travaille sur
#  la source décompressée — décisif sur un téléphone.
#
#  Palier discuté, pas monté en douce : options-intel.js atteint 64,2 ko après
#  le lot Options, dont 9,2 ko (15 %) de commentaires portant les mesures qui
#  empêchent les défauts de revenir. Les effacer pour tenir un seuil serait
#  échanger une garantie durable contre 9 ko : le seuil monte à 72, et le
#  budget compressé, lui, se resserre.
BUDGET_JS_KB = 72      # plus gros actuel : options-intel.js 64,2 kB (89 %)
BUDGET_CSS_KB = 96     # plus gros actuel : vertex-2-0.css (~65 kB) — la COUCHE
                       # DE VÉRITÉ FINALE, qui absorbe les rapatriements des
                       # feuilles mortes (neon-glass.css 47 kB SUPPRIMÉE au
                       # lot 24 : le total CSS du dépôt baisse). Palier discuté
                       # et autorisé avec le lot 24, pas monté en douce ;
                       # prochain palier = même règle.


def _walk(ext, base='vertex/static'):
    for root, dirs, files in os.walk(base):
        for f in files:
            if f.endswith(ext):
                yield os.path.join(root, f)


def test_vendor_lightweight_charts_only_on_analysis():
    shell = open('vertex/ui/shell/__init__.py', encoding='utf-8').read()
    assert 'lightweight-charts' not in shell, (
        'le vendor 160 kB ne doit jamais être dans le shell (toutes pages)')
    ana = open('vertex/ui/pages/analysis_page.py', encoding='utf-8').read()
    assert 'lightweight-charts' in ana, (
        'le vendor doit rester chargé par la seule page qui en a besoin')


def test_first_party_js_within_budget():
    fat = [p for p in _walk('.js')
           if os.sep + 'vendor' + os.sep not in p
           and os.path.getsize(p) > BUDGET_JS_KB * 1024]
    assert not fat, f'JS première partie au-delà de {BUDGET_JS_KB} kB : {fat}'


def test_first_party_js_transfer_within_budget():
    """Ce que le navigateur TÉLÉCHARGE, pas ce que le disque contient."""
    gros = []
    for p in _walk('.js'):
        if os.sep + 'vendor' + os.sep in p:
            continue
        with open(p, 'rb') as f:
            n = len(gzip.compress(f.read(), 5))
        if n > BUDGET_JS_GZIP_KB * 1024:
            gros.append('%s : %.1f kB compressés' % (p, n / 1024))
    assert not gros, ('JS première partie au-delà de %d kB une fois compressé : %s'
                      % (BUDGET_JS_GZIP_KB, gros))


def test_css_transfer_within_budget():
    gros = []
    for p in _walk('.css'):
        with open(p, 'rb') as f:
            n = len(gzip.compress(f.read(), 5))
        if n > BUDGET_CSS_GZIP_KB * 1024:
            gros.append('%s : %.1f kB compressés' % (p, n / 1024))
    assert not gros, ('CSS au-delà de %d kB une fois compressé : %s'
                      % (BUDGET_CSS_GZIP_KB, gros))


def test_css_within_budget():
    fat = [p for p in _walk('.css')
           if os.path.getsize(p) > BUDGET_CSS_KB * 1024]
    assert not fat, f'CSS au-delà de {BUDGET_CSS_KB} kB : {fat}'
