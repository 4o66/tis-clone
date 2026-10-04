#!/usr/bin/env python3
"""Find everything TIS has for one vehicle, by model and year or by VIN, and optionally download it.

Does what the library search page does: stores the division, model and year in the session
(ajax/setDataInSession.jsp), submits the search form, then reads each result tab
(_pageLabel=lib_rm_page, lib_ewd_page, ...). Every result link carries objType= and either the
manual's publication number or href=<type>/<ID>/xhtml/<ID>.html, which is all the other scripts need.

With --vin it first runs the Vehicle Inquiry lookup and reads the model and model year from it.

Prints the manuals (rm, ewdappu, ncf, cr) and standalone documents (bulletins, collision repair
bulletins, campaigns, accessory and training guides) as a plan, and writes it to
$DOWNLOAD_TO/<division>-<model>-<year>.plan.  With --download it then fetches all of it: manuals via
dl-html-inc.sh / dl-html-ewd.sh, documents via tis-docs.py.

Reads COOKIES, DOWNLOAD_TO, WEBSITE and SCRIPT_BASE from the environment (search.sh exports them
from tis-clone.cfg). Standard library only.

usage: tis-search.py [--division TOYOTA] --model "Prius Prime" --year 2019 [--download]
       tis-search.py --vin <17-character VIN> [--download]
       tis-search.py --list-models [--division TOYOTA]
"""
import argparse, html, http.cookiejar, os, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from html.parser import HTMLParser

SITE = os.environ.get('WEBSITE', 'https://techinfo.toyota.com').rstrip('/')
APP = SITE + '/t3Portal/appmanager/t3/ti'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0'
TABS = ['lib_rm_page', 'lib_ewd_page', 'lib_ncf_page', 'lib_cr_page', 'lib_tsb_page',
        'lib_cp_page', 'lib_accy_page', 'lib_qtg_page']
MANUALS = {'rm', 'ewdappu', 'ncf', 'cr'}

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


def fetch(url, data=None):
    time.sleep(0.5)
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    with opener.open(url, body, timeout=60) as r:
        if rejected(r.geturl()):
            raise Rejected(url.split('?')[0])
        return r.read().decode('utf-8', 'replace')


def session(name, value):
    fetch(SITE + '/t3Portal/ajax/setDataInSession.jsp?' + urllib.parse.urlencode(
        {'attValue': value, 'attName': name, 'time': int(time.time() * 1000)}))


def options(dataset, key, **extra):
    """getVehicle.jsp answers with JS: var _keys = [["value","label"], ...]"""
    q = {'dataset': dataset, 'key': key, 'target': 'x', 'addAll': 'true', 'formTagId': 'searchDocument',
         'isFireTarget': ''}
    q.update(extra)
    js = fetch(SITE + '/t3Portal/ajax/getVehicle.jsp?' + urllib.parse.urlencode(q))
    return [v for v, _ in re.findall(r'\["([^"]*)","([^"]*)"\]', js) if v != 'ALL']


class Forms(HTMLParser):
    """Collect each form's action and its named fields with their current values."""
    def __init__(self):
        super().__init__()
        self.forms, self.cur, self.select = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self.cur = {'id': a.get('id') or a.get('name') or '', 'action': html.unescape(a.get('action') or ''), 'fields': {}}
            self.forms.append(self.cur)
        elif self.cur is not None and tag == 'input' and a.get('name'):
            if a.get('type') in ('checkbox', 'radio') and 'checked' not in a:
                return
            self.cur['fields'][a['name']] = a.get('value') or ''
        elif self.cur is not None and tag == 'select' and a.get('name'):
            self.select = a['name']
            self.cur['fields'].setdefault(self.select, '')
        elif self.select and tag == 'option' and 'selected' in a:
            self.cur['fields'][self.select] = a.get('value') or ''

    def handle_endtag(self, tag):
        if tag == 'select':
            self.select = None
        elif tag == 'form':
            self.cur = None


def form(page_html, want):
    p = Forms()
    p.feed(page_html)
    for f in p.forms:
        if want in f['action'] or want == f['id']:
            return f
    sys.exit(f'search form ({want}) not found on the page; TIS may have changed')


def set_field(fields, part, value, required=True):
    for k in fields:
        if part in k:
            fields[k] = value
            return
    if required:
        sys.exit(f'form field containing {part!r} not found; TIS may have changed')


def lookup_vin(vin):
    page = fetch(APP + '?_nfpb=true&_pageLabel=t3_vin_page')
    f = form(page, 'vinLookup')
    set_field(f['fields'], 'actionForm.vin', vin)
    res = fetch(urllib.parse.urljoin(APP, f['action']), f['fields'])
    text = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', res)))
    # The page keeps some fields from earlier lookups; only trust it if it echoes this VIN
    # (shown with dashes, e.g. JTD-KARFP-7K3109314).
    echoed = re.search(r'VIN:\s*([A-HJ-NPR-Z0-9-]{17,21})', text)
    if not echoed or echoed.group(1).replace('-', '') != vin:
        sys.exit('VIN lookup found no vehicle for that VIN; check it')
    div = re.search(r'Division:\s*([A-Za-z]+)', text)
    model = re.search(r'Model:\s*(.+?)\s+(?:Grade|Model Year):', text)
    year = re.search(r'Model Year:\s*(\d{4})', text)
    if not (model and year) or not 1980 <= int(year.group(1)) <= 2100:
        sys.exit('VIN lookup found no vehicle for that VIN; check it')
    return (div.group(1).upper() if div else 'TOYOTA'), model.group(1).strip(), year.group(1)


