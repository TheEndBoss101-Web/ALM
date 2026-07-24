"""
Line classification engine for adblock lists.

Takes a line from any blocklist format and classifies it into:
  ipv4, ipv6, ips, domains, hosts, urls, or abp

Priority-ordered matching (first match wins):
  1. Empty / whitespace
  2. ABP cosmetic filter (## / #@# / #?#) — before comment check
  3. Comment (! or #)
  4. ABP header ([Adblock ...])
  5. Validated IPv4 (with optional CIDR)
  6. Validated IPv6 (with optional CIDR)
  7. ABP whitelist domain  (@@||domain^)
  8. ABP domain rule  (||domain^)
  9. ABP exact URL  (|http://...|)
 10. Domain-specific element hiding (domain##selector)
 11. Hosts format  (IP whitespace domain)
 12. Plain URL  (http:// or https://)
 13. Wildcard domain  (*.domain.tld → domain.tld)
 14. Plain domain
 15. Anything else → ABP pass-through
"""

import re
import ipaddress

# -------------------------------------------------------------------
# Patterns
# -------------------------------------------------------------------

# IPv4 address or CIDR — validation happens via ipaddress module
IPV4_RAW = re.compile(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:/\d{1,2})?$')

# IPv6 address or CIDR
IPV6_RAW = re.compile(r'^([0-9a-fA-F:]+)(?:/\d{1,3})?$')

# ABP whitelist: @@||domain.tld^
ABP_WHITELIST = re.compile(r'^@@\|\|([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\^')

# ABP domain rule: ||domain.tld^ (optionally followed by $options)
ABP_DOMAIN_RULE = re.compile(r'^\|\|([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\^')

# ABP exact URL: |http://...| or |https://...|
ABP_EXACT_URL = re.compile(r'^\|(https?://[^|]+)\|$')

# ABP element hiding (domain-specific or generic):
#   domain##selector
#   domain#@#selector
#   domain#?#selector
#   ##selector
#   #@#selector
#   #?#selector
ABP_ELEM_HIDING = re.compile(
    r'^([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})?(#[@#?]?#)(.+)$'
)

# Hosts format: IP whitespace domain
HOSTS_LINE = re.compile(r'^(\S+)\s+(\S+)')

# Plain URL — must NOT contain ABP-style $options in the path part
# Lines like http://ads.com$third-party are ABP rules, not plain URLs.
# But $ in query strings (price=$10) is valid — only check before ? or #.
def _has_abp_url_options(url):
    """True if the URL has $\w in the path part (before any ? or #)."""
    path_part = url.split('?')[0].split('#')[0]
    return bool(re.search(r'\$\w', path_part))

PLAIN_URL = re.compile(r'^(https?://\S+)$', re.IGNORECASE)

# Simple domain (no protocol, no wildcard, no path)
SIMPLE_DOMAIN = re.compile(
    r'^([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
)

# Hostname without TLD (for hosts entries like 'localhost', 'broadcasthost')
HOSTNAME_NO_DOT = re.compile(
    r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$'
)

# Wildcard domain: *.domain.tld or .domain.tld
WILDCARD_DOMAIN = re.compile(r'^(\*\.)?(.+)$')

# ABP-like pattern indicator (fast heuristic for format detection)
ABP_MARKER = re.compile(
    r'^(\|\||@@\|\||\|\|?[a-z]+\^|##|#@#|#\?#|\[Adblock|\[AdBlock|\[uBlock)'
)

# -------------------------------------------------------------------
# Classification type constants
# -------------------------------------------------------------------

EMPTY = 'empty'
COMMENT = 'comment'
HEADER = 'header'     # [Adblock Plus 2.0] etc.
IPV4 = 'ipv4'
IPV6 = 'ipv6'
ABP = 'abp'
HOSTS = 'hosts'
URL = 'url'
DOMAIN = 'domain'


# -------------------------------------------------------------------
# Validation helpers
# -------------------------------------------------------------------

def _valid_ipv4(s):
    """Return True if s is a valid IPv4 address or network."""
    try:
        if '/' in s:
            ipaddress.IPv4Network(s, strict=False)
        else:
            ipaddress.IPv4Address(s)
        return True
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
        return False


def _valid_ipv6(s):
    """Return True if s is a valid IPv6 address or network."""
    try:
        if '/' in s:
            ipaddress.IPv6Network(s, strict=False)
        else:
            ipaddress.IPv6Address(s)
        return True
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
        return False


# -------------------------------------------------------------------
# Format detection
# -------------------------------------------------------------------

def detect_is_abp(content):
    """
    Heuristic: scan first 30 non-comment, non-empty lines.
    If any looks like an ABP-specific construct, classify as ABP.
    """
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('!') or stripped.startswith('#'):
            continue
        count += 1
        if count > 30:
            break
        if ABP_MARKER.match(stripped):
            return True
    return False


