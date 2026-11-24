"""Post the news desk's headline images to the channel's Posts (Community) tab.

Owner choice (2026-11-23): images go on the Viral Moment Clips YouTube page. YouTube's Data API cannot
create Community posts, so this drives a real Chrome window on the Mac with its own saved sign-in
(Playwright persistent profile in data/community-browser). One-time setup on the Mac:

    .venv/bin/python -m pip install playwright
    .venv/bin/python community.py login      # sign in to the channel's Google account, then close the window

After that autopilot posts one pending image per hourly tick between 9:00 and 23:00. Every attempt is
recorded in the image's JSON (posted/attempts/last_error); a failure saves a screenshot in
data/newsdesk/community-errors/ and never blocks clips. YouTube can change its page at any time, so
selectors below try several strategies; `community.py check` reports what it finds without posting.
"""
import datetime as dt
import re
import sys
import time
from pathlib import Path

import pipeline as p

CHANNEL_ID='UC66Gf5TgUNxGHM7DbPUqrSw'
POSTS_URL=f'https://www.youtube.com/channel/{CHANNEL_ID}/posts'
STUDIO_URL=f'https://studio.youtube.com/channel/{CHANNEL_ID}'
MAX_ATTEMPTS=3
# Each list is tried in order; the first visible match wins.
OPEN_EDITOR=['ytd-backstage-post-dialog-renderer #commentbox','#placeholder-area','text=/share a sneak peek|create a post|what.s on your mind|share your thoughts/i',
             'button[aria-label*="Create post" i]','[role="button"]:has-text("Create post")']
TEXT_BOX=['ytd-backstage-post-dialog-renderer #contenteditable-root','#contenteditable-root[contenteditable="true"]',
          'div[contenteditable="true"][aria-label*="post" i]','div[contenteditable="true"]']
IMAGE_BUTTON=['ytd-backstage-post-dialog-renderer #image-button','button[aria-label="Image" i]','button[aria-label*="Add image" i]',
              '[role="button"][aria-label*="image" i]','text=/^image$/i']
SUBMIT=['ytd-backstage-post-dialog-renderer #submit-button button','#submit-button button','button[aria-label="Post" i]',
        'ytd-button-renderer:has-text("Post") button','button:has-text("Post")']


def profile():
    return p.DATA/'community-browser'


def errors_folder():
    return p.DATA/'newsdesk'/'community-errors'


def browser(playwright, headless=True):
    """Persistent Chrome profile. Real Chrome is preferred because Google refuses sign-in in test browsers."""
    options=dict(user_data_dir=str(profile()),headless=headless,viewport=dict(width=1280,height=900),
                 ignore_default_args=['--enable-automation'],args=['--disable-blink-features=AutomationControlled'])
    profile().mkdir(parents=True,exist_ok=True)
    try: return playwright.chromium.launch_persistent_context(channel='chrome',**options)
    except Exception: return playwright.chromium.launch_persistent_context(**options)


def first(page, selectors, timeout=4000):
    """The first selector with a visible element, or None."""
    deadline=time.time()+timeout/1000
    while True:
        for selector in selectors:
            try:
                handle=page.locator(selector).first
                if handle.count() and handle.is_visible(): return handle
            except Exception: continue
        if time.time()>=deadline: return None
        page.wait_for_timeout(400)


def signed_in(page):
    """Signed in when the avatar button exists and there is no Sign in link."""
    try:
        if page.locator('a[href*="accounts.google.com/ServiceLogin"], a[aria-label="Sign in"]').first.is_visible(): return False
    except Exception: pass
    return bool(first(page,['#avatar-btn','button#avatar-btn','ytd-topbar-menu-button-renderer img'],3000))


def publish(page, image, text, wait=1500):
    """Create one image post on the open Posts tab. Raises with a clear message at the step that failed."""
    page.goto(POSTS_URL,wait_until='domcontentloaded'); page.wait_for_timeout(wait)
    if not signed_in(page):
        raise PermissionError('Not signed in to YouTube in the posting browser. On the Mac run: .venv/bin/python community.py login')
    opener=first(page,OPEN_EDITOR,8000)
    if not opener:
        raise RuntimeError('No "create post" box on the Posts tab (the channel may not have posts enabled yet, or YouTube changed the page)')
    opener.click(); page.wait_for_timeout(600)
    box=first(page,TEXT_BOX,6000)
    if not box: raise RuntimeError('The post editor did not open')
    box.click(); page.keyboard.insert_text(text)
    button=first(page,IMAGE_BUTTON,4000)
    if button:
        try:
            with page.expect_file_chooser(timeout=6000) as chooser: button.click()
            chooser.value.set_files(str(image))
        except Exception:
            page.locator('input[type="file"]').first.set_input_files(str(image))
    else:
        page.locator('input[type="file"]').first.set_input_files(str(image))
    page.wait_for_timeout(2500)
    submit=first(page,SUBMIT,6000)
    if not submit: raise RuntimeError('No Post button in the editor')
    for _ in range(30):
        # The button stays disabled until the image finishes uploading.
        if submit.is_enabled(): break
        page.wait_for_timeout(1000)
    submit.click()
    page.wait_for_timeout(4000)
    if first(page,TEXT_BOX,1000) and first(page,SUBMIT,500) and submit.is_visible():
        raise RuntimeError('The post editor is still open after pressing Post')
    return True


