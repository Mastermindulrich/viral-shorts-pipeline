"""Channel preferences. Metadata screening is a heuristic, not artist verification."""
import re

VERSION='fresh-coherent-180s-v4'
# The former one-minute cap was removed. Keep a practical three-minute ceiling so
# clips remain short-form and rendering/upload costs remain bounded.
MAX_CLIP_SECONDS=180
# Sources must be finished, publicly downloadable videos short enough to process
# locally. Discovery and import share these limits so step 1 never offers a video
# that the download step will refuse.
MAX_SOURCE_SECONDS=20*60
MIN_SOURCE_SECONDS=30
# Owner focus (2026-11-22): GTA 6 is trending, so it keeps one search per scan and a
# small ranking boost. Later the same day the owner widened the channel back to viral
# moments across the spectrum (news, politics, geopolitics, celebrities, culture), so
# GTA no longer dominates; see scouting.trending_queries for the "what is buzzing today" source.
FOCUS={'name':'GTA 6 gameplay',
       'pattern':r'\bgta\s*-?\s*(6|vi)\b|\bgta6\b|grand\s+theft\s+auto\s*(6|vi)\b',
       'queries':['"GTA 6" gameplay funny moments','"GTA 6" gameplay first time playing reaction',
                  '"GTA 6" streamer gameplay crazy moment','"GTA 6" police chase gameplay',
                  '"GTA 6" gameplay commentary','"GTA 6" online gameplay chaos',
                  '"GTA 6" gameplay vice city exploring','"GTA 6" fails glitches gameplay']}

def is_focus(item):
    # Title and description only: a search hit is not GTA footage just because the query was.
    text=str(item.get('title',''))+' '+str(item.get('description',''))[:600]
    return bool(re.search(FOCUS['pattern'],text,re.I))

TOPICS=[
    {'name':'Champions League and football','query':'"Champions League" | Mbappe | Messi | Ronaldo reaction controversy goal fan footage'},
    {'name':'Viral sports moments','query':'NBA | basketball | football | tennis incredible moment controversy athlete reaction'},
    {'name':'Influencer life','query':'influencer creator drama surprise lifestyle viral moment'},
    {'name':'Streamer moments','query':'Kai Cenat | IShowSpeed | streamer viral moment reaction'},
    {'name':'Just happened','query':'breaking unexpected unbelievable caught on camera incident'},
    {'name':'Sports controversies','query':'athlete football player apology controversy interview reaction'},
    {'name':'Movie scenes and fan cuts','query':'fan reaction theater moment premiere crowd -"official clip" -movieclips'},
    {'name':'Engineering hacks','query':'engineering hack invention clever mechanism demonstration'},
    {'name':'Celebrity viral footage','query':'celebrity red carpet beach fashion paparazzi viral moment'},
    {'name':'Gaming and streamers','query':'gaming streamer funny intense viral moments'},
    {'name':'Hot interviews','query':'heated revealing celebrity interview viral'},
    {'name':'African urban dance','query':'African urban dance amapiano afrobeats azonto dance'},
    {'name':'TikTok dance challenges','query':'TikTok viral dance challenge'},
    {'name':'Movie trailers','query':'trailer reaction breakdown things you missed'},
    {'name':'Music reactions','query':'music video reaction first time hearing'},
    {'name':'Breaking news today','query':'breaking news today what happened reaction'},
    {'name':'Politics today','query':'politics news today speech debate moment'},
    {'name':'World news and geopolitics','query':'world news today geopolitics conflict announcement'},
    {'name':'Celebrity news','query':'celebrity news today viral moment interview'}]

def discovery_config(config):
    """Overlay policy on old local configs, which the updater deliberately preserves."""
    result=dict(config)
    topics=[dict(x) for x in config.get('topics',[]) if x['name'] not in
            ('Music and concerts','Gaming and internet culture')]
    names={x['name'] for x in topics}
    topics.extend(dict(x) for x in TOPICS if x['name'] not in names)
    result['topics']=topics
    return result


