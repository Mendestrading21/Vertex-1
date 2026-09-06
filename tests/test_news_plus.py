"""tests/test_news_plus.py — SKYLER LOT 102 : gardien XSS des news figé.

Trou réel de couverture : vertex/services/news_plus.py — la règle n°5 du
projet (« tout texte externe passe par sanitize_news avant d'être servi,
rendu en innerHTML ») n'était testée qu'indirectement au point de sortie
d'une route (test_events_timeline). Le gardien lui-même (échappement,
liens javascript:, balises cassées), le sentiment lexical, le parse RSS
et la déduplication n'avaient AUCUN test direct.
Caractérisations nées vertes (dites) — moteur INTACT, aucun réseau.
"""
from vertex.services import news_plus as np


# ------------------------------------------------------------ sanitize (XSS)

def test_script_tags_stripped_and_metacharacters_escaped():
    items = [{'title': '<script>alert(1)</script>Apple & "Co" <b>up</b>',
              'sym': "AA'PL"}]
    out = np.sanitize_news(items)
    t = out[0]['title']
    assert '<' not in t and '>' not in t and '"' not in t and "'" not in t
    assert 'alert(1)Apple &amp; &quot;Co&quot; up' == t, (
        'balises retirées PUIS méta-caractères échappés — sûr en innerHTML')
    assert out[0]['sym'] == 'AA&#39;PL'


def test_unclosed_tag_cannot_smuggle_html():
    # Balise jamais fermée : la regex ne la voit pas, l'échappement la neutralise.
    out = np.sanitize_news([{'title': '<img src=x onerror=alert(1)'}])
    assert out[0]['title'].startswith('&lt;img'), (
        'même une balise cassée sort inerte — le < est encodé')


def test_dangerous_link_schemes_are_dropped_https_kept():
    items = [{'title': 'a', 'link': 'javascript:alert(1)'},
             {'title': 'b', 'link': 'data:text/html,<script>x</script>'},
             {'title': 'c', 'link': '  HTTPS://ex.com/a?q="x"&r=\'y\'<z>  '}]
    out = np.sanitize_news(items)
    assert out[0]['link'] is None and out[1]['link'] is None, (
        'seul http(s) sort — jamais un schéma exécutable')
    lk = out[2]['link']
    assert lk.startswith('HTTPS://ex.com/') and '%22' in lk and '%27' in lk
    assert '<' not in lk and '>' not in lk        # sûr en href ET window.open


def test_sanitize_skips_non_dicts_and_preserves_other_keys():
    out = np.sanitize_news([None, 'texte', 42, {'title': 'ok', 'senti': -1}])
    assert len(out) == 1 and out[0]['senti'] == -1
    assert np.sanitize_news(None) == []


# ----------------------------------------------------------------- sentiment

def test_sentiment_lexical_fr_en_and_neutral():
    assert np.sentiment('Apple beats estimates, shares surge') == 1
    assert np.sentiment('Le titre plonge après une enquête') == -1
    assert np.sentiment('beat announced but lawsuit filed') == 0   # mixte 1-1
    assert np.sentiment('') == 0 and np.sentiment(None) == 0


def test_aggregate_rounds_and_skips_items_without_symbol():
    """Agrégat de PROVENANCE (comportement par défaut, inchangé).

    MESURE (2026-09-06) : ce groupement par `sym` est un groupement par FIL
    INTERROGÉ, pas par sujet — voir `test_aggregate_par_sujet_ne_compte_que_les_articles_du_titre`.
    Le défaut est conservé parce que deux gardiens hors de ce lot l'épinglent
    encore (`tests/test_real_data.py`), mais la route dit désormais sa base
    (`sentiment_base`) et sert l'agrégat par sujet à côté.
    """
    items = [{'sym': 'AAPL', 'senti': 1}, {'sym': 'AAPL', 'senti': 0},
             {'sym': 'AAPL'}, {'senti': -1}]
    agg = np.aggregate(items)
    assert agg == {'AAPL': {'score': 0.33, 'n': 3}}, (
        'senti absent compte 0, item sans sym ignoré, arrondi à 2 décimales')
    #  Sans titre, aucun sujet n'est établi : la table est VIDE, pas à zéro.
    assert np.aggregate(items, sujets_seulement=True) == {}


