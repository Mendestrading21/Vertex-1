"""`scores.data_quality` : chaque état de fraîcheur garde sa note ET son nom.

Le lot K a corrigé la table de notation d'`executive_engine.decide` (DEMO et
étiquette hors vocabulaire passaient de 50 à 0) mais n'a laissé AUCUN banc
derrière lui : aucun test du dépôt n'exerçait ces étiquettes, si bien que le
correctif n'était protégé par rien et que sa propre confusion résiduelle n'a
été vue par personne.

Mesures, `decide()` sur un paquet ne différant que par `data_quality` :

    étiquette      avant lot K   après lot K   après ce banc
    FRESH          100           100           100
    RECENT          75            75            75
    STALE           30            30            30
    EXPIRED          0             0             0
    MISSING          0             0             0
    DEMO            50             0             0
    hors vocab.     50             0 + nommé     0 + nommé
    bloc ABSENT     50             0  (MUET)     0 + nommé
    bloc {}         50             0  (MUET)     0 + nommé

Les deux dernières lignes sont la régression que ce fichier ferme : le lot K a
fait tomber l'absence de 50 à 0 sans la nommer, donc un paquet SANS preuve de
fraîcheur rendait exactement la même sortie qu'un `EXPIRED` MESURÉ — même note,
`unknowns` vide, aucune ligne d'audit. L'invariant 4 exige que l'absence, le
zéro et l'erreur restent distincts ; ils le sont ici par le canal prévu
(`unknowns` + `audit_trail`), sans déplacer aucune note ni aucun seuil.
"""
from vertex.strategy import executive_engine as ee

VOCABULAIRE_CANONIQUE = {'FRESH': 100, 'RECENT': 75, 'STALE': 30,
                         'EXPIRED': 0, 'MISSING': 0}


def _paquet(**extra):
    """Paquet minimal dont SEULE la qualité de données varie."""
    p = {'symbol': 'X',
         'technical': {'score': 70, 'reward_risk': 2.5},
         'fundamental': {'score': 70},
         'catalysts': {'score': 70},
         'sentiment': {'score': 70}}
    p.update(extra)
    return p


def _decide(**extra):
    r = ee.decide(_paquet(**extra))
    return (r['scores']['data_quality'],
            'data_quality' in r['unknowns'],
            [a for a in r['audit_trail'] if 'qualité de données' in a])


def test_les_cinq_etiquettes_canoniques_gardent_leur_note_exacte():
    """Le vocabulaire de `vertex/data_sources/models.py` est noté sans surprise."""
    for etiquette, note in VOCABULAIRE_CANONIQUE.items():
        obtenue, nommee, _ = _decide(data_quality={'overall': etiquette})
        assert obtenue == note, (etiquette, obtenue, note)
        assert nommee is False, etiquette


def test_une_donnee_de_demonstration_ne_vaut_aucune_fraicheur():
    """DEMO = donnée FABRIQUÉE : 0, jamais mieux qu'une donnée réelle rassise.

    Mesuré avant le lot K : DEMO notait 50, donc au-dessus de STALE (30) — une
    donnée inventée était publiée comme plus fiable qu'une donnée réelle
    périmée. `decision_packet._source_quality` pose cette étiquette dès que
    ``scan_state['source'] == 'demo'`` : le cas est atteignable, pas théorique.
    """
    demo, _, _ = _decide(data_quality={'overall': 'DEMO'})
    rassis, _, _ = _decide(data_quality={'overall': 'STALE'})
    assert demo == 0, demo
    assert demo < rassis, (demo, rassis)


def test_une_etiquette_hors_vocabulaire_est_notee_zero_ET_nommee():
    """Un mot inconnu ne se fond pas dans la table : il est déclaré inconnu."""
    for etiquette in ('CONFLICTED', 'OK', 'DEGRADED', 'n_importe_quoi'):
        note, nommee, audit = _decide(data_quality={'overall': etiquette})
        assert note == 0, (etiquette, note)
        assert nommee is True, etiquette
        assert audit, etiquette


def test_l_absence_de_bloc_est_nommee_et_reste_distincte_d_une_peremption():
    """RÉGRESSION FERMÉE : absence de preuve ≠ péremption MESURÉE.

    Mesuré sur le lot K avant ce banc, sur trois paquets différents :
        bloc `data_quality` ABSENT -> note 0, unknowns [], audit []
        bloc `data_quality` = {}   -> note 0, unknowns [], audit []
        overall = 'EXPIRED'        -> note 0, unknowns [], audit []
    Trois sorties BYTE-IDENTIQUES pour trois états que l'invariant 4 sépare.
    La note 0 est juste dans les trois cas (aucune fraîcheur n'est prouvée) ;
    ce qui manquait, c'est le NOM de la cause.
    """
    perime = _decide(data_quality={'overall': 'EXPIRED'})
    absent = _decide()
    vide = _decide(data_quality={})

    # 1. La note ne bouge pas : aucune fraîcheur prouvée = 0 partout.
    assert perime[0] == absent[0] == vide[0] == 0

    # 2. Mais l'absence est NOMMÉE, la péremption mesurée ne l'est pas.
    assert absent[1] is True and vide[1] is True
    assert perime[1] is False

    # 3. Et l'audit distingue les deux causes par leur texte, pas par la note.
    assert any('ABSENCE' in a for a in absent[2]), absent[2]
    assert any('ABSENCE' in a for a in vide[2]), vide[2]
    assert not perime[2], perime[2]


def test_aucune_note_de_qualite_ne_deplace_une_decision():
    """`data_quality` informe, il ne décide pas — le verdict est inchangé.

    Garde de portée : le correctif ci-dessus change une NOTE publiée et un
    canal d'aveu, jamais un seuil. `unknowns_critical` ne retient que
    fundamental/technical, et aucune branche de `decide()` ne lit
    `scores['data_quality']`.
    """
    verdicts = {etiquette: ee.decide(_paquet(
        data_quality={'overall': etiquette}))['final_decision']
        for etiquette in list(VOCABULAIRE_CANONIQUE) + ['DEMO', 'zzz']}
    verdicts['bloc_absent'] = ee.decide(_paquet())['final_decision']
    assert len(set(verdicts.values())) == 1, verdicts
