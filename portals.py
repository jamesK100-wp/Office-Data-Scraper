"""Discovery and extraction limited to the user's two approved portals."""
import re
from datetime import date
from urllib.parse import urljoin, urlsplit, quote
from urllib.robotparser import RobotFileParser
import requests
from enrichment import Page, fetch, extract

DOMAINS = ('magicbricks.com', '99acres.com')


def failure_reason(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        reason = {401: 'authentication required', 403: 'access denied by portal',
                  404: 'page not found', 429: 'rate limit reached; try later'}.get(status, 'portal request failed')
        return f'HTTP {status}: {reason}'
    if isinstance(exc, requests.exceptions.SSLError):
        return 'TLS certificate verification failed; check certificates and network settings'
    if isinstance(exc, requests.exceptions.ProxyError):
        return 'proxy connection failed; check proxy settings'
    if isinstance(exc, requests.Timeout):
        return 'request timed out after retries'
    if isinstance(exc, requests.ConnectionError):
        return 'connection failed after retries; check internet, DNS and firewall settings'
    if isinstance(exc, ValueError):
        return str(exc)
    return f'{type(exc).__name__}: page could not be read or parsed'


def allowed(url):
    p = urlsplit(url)
    return p.scheme in ('http', 'https') and any(p.hostname == d or (p.hostname or '').endswith('.' + d) for d in DOMAINS)


def get_page(url):
    if not allowed(url):
        raise ValueError('Source is outside the approved portals')
    p = urlsplit(url)
    try:
        text, _ = fetch(f'{p.scheme}://{p.netloc}/robots.txt', allowed=allowed)
    except requests.HTTPError as exc:
        if exc.response.status_code != 404:
            raise
        text = ''
    robot = RobotFileParser()
    robot.parse(text.splitlines())
    if not robot.can_fetch('PIGurbaniResearch/1.0', url):
        raise ValueError('Portal restricts automated access')
    html, final = fetch(url, allowed=allowed)
    return Page(html), final


def project_links(page, base, city):
    result = []
    slug = re.sub(r'\s+', '-', city.lower().split(',')[0].strip())
    for link in page.links:
        url = urljoin(base, link).split('?')[0].split('#')[0]
        if allowed(url) and slug in urlsplit(url).path.lower() and (
                '-pdpid-' in url or re.search(r'-npid-\d+', url)):
            if url not in result:
                result.append(url)
    return result


def discover(city, progress=None):
    slug = quote(city.split(',')[0].strip().replace(' ', '-').lower())
    slug = {'bengaluru':'bangalore','gurugram':'gurgaon'}.get(slug, slug)
    seeds = [('Magicbricks', f'https://www.magicbricks.com/residential-projects-in-{slug}-nprid'),
             ('99acres', f'https://www.99acres.com/new-projects-in-{slug}-ffid')]
    candidates, details, reports = {}, {}, []
    for portal, seed in seeds:
        if progress:
            progress(f'Checking {portal} city project directory')
        try:
            page, final = get_page(seed)
            links = project_links(page, final, slug)
            reports.append(f'{portal}: {len(links)} project links on the first directory page; not an exhaustive city list.')
            if not links:
                reports.append(f'{portal}: no supported project links in returned HTML; page may require JavaScript or have changed layout.')
        except (requests.RequestException, ValueError, OSError) as exc:
            reports.append(f'{portal}: {failure_reason(exc)}. Directory: {seed}. No data imported.')
            continue
        for index, url in enumerate(links[:30], 1):
            if progress:
                progress(f'{portal}: reading project {index} of {min(30, len(links))}')
            try:
                page, final = get_page(url)
                name = page.heading.strip()
                if not name:
                    reports.append(f'{portal}: no project heading in returned HTML: {url}')
                    continue
                if name.casefold() in ('access denied', 'just a moment...', 'verify you are human'):
                    raise ValueError('Portal returned an access challenge instead of a project page')
                # A project page and a city-bearing URL are required, not a generic search snippet.
                fields, units = extract(page, name, city)
                text = '\n'.join(page.text)
                # Only labeled overview values before listings/floor plans are considered.
                start = text.find(name)
                overview = text[start:] if start >= 0 else ''
                overview = re.split(r'Properties in |Floor Plans & Pricing', overview, maxsplit=1)[0]
                for label, column in [('Total Units','Number of Units'),('Total towers','Number of Towers')]:
                    values = re.findall(r'(?im)^' + label + r'\s*\n([\d,]+)\s*$', overview)
                    if len(set(values)) == 1:
                        fields[column] = int(values[0].replace(',', ''))
                acres = re.findall(r'(?im)^Project Size\s*\n([\d.]+)\s*Acres?\s*$', overview)
                if len(set(acres)) == 1:
                    fields['Total Project Area (Acres)'] = float(acres[0])
                pid = final
                candidates[pid] = {'place': {'displayName': {'text': name}, 'websiteUri': final},
                                   'queries': {portal + ' project directory'}}
                details[pid] = {'name':name,'fields':fields,'units':units,'source':final,
                    'checked':date.today().isoformat(),'review':'Portal page checked; partial details',
                    'auto_status':'Only supported published fields extracted', 'auto_checked':date.today().isoformat(),
                    'notes':'Portal overview claims; phase scope unverified. Blank values not published in a supported format. No other sources used.'}
            except (requests.RequestException, ValueError, OSError, TypeError) as exc:
                reports.append(f'{portal}: {failure_reason(exc)}. Project: {url}')
    return candidates, details, reports
