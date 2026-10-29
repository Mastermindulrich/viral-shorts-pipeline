"""Saved production defaults and local-time publishing history."""
import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import pipeline as p

DEFAULTS = dict(captions=True, count='auto', transcription_model='small',
                editor_model='qwen2.5:7b', timezone='America/Toronto', clearance='')


def preferences():
    path = p.DATA/'studio-preferences.json'
    return dict(DEFAULTS, **(p.read(path) if path.exists() else {}))


def save_preferences(values):
    result = dict(preferences(), **values)
    ZoneInfo(result['timezone'])
    if result['transcription_model'] not in ('base', 'small', 'medium'):
        raise ValueError('Choose base, small or medium transcription')
    result['count'] = 'auto' if result['count'] in (None, 'auto') else min(5, max(1, int(result['count'])))
    with p.lock(): p.write(p.DATA/'studio-preferences.json', result)
    return result


def publication_time(record, timezone='America/Toronto'):
    """Old receipts contain only a UTC day; do not invent a precise local time."""
    value = record.get('published_at') or record.get('uploaded_at')
    if value:
        try:
            instant = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if instant.tzinfo is None: return None, 'Unknown time'
            local = instant.astimezone(ZoneInfo(timezone))
            return local.date(), local.strftime('%Y-%m-%d %H:%M %Z')
        except (ValueError, TypeError, ZoneInfoNotFoundError): pass
    try:
        day = dt.date.fromisoformat(record.get('day', ''))
        return day, day.isoformat()+' (legacy UTC date; exact time unavailable)'
    except (ValueError, TypeError): return None, 'Unknown date'


def publication_rows(jobs, timezone='America/Toronto'):
    rows = []
    for path, job in jobs:
        receipt = path.parent/'upload.json'
        if not receipt.exists(): continue
        record = p.read(receipt)
        day, label = publication_time(record, timezone)
        rows.append(dict(job=job, record=record, path=path, day=day, date_label=label))
    return sorted(rows, key=lambda x:(x['day'] or dt.date.min,
                  x['record'].get('uploaded_at', ''), x['job']['id']), reverse=True)


def filter_publications(rows, mode='All dates', day=None, year=None, month=None, query=''):
    result = []
    for row in rows:
        value = row['day']
        if mode in ('Today', 'Choose a day') and value != day: continue
        if mode in ('Month', 'Year') and (value is None or value.year != year): continue
        if mode == 'Month' and value.month != month: continue
        if query.strip() and query.casefold().strip() not in row['job']['title'].casefold(): continue
        result.append(row)
    return result


def sync_publication_dates():
    """Read YouTube timestamps to backfill legacy receipts; never change visibility."""
    from googleapiclient.discovery import build
    lookup={}
    for path in (p.DATA/'exports').glob('*/upload.json'):
        record=p.read(path)
        if record.get('video_id'):
            lookup[record['video_id']]=(path,record)
    if not lookup: return 0
    service=build('youtube','v3',credentials=p.credentials(),cache_discovery=False)
    ids=list(lookup); updated=0
    for offset in range(0,len(ids),50):
        result=service.videos().list(part='snippet,status',id=','.join(ids[offset:offset+50])).execute()
        for item in result.get('items',[]):
            if item.get('id') not in lookup: continue
            value=item.get('snippet',{}).get('publishedAt')
            if not value: continue
            instant=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            if instant.tzinfo is None: continue
            path,record=lookup[item['id']]
            record.update(published_at=value,privacy=item.get('status',{}).get('privacyStatus',record.get('privacy','unknown')))
            p.write(path,record); updated+=1
    return updated
