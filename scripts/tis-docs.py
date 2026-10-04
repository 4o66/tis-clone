#!/usr/bin/env python3
"""Download standalone TIS documents by type and ID: service bulletins, collision repair bulletins,
campaigns, accessory installation instructions, quick training guides.

Each document's page is /t3Portal/external/en/<type>/<ID>/xhtml/<ID>.html.  Most are a chain of JS
`location='...'` redirects ending at a PDF, saved as <DOWNLOAD_TO>/docs/<type>/<ID>.pdf.  A page that
is real content is saved as <ID>.html, with its images under the usual techinfo.toyota.com tree.

Types seen in TIS's library search results (the objType= in each result link):
  sb          service bulletins; older ones are T-<ID>, e.g. T-BO005-92
  sb-usa-tdm  newer US service bulletins, e.g. T-SB-0012-21
  sb-tdm      e.g. T-TDM-PA005-04
  sb-tci      Canadian bulletins, e.g. T-TCI-0961
  crib        collision repair information bulletins, e.g. T-CRIB-201-D
  cp          service campaigns
  ai, ai-gst, ai-set   accessory installation instructions
  qtg         quick training guides

Stops with exit 3 when TIS rejects the session.  Reads COOKIES, DOWNLOAD_TO, WEBSITE and SIID from
the environment (get-docs.sh exports them from tis-clone.cfg).

usage: tis-docs.py TYPE:ID [TYPE:ID ...]
"""
import http.cookiejar, os, re, sys, time, urllib.error, urllib.request

SITE = os.environ.get('WEBSITE', 'https://techinfo.toyota.com').rstrip('/')
ROOT = os.path.join(os.environ['DOWNLOAD_TO'], 'techinfo.toyota.com')
SIID = '?sisuffix=ff&locale=en&siid=' + os.environ.get('SIID', '1520435234586')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0'
jar = http.cookiejar.MozillaCookieJar(os.environ['COOKIES'])
jar.load(ignore_discard=True, ignore_expires=True)
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [('User-Agent', UA)]


class Rejected(Exception):
    pass


def rejected(final_url):
    # Documents live under /t3Portal/.  A rejected session ends up at concurrentLoginFailure.html, or
    # is redirected via /techInfoPortal/login/ to the pre-login home page, which answers 200.
    return 'concurrentLoginFailure' in final_url or '/techInfoPortal/' in final_url


def get(path):
    time.sleep(0.5)
    try:
        with opener.open(SITE + path, timeout=60) as r:
            if rejected(r.geturl()):
                raise Rejected(path)
            return 200, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''


ok, bad = [], []
try:
    for spec in sys.argv[1:]:
        typ, doc = spec.split(':', 1)
        OUT = os.path.join(os.environ['DOWNLOAD_TO'], 'docs', typ)
        os.makedirs(OUT, exist_ok=True)
        path = f'/t3Portal/external/en/{typ}/{doc}/xhtml/{doc}.html' + SIID
        body = b''
        for hop in range(5):
            code, body = get(path)
            if body[:5] == b'%PDF-':
                break
            m = re.search(rb"location\s*=\s*['\"]([^'\"]+)['\"]", body)
            if not m or b'concurrentLoginFailure' in m.group(1):
                break
            path = m.group(1).decode()
        if body[:5] == b'%PDF-':
            open(os.path.join(OUT, doc + '.pdf'), 'wb').write(body)
            ok.append(doc); print('pdf ', doc, flush=True)
        elif code == 200 and b'No documents were found' not in body and len(body) > 1500:
            open(os.path.join(OUT, doc + '.html'), 'wb').write(body)
            for src in set(re.findall(rb'src="(/t3Portal/[^"?#]+)"', body)):
                dst = ROOT + src.decode()
                if not os.path.exists(dst) and not src.endswith(b'.js'):
                    c, img = get(src.decode())
                    if c == 200 and img:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        open(dst, 'wb').write(img)
            ok.append(doc); print('html', doc, flush=True)
        else:
            bad.append(doc); print('FAIL', doc, code, len(body), flush=True)
except Rejected as e:
    print(f'TIS rejected the session at {e}: it expired, or the account is logged in elsewhere.', flush=True)
    sys.exit(3)
finally:
    jar.save(ignore_discard=True, ignore_expires=True)
print(f'{len(ok)} ok, {len(bad)} failed: {" ".join(bad)}', flush=True)
