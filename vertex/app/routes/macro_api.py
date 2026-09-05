"""vertex/app/routes/macro_api.py — références macro officielles (FRED, BCE, BNS).

GET /api/macro/officiel : l'instantané du collecteur de fond, jamais une
collecte réseau dans la requête. Chaque série porte valeur, unité, fréquence,
date d'observation chez la source, précédente observation, heure de réception,
URL de la source et, le cas échéant, son erreur. Lecture seule.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from vertex.services import macro_officiel as _svc

bp = Blueprint('macro_api', __name__)


@bp.route('/api/macro/officiel')
def api_macro_officiel():
    snap = _svc.snapshot()
    reponse = jsonify(snap)
    #  Instantané de fond : le navigateur peut le garder une minute, la boucle
    #  ne le renouvelle que toutes les `cadence_min` minutes.
    reponse.headers['Cache-Control'] = 'private, max-age=60'
    return reponse


__all__ = ['bp']