def source_type(item):
    """Estimate only; channel names are not verified ownership badges."""
    channel=item.get('channelTitle',item.get('source',item.get('creator',''))).lower()
    if re.search(r'\bofficial\b|\b(espn|uefa|fifa|nba|nfl|sky sports|bbc|cnn|netflix)\b|vevo| - topic$',channel):
        return 'Likely official / publisher'
    return 'Unverified / possibly independent'

# Copyright guard (owner 2026-11-24): never clip uploads from the rights holders themselves
# (studios, TV networks, streaming services, record labels, game publishers, sports leagues and
# broadcasters, news networks) and never clip their official cuts (official trailers, official
# clips, full episodes), even when someone else re-uploads them, because Content ID claims those.
# Footage that other people filmed or posted (fans, eyewitnesses, streamers, commentators,
# reactions and breakdowns) stays allowed. Matching is on channel names and titles, an estimate.
RIGHTS_HOLDER_NAMES=[
    # Film studios and streaming services
    'hbo','hbo max','max','disney','disney plus','disney\\+','walt disney studios','marvel','marvel entertainment','marvel studios',
    'pixar','lucasfilm','star wars','dreamworks','dreamworks animation','warner bros','warner bros pictures','warner bros entertainment',
    'universal pictures','universal studios','illumination','sony pictures','sony pictures entertainment','columbia pictures',
    'paramount','paramount pictures','paramount plus','paramount\\+','lionsgate','lionsgate movies','a24','neon','focus features',
    '20th century studios','searchlight pictures','mgm','amazon mgm studios','prime video','amazon prime video','netflix',
    'netflix is a joke','apple tv','apple tv plus','apple tv\\+','hulu','peacock','crunchyroll','legendary','blumhouse','studiocanal',
    'movieclips','movieclips trailers','fandango','fandango movieclips','rotten tomatoes trailers','kinocheck','zero media',
    # TV networks and entertainment channels
    'nbc','abc','cbs','fox','fx','fx networks','amc','showtime','starz','bbc','bbc one','bbc three','itv','channel 4','sky',
    'comedy central','mtv','bet','e! entertainment','bravo','tlc','discovery','national geographic','nat geo','history',
    'cartoon network','adult swim','nickelodeon','the tonight show starring jimmy fallon','jimmy kimmel live','the late show with stephen colbert',
    'late night with seth meyers','the daily show','saturday night live','snl','the graham norton show','the ellen show',
    'the kelly clarkson show','good morning america','today','60 minutes','wwe','aew',
    # News networks
    'cnn','fox news','msnbc','nbc news','abc news','cbs news','cbs mornings','bbc news','sky news','al jazeera english',
    'reuters','associated press','the associated press','cnbc','bloomberg','bloomberg television','the guardian','the new york times',
    'the washington post','wall street journal','the wall street journal','pbs newshour','nbc nightly news','channel 4 news','itv news',
    'global news','cbc news','ctv news','france 24 english','dw news','times radio','gb news','newsmax','fox business',
    # Record labels and music companies
    'universal music group','umg','sony music','sony music entertainment','warner music','warner music group','atlantic records',
    'interscope','interscope records','def jam','def jam recordings','columbia records','rca records','capitol records',
    'republic records','island records','epic records','motown','big machine','hybe labels','smtown','jyp entertainment',
    'yg entertainment','mavin records','chocolate city','ymcmb','top dawg entertainment','ovo sound',
    # Game publishers (official trailers, reveals)
    'rockstar games','playstation','xbox','nintendo','nintendo of america','ea','electronic arts','ea sports','ubisoft',
    'activision','call of duty','blizzard entertainment','bethesda','square enix','capcom','bandai namco','sega','epic games',
    'fortnite','riot games','valve','2k','2k games','nba 2k','take-two interactive',
    # Sports leagues, clubs' rights holders and broadcasters
    'nba','nfl','mlb','nhl','mls','wnba','fifa','uefa','uefa champions league','premier league','laliga','la liga','bundesliga',
    'serie a','ligue 1','ufc','pga tour','atp tour','wta','formula 1','f1','nascar','olympics','espn','espn fc','espn uk',
    'sky sports','sky sports football','sky sports news','bt sport','tnt sports','tnt sports football','cbs sports','cbs sports golazo',
    'nbc sports','fox sports','dazn','dazn boxing','bein sports','sportsnet','tsn','house of highlights','bleacher report',
    'nfl films','nba on tnt','top rank boxing','matchroom boxing']
