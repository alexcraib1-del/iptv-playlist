import json
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from collections import defaultdict

API = "https://iptv-org.github.io/api"
OUTPUT_FILE = "guide.xml"

TIMEOUT = 30


def download_json(filename):
    url = f"{API}/{filename}"

    print(f"Downloading {filename}...")

    with urllib.request.urlopen(
        url,
        timeout=TIMEOUT
    ) as response:
        return json.load(response)


def download_xml(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=TIMEOUT
    ) as response:
        return response.read()


def playlist_channel_ids():
    """
    Read the channel IDs actually present in playlist-v2.m3u.
    """

    ids = set()

    with open(
        "playlist-v2.m3u",
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
    print("GENERATING EPG")
    print("========================")

    playlist_ids = playlist_channel_ids()

    print(
        f"Unique playlist IDs: "
        f"{len(playlist_ids)}"
    )

    guides = download_json("guides.json")

    # Find English EPG sources relevant to our playlist.
    sources = defaultdict(set)

    for guide in guides:

        if guide.get("lang") != "en":
            continue

        channel_id = guide.get("channel")

        if not channel_id:
            continue

        # Accept both ordinary channel IDs and
        # feed-specific IDs used by IPTV-org.
        feed_id = guide.get("feed")

        possible_ids = {
            channel_id
        }

        if feed_id:
            possible_ids.add(
                f"{channel_id}@{feed_id}"
            )

        matching_ids = (
            possible_ids & playlist_ids
        )

        if not matching_ids:
            continue

        for source in guide.get(
            "sources",
            []
        ):
            if source.get("format") != "XML":
                continue

            url = source.get("url")

            if not url:
                continue

            for xmltv_id in matching_ids:
                sources[url].add(xmltv_id)

    wanted_ids = set()

    for ids in sources.values():
        wanted_ids.update(ids)

    print(
        f"EPG source URLs: "
        f"{len(sources)}"
    )

    print(
        f"Playlist IDs with EPG mappings: "
        f"{len(wanted_ids)}"
    )

    # Master XMLTV document.
    output_root = ET.Element("tv")

    added_channels = set()
    programme_count = 0

    successful_sources = 0
    failed_sources = 0

    for number, (url, source_ids) in enumerate(
        sources.items(),
        start=1
    ):

        print(
            f"[{number}/{len(sources)}] "
            f"Downloading EPG source..."
        )

        try:
            xml_data = download_xml(url)

            root = ET.fromstring(xml_data)

            successful_sources += 1

        except Exception as e:

            failed_sources += 1

            print(
                f"  Failed: "
                f"{type(e).__name__}"
            )

            continue

        # Add matching channel definitions.
        for channel in root.findall(
            "channel"
        ):

            channel_id = channel.get("id")

            if (
                channel_id in source_ids
                and channel_id
                not in added_channels
            ):
                output_root.append(channel)
                added_channels.add(
                    channel_id
                )

        # Add matching programmes.
        for programme in root.findall(
            "programme"
        ):

            channel_id = programme.get(
                "channel"
            )

            if channel_id in source_ids:
                output_root.append(
                    programme
                )

                programme_count += 1

    tree = ET.ElementTree(output_root)

    ET.indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )

    print()
    print("========================")
    print("EPG COMPLETE")
    print("========================")

    print(
        f"Sources successful: "
        f"{successful_sources}"
    )

    print(
        f"Sources failed: "
        f"{failed_sources}"
    )

    print(
        f"EPG channels written: "
        f"{len(added_channels)}"
    )

    print(
        f"Programmes written: "
        f"{programme_count}"
    )

    print(
        f"Output: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
