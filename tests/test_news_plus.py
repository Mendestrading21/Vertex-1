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