CHANNEL_SUFFIX=r'(?:\s+(?:official|channel|tv|uk|us|usa|ca|canada|india|australia|movies|trailers|on demand|news|hd|global|international|family|entertainment|studios|youtube))*'
RIGHTS_HOLDER=re.compile(r'^(?:the\s+)?(?:'+'|'.join(RIGHTS_HOLDER_NAMES)+r')'+CHANNEL_SUFFIX+r'$',re.I)
OFFICIAL_CUT=re.compile(r'\bofficial\s+(?:(?:final|teaser|international|uk|us|red band|launch|reveal|story|gameplay)\s+)?(?:trailer|teaser|clip|sneak peek|promo|featurette)\b|'
                        r'\bfull\s+episodes?\b|\bfull\s+movie\b|\bmovie\s*clip\b|\bscene\s*\(\d{4}\)|\|\s*movieclips\b',re.I)
COMMENTARY=re.compile(r'\b(react(?:s|ing|ion|ions)?|breakdown|explained|analysis|review|first time (?:watching|hearing|seeing)|things you missed|easter eggs|theory|theories|predictions?)\b',re.I)


def normal_channel(item):
    name=str(item.get('channelTitle') or item.get('source') or item.get('creator') or '').strip()
    return re.sub(r'\s+',' ',re.sub(r'[\u2122\u00ae|•·:()\[\]_.,!-]+',' ',name)).strip()


def copyright_overrides():
    """Owner edits in config/copyright.json: allow_channels / block_channels (exact names, any case)."""
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parent/'config'/'copyright.json'
    try: data=json.loads(path.read_text()) if path.exists() else {}
    except (OSError,ValueError): data={}
    clean=lambda values:{normal_channel(dict(source=x)).casefold() for x in values or [] if str(x).strip()}
    return clean(data.get('allow_channels')),clean(data.get('block_channels'))


def copyright_risk(item):
    """Plain-English reason a video is likely the rights holder's own material, or ''.

    An estimate from channel name and title. Fan, eyewitness, streamer, reaction and
    commentary uploads are allowed; an official cut stays blocked even when re-uploaded."""
    channel=normal_channel(item)
    allowed,blocked=copyright_overrides()
    if channel.casefold() in allowed: return ''
    if channel and (RIGHTS_HOLDER.match(channel) or channel.casefold() in blocked):
        return f'Official rights-holder channel ({channel}): skipped to avoid copyright claims'
    title=str(item.get('title',''))
    if OFFICIAL_CUT.search(title) and not COMMENTARY.search(title):
        return 'Official studio, network or publisher cut (trailer, clip or episode): skipped to avoid copyright claims'
    return ''