# --------------------------------------------------- attribution sym : sujet ?

#: Les cinq cas NON AMBIGUS relevés le 2026-09-06 dans les 45 items servis par
#: `/news-feed` (22 titres sur 45 ne nommaient ni le ticker ni la société).
_HORS_SUJET_MESURES = [
    ('NVDA', 'Where Will Shopify Stock Be in 5 Years?'),
    ('NVDA', 'Should You Buy Snowflake Stock After Its Recent Surge?'),
    ('NVDA', 'Oil Surged, Then Slumped, Year to Date in 2026.'),
    ('AMZN', 'Costco silently kills member perk'),
    ('META', "'AI Laggard' Apple Is Sitting Pretty, But AAPL Stock Is a Buy"),
]


def test_le_ticker_du_fil_ne_vaut_pas_sujet_confirme():
    """MESURE : `sym` est le fil interrogé (boucle `for sym in NEWS_SYMS + hot`),
    pas le sujet de la dépêche ; le repli web est une recherche de mot-clé
    Google News. Sur les items réels ci-dessus, la puce annonçait NVDA, AMZN
    ou META pour des articles sur Shopify, Snowflake, le pétrole, Costco et
    Apple — le dernier nommant explicitement un AUTRE ticker."""
    for sym, titre in _HORS_SUJET_MESURES:
        assert np.sujet_confirme({'sym': sym, 'title': titre}) is False, titre
        assert np.role_sujet({'sym': sym, 'title': titre}) == 'fil'


def test_le_sujet_est_confirme_par_le_ticker_le_nom_ou_l_attestation_du_vendeur():
    ok = [{'sym': 'NVDA', 'title': 'Nvidia beats estimates, shares surge'},
          {'sym': 'AMD', 'title': 'AMD unveils new chip'},
          {'sym': 'TSLA', 'title': 'Q3 deliveries', 'fr': 'Tesla livre plus que prévu'},
          {'sym': 'AAPL', 'title': 'Apple&#39;s event'},          # entité HTML décodée
          #  Dépêche du courtier : le fournisseur l'attribue au contrat.
          {'sym': 'NVDA', 'title': 'Chip demand stays hot', 'sym_atteste': True}]
    for it in ok:
        assert np.sujet_confirme(it) is True, it['title']
    #  Mot entier : « META » ne se confirme pas sur « metadata ».
    assert np.sujet_confirme({'sym': 'META', 'title': 'New metadata standard'}) is False
    assert np.sujet_confirme({'sym': '', 'title': 'Nvidia beats'}) is False
    assert np.sujet_confirme('pas-un-dict') is False


def test_aggregate_par_sujet_ne_compte_que_les_articles_du_titre():
    """MESURE : `/news-feed` servait `sentiment['NVDA'] = {'n': 4, 'score': 0.5}`
    ; les 4 articles qui produisaient ce +0,5 haussier étaient Snowflake, le
    pétrole, GitLab et Shopify — AUCUN sur Nvidia. Un ticker sans article
    confirmé doit DISPARAÎTRE de la table : une absence dite, jamais un score
    fabriqué."""
    items = [{'sym': s, 'title': t, 'senti': 1} for s, t in _HORS_SUJET_MESURES]
    items.append({'sym': 'NVDA', 'title': 'Nvidia beats estimates', 'senti': -1})
    assert np.aggregate(items)['NVDA'] == {'score': 0.5, 'n': 4}, 'le défaut mesuré'
    sujets = np.aggregate(items, sujets_seulement=True)
    assert sujets == {'NVDA': {'score': -1.0, 'n': 1}}
    assert 'AMZN' not in sujets and 'META' not in sujets


