"""
vertex/services/news_plus.py — NEWS MULTI-SOURCES + SENTIMENT.

1. `rss_news(sym)` — repli Google News RSS quand yfinance ne rend rien
   pour un titre (throttle, panne) : mêmes clés que le fil existant
   (title/link/publisher/time). Erreurs avalées → liste vide, jamais
   d'exception qui remonte dans la boucle.

2. `sentiment(text)` — score -1/0/+1 par heuristique lexicale FR/EN
   (fonctionne SANS clé IA, partout, gratuitement). Si l'IA est
   disponible (ANTHROPIC_API_KEY), les briefs l'affinent déjà — cette
   heuristique reste la base honnête et déterministe.

Analyse only.
"""

import html as _html
import re

_POS = ('beat', 'beats', 'surge', 'soar', 'rally', 'record', 'upgrade', 'raises',
        'strong', 'growth', 'profit', 'wins', 'approval', 'breakthrough', 'buyback',
        'dépasse', 'bondit', 'record', 'relève', 'hausse', 'accord', 'approbation')
_NEG = ('miss', 'misses', 'fall', 'falls', 'plunge', 'drop', 'cut', 'cuts', 'downgrade',
        'lawsuit', 'probe', 'recall', 'layoff', 'warning', 'weak', 'loss', 'fraud', 'halt',
        'chute', 'plonge', 'abaisse', 'baisse', 'procès', 'enquête', 'rappel', 'avertissement')


def sentiment(text):
    """Score lexical TERNAIRE : rend EXACTEMENT +1, -1 ou 0. Jamais autre chose.

    CONTRAT (lot 609, explicité après mesure) — le domaine est {-1, 0, +1} et
    rien d'autre. Ce n'est pas une intensité : trois mots positifs valent un
    seul, et « 3 positifs / 2 négatifs » rend la même chose que « 1 positif ».
    Le comparateur est `pos > neg`, pas une amplitude.

    POURQUOI ON NE LE REND PAS CONTINU. Une forme `(pos-neg)/(pos+neg)` donnerait
    des décimales — donc l'apparence d'une mesure — construites sur un lexique de
    22 mots positifs et 22 négatifs. Un « 0,333 » issu de trois mots-clés a l'air
    d'une mesure et n'en est pas une. Tant qu'on ne peut pas montrer que
    l'amplitude est FONDÉE, le ternaire est plus honnête que le continu.

    CE QUI EN DÉPEND, mesuré : `news_impact.score_importance` ajoute +5 quand le
    score est signé, ce qui participe au choix de l'« Actualité dominante »
    affichée sur `/`. La valeur a donc une conséquence visible — mais deux états
    utiles seulement (signé / neutre).

    Gardien : `tests/test_sentiment_contrat.py`.
    """
    t = ' ' + (text or '').lower() + ' '
    pos = sum(1 for w in _POS if w in t)
    neg = sum(1 for w in _NEG if w in t)
    return 1 if pos > neg else -1 if neg > pos else 0


#: Noms de société par ticker, ÉCRITS À LA MAIN comme `data/descriptions_fr`.
#: Ils servent à répondre à une seule question : le titre de la dépêche
#: NOMME-T-IL le titre auquel le fil l'attribue ? Un ticker absent de la table
#: ne peut être confirmé que par son propre code dans le titre — l'inconnu
#: reste inconnu, il ne devient jamais un « oui » par défaut.
NOMS_SOCIETE: dict[str, tuple[str, ...]] = {
    'AAPL': ('apple', 'iphone'),
    'MSFT': ('microsoft', 'windows', 'azure'),
    'NVDA': ('nvidia',),
    'GOOGL': ('google', 'alphabet', 'youtube'),
    'GOOG': ('google', 'alphabet', 'youtube'),
    'AMZN': ('amazon', 'aws'),
    'META': ('meta platforms', 'facebook', 'instagram', 'whatsapp'),
    'TSLA': ('tesla',),
    'AMD': ('advanced micro devices',),
    'AVGO': ('broadcom',),
    'PLTR': ('palantir',),
    'NFLX': ('netflix',),
    'CRM': ('salesforce',),
    'COST': ('costco',),
    'LLY': ('eli lilly', 'lilly'),
    'JPM': ('jpmorgan', 'jp morgan'),
    'V': ('visa inc', 'visa card'),
    'MA': ('mastercard',),
    'HD': ('home depot',),
    'UNH': ('unitedhealth',),
    'XOM': ('exxon',),
    'WMT': ('walmart',),
    'SPY': ('s&p 500', 's&p500'),
    'QQQ': ('nasdaq 100', 'nasdaq-100'),
}


