import urllib.request
import re

BASE = "https://iptv-org.github.io/iptv"

# These are the four main sources we want.
SOURCES = [
    ("Canada", f"{BASE}/countries/ca.m3u"),
    ("United States", f"{BASE}/countries/us.m3u"),
    ("Movies", f"{BASE}/categories/movies.m3u"),
    ("Series", f"{BASE}/categories/series.m3u"),
]

def download(url):
    print(f"Downloading {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_playlist(text, group_name):
    lines = text.splitlines()
    entries = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("#EXTINF"):
            extinf = line

            # Find the next actual stream URL
            j = i + 1
            extra_lines = []

            while j < len(lines):
                next_line = lines[j].strip()

                if next_line.startswith("#EXTINF"):
                    break

                if next_line and not next_line.startswith("#"):
                    url = next_line
                    break

                if next_line:
                    extra_lines.append(next_line)

                j += 1
            else:
                i += 1
                continue

            # Replace existing group-title or add one
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

            entries.append((extinf, extra_lines, url))
            i = j

        i += 1

    return entries


def main():
    all_entries = []
    seen_urls = set()

    for group_name, url in SOURCES:
        try:
            playlist = download(url)
            entries = parse_playlist(playlist, group_name)

            added = 0

            for extinf, extra_lines, stream_url in entries:
                # Prevent the exact same stream appearing repeatedly
                if stream_url in seen_urls:
                    continue

                seen_urls.add(stream_url)
                all_entries.append(
                    (group_name, extinf, extra_lines, stream_url)
                )
                added += 1

            print(f"{group_name}: added {added} streams")

        except Exception as e:
            print(f"ERROR downloading {group_name}: {e}")

    # Keep groups together
    group_order = {
        "Canada": 0,
        "United States": 1,
        "Movies": 2,
        "Series": 3,
    }

    all_entries.sort(
        key=lambda x: (
            group_order.get(x[0], 99),
            x[1].lower()
        )
    )

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")

        for group_name, extinf, extra_lines, stream_url in all_entries:
            f.write(extinf + "\n")

            for extra in extra_lines:
                f.write(extra + "\n")

            f.write(stream_url + "\n")

    print()
    print(f"Finished! {len(all_entries)} unique streams written to playlist.m3u")


if __name__ == "__main__":
    main()