#: Les tickers de l'univers scanné (`vertex/data/universe`, 517 titres) qui
#: sont aussi des mots anglais courants. Ils sont ÉLIGIBLES aux 6 titres
#: « chauds » que la boucle d'actualités injecte à chaque tour.
_TICKERS_MOTS_COURANTS = ('A', 'ALL', 'ARE', 'CAT', 'COST', 'DD', 'FAST', 'HAS',
                          'IT', 'KEY', 'KO', 'LOW', 'NOW', 'ON', 'SO', 'T', 'WELL')

#: Titres REÉLS servis par `/news-feed` le 2026-09-06, choisis parce qu'ils
#: faisaient confirmer un sujet à tort (mesure ci-dessous).
_TITRES_REELS = (
    'Fed Holds Rates Steady on Inflation Concerns',
    'All Eyes Are on the Jobs Report',
    "Bill Gates Says He Still Won't Invest in Crypto, Calls It a Pure Mania",
    'CrowdStrike (CRWD) Unveiled A Broad AI Security Platform Push',
    'Equifax (EFX) Faces Complaint Portal Focus, Is It A Bargain?',
    'The Agent Production Gap: When 171% ROI Isn’t Enough to Ship',
)


def test_un_ticker_qui_est_un_mot_courant_ne_confirme_aucun_sujet():
    """MESURE DU 2026-09-06 — le juge de sujet confirmait À TORT.

    Le premier correctif comparait le ticker APRÈS abaissement de casse
    (`(?<![a-z0-9])t(?![a-z0-9])`). Croisé avec les 45 titres réellement servis
    et les 17 tickers de l'univers qui sont des mots anglais courants, cela
    faisait **20 confirmations dont 19 fausses** sur 765 paires : « Fed Holds
    Rates Steady on Inflation » confirmait ON, « All Eyes Are on the Jobs
    Report » confirmait ALL *et* ARE, « Bill Gates… Won't Invest in Crypto »
    confirmait T (la frontière de mot accepte l'apostrophe). La chaîne complète
    rendait alors `aggregate(..., sujets_seulement=True)` =
    `{'T': {'score': 1.0, 'n': 1}}` — le score de ticker fabriqué que ce lot
    prétend supprimer, seulement plus rare.

    Après correctif, sur les mêmes paires : **0 confirmation fausse**.
    """
    fausses = [(m, t) for t in _TITRES_REELS for m in _TICKERS_MOTS_COURANTS
               if np.sujet_confirme({'sym': m, 'title': t})]
    assert fausses == [], fausses
    #  La chaîne complète : plus aucun score de ticker n'en sort.
    items = [{'sym': 'T', 'title': _TITRES_REELS[2], 'senti': 1}]
    assert np.aggregate(items, sujets_seulement=True) == {}
    assert np.aggregate(items)['T'] == {'score': 1.0, 'n': 1}, 'la provenance, elle, reste'


def test_un_ticker_court_n_est_etabli_que_par_le_nom_de_la_societe():
    """Un code d'une ou deux lettres écrit en majuscules n'est pas distinctif :
    mesuré, « A » (Agilent, dans l'univers) se confirmait sur 2 des 45 titres
    réels, où le « A » est l'article anglais d'un titre en casse de titre."""
    assert np.LONGUEUR_TICKER_PROBANTE == 3
    assert np.sujet_confirme({'sym': 'A', 'title': 'Is It A Bargain?'}) is False
    assert np.sujet_confirme({'sym': 'IT', 'title': 'IT spending rebounds'}) is False
    #  Le nom de société reste une preuve, quelle que soit la longueur du code.
    assert np.sujet_confirme({'sym': 'V', 'title': 'Visa Inc lifts guidance'}) is True
    #  À partir de 3 lettres, le code ÉCRIT COMME UN TICKER vaut preuve…
    assert np.sujet_confirme({'sym': 'AMD', 'title': 'AMD unveils new chip'}) is True
    #  … mais seulement en majuscules : « amd » en minuscules dans un mot
    #  ordinaire n'en est pas un.
    assert np.sujet_confirme({'sym': 'ALL', 'title': 'all eyes on the jobs report'}) is False