def sujet_confirme(item, sym=None) -> bool:
    """Le SUJET de la dépêche est-il établi comme étant `sym` ?

    ## Pourquoi la question se pose — mesure du 2026-09-06

    `sym` n'est PAS le sujet de l'article : c'est le FIL INTERROGÉ. La boucle
    de collecte écrit `feed.append({**it, 'sym': sym})` où `sym` est la
    variable de boucle `for sym in NEWS_SYMS + hot`, et le repli web est une
    simple recherche de mot-clé Google News (`q='%s stock'`). Rien ne garantit
    que la dépêche PARLE du titre.

    Mesure sur les 45 items servis par `/news-feed` : **22 titres sur 45** ne
    nomment ni le ticker ni la société — `[AMZN] Costco silently kills member
    perk`, `[SNDK] Nike Exits the S&P 100 Index`, `[GOOGL] Why Rezolve AI Stock
    Plummeted`, et `[META] 'AI Laggard' Apple Is Sitting Pretty…` qui nomme
    explicitement un AUTRE ticker. Conséquence chiffrée : `aggregate` servait
    `NVDA {'n': 4, 'score': 0.5}` construit sur Snowflake, le pétrole, GitLab
    et Shopify — un sentiment de marché qu'aucune actualité NVDA ne soutient.

    ## Ce qui vaut preuve, et rien d'autre

    1. l'attestation du VENDEUR (`sym_atteste`) : une dépêche du courtier est
       attribuée au contrat par le fournisseur lui-même. Aucun producteur ne
       pose ce drapeau aujourd'hui — il est lu ici pour que la chaîne devienne
       juste dès que la boucle le posera, sans nouveau passage ici ;
    2. le ticker écrit dans le texte servi (titre + traduction FR), en mot
       entier ;
    3. un nom de société de `NOMS_SOCIETE`.

    Tout le reste est `False` : « pertinence sectorielle » n'est pas une
    preuve de sujet, et l'absence de preuve n'est pas une preuve d'absence —
    l'item reste servi, il cesse seulement d'AFFIRMER un sujet.
    """
    if not isinstance(item, dict):
        return False
    s = str(sym if sym is not None else (item.get('sym') or '')).upper().strip()
    if not s:
        return False
    if item.get('sym_atteste'):
        return True
    texte = ' %s %s ' % (item.get('title') or '', item.get('fr') or '')
    texte = _html.unescape(str(texte)).lower()
    if re.search(r'(?<![a-z0-9])%s(?![a-z0-9])' % re.escape(s.lower()), texte):
        return True
    return any(nom in texte for nom in NOMS_SOCIETE.get(s, ()))


def role_sujet(item, sym=None) -> str:
    """`'sujet'` quand l'article est établi comme portant sur `sym`, sinon
    `'fil'` — le ticker n'est alors qu'une PROVENANCE de collecte."""
    return 'sujet' if sujet_confirme(item, sym) else 'fil'


def marquer_sujets(items):
    """Copie des items, chacun portant son `sym_role` (`sujet` | `fil`).

    Additif : aucun item n'est retiré ni réécrit. Un consommateur qui affirme
    un sujet (puce cliquable, agrégat par ticker, entités d'un événement) doit
    lire ce champ ; sans lui, il présente une provenance pour un sujet."""
    out = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        d = dict(it)
        d['sym_role'] = role_sujet(d)
        out.append(d)
    return out