def pending(days=2):
    """Unposted images from today and yesterday, oldest first, skipping ones that failed too often."""
    root=p.DATA/'newsdesk'/'images'
    if not root.exists(): return []
    cutoff=(dt.date.today()-dt.timedelta(days=days-1)).isoformat()
    items=[]
    for folder in sorted(x for x in root.iterdir() if x.is_dir() and x.name>=cutoff):
        for record_path in sorted(folder.glob('*.json')):
            try: record=p.read(record_path)
            except (OSError,ValueError): continue
            if record.get('posted') or record.get('attempts',0)>=MAX_ATTEMPTS: continue
            # Cards made before the 2026-11-23 fix could carry one-letter fact bullets: never post those.
            if any(len(str(f))<10 for f in record.get('card',{}).get('facts',[])): continue
            if (folder/record.get('image','')).exists(): items.append(record_path)
    return items


def post_next(limit=1, playwright_factory=None, headless=True):
    """Post up to `limit` pending images. Returns the posted record paths."""
    queue=pending()[:limit]
    if not queue: return []
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright
        playwright_factory=sync_playwright
    posted=[]
    with playwright_factory() as playwright:
        context=browser(playwright,headless)
        try:
            page=context.pages[0] if context.pages else context.new_page()
            for record_path in queue:
                record=p.read(record_path)
                image=record_path.parent/record['image']
                record['attempts']=record.get('attempts',0)+1
                try:
                    publish(page,image,record['caption'])
                    record.update(posted=True,posted_at=dt.datetime.now(dt.timezone.utc).isoformat(),last_error='')
                    posted.append(record_path)
                    print(f'Community post published: {record["card"]["headline"][:80]}',flush=True)
                except PermissionError:
                    p.write(record_path,dict(record,attempts=record['attempts']-1)); raise
                except Exception as exc:
                    if 'create post' in str(exc).lower():
                        # The Posts tab itself is unavailable, not this image: keep the image's attempts and
                        # stop; autopilot pauses image posts for a day instead of retrying every hour.
                        p.write(record_path,dict(record,attempts=record['attempts']-1,last_error=str(exc)[:300]))
                        raise
                    record['last_error']=str(exc)[:300]
                    errors_folder().mkdir(parents=True,exist_ok=True)
                    try: page.screenshot(path=str(errors_folder()/(record_path.stem+f'-{record["attempts"]}.png')))
                    except Exception: pass
                    print(f'Community post failed ({record["attempts"]}/{MAX_ATTEMPTS}): {exc}',flush=True)
                p.write(record_path,record)
        finally:
            context.close()
    return posted


def login():
    """Opens the posting browser so the owner can sign in once. Close the window when done."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        context=browser(playwright,headless=False)
        page=context.pages[0] if context.pages else context.new_page()
        page.goto('https://accounts.google.com/ServiceLogin?continue='+POSTS_URL)
        print('Sign in to the Google account that owns Viral Moment Clips, check the Posts tab opens, then close the window.')
        try: page.wait_for_event('close',timeout=0)
        except Exception: pass
        context.close()


def check():
    """Report what the posting browser sees, without posting."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        context=browser(playwright,headless=True)
        page=context.pages[0] if context.pages else context.new_page()
        page.goto(POSTS_URL,wait_until='domcontentloaded'); page.wait_for_timeout(3000)
        report=dict(signed_in=signed_in(page),create_box=bool(first(page,OPEN_EDITOR,6000)),pending=len(pending()))
        errors_folder().mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(errors_folder()/'check.png'))
        context.close()
    print(report)
    return report


if __name__=='__main__':
    command=sys.argv[1] if len(sys.argv)>1 else 'check'
    if command=='login': login()
    elif command=='check': check()
    elif command=='post': print(post_next(int(sys.argv[2]) if len(sys.argv)>2 else 1,headless='--show' not in sys.argv))
    else: print('Usage: python community.py login|check|post [count] [--show]')
