"""Conservative public-page enrichment. Never infer prices or project identifiers."""
import copy
import ipaddress
import json
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

AGENT = 'PIGurbaniResearch/1.0'


def public_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError('Unsupported website address')
    addresses = socket.getaddrinfo(p.hostname, p.port or 443)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Non-public website address')
    return url


def fetch(url, allowed=None):
    """Retry temporary failures twice; never retry access denials."""
    for attempt in range(3):
        try:
            return _fetch_once(url, allowed)
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code not in (502, 503, 504):
                raise
            # Leave server-directed retry scheduling to a later search.
            if exc.response.headers.get('Retry-After'):
                raise
            if attempt == 2:
                raise
        except (requests.exceptions.SSLError, requests.exceptions.ProxyError):
            raise
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def _fetch_once(url, allowed=None):
    for _ in range(4):
        if allowed is not None and not allowed(url):
            raise ValueError('Redirect outside approved sources')
        public_url(url)
        with requests.get(url, headers={'User-Agent': AGENT}, timeout=(4, 8),
                          allow_redirects=False, stream=True) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            chunks = []
            size = 0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 1500000:
                    raise ValueError('Page too large')
                chunks.append(chunk)
            return b''.join(chunks).decode('utf-8', errors='replace'), url
    raise ValueError('Too many redirects')


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.text = []
        self.links = []
        self.schemas = []
        self.script = None
        self.hidden = 0
        self.heading = ''
        self.in_heading = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1':
            self.in_heading = True
        if tag in ('script', 'style'):
            self.hidden += 1
            if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
                self.script = ''
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])

    def handle_endtag(self, tag):
        if tag == 'h1':
            self.in_heading = False
        if tag in ('script', 'style'):
            if tag == 'script' and self.script is not None:
                try:
                    self.schemas.append(json.loads(self.script))
                except ValueError:
                    pass
                self.script = None
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if self.in_heading and not self.heading and value.strip():
            self.heading = value.strip()
        if self.script is not None:
            self.script += value
        elif not self.hidden and value.strip():
            self.text.append(value.strip())


def normalized(value):
    return ' '.join(re.findall(r'\w+', str(value).casefold()))


def matched(name, candidate):
    a, b = normalized(name), normalized(candidate)
    # Full source entity name must occur in the Google listing name.
    return len(b.split()) >= 2 and (b == a or (' ' + b + ' ') in (' ' + a + ' '))


def entities(value):
    if isinstance(value, list):
        for item in value:
            yield from entities(item)
    elif isinstance(value, dict):
        yield value
        if '@graph' in value:
            yield from entities(value['@graph'])


def number(value):
    if isinstance(value, dict):
        value = value.get('value')
    try:
        result = float(str(value).replace(',', ''))
        return result if 0 < result < 1e12 else None
    except (ValueError, TypeError):
        return None


def extract(page, name, city):
    """Only exact project entities with matching locality supply facts."""
    for entity in entities(page.schemas):
        types = entity.get('@type', [])
        types = [types] if isinstance(types, str) else types
        address = entity.get('address')
        if not isinstance(address, dict):
            continue
        if 'ApartmentComplex' not in types or not matched(name, entity.get('name', '')):
            continue
        if normalized(address.get('addressLocality', '')) != normalized(city.split(',')[0]):
            continue
        fields = {'Configurations Type': 'Apartment'}
        count = number(entity.get('numberOfAccommodationUnits'))
        if count and count.is_integer():
            fields['Number of Units'] = int(count)
        amenities = entity.get('amenityFeature', [])
        if isinstance(amenities, dict):
            amenities = [amenities]
        names = [a['name'] for a in amenities if isinstance(a, dict)
                 and isinstance(a.get('name'), str) and a.get('value') is True]
        if names:
            fields['Amenities'] = '; '.join(names[:30])
        updated = entity.get('dateModified', '')
        try:
            fields['Last Updated Date'] = date.fromisoformat(updated[:10]).isoformat()
        except (ValueError, TypeError):
            pass
        units = []
        plans = entity.get('hasFloorPlan', [])
        if isinstance(plans, dict):
            plans = [plans]
        for plan in plans if isinstance(plans, list) else []:
            if not isinstance(plan, dict):
                continue
            bedrooms = number(plan.get('numberOfBedrooms'))
            if not bedrooms or not bedrooms.is_integer() or bedrooms > 20:
                continue
            size = plan.get('floorSize', {})
            size = size if isinstance(size, dict) else {}
            area = number(size)
            code = str(size.get('unitCode', '')).upper()
            if code == 'MTK' and area:
                area = round(area * 10.7639104167, 2)
            elif code != 'FTK':
                area = None
            # Do not treat generic Offer amounts as sale prices (could be rent).
            units.append([f'{int(bedrooms)} BHK', area, None, 'Not specified',
                          'Structured floor plan; measurement basis and sale price not verified'])
        return fields, units
    return {}, []