def aggregate(items, sujets_seulement=False):
    """Sentiment agrégé par ticker : {sym: {'score': -1..1, 'n': N}}.

    ATTENTION AU SENS DE LA CLÉ. Par défaut, l'agrégat groupe par `sym`, qui
    est le FIL INTERROGÉ et non le sujet de la dépêche (voir `sujet_confirme`) :
    c'est un agrégat de PROVENANCE, pas un sentiment du titre. Mesuré le
    2026-09-06 sur le fil réel : `NVDA {'n': 4, 'score': 0.5}` sans une seule
    actualité Nvidia dedans.

    `sujets_seulement=True` ne compte que les items dont le sujet est ÉTABLI.
    Un ticker sans item confirmé DISPARAÎT alors de la table : une absence
    dite, jamais un `0.0` fabriqué. C'est la forme à servir dès qu'un
    consommateur affiche cette table par ticker.

    Le défaut reste `False` parce que deux gardiens hors de ce lot épinglent
    encore la forme de provenance (`tests/test_real_data.py::test_aggregate_by_ticker`
    et `::test_news_feed_exposes_sentiment`, items sans titre) : les basculer
    est le geste qui manque, il appartient au lot qui possède ce fichier.
    """
    by = {}
    for it in items or []:
        s = it.get('sym')
        if not s:
            continue
        if sujets_seulement and not sujet_confirme(it, s):
            continue
        d = by.setdefault(s, {'sum': 0, 'n': 0})
        d['sum'] += it.get('senti', 0)
        d['n'] += 1
    return {s: {'score': round(d['sum'] / d['n'], 2) if d['n'] else 0, 'n': d['n']}
            for s, d in by.items()}


#: Plafond de taille d'un flux. Un RSS Google News fait quelques dizaines de
#: kilo-octets ; deux mega-octets laissent une marge confortable et bornent ce
#: qu'un flux hostile peut faire avaler au processus avant meme le parsing.
TAILLE_MAX_FLUX = 2 * 1024 * 1024


class FluxRefuse(ValueError):
    """Ce flux ne sera pas parse — et on dit pourquoi."""


def _items_surs(brut: str, n: int) -> list:
    """Les `n` premiers `<item>` d'un flux, lus par un parseur QUI REFUSE le DTD.

    ## La mesure qui justifie ce refus

    `parse_rss` lit du XML **distant et non fiable** (Google News). Il passait
    par `minidom.parseString`, dont l'expansion d'entites est active. Mesure du
    25 aout 2026, sur le vrai `parse_rss` :

    | niveaux | charge envoyee | titre rendu | facteur |
    |---|---:|---:|---:|
    | 3 | 233 o | 800 o | x100 |
    | 5 | 343 o | 80 000 o | x10 000 |
    | 6 | **398 o** | **800 000 o** | **x100 000** |

    Chaque niveau supplementaire multiplie par dix : neuf niveaux tiennent
    encore dans 500 octets et rendent 800 Mo. C'est un *billion laughs*, et il
    est atteignable depuis un flux que Vertex va chercher lui-meme.

    ## Pourquoi expat directement, et pas `ElementTree`

    Premiere tentative : poser les gestionnaires sur `ET.XMLParser().parser`.
    En Python 3.12, `XMLParser` est l'implantation C et n'expose PAS `.parser`
    — le `getattr(..., None)` rendait donc le durcissement **silencieusement
    inoperant**, et la mesure d'apres montrait l'expansion intacte. Un
    durcissement qui ne durcit rien est pire que pas de durcissement : il
    rassure. C'est la mesure qui l'a dit, pas la relecture.

    ## Pourquoi refuser le DOCTYPE, et pas seulement les entites

    Un flux RSS n'a jamais besoin d'une declaration de type. La refuser a la
    racine supprime l'expansion d'entites, les entites externes et les
    references recursives d'un seul geste — et se raisonne en une phrase, ce
    qu'une liste d'interdictions particulieres ne permet pas.

    ## Pourquoi pas `defusedxml`

    Une dependance nouvelle exige licence verifiee, version verrouillee, audit
    et rollback (CLAUDE.md). Le refus ci-dessus est plus STRICT que le defaut
    de `defusedxml` — qui interdit les entites mais parse encore le DTD — et
    tient dans la bibliotheque standard.
    """
    from xml.parsers import expat

    analyseur = expat.ParserCreate()

    def _refuser(*_a, **_k):
        raise FluxRefuse('declaration de type de document refusee')

    def _refuser_externe(*_a, **_k):
        raise FluxRefuse('entite externe refusee')

    analyseur.StartDoctypeDeclHandler = _refuser
    analyseur.EntityDeclHandler = _refuser
    analyseur.ExternalEntityRefHandler = _refuser_externe

    items, pile, courant, texte = [], [], None, []

    def _debut(nom, _attrs):
        nonlocal courant, texte
        local = nom.rsplit(':', 1)[-1]
        pile.append(local)
        if local == 'item' and len(items) < n:
            courant = {}
        texte = []

    def _texte(donnees):
        if courant is not None:
            texte.append(donnees)

    def _fin(nom):
        nonlocal courant, texte
        local = nom.rsplit(':', 1)[-1]
        if pile:
            pile.pop()
        if courant is None:
            texte = []
            return
        if local == 'item':
            items.append(courant)
            courant = None
        elif local not in courant:
            courant[local] = ''.join(texte).strip()
        texte = []

    analyseur.StartElementHandler = _debut
    analyseur.CharacterDataHandler = _texte
    analyseur.EndElementHandler = _fin
    analyseur.Parse(brut.encode('utf-8') if isinstance(brut, str) else brut, True)
    return items[:n]


