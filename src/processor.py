"""
Process a single blocklist: classify every line, separate into categories,
deduplicate, and write to disk.

The ABP file is always generated from extracted data (domains, IPs, URLs).
No raw pass-through, no source comments preserved — the ABP file is a clean
synthetic render of what was extracted.
"""

import os
from urllib.parse import urlparse
from . import parser
from .whitelist import load_whitelist, apply_whitelist


def _dedup(lines):
    """Remove duplicates while preserving order."""
    seen = set()
    result = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            result.append(line)
    return result


def _extract_host_from_url(url):
    """Extract the hostname from a URL string, or None."""
    try:
        parsed = urlparse(url)
        if parsed.hostname:
            return parsed.hostname
    except Exception:
        pass
    return None

def _generate_abp_rules(domains, ips, urls):
    """Convert extracted domains, IPs, and URLs into ABP rules."""
    rules = []
    for domain in domains:
        rules.append(f'||{domain}^$all')
    for ip in ips:
        rules.append(f'||{ip}^$all')
    for url in urls:
        rules.append(url)
    return rules


def process_list(content, name):
    """
    Process raw list content and save categorized output to disk.

    Args:
        content:  Raw list content (string)
        name:     List name (used for output directory)

    Writes to:  lists/<name>/{ipv4, ipv6, ips, domains, hosts, urls, abp}
    Returns:    dict of {category: line_count}
    """
    categories = {
        'ipv4': [], 'ipv6': [], 'ips': [],
        'domains': [], 'hosts': [], 'urls': [],
        'abp': [],
    }

    domains_for_abp = []
    ips_for_abp = []
    urls_for_abp = []

    for line in content.splitlines():
        kind, data = parser.classify_line(line)

        if kind in (parser.EMPTY, parser.COMMENT, parser.HEADER):
            continue

        if kind == parser.IPV4:
            categories['ipv4'].append(data['ip'])
            categories['ips'].append(data['ip'])
            ips_for_abp.append(data['ip'])
            continue

        if kind == parser.IPV6:
            categories['ipv6'].append(data['ip'])
            categories['ips'].append(data['ip'])
            ips_for_abp.append(data['ip'])
            continue

        if kind == parser.ABP:
            domain = data.get('domain')
            url = data.get('url')
            is_whitelist = data.get('whitelist', False)

            # Extract domain — whitelist rules are excluded entirely
            if domain and not is_whitelist:
                categories['domains'].append(domain)
                categories['hosts'].append(f'0.0.0.0 {domain}')
                domains_for_abp.append(domain)

            # Extract URL
            if url:
                categories['urls'].append(url)
                host = _extract_host_from_url(url)
                if host:
                    categories['domains'].append(host)
                    categories['hosts'].append(f'0.0.0.0 {host}')
                    domains_for_abp.append(host)
                urls_for_abp.append(url)
            continue

        if kind == parser.HOSTS:
            categories['hosts'].append(data['raw'])
            categories['ips'].append(data['ip'])
            categories['domains'].append(data['domain'])
            domains_for_abp.append(data['domain'])
            ips_for_abp.append(data['ip'])
            continue

        if kind == parser.URL:
            categories['urls'].append(data['url'])
            urls_for_abp.append(data['url'])
            host = _extract_host_from_url(data['url'])
            if host:
                categories['domains'].append(host)
                categories['hosts'].append(f'0.0.0.0 {host}')
                domains_for_abp.append(host)
            continue

        if kind == parser.DOMAIN:
            categories['domains'].append(data['domain'])
            categories['hosts'].append(f'0.0.0.0 {data["domain"]}')
            domains_for_abp.append(data['domain'])
            continue

    # --- Deduplication ---
    for cat in ('ipv4', 'ipv6', 'ips', 'domains', 'hosts', 'urls'):
        categories[cat] = _dedup(categories[cat])

    # Generate ABP from extracted data — always
    abp_lines = _generate_abp_rules(
        _dedup(domains_for_abp), _dedup(ips_for_abp), _dedup(urls_for_abp)
    )
    categories['abp'] = _dedup(abp_lines)

    # --- Apply whitelist pruning ---
    wl_patterns = load_whitelist()
    if wl_patterns:
        for cat in categories:
            categories[cat] = apply_whitelist(categories[cat], wl_patterns)

    # --- Write to disk ---
    out_dir = os.path.join('lists', name)
    os.makedirs(out_dir, exist_ok=True)

    stats = {}
    for cat, lines in categories.items():
        file_path = os.path.join(out_dir, cat)
        with open(file_path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
            if lines:
                fh.write('\n')
        stats[cat] = len(lines)

    return stats