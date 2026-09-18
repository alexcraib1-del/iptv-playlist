import json
import urllib.request
import xml.etree.ElementTree as ET

API = "https://iptv-org.github.io/api"
PLAYLIST = "playlist-v2.m3u"
OUTPUT = "channels.xml"


def download_json(filename):
    print(f"Downloading {filename}...")

    with urllib.request.urlopen(
        f"{API}/{filename}",
        timeout=30
    ) as response:
        return json.load(response)


def get_playlist_ids():
    ids = set()

    with open(
        PLAYLIST,
        "r",
        encoding="utf-8"
    ) as f:
        for line in f:
            if not line.startswith("#EXTINF:"):
                continue

            marker = 'tvg-id="'

            if marker not in line:
                continue

            channel_id = (
                line.split(marker, 1)[1]
                .split('"', 1)[0]
                .strip()
            )

            if channel_id:
                ids.add(channel_id)

    return ids


def main():
    print()
    print("========================")
    print("BUILDING EPG CHANNEL LIST")
    print("========================")

    playlist_ids = get_playlist_ids()

    print(
        f"Unique playlist IDs: "
        f"{len(playlist_ids)}"
    )

    guides = download_json("guides.json")

    # Keep only ONE EPG mapping for each playlist channel.
    selected = {}

    for guide in guides:
        if guide.get("lang") != "en":
            continue

        channel_id = guide.get("channel")

        if not channel_id:
            continue

        if channel_id not in playlist_ids:
            continue

        site = guide.get("site")
        site_id = guide.get("site_id")

        if not site or not site_id:
            continue

        # If we already selected an EPG source for this
        # channel, don't add another one.
        if channel_id in selected:
            continue

        selected[channel_id] = guide

    root = ET.Element("channels")
    sites = set()

    for channel_id, guide in selected.items():
        site = guide["site"]
        site_id = guide["site_id"]
        feed_id = guide.get("feed")

        sites.add(site)

        # Keep feed-specific XMLTV IDs when the guide
        # specifically identifies a feed.
        if feed_id:
            xmltv_id = (
                f"{channel_id}@{feed_id}"
            )
        else:
            xmltv_id = channel_id

        element = ET.SubElement(
            root,
            "channel",
            {
                "site": site,
                "site_id": site_id,
                "lang": "en",
                "xmltv_id": xmltv_id
            }
        )

        element.text = (
            guide.get("site_name")
            or channel_id
        )

    tree = ET.ElementTree(root)

    ET.indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT,
        encoding="utf-8",
        xml_declaration=True
    )

    print()
    print("========================")
    print("EPG CHANNEL LIST COMPLETE")
    print("========================")

    print(
        f"EPG channels selected: "
        f"{len(selected)}"
    )

    print(
        f"Unique EPG sites: "
        f"{len(sites)}"
    )

    print(
        f"Output: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