def parse_rss(xml_text, n=4):
    """Parse un flux RSS Google News -> [{title, link, publisher, time}].

    Rend `[]` sur n'importe quelle entree invalide ou hostile, et ne leve
    jamais : c'est un repli reseau, il ne doit pas emporter l'appelant.
    """
    out = []
    try:
        brut = xml_text if isinstance(xml_text, str) else (xml_text or '')
        if len(brut) > TAILLE_MAX_FLUX:
            #  Refus AVANT parsing : un flux hostile ne doit pas etre lu du
            #  tout, pas seulement mal lu.
            return []
        for champs in _items_surs(brut, n):
            title = champs.get('title') or ''
            if not title:
                continue
            #  Google News suffixe « - Editeur » au titre.
            pub = champs.get('source') or (title.rsplit(' - ', 1)[1]
                                           if ' - ' in title else '')
            out.append({'title': re.sub(r'\s+-\s+[^-]+$', '', title),
                        'link': champs.get('link') or '',
                        'publisher': pub,
                        'time': champs.get('pubDate') or ''})
    except Exception:
        return []
    return out


def rss_news(sym, n=4, timeout=6):
    """Repli réseau : Google News RSS pour un ticker. [] en cas d'échec."""
    try:
        import requests
        r = requests.get('https://news.google.com/rss/search',
                         params={'q': '%s stock' % sym, 'hl': 'en-US', 'gl': 'US'},
                         timeout=timeout, headers={'User-Agent': 'VertexDesk/1.0'})
        if r.status_code != 200:
            return []
        return parse_rss(r.text, n=n)
    except Exception:
        return []


_TAG_RE = re.compile(r'<[^>]*>')


def _clean_text(s):
    """Neutralise tout HTML/JS d'un texte externe, **une seule fois**.

    Balises retirées, méta-caractères échappés. Le résultat est sûr dans
    innerHTML, dans un attribut ET dans une chaîne JS inline côté client.

    ## Le défaut du double échappement

    Dow Jones et IBKR envoient des titres **déjà porteurs d'entités HTML** :

    ```text
    Stocks That Explain Today&#39;s Market -- Barrons.com
    ```

    Échapper sans décoder d'abord transformait le `&` en `&amp;`, et l'écran
    affichait littéralement `Today&#39;s Market`. Vu sur le desk réel le
    27 août 2026, sur trois dépêches de la première page.

    On **décode d'abord**, on échappe ensuite : l'opération devient
    idempotente, et un texte déjà propre traverse sans être abîmé.

    ## Pourquoi décoder n'ouvre pas de brèche

    Parce que l'échappement qui suit s'applique au texte décodé. Une source
    qui enverrait `&lt;script&gt;` obtient `<script>` après décodage, puis
    `&lt;script&gt;` de nouveau après échappement — exactement ce qu'il faut.
    Le décodage ne fait que ramener le texte à sa forme littérale ; c'est
    l'échappement final qui protège, et il est toujours le dernier mot.
    """
    #  `unescape` avant `_TAG_RE` : une balise ecrite `&lt;script&gt;` doit
    #  redevenir une balise pour que le retrait la voie, sinon elle passerait
    #  pour du texte et ressortirait telle quelle.
    s = _html.unescape(str(s))
    s = _TAG_RE.sub('', s)
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
             .replace('"', '&quot;').replace("'", '&#39;'))