def screen(item):
    title=item.get('title','').lower()
    channel=item.get('channelTitle',item.get('source',item.get('creator',''))).lower()
    description=item.get('description','').lower()
    reaction=bool(re.search(r'\b(reacts?|reacting|reaction|reactions)\b|first time (hearing|listening)',title))
    trailer=bool(re.search(r'\b(trailer|teaser)\b',title))
    # A genre or the word "dance" alone may just be a song title.
    dance=bool(re.search(r'\b(choreography|choreo|dancing|dancers)\b|'
                         r'\bdance\s+(challenge|cover|tutorial|performance|battle|routine|practice|compilation)\b|'
                         r'\b(african|amapiano|azonto)\b.*\bdance\b|\btiktok\b.*\bdance\b|#dancechallenge',title))
    spoken_format=bool(re.search(r'\b(interview|podcast|conversation|debate|gameplay)\b',title))
    official=bool(re.search(r'\bofficial\s+(music\s+)?(video|audio|visuali[sz]er|lyric(?:s)?(?: video)?)\b',title))
    release_label=bool(re.search(r'\b(music video|lyric(?:s)?(?: video)?|visuali[sz]er|official audio|audio only)\b|'
                                 r'(?<!\w)m\s*/?\s*v(?!\w)|\((audio|remix|sped up|slowed(?: down)?)\)',title))
    if (official or release_label) and reaction:
        reaction=bool(re.search(r'\breact(?:s|ing)?\s+to\b|\breaction\s+to\b|first time (hearing|listening)|^reaction\s*[:|]|\breactions?\s*[!?.]*$',title))
    artist_channel=('vevo' in channel or channel.endswith(' - topic'))
    music_category=str(item.get('categoryId',''))=='10'
    auto_music='provided to youtube by' in description or 'auto-generated by youtube' in description
    release=official or release_label or music_category or artist_channel or auto_music
    # A Music category upload must clearly be an allowed editorial/visual format.
    # Never exempt a release solely because it mentions amapiano, dance, or a genre.
    allowed_format=reaction or trailer or spoken_format or (dance and not official and not release_label)
    if release and not allowed_format:
        return dict(eligible=False,reason='Standalone music video/audio or Music-category release',kind='music_release',language_status='unchecked')
    risk=copyright_risk(item)
    if risk:
        return dict(eligible=False,reason=risk,kind='copyright',language_status='unchecked')
    audio=str(item.get('defaultAudioLanguage',item.get('audio_language','')) or '').lower()
    english=audio=='en' or audio.startswith('en-') or audio=='eng'
    visual=dance and not reaction and not trailer
    if audio and not english and not visual:
        return dict(eligible=False,reason='Declared audio is not English',kind='spoken',language_status=audio)
    kind='reaction' if reaction else 'trailer' if trailer else 'dance' if dance else 'spoken'
    language='English declared' if english else 'Visual dance — review dialogue' if visual else 'Language needs verification'
    return dict(eligible=True,reason='Matches channel screening rules',kind=kind,language_status=language)

def source_problem(item):
    """Plain-English reason a discovered video cannot be processed, or '' when it can.

    Uses only fields already present in the saved metadata, so stale saved results
    are filtered as well as new scans."""
    live=str(item.get('live_status') or item.get('liveBroadcastContent') or '').lower()
    if live in ('live','is_live','upcoming','is_upcoming','post_live'):
        return 'Still live, upcoming or still processing after a live stream'
    if item.get('live_started') and not item.get('live_ended'):
        return 'Still live, upcoming or still processing after a live stream'
    seconds=item.get('duration_seconds')
    if seconds is not None:
        if seconds<MIN_SOURCE_SECONDS: return f'Shorter than {MIN_SOURCE_SECONDS} seconds'
        if seconds>MAX_SOURCE_SECONDS: return f'Longer than {MAX_SOURCE_SECONDS//60} minutes'
    if item.get('age_restricted'): return 'Age-restricted (needs a signed-in download)'
    if item.get('privacy') not in (None,'','public'): return 'Not a public video'
    if item.get('upload_status') not in (None,'','processed'): return 'YouTube is still processing this video'
    if item.get('region_blocked'): return 'Blocked in your region'
    if item.get('unsupported'): return 'Could not be downloaded earlier: '+str(item['unsupported'])[:160]
    return ''


def visible_candidates(items):
    """Re-screen saved results too; never show excluded releases after an update."""
    result=[]
    for item in items:
        decision=screen(item)
        if decision['eligible']: result.append(dict(item,policy=decision))
    return result