# -------------------------------------------------------------------
# Line classifier
# -------------------------------------------------------------------

def classify_line(line):
    """
    Classify a single line from a blocklist.

    Returns a tuple:
      (category, data_dict)

    data_dict keys vary by category:
      ipv4:     {'raw': str}
      ipv6:     {'raw': str}
      abp:      {'raw': str}         always present
                {'domain': str}      optional, extracted if rule targets a domain
                {'url': str}         optional, extracted if rule targets a URL
      hosts:    {'ip': str, 'domain': str, 'raw': str}
      url:      {'url': str}
      domain:   {'domain': str, 'wildcard': bool}
      comment:  {'raw': str}
      header:   {'raw': str}
      empty:    {}
    """
    stripped = line.strip()
    lower = stripped.lower()

    # --- 1. Empty ---
    if not stripped:
        return EMPTY, {}

    # --- 2. ABP cosmetic filter before comment check ---
    # ##, #@#, #?# must be checked before generic # comment check
    if stripped.startswith('##') or stripped.startswith('#@#') or stripped.startswith('#?#'):
        # Check if it's domain-specific: domain##selector, domain#@#selector, domain#?#selector
        m = ABP_ELEM_HIDING.match(stripped)
        if m:
            domain = m.group(1)
            if domain:
                return ABP, {'raw': stripped, 'domain': domain}
            return ABP, {'raw': stripped}
        return ABP, {'raw': stripped}

    # --- 3. Comment ---
    if stripped.startswith('!') or stripped.startswith('#'):
        return COMMENT, {'raw': stripped}

    # --- 4. ABP header ---
    if stripped.startswith('[') and \
       ('adblock' in lower or 'ublock' in lower):
        return HEADER, {'raw': stripped}

    # --- 4. IPv4 ---
    m = IPV4_RAW.match(stripped)
    if m and _valid_ipv4(m.group(1)):
        return IPV4, {'ip': m.group(1), 'cidr': stripped}

    # --- 5. IPv6 ---
    m = IPV6_RAW.match(stripped)
    if m and _valid_ipv6(m.group(1)):
        return IPV6, {'ip': m.group(1), 'cidr': stripped}

    # --- 6. ABP whitelist domain: @@||domain.tld^ ---
    m = ABP_WHITELIST.match(stripped)
    if m:
        return ABP, {'raw': stripped, 'domain': m.group(1), 'whitelist': True}

    # --- 7. ABP domain rule: ||domain.tld^ ---
    m = ABP_DOMAIN_RULE.match(stripped)
    if m:
        return ABP, {'raw': stripped, 'domain': m.group(1), 'whitelist': False}

    # --- 8. ABP exact URL: |http://...| ---
    m = ABP_EXACT_URL.match(stripped)
    if m:
        return ABP, {'raw': stripped, 'url': m.group(1)}

    # --- 9. Domain-specific element hiding ---
    # Lines like domain##selector that didn't start with ## (handled in step 2)
    m = ABP_ELEM_HIDING.match(stripped)
    if m and m.group(1):  # only match when a domain is present
        return ABP, {'raw': stripped, 'domain': m.group(1), 'whitelist': False}

    # --- 10. Hosts format: IP whitespace domain ---
    m = HOSTS_LINE.match(stripped)
    if m:
        ip_part = m.group(1)
        domain_part = m.group(2)
        # Strip inline comments from the domain part
        domain_clean = domain_part.split('#')[0].split('!')[0].strip()
        # Validate IP part
        is_ip4 = bool(IPV4_RAW.match(ip_part)) and _valid_ipv4(ip_part.split('/')[0])
        is_ip6 = bool(IPV6_RAW.match(ip_part)) and _valid_ipv6(ip_part.split('/')[0])
        # Accept proper domains AND bare hostnames (localhost, etc.)
        valid_hostname = SIMPLE_DOMAIN.match(domain_clean) or HOSTNAME_NO_DOT.match(domain_clean)
        if (is_ip4 or is_ip6) and valid_hostname:
            return HOSTS, {
                'ip': ip_part,
                'domain': domain_clean,
                'raw': f'{ip_part} {domain_clean}'
            }

    # --- 11. Plain URL — reject if it has ABP $options like $third-party ---
    if PLAIN_URL.match(stripped):
        # http://ads.com$third-party is an ABP rule, not a URL
        if not _has_abp_url_options(stripped):
            return URL, {'url': stripped}

    # --- 12. Wildcard domain ---
    m = WILDCARD_DOMAIN.match(stripped)
    if m:
        bare = m.group(2)
        if SIMPLE_DOMAIN.match(bare):
            return DOMAIN, {'domain': bare, 'wildcard': bool(m.group(1))}

    # --- 13. Plain domain ---
    if SIMPLE_DOMAIN.match(stripped):
        return DOMAIN, {'domain': stripped, 'wildcard': False}

    # --- 14. Everything else → ABP pass-through ---
    return ABP, {'raw': stripped}