def research(entry, city, saved):
    result = copy.deepcopy(saved or {})
    result.setdefault('fields', {})
    place = entry['place']
    name = place.get('displayName', {}).get('text', '')
    website = place.get('websiteUri')
    result.setdefault('name', name)
    if not website:
        result['auto_status'] = 'No project website supplied by Google; manual source needed'
        return result
    try:
        parts = urlsplit(public_url(website))
        robot_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
        try:
            robots, _ = fetch(robot_url)
        except requests.HTTPError as exc:
            if exc.response.status_code != 404:
                raise
            robots = ''
        robot = RobotFileParser()
        robot.parse(robots.splitlines())
        if not robot.can_fetch(AGENT, website):
            raise ValueError('Website disallows automated access')
        html, final = fetch(website)
        page = Page(html)
        fields, units = extract(page, name, city)
        source = final
        # Try at most two project-specific links on the same developer website.
        links = [urljoin(final, link) for link in page.links]
        tokens = [t for t in normalized(name).split() if len(t) > 3]
        links = list(dict.fromkeys(link for link in links if urlsplit(link).netloc == urlsplit(final).netloc
                    and sum(t in normalized(urlsplit(link).path) for t in tokens) >= 2))[:2]
        if not fields:
            for link in links:
                if robot.can_fetch(AGENT, link):
                    child, url = fetch(link)
                    fields, units = extract(Page(child), name, city)
                    if fields:
                        source = url
                        break
        if fields:
            existing = result['fields']
            added = {k: v for k, v in fields.items() if not existing.get(k)}
            existing.update(added)
            if not result.get('units') and units:
                # Unit provenance stays independent of existing manual research.
                result['units'] = units
                result['unit_source'] = source
                result['unit_updated'] = fields.get('Last Updated Date', '')
            result.setdefault('source', source)
            result.setdefault('review', 'Source found; partial details')
            result['auto_status'] = 'Matched project website; added ' + str(len(added)) + ' fields'
            result['notes'] = result.get('notes', '') + '\nAutomatic source: ' + source + '; added fields: ' + ', '.join(added)
        else:
            result['auto_status'] = 'Page checked; no matching structured project details. Manual research required'
    except (requests.RequestException, ValueError, OSError, TypeError, KeyError):
        result['auto_status'] = 'Website unavailable, restricted or unsupported; saved details retained'
    result['auto_checked'] = date.today().isoformat()
    return result


def enrich(candidates, city, saved, progress=None):
    results = dict(saved)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(research, entry, city, saved.get(pid)): pid for pid, entry in candidates.items()}
        done = 0
        for job in as_completed(jobs):
            pid = jobs[job]
            try:
                results[pid] = job.result()
            except Exception:
                results[pid] = copy.deepcopy(saved.get(pid, {}))
                results[pid]['auto_status'] = 'Website could not be processed; saved details retained'
            done += 1
            if progress:
                progress(f'Checking project websites: {done} of {len(candidates)}')
    return results