def collect(page_html, found):
    for m in re.finditer(r'<a\b[^>]*>(.*?)</a>', page_html, re.S):
        tag, title = m.group(0), html.unescape(re.sub(r'<[^>]+>|\s+', ' ', m.group(1))).strip()
        raw = html.unescape(tag)
        ob = re.search(r'[?&]objType=([^&\'" ]+)', raw)
        if not ob or not title:
            continue
        typ = ob.group(1)
        pub = re.search(r'[?&](?:publicationNumber|ewdNo)=([^&\'" ]+)', raw)
        href = re.search(r'[?&]href=([^&\'" ]+)', raw)
        if typ in MANUALS and pub:
            key = (typ, urllib.parse.unquote(pub.group(1)))
        elif href:
            key = (typ, urllib.parse.unquote(href.group(1)).split(';')[0].split('/')[1])
        else:
            continue
        found.setdefault(key, title)


def next_links(page_html):
    links = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]*goNext[^"]*)"', page_html):
        u = re.sub(r';[A-Za-z0-9_]+=[^?]*', '', html.unescape(m.group(1)))
        if u not in links:
            links.append(urllib.parse.urljoin(APP, u))
    return links


def search(division, model, year):
    page = fetch(APP + '?_nfpb=true&_pageLabel=t3_library_repair_search')
    session('SEARCH_TYPE', 'repair')
    session('SEARCH_DIVISION', division)
    session('SEARCH_MODEL', model)
    session('SEARCH_YEAR', year)
    f = form(page, 'searchDocument')
    set_field(f['fields'], 'actionForm.division', division, required=False)
    set_field(f['fields'], 'actionForm.model', model)
    set_field(f['fields'], 'actionForm.year', year)
    fetch(urllib.parse.urljoin(APP, f['action']), f['fields'])

    found = {}   # (type, id) -> title
    for tab in TABS:
        tab_html = fetch(APP + '?_nfpb=true&_pageLabel=' + tab)
        collect(tab_html, found)
        # Long result lists are paged: each list has its own stateful "next >" link
        # (..._actionOverride=.../searchResult/goNext).  Follow each until it stops adding documents.
        for nxt in next_links(tab_html):
            for _ in range(50):
                before = len(found)
                page = fetch(nxt)
                collect(page, found)
                if len(found) == before or nxt not in next_links(page):
                    break
    return found


def main():
    ap = argparse.ArgumentParser(description='Find and download everything TIS has for one vehicle')
    ap.add_argument('--division', default='TOYOTA')
    ap.add_argument('--model')
    ap.add_argument('--year')
    ap.add_argument('--vin')
    ap.add_argument('--list-models', action='store_true')
    ap.add_argument('--download', action='store_true')
    a = ap.parse_args()
    try:
        if a.list_models:
            print('\n'.join(options('model', a.division)))
            return
        if a.vin:
            a.division, a.model, a.year = lookup_vin(a.vin.strip().upper())
            print(f'VIN is a {a.year} {a.division} {a.model}')
        if not (a.model and a.year):
            ap.error('give --model and --year, or --vin')
        years = options('year', a.model, division=a.division, year='ALL')
        if years and a.year not in years:
            sys.exit(f'TIS has no {a.year} {a.model}; years listed: {" ".join(years)}')
        found = search(a.division, a.model, a.year)
    except Rejected as e:
        sys.exit(f'TIS rejected the session at {e}: it expired, or the account is logged in elsewhere. '
                 'Run tis-renew.sh or tis-login.sh.')
    finally:
        jar.save(ignore_discard=True, ignore_expires=True)

    manuals = sorted(k for k in found if k[0] in MANUALS)
    docs = sorted(k for k in found if k[0] not in MANUALS)
    plan = os.path.join(os.environ['DOWNLOAD_TO'], re.sub(r'\W+', '-', f'{a.division}-{a.model}-{a.year}') + '.plan')
    with open(plan, 'w') as fh:
        for t, i in manuals + docs:
            fh.write(f'{t}:{i}\t{found[(t, i)]}\n')
    print(f'{len(manuals)} manuals, {len(docs)} documents (plan written to {plan})')
    for t, i in manuals:
        print(f'  {t:8} {i:12} {found[(t, i)][:70]}')
    counts = {}
    for t, _ in docs:
        counts[t] = counts.get(t, 0) + 1
    print('  documents: ' + ', '.join(f'{n} {t}' for t, n in sorted(counts.items())))

    if not a.download:
        return
    base = os.environ['SCRIPT_BASE']
    for t, i in manuals:
        if t == 'ewdappu':
            cmd = [base + '/dl-html-ewd.sh', i[2:]]
        else:
            cmd = [base + '/dl-html-inc.sh', f'/t3Portal/external/en/{t}/{i}']
        print('==>', ' '.join(cmd), flush=True)
        if subprocess.run(cmd, cwd=os.environ['DOWNLOAD_TO']).returncode != 0:
            sys.exit(f'{" ".join(cmd)} failed; fix that and rerun, files already fetched are kept')
    if docs:
        print(f'==> tis-docs.py ({len(docs)} documents)', flush=True)
        sys.exit(subprocess.run([sys.executable, base + '/tis-docs.py'] + [f'{t}:{i}' for t, i in docs]).returncode)


if __name__ == '__main__':
    main()
