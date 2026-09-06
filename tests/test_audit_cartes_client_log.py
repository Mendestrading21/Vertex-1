"""La couche de PREUVE doit distinguer un zéro d'un échec de mesure.

## La mesure (6 sept. 2026)

`tools/qa/audit_cartes.py` relève `/api/client-log` à la fin de l'audit et en
rend une ligne dans son rapport Markdown. Il lisait `items`, `entries` ou
`logs` — trois clés que le serveur n'a **jamais** servies :

```text
blueprint isolé, 2 erreurs JS POSTées
  clés renvoyées : ['count', 'errors'] · count = 2 · len(errors) = 2
  ligne du rapport MD : `/api/client-log` : 0 entrée(s) pendant l’audit.
git log -S"_CLIENT_ERRORS" → un seul commit : la forme {count, errors} n'a
jamais changé. La clé lue était inventée par l'outil, pas dérivée du contrat.
```

Trois états distincts rendaient donc la même ligne constante :

```text
endpoint injoignable ({'erreur': 'HTTP Error 502'})  → « 0 entrée(s) »
5 erreurs JS réelles                                 → « 0 entrée(s) »
journal réellement vide (vérité = 0)                 → « 0 entrée(s) »
```

Ce n'est pas un compteur mal lu : c'est un zéro constant qui avale aussi
l'ÉCHEC de mesure et le présente comme un résultat propre — l'invariant 5
(« zéro, absent, estimation, delayed, stale, démo et erreur restent
distincts ») enfreint dans l'outil censé prouver que le produit le respecte.
L'application, elle, est intacte : `/api/client-log` sert {count, errors} et
ses bancs le couvrent (`tests/test_post_routes.py`). Seul le Markdown mentait ;
le JSON (`--json`) portait déjà la vérité.
"""
from __future__ import annotations

import pathlib
import sys

RACINE = pathlib.Path(__file__).resolve().parents[1]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from tools.qa import audit_cartes as _audit  # noqa: E402


def _rapport(client_log):
    return {'base': 'http://127.0.0.1:5003', 'debut': 'T0', 'fin': 'T1',
            'largeurs': [1600, 390], 'pages': [], 'client_log': client_log}


def test_un_echec_de_releve_n_est_pas_zero_erreur():
    """L'état le plus dangereux des trois : la mesure n'a pas eu lieu, et la
    ligne servie disait « 0 entrée(s) » — une preuve fabriquée."""
    md = _audit.markdown(_rapport({'erreur': 'HTTP Error 502: Bad Gateway'}))
    assert 'NON MESURÉ' in md, md[-300:]
    assert 'HTTP Error 502' in md, 'la cause de l’échec doit être nommée'
    assert '0 entrée(s)' not in md, (
        'un relevé impossible est présenté comme un journal propre')


def test_les_erreurs_reelles_sont_comptees_et_lisibles():
    """MESURÉ : 2 erreurs JS POSTées → `count=2`, et la ligne annonçait 0."""
    md = _audit.markdown(_rapport(
        {'count': 2, 'errors': [{'msg': 'TypeError: x est nul'},
                                {'msg': 'boom déjà vu'}]}))
    assert '2 entrée(s)' in md
    assert 'TypeError: x est nul' in md, (
        'une preuve à N doit être lisible, sinon elle ne sert qu’à cocher')
    assert 'déjà vu' in md, 'accents intacts (pas d’échappement \\u)'


def test_un_journal_vraiment_vide_reste_zero():
    """Contre-épreuve : le vrai zéro doit rester un zéro, sinon la correction
    remplacerait un faux calme par une fausse alarme."""
    md = _audit.markdown(_rapport({'count': 0, 'errors': []}))
    assert '0 entrée(s)' in md
    assert 'NON MESURÉ' not in md


def test_la_forme_lue_est_celle_que_le_serveur_sert():
    """Le compte se déduit encore d'`errors` si `count` manque — même règle que
    `tools/rc_short_audit.js` (`clientLog.count ?? errors.length`), qui lisait
    déjà correctement pendant que cet outil-ci inventait ses clés."""
    md = _audit.markdown(_rapport({'errors': [{'msg': 'a'}, {'msg': 'b'}, {'msg': 'c'}]}))
    assert '3 entrée(s)' in md
    #  Les clés jamais servies ne doivent plus décider de rien.
    md_mort = _audit.markdown(_rapport({'count': 4, 'errors': [1, 2, 3, 4],
                                        'items': [], 'entries': [], 'logs': []}))
    assert '4 entrée(s)' in md_mort, (
        'la lecture retombe sur des clés que le serveur n’a jamais servies')