#: Les trois producteurs de news du produit n'emettent PAS la meme cle :
#:
#:   `data_sources/ibkr_news`            -> `pub`
#:   `options/legacy_engine` (fil yfinance) -> `pub`
#:   `services/news_plus.rss_news`       -> `publisher`
#:
#: Chaque consommateur qui choisit sa cle perd les producteurs qu'il ignore.
#: Mesure du 26 aout 2026 : `market/news_pipeline` exigeait `publisher` ou
#: `source` et **rejetait 2 articles sur 3** — toutes les depeches IBKR et tout
#: le fil yfinance — en les comptant comme MALFORMES.
CLES_PUBLIEUR = ('publisher', 'pub', 'source', 'prov')


def nom_publieur(item) -> str:
    """Le nom du publieur, quelle que soit la cle du producteur.

    Rend `''` quand aucune cle n'est renseignee : une absence reste une
    absence, et inventer « externe » ici la ferait passer pour servie.
    """
    if not isinstance(item, dict):
        return ''
    for cle in CLES_PUBLIEUR:
        v = item.get(cle)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ''


def _lien_sur(lk):
    """Un lien servi en `href` / `window.open` — ou `None`.

    Extrait de `sanitize_news` pour que `sources[].link` passe par la MEME
    regle : une fonction d'assainissement recopiee diverge, et il suffit
    qu'une copie oublie un caractere (D-086).
    """
    if not lk:
        return None
    lk = str(lk).strip()
    if not lk.lower().startswith(('http://', 'https://')):
        return None
    return (lk.replace('"', '%22').replace("'", '%27')
              .replace('<', '%3C').replace('>', '%3E'))


def sanitize_news(items):
    """Assainit une liste d'items de news EXTERNES (yfinance/RSS/traduction) avant
    de la servir au client. XSS : les titres/liens de publishers tiers sont rendus
    en innerHTML côté client — on neutralise ici, au point unique de sortie.
    - title/fr/pub/publisher/sym/why : balises retirées + échappement complet ;
    - link : schéma http(s) obligatoire (sinon supprimé) + quotes/chevrons encodés
      (sûr en href="…" comme dans window.open('…'))."""
    out = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        d = dict(it)
        for k in ('title', 'fr', 'pub', 'publisher', 'sym', 'why', 'time'):
            if d.get(k) is not None:
                d[k] = _clean_text(d[k])
        d['link'] = _lien_sur(d.get('link'))
        #  `sources` porte des `pub` et des `link` d'origine EXTERNE, au meme
        #  titre que les champs de premier niveau. Ne pas l'assainir rouvrirait
        #  la breche de D-086 sur un champ tout neuf.
        if isinstance(d.get('sources'), list):
            d['sources'] = [
                {'pub': _clean_text(o.get('pub')) if o.get('pub') is not None else None,
                 'link': _lien_sur(o.get('link')),
                 'time': _clean_text(o.get('time')) if o.get('time') is not None else None}
                for o in d['sources'] if isinstance(o, dict)]
        out.append(d)
    return out


