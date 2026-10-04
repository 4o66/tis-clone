#!/usr/bin/env python3
"""Fetch every document in a TIS toc.xml, plus the images it references, skipping what is on disk.

Called by dl-html-inc.sh. The old loop started `wget -m` once per document, so each page re-requested
the shared stylesheet, script, robots.txt and page graphics, and followed every cross-reference into a
?linkId= redirect stub: about 29 requests per page, 6-10 of them content. This makes about
1 + (new images) requests per page at the same pacing, about six times faster.

Files land where wget put them, so toc2html, the PDF tools and tis-urlstripper.sh work unchanged, and
a rerun only fetches what is missing.

Stops with exit 3 when TIS rejects the session (concurrent login, issue #11, or expired), so a long run
can't quietly fill the tree with error pages.

Reads COOKIES, FSM_URLBASE, WEBSITE, SIID and WAIT from the environment (dl-html-inc.sh exports them
from tis-clone.cfg).

usage: tis-fetch.py TOC_URL_PATH        e.g. /t3Portal/external/en/rm/RM27J0U
"""
import http.cookiejar, os, re, sys, time, urllib.error, urllib.request, xml.etree.ElementTree as ET

FOLDER = sys.argv[1].rstrip('/')
SITE = os.environ.get('WEBSITE', 'https://techinfo.toyota.com').rstrip('/')
ROOT = os.environ['FSM_URLBASE'].rstrip('/')
WAIT = float(os.environ.get('WAIT', '0.5'))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0'
SIID = '?sisuffix=ff&locale=en&siid=' + os.environ.get('SIID', '1520435234586')
KNOWN_404 = {'/t3Portal/stylegraphics/clear.gif'}

jar = http.cookiejar.MozillaCookieJar(os.environ['COOKIES'])
jar.load(ignore_discard=True, ignore_expires=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [('User-Agent', UA)]
requests = 0


class Rejected(Exception):
    pass


def rejected(final_url):
    # Documents live under /t3Portal/.  A rejected session ends up at concurrentLoginFailure.html, or
    # is redirected via /techInfoPortal/login/ to the pre-login home page, which answers 200.
    return 'concurrentLoginFailure' in final_url or '/techInfoPortal/' in final_url


def get(path, query=''):
    global requests
    time.sleep(WAIT)
    requests += 1
    try:
        with opener.open(SITE + path + query, timeout=60) as r:
            if rejected(r.geturl()):
                raise Rejected(path)
            body = r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    if b'concurrentLoginFailure' in body[:2000]:
        raise Rejected(path)
    return 200, body


def save(path, body):
    dst = ROOT + path
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst + '.part', 'wb') as f:
        f.write(body)
    os.replace(dst + '.part', dst)


done = failed = images = streak = 0
MAX_STREAK = 10   # this many failed pages in a row means the session or site is broken, not the pages
start = time.time()
try:
    toc_path = FOLDER + '/toc.xml'
    if not os.path.exists(ROOT + toc_path):
        code, body = get(toc_path)
        if code != 200:
            sys.exit(f'toc.xml: HTTP {code}')
        save(toc_path, body)
    hrefs = []
    for it in ET.parse(ROOT + toc_path).getroot().iter('item'):
        h = it.get('href') or ''
        if h.endswith('.html') and h not in hrefs:
            hrefs.append(h)
    have = sum(os.path.exists(ROOT + h) for h in hrefs)
    print(f'{FOLDER}: {len(hrefs)} documents, {have} already on disk', flush=True)
    for i, h in enumerate(hrefs, 1):
        if not os.path.exists(ROOT + h):
            code, body = get(h, SIID)
            if code != 200 or not body:
                print(f'FAIL {code} {h}', flush=True)
                failed += 1
                streak += 1
                if streak >= MAX_STREAK:
                    print(f'{streak} pages in a row failed; stopping. Check the session with confirm-login.sh.', flush=True)
                    sys.exit(3)
                continue
            save(h, body)
            done += 1
            streak = 0
        else:
            body = open(ROOT + h, 'rb').read()
        for src in set(re.findall(rb'src="(/t3Portal/[^"?#]+)"', body)):
            src = src.decode()
            if src in KNOWN_404 or src.endswith('.js') or os.path.exists(ROOT + src):
                continue
            code, img = get(src)
            if code == 200 and img:
                save(src, img)
                images += 1
            else:
                KNOWN_404.add(src)
                print(f'FAIL {code} {src}', flush=True)
        if i % 100 == 0:
            rate = done / max(time.time() - start, 1) * 60
            print(f'  {i}/{len(hrefs)}: {done} pages, {images} images, {failed} failed, '
                  f'{requests} requests, {rate:.1f} pages/min', flush=True)
except Rejected as e:
    print(f'TIS rejected the session at {e}: it expired, or the account is logged in elsewhere.', flush=True)
    print('Log out of TIS in any browser, run tis-login.sh, then rerun; files already fetched are kept.', flush=True)
    sys.exit(3)
finally:
    # TIS rotates portal cookies during long runs. Write them back, or the next tool to read
    # cookies.txt presents a stale session and TIS treats it as a second login.
    jar.save(ignore_discard=True, ignore_expires=True)
print(f'done: {done} pages, {images} images fetched, {failed} failed, {requests} requests', flush=True)
sys.exit(1 if failed else 0)