# Niches (owner 2026-11-24: "easily clickable shorts in many niches"). Used to keep the
# shortlist and the posting order varied and to learn which niches the channel's viewers like.
NICHES=[
    ('GTA 6 and gaming',r'\b(gta\s*-?\s*(?:6|vi)|gta6|gameplay|gaming|gamer|fortnite|minecraft|call of duty|playstation|xbox|nintendo)\b'),
    ('World news',r'\b(war|iran|israel|gaza|russia|ukraine|china|taiwan|nato|missile|strike|sanction|ceasefire|un security|geopolit|border|refugee|summit)\b'),
    ('Politics',r'\b(politic\w*|president|senate|congress|election|vote|minister|parliament|trump|biden|harris|white house|governor|mayor|campaign|debate)\b'),
    ('Crime and incidents',r'\b(arrest\w*|police|caught on camera|crash|fire|shooting|robbery|chase|incident|accident|evacuat\w*|explosion|rescue|storm|flood|earthquake)\b'),
    ('Celebrities',r'\b(celebrit\w*|red carpet|paparazzi|premiere|met gala|oscars|grammys?|kardashian|beyonc\w*|taylor swift|drake|rihanna|diddy|kanye|actor|actress|singer|rapper)\b'),
    ('Football',r'\b(champions league|premier league|football|soccer|mbapp\w*|messi|ronaldo|haaland|real madrid|barcelona|arsenal|chelsea|liverpool|man(?:chester)? (?:united|city))\b'),
    ('Sports',r'\b(nba|nfl|mlb|ufc|boxing|tennis|basketball|lebron|curry|olympic\w*|athlete|f1|formula 1|golf|wrestl\w*|fight|knockout)\b'),
    ('Streamers and creators',r'\b(streamer|kai cenat|ishowspeed|speed|adin ross|mrbeast|twitch|kick|creator|influencer|youtuber|vlog\w*)\b'),
    ('Money and business',r'\b(billion\w*|million\w*|stock\w*|market|crypto|bitcoin|elon|musk|ceo|business|startup|tesla|amazon|apple|salary|rich)\b'),
    ('Tech and engineering',r'\b(ai|robot\w*|engineer\w*|invention|hack|mechanism|tech|iphone|spacex|nasa|rocket|space|science|experiment|machine)\b'),
    ('Dance and music culture',r'\b(dance|amapiano|afrobeats?|azonto|choreo\w*|tiktok|concert|festival|music reaction)\b'),
    ('Movies and TV',r'\b(movie|film|trailer|series|season|episode|netflix|marvel|cinema|box office|anime)\b'),
    ('Interviews and debates',r'\b(interview|podcast|debate|heated|confront\w*|argument|clapback|responds?|reacts?)\b')]
NICHE_NAMES=[name for name,_ in NICHES]+['Viral moments']


def niche(item):
    """The first matching niche for a video or clip (title, then description start)."""
    text=' '.join(str(item.get(k,'')) for k in ('title','source_title','discovered_via'))+' '+str(item.get('description',''))[:300]
    for name,pattern in NICHES:
        if re.search(pattern,text,re.I): return name
    return 'Viral moments'


CLICK_WORDS=r'\b(slams?|destroys?|exposed?|reacts?|responds?|confronts?|caught|insane|crazy|shocking|unbelievable|first time|finally|banned|fired|arrested|leaked?|record|history|breaking|just|live reaction|goes viral|walks? off|storms? off|breaks? down|cries|apolog\w*|refuses?|warns?|reveals?|admits?|chaos|meltdown|wins?|loses?|vs\.?)\b'
DULL_WORDS=r'\b(compilation|part \d+|ep(?:isode)?\.? ?\d+|full (?:stream|podcast|video|interview|show|match)|vod|day \d+|week \d+|#shorts|asmr|lofi|playlist|livestream|live stream|stream highlights|unboxing|tutorial|how to)\b'


def clickability(item):
    """0-20 estimate of how clickable a title is: a concrete subject, a number, tension or news.
    A heuristic on the title only, used as a tie-breaker in ranking, never as a filter."""
    title=str(item.get('title',''))
    score=0
    names=re.findall(r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b',title)
    if names: score+=4 if len(names)>=2 else 3
    if re.search(r'\d',title): score+=3
    score+=min(8,4*len(re.findall(CLICK_WORDS,title,re.I)))
    if '?' in title or re.search(r'\b(why|how|what happened|nobody expected)\b',title,re.I): score+=2
    if 25<=len(title)<=90: score+=3
    if re.search(DULL_WORDS,title,re.I): score-=8
    if title.isupper() and len(title)>20: score-=2
    return max(0,min(20,score))