def test_l_attestation_du_vendeur_suit_ses_producteurs_reels():
    """La déclaration de `PREUVES_SUJET` doit suivre le CODE — dans les deux sens.

    ## Le gardien ne voyait pas le producteur (mesure du 2026-09-06)

    Version précédente : balayage de `vertex/**/*.py` (322 fichiers) et
    assertion « aucun producteur, donc NON_IMPLÉMENTÉ ». Or le SEUL producteur
    du fil est `terminal.py::_news_loop`, à la RACINE du dépôt : il n'entrait
    pas dans le glob. Le jour où quelqu'un y posait le drapeau — geste
    explicitement demandé par le reste de programme — le test restait VERT
    pendant que `/news-feed` continuait d'annoncer `NON_IMPLÉMENTÉ` sur un
    canal devenu vivant : l'invariant 8 inversé, avec un gardien aveugle.

    ## Le détecteur ne voyait pas la forme réelle de la pose

    Second trou mesuré : le motif n'acceptait que `'sym_atteste':` (littéral de
    dictionnaire) et `sym_atteste =`. La pose réelle s'écrit
    `_it['sym_atteste'] = True` — un indiçage — qu'aucune des deux alternatives
    ne reconnaît. Le motif couvre désormais les trois formes.

    ## Ce que ce test fige aujourd'hui

    Balayage élargi : 1 producteur, `terminal.py` (branche courtier
    `depeches_lot`, où IBKR rattache la dépêche au `conId` qualifié). La valeur
    attendue est DÉRIVÉE du balayage : si le producteur disparaît, ce test
    exige de repasser la déclaration à `NON_IMPLÉMENTÉ` ; s'il reste et que la
    déclaration retombe, il tombe aussi.
    """
    import pathlib
    import re as _re
    racine = pathlib.Path(__file__).resolve().parents[1]
    #  POSER le drapeau, pas en parler : clé de dictionnaire, indiçage ou
    #  affectation. Les mentions en prose (docstring de la route) ne comptent
    #  pas — elles décrivent le canal, elles ne le posent pas.
    pose = _re.compile(r'''['\"]sym_atteste['\"]\s*(?::|\]\s*=)|(?<!\.)\bsym_atteste\s*=''')
    #  terminal.py vit à la RACINE : sans lui, le balayage manque le seul
    #  producteur du fil.
    fichiers = [racine / 'terminal.py'] + sorted(racine.glob('vertex/**/*.py'))
    producteurs = [str(c.relative_to(racine)) for c in fichiers
                   if c.name != 'news_plus.py'
                   and pose.search(c.read_text(encoding='utf-8', errors='replace'))]
    attendu = 'ACTIF' if producteurs else 'NON_IMPLÉMENTÉ'
    assert np.PREUVES_SUJET['attestation_vendeur'] == attendu, producteurs
    assert 'terminal.py' in producteurs, (
        'le seul producteur du fil ne pose plus l’attestation du courtier : '
        'les dépêches IBKR retomberaient en « fil » dès que leur titre ne '
        'nomme pas la société')
    assert np.PREUVES_SUJET['ticker_ecrit_en_majuscules'] == 'ACTIF'
    assert np.PREUVES_SUJET['nom_de_societe'] == 'ACTIF'
    #  La règle reste juste et reste lue : un producteur qui l'attesterait
    #  serait cru immédiatement.
    assert np.sujet_confirme({'sym': 'NVDA', 'title': 'Chip demand stays hot',
                              'sym_atteste': True}) is True