def horodatage_source(t):
    """Normalise l'horodatage FOURNI par la source en `YYYY-MM-DDTHH:MM` (+ `Z`
    quand la source déclare GMT/UTC, sinon sans fuseau : on n'invente pas un
    fuseau). Formats vus dans le fil : IBKR/yfinance `YYYY-MM-DD HH:MM`, RSS
    RFC 2822 `Sat, 06 Sep 2026 07:00:00 GMT`. None si illisible.

    ## Le fuseau DÉCLARÉ n'est plus perdu sur la branche ISO

    Mesure du 2026-09-06 : `horodatage_source('2026-09-02T10:15:00Z')` — le
    `<dc:date>` d'un communiqué BNS — rendait `'2026-09-02T10:15'`, sans le
    `Z` que la source déclare pourtant, alors que la branche RFC 2822 rend
    bien `'…T07:00Z'`. Le même écran affichait donc les communiqués BCE
    marqués UTC et les communiqués BNS sans marque, pour deux flux également
    horodatés en UTC. Un décalage déclaré (`+02:00`) était encore plus faux :
    l'heure locale était servie telle quelle, sans marque, comme si aucun
    fuseau n'avait été déclaré.

    Règle : on CONSERVE ce que la source déclare (`Z` → `Z`, décalage →
    converti en UTC comme le fait déjà la branche RFC 2822) et on n'invente
    rien quand elle ne déclare rien (pas de fuseau → pas de suffixe)."""
    s = str(t or '').strip()
    if not s:
        return None
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?'
                 r'\s*(Z|z|[+-]\d{2}:?\d{2})?$', s)
    if m:
        zone = (m.group(3) or '').strip()
        if not zone:
            #  La source n'a pas déclaré de fuseau : on n'en invente pas un.
            return '%sT%s' % (m.group(1), m.group(2))
        if zone in ('Z', 'z') or zone.replace(':', '') in ('+0000', '-0000'):
            return '%sT%sZ' % (m.group(1), m.group(2))
        import datetime as _dt
        signe = -1 if zone[0] == '-' else 1
        chiffres = zone[1:].replace(':', '')
        decale = _dt.timedelta(minutes=signe * (int(chiffres[:2]) * 60 + int(chiffres[2:])))
        base = _dt.datetime.strptime('%sT%s' % (m.group(1), m.group(2)), '%Y-%m-%dT%H:%M')
        return (base - decale).strftime('%Y-%m-%dT%H:%MZ')
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})', s)
    if m:
        #  Queue non reconnue (secondes exotiques, texte accolé) : on garde la
        #  date et l'heure lues, sans fuseau — jamais un fuseau supposé.
        return '%sT%s' % (m.group(1), m.group(2))
    try:
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    if d.tzinfo is not None:
        import datetime as _dt
        d = d.astimezone(_dt.timezone.utc)
        return d.strftime('%Y-%m-%dT%H:%MZ')
    return d.strftime('%Y-%m-%dT%H:%M')


def dedupe_news(items):
    """Consolide les doublons **sans perdre les sources**.

    `VERTEX-INTELLIGENCE-2.0` Phase 4, critere d'acceptation : « meme evenement
    consolide sans perdre les sources ».

    ## Le defaut, mesure le 26 aout 2026

    Cette fonction gardait le premier item et **jetait les autres**. Vertex
    collecte a la fois un flux RSS multi-agences et les depeches IBKR : la
    collision est structurelle, pas hypothetique. Mesure sur le cas reel du
    produit :

    ```text
    entree : 4 articles, 3 sources distinctes (Reuters, Bloomberg, IBKR)
    sortie : 2 articles
    SOURCES PERDUES : Bloomberg, IBKR
    ```

    Trois agences independantes rapportant le meme fait est une information
    **plus forte** qu'une seule. Le produit ne pouvait pas faire la difference :
    rien ne portait le nombre de sources.

    Effet de bord mesure : la depeche **IBKR** — le flux du courtier, celui du
    desk — est systematiquement celle qu'on jetait, par simple ordre d'arrivee,
    parce qu'elle n'a pas d'URL et arrive apres le RSS.

    ## Ce qui ne change pas

    Le premier item reste conserve **et jamais reecrit**, l'ordre d'arrivee est
    preserve, les entrees non-dict ignorees. On AJOUTE `sources` et
    `n_sources` ; on ne deplace rien.
    """
    out, par_titre, par_lien = [], {}, {}
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        cle_titre = re.sub(r'[^a-z0-9]+', ' ', str(it.get('title') or '').lower()).strip()
        lien = str(it.get('link') or '').strip()
        garde = (par_titre.get(cle_titre) if cle_titre else None)             or (par_lien.get(lien) if lien else None)
        origine = {'pub': nom_publieur(it) or None,
                   'link': it.get('link') or None,
                   'time': it.get('time') or None}
        if garde is not None:
            #  Doublon : on n'ecrase RIEN, on enregistre la source de plus.
            if origine not in garde['sources']:
                garde['sources'].append(origine)
                garde['n_sources'] = len(garde['sources'])
            continue
        d = dict(it)
        d['sources'] = [origine]
        d['n_sources'] = 1
        if cle_titre:
            par_titre[cle_titre] = d
        if lien:
            par_lien[lien] = d
        out.append(d)
    return out


__all__ = ['sentiment', 'aggregate', 'parse_rss', 'rss_news', 'sanitize_news',
           'dedupe_news', 'nom_publieur', 'CLES_PUBLIEUR', 'horodatage_source',
           'sujet_confirme', 'role_sujet', 'marquer_sujets', 'NOMS_SOCIETE']
