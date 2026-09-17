import urllib.request
import re

BASE = "https://iptv-org.github.io/iptv"

# Main feeds
MAIN_SOURCES = [
    ("Canada", f"{BASE}/countries/ca.m3u"),
    ("United States", f"{BASE}/countries/us.m3u"),
    ("Movies", f"{BASE}/categories/movies.m3u"),
    ("Series", f"{BASE}/categories/series.m3u"),
]

# Canadian province/territory codes
CA_SUBDIVISIONS = {
    "ab", "bc", "mb", "nb", "nl", "ns", "nt",
    "nu", "on", "pe", "qc", "sk", "yt"
}

# US state/territory codes
US_SUBDIVISIONS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga",
    "hi", "id", "il", "in", "ia", "ks", "ky", "la", "me", "md",
    "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc",
    "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy",
    "dc", "pr", "vi", "gu", "as", "mp"
}


def download(url):
    print(f"Downloading {url}")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def discover_local_playlists():
    """
    Read IPTV-org's published playlist documentation and discover
    subdivision/city playlist URLs belonging to Canada or the USA.
    """

    url = "https://raw.githubusercontent.com/iptv-org/iptv/master/PLAYLISTS.md"

    print("Discovering local IPTV-org playlists...")

    text = download(url)

    urls = re.findall(
        r'https://iptv-org\.github\.io/iptv/[^\s\)<>"]+\.m3u',
        text
    )

    canada = set()
    usa = set()

    for url in urls:

        # subdivision playlists such as subdivisions/ca-on.m3u
        match = re.search(r'/subdivisions/([a-z]{2})-([a-z]{2})\.m3u', url)

        if match:
            country = match.group(1)
            subdivision = match.group(2)

            if country == "ca" and subdivision in CA_SUBDIVISIONS:
                canada.add(url)

            elif country == "us" and subdivision in US_SUBDIVISIONS:
                usa.add(url)

            continue

        # City playlists use IDs beginning with their country code.
        # Examples:
        # Canada: caott.m3u (Ottawa), cator.m3u (Toronto)
        # USA:    uslax.m3u (Los Angeles), usphx.m3u (Phoenix)
        city_match = re.search(r'/cities/([a-z0-9]+)\.m3u', url)

        if city_match:
            city_id = city_match.group(1)

            if city_id.startswith("ca"):
                canada.add(url)

            elif city_id.startswith("us"):
                usa.add(url)

    print(f"Found {len(canada)} Canadian regional/city playlists")
    print(f"Found {len(usa)} US regional/city playlists")

    return sorted(canada), sorted(usa)


def parse_playlist(text, group_name):
    lines = text.splitlines()
    entries = []

    i = 0

    while i < len(lines):

        line = lines[i].strip()

        if line.startswith("#EXTINF"):

            extinf = line
            j = i + 1
            extra_lines = []

            while j < len(lines):

                next_line = lines[j].strip()

                if next_line.startswith("#EXTINF"):
                    break

                if next_line and not next_line.startswith("#"):
                    stream_url = next_line
                    break

                if next_line:
                    extra_lines.append(next_line)

                j += 1

            else:
                i += 1
                continue

            # Force everything into our four clean groups
            if 'group-title="' in extinf:

                extinf = re.sub(
                    r'group-title="[^"]*"',
                    f'group-title="{group_name}"',
                    extinf
                )

            else:

                extinf = extinf.replace(
                    "#EXTINF:-1",
                    f'#EXTINF:-1 group-title="{group_name}"',
                    1
                )

            entries.append(
                (extinf, extra_lines, stream_url)
            )

            i = j

        i += 1

    return entries


def main():

    canada_local, usa_local = discover_local_playlists()

    sources = list(MAIN_SOURCES)

    # Add all discovered local feeds
    for url in canada_local:
        sources.append(("Canada", url))

    for url in usa_local:
        sources.append(("United States", url))

    all_entries = []
    seen_urls = set()

    stats = {
        "Canada": 0,
        "United States": 0,
        "Movies": 0,
        "Series": 0
    }

    for group_name, url in sources:

        try:

            playlist = download(url)

            entries = parse_playlist(
                playlist,
                group_name
            )

            added = 0

            for extinf, extra_lines, stream_url in entries:

                # Deduplicate identical streams
                if stream_url in seen_urls:
                    continue

                seen_urls.add(stream_url)

                all_entries.append(
                    (
                        group_name,
                        extinf,
                        extra_lines,
                        stream_url
                    )
                )

                added += 1
                stats[group_name] += 1

            print(
                f"{group_name}: +{added} unique streams"
            )

        except Exception as e:

            # One dead regional playlist shouldn't kill
            # the entire daily build.
            print(
                f"WARNING: Could not process {url}: {e}"
            )

    group_order = {
        "Canada": 0,
        "United States": 1,
        "Movies": 2,
        "Series": 3
    }

    all_entries.sort(
        key=lambda x: (
            group_order.get(x[0], 99),
            x[1].lower()
        )
    )

    with open(
        "playlist.m3u",
        "w",
        encoding="utf-8"
    ) as f:

        f.write("#EXTM3U\n")

        for (
            group_name,
            extinf,
            extra_lines,
            stream_url
        ) in all_entries:

            f.write(extinf + "\n")

            for extra in extra_lines:
                f.write(extra + "\n")

            f.write(stream_url + "\n")

    print("\n========================")
    print("PLAYLIST COMPLETE")
    print("========================")

    for group, count in stats.items():
        print(f"{group}: {count}")

    print("------------------------")
    print(f"TOTAL: {len(all_entries)}")


if __name__ == "__main__":
    main()