def test_marquer_sujets_est_additif_et_ne_retire_aucune_information():
    items = [{'sym': 'AMZN', 'title': 'Costco silently kills member perk', 'senti': 1},
             {'sym': 'NVDA', 'title': 'Nvidia beats estimates'},
             'pas-un-dict']
    out = np.marquer_sujets(items)
    assert [i['sym_role'] for i in out] == ['fil', 'sujet']
    assert out[0]['title'] == 'Costco silently kills member perk' and out[0]['senti'] == 1
    assert items[0].get('sym_role') is None, 'les items d’origine ne sont pas mutés'


# ------------------------------------------------------------------ parse_rss

def test_parse_rss_strips_publisher_suffix_and_caps_items():
    xml = ('<rss><channel>'
           + ''.join(f'<item><title>Titre {i} - Éditeur{i}</title>'
                     f'<link>https://ex.com/{i}</link>'
                     f'<pubDate>D{i}</pubDate></item>' for i in range(6))
           + '</channel></rss>')
    out = np.parse_rss(xml, n=4)
    assert len(out) == 4                              # cap n respecté
    assert out[0]['title'] == 'Titre 0' and out[0]['publisher'] == 'Éditeur0'
    assert out[0]['link'] == 'https://ex.com/0'


def test_parse_rss_garbage_xml_returns_empty_never_raises():
    assert np.parse_rss('pas du xml <<<') == []
    assert np.parse_rss('<rss><channel><item><title></title></item></channel></rss>') == []


# ---------------------------------------------------------------- dedupe_news

def test_dedupe_by_normalized_title_and_link_keeps_first():
    items = [{'title': 'Apple beats!', 'link': 'https://a.com/1'},
             {'title': 'APPLE — BEATS', 'link': 'https://a.com/2'},   # même titre normalisé
             {'title': 'Autre news', 'link': 'https://a.com/1'},      # même lien
             {'title': 'Troisième', 'link': 'https://a.com/3'},
             'pas-un-dict']
    out = np.dedupe_news(items)
    assert [i['title'] for i in out] == ['Apple beats!', 'Troisième'], (
        'premier conservé tel quel, ordre préservé, non-dicts ignorés')


def test_les_raisons_sociales_manquantes_rendaient_de_VRAIES_attributions():
    """MESURE DU CONTRÔLE ADVERSE (2026-09-06) — `NOMS_SOCIETE` ne couvrait
    que 11 des 16 tickers réellement servis par le fil.

    Sur la tranche des 5 non couverts (ALAB, EFX, FICO, LULU, SNDK), la règle
    « pas de nom, pas de preuve » supprimait 3 attributions VRAIES : les titres
    ci-dessous NOMMENT la société en toutes lettres. Rappel 100 % → 67 % sur
    cette tranche, pour une précision passée de 75 % à 100 %. Le trou est
    structurel — il se comble par des raisons sociales RÉELLES, écrites à la
    main, jamais en relâchant la preuve.
    """
    for sym, titre in (
            ('LULU', 'Lululemon makes big cuts to one kind of store'),
            ('LULU', "Lululemon's Earnings Beat Hid a Bigger Problem"),
            ('SNDK', 'Prediction: This Is What Sandisk Stock Will Be Worth in 12 Months')):
        assert np.sujet_confirme({'sym': sym, 'title': titre}) is True, titre
    #  Le ticker seul ne suffit toujours pas : « Lululemon » n'est pas « LULU ».
    assert np.sujet_confirme({'sym': 'LULU', 'title': 'lululemon in lowercase'}) is True
    #  Et la preuve reste une preuve : un titre qui ne nomme pas la société
    #  n'est pas confirmé, exactement comme avant l'ajout.
    assert np.sujet_confirme({'sym': 'SNDK', 'title': 'Nike Exits the S&P 100 Index'}) is False
    assert np.sujet_confirme({'sym': 'ALAB', 'title': 'Chip demand stays hot'}) is False
