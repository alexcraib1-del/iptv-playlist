import json
import urllib.request
import urllib.error
import socket
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

API = "https://iptv-org.github.io/api"

GROUP_ORDER = {
    "Canada": 0,
    "United States": 1,
    "Other English": 2,
    "Movies": 3,
    "Series": 4,
}


def download_json(filename):
    url = f"{API}/{filename}"
    print(f"Downloading {url}")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def escape_attr(value):
    if value is None:
        return ""
    return str(value).replace('"', "'")


def choose_logo(channel_id, feed_id, logos_by_channel):
    logos = logos_by_channel.get(channel_id, [])

    if not logos:
        return ""

    # Prefer a current logo for the exact feed
    if feed_id:
        matches = [
            x for x in logos
            if x.get("feed") == feed_id and x.get("in_use")
        ]
        if matches:
            return matches[0]["url"]

    # Then current channel-wide logo
    matches = [
        x for x in logos
        if x.get("feed") is None and x.get("in_use")
    ]
    if matches:
        return matches[0]["url"]

    # Fall back to any current logo
    matches = [x for x in logos if x.get("in_use")]
    if matches:
        return matches[0]["url"]

    return logos[0].get("url", "")


def make_entry(channel, stream, group, logo):
    channel_id = channel["id"]

    # Prefer stream title when it identifies a specific local/feed variant.
    name = stream.get("title") or channel.get("name") or channel_id

    attrs = [
        f'tvg-id="{escape_attr(channel_id)}"',
        f'tvg-name="{escape_attr(name)}"',
        f'group-title="{escape_attr(group)}"',
    ]

    if logo:
        attrs.append(f'tvg-logo="{escape_attr(logo)}"')

    extinf = f'#EXTINF:-1 {" ".join(attrs)},{name}'

    lines = [extinf]

    # Preserve IPTV-org's required playback headers.
    if stream.get("referrer"):
        lines.append(
            f'#EXTVLCOPT:http-referrer={stream["referrer"]}'
        )

    if stream.get("user_agent"):
        lines.append(
            f'#EXTVLCOPT:http-user-agent={stream["user_agent"]}'
        )

    lines.append(stream["url"])

    return lines

HEALTH_FILE = "stream-health.json"
DEAD_FILE = "dead-streams.txt"

CHECK_TIMEOUT = 8
MAX_WORKERS = 30
FAILURES_BEFORE_REMOVAL = 2


def load_health():
    if not os.path.exists(HEALTH_FILE):
        return {}

    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_health(health):
    with open(HEALTH_FILE, "w", encoding="utf-8") as f:
        json.dump(health, f, indent=2, sort_keys=True)


def check_stream(stream):
    url = stream["url"]

    headers = {
        "User-Agent": stream.get("user_agent")
        or "Mozilla/5.0"
    }

    if stream.get("referrer"):
        headers["Referer"] = stream["referrer"]

    try:
        req = urllib.request.Request(
            url,
            headers=headers
        )

        # We only need enough data to establish that
        # the endpoint responds.
        with urllib.request.urlopen(
            req,
            timeout=CHECK_TIMEOUT
        ) as response:
            response.read(1024)
            code = response.getcode()

            return url, "working", code

    except urllib.error.HTTPError as e:

        if e.code in (404, 410):
            return url, "dead", e.code

        # 401/403/451 etc. may be authorization,
        # geo-blocking or CDN restrictions.
        return url, "restricted", e.code

    except (
        urllib.error.URLError,
        socket.timeout,
        TimeoutError
    ):
        # A GitHub runner failing to reach a stream
        # does NOT prove the stream is dead.
        return url, "uncertain", None

    except Exception:
        return url, "uncertain", None


def health_check_streams(streams):
    previous = load_health()
    current = {}
    results = {}

    print()
    print("========================")
    print("CHECKING STREAM HEALTH")
    print("========================")
    print(f"Streams to check: {len(streams)}")
    print(f"Workers: {MAX_WORKERS}")
    print(f"Timeout: {CHECK_TIMEOUT}s")
    print()

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS
    ) as executor:

        futures = {
            executor.submit(
                check_stream,
                stream
            ): stream
            for stream in streams
        }

        completed = 0

        for future in as_completed(futures):
            stream = futures[future]

            url, status, code = future.result()

            old = previous.get(url, {})
            failures = old.get(
                "consecutive_dead",
                0
            )

            if status == "dead":
                failures += 1
            else:
                failures = 0

            current[url] = {
                "status": status,
                "http_code": code,
                "consecutive_dead": failures
            }

            results[url] = current[url]

            completed += 1

            if completed % 250 == 0:
                print(
                    f"Checked {completed}/{len(streams)}"
                )

    save_health(current)

    return results


def should_keep_stream(stream, health):
    result = health.get(stream["url"])

    if not result:
        return True

    # Only remove a URL after repeated,
    # high-confidence 404/410 failures.
    if (
        result["status"] == "dead"
        and result["consecutive_dead"]
        >= FAILURES_BEFORE_REMOVAL
    ):
        return False

    return True


def write_dead_report(streams, health):
    removed = []

    for stream in streams:
        result = health.get(stream["url"])

        if not result:
            continue

        if (
            result["status"] == "dead"
            and result["consecutive_dead"]
            >= FAILURES_BEFORE_REMOVAL
        ):
            removed.append(
                (
                    stream.get("title")
                    or stream.get("channel")
                    or "Unknown",
                    result.get("http_code"),
                    stream["url"]
                )
            )

    with open(
        DEAD_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        for name, code, url in sorted(removed):
            f.write(
                f"{name} | HTTP {code} | {url}\n"
            )

    return len(removed)

def main():
    channels = download_json("channels.json")
    feeds = download_json("feeds.json")
    streams = download_json("streams.json")
    logos = download_json("logos.json")
        health = health_check_streams(streams)
    removed_count = write_dead_report(
        streams,
        health
    )

    channels_by_id = {
        channel["id"]: channel
        for channel in channels
    }

    # Feed metadata tells us broadcast language.
    feeds_by_key = {}

    for feed in feeds:
        feeds_by_key[(feed["channel"], feed["id"])] = feed

    # Main feed fallback for streams where feed is null.
    main_feed_by_channel = {}

    for feed in feeds:
        if feed.get("is_main"):
            main_feed_by_channel[feed["channel"]] = feed

    logos_by_channel = defaultdict(list)

    for logo in logos:
        logos_by_channel[logo["channel"]].append(logo)

    groups = defaultdict(list)

    # Deduplicate WITHIN each group, but intentionally allow the
    # same channel/stream to appear in a geographic group and
    # again in Movies or Series.
    seen_by_group = defaultdict(set)

    stats = defaultdict(int)

    english_streams = 0
    skipped_non_english = 0
    skipped_unknown = 0

    for stream in streams:
                if not should_keep_stream(
            stream,
            health
        ):
            continue
        channel_id = stream.get("channel")

        if not channel_id:
            skipped_unknown += 1
            continue

        channel = channels_by_id.get(channel_id)

        if not channel:
            skipped_unknown += 1
            continue

        # Ignore NSFW and closed channels.
        if channel.get("is_nsfw"):
            continue

        if channel.get("closed"):
            continue

        feed_id = stream.get("feed")

        if feed_id:
            feed = feeds_by_key.get((channel_id, feed_id))
        else:
            feed = main_feed_by_channel.get(channel_id)

        # If there is no feed metadata, we can't reliably determine
        # that the stream is English.
        if not feed:
            skipped_unknown += 1
            continue

        languages = feed.get("languages") or []

        if "eng" not in languages:
            skipped_non_english += 1
            continue

        english_streams += 1

        country = channel.get("country")
        categories = set(channel.get("categories") or [])

        if country == "CA":
            geographic_group = "Canada"
        elif country == "US":
            geographic_group = "United States"
        else:
            geographic_group = "Other English"

        logo = choose_logo(
            channel_id,
            feed_id,
            logos_by_channel
        )

        # Geographic group
        geo_key = stream["url"]

        if geo_key not in seen_by_group[geographic_group]:
            seen_by_group[geographic_group].add(geo_key)

            groups[geographic_group].append(
                (
                    channel.get("name", ""),
                    make_entry(
                        channel,
                        stream,
                        geographic_group,
                        logo
                    )
                )
            )

            stats[geographic_group] += 1

        # Secondary category groups.
        # These intentionally duplicate streams from the geographic groups.
        if "movies" in categories:
            if stream["url"] not in seen_by_group["Movies"]:
                seen_by_group["Movies"].add(stream["url"])

                groups["Movies"].append(
                    (
                        channel.get("name", ""),
                        make_entry(
                            channel,
                            stream,
                            "Movies",
                            logo
                        )
                    )
                )

                stats["Movies"] += 1

        if "series" in categories:
            if stream["url"] not in seen_by_group["Series"]:
                seen_by_group["Series"].add(stream["url"])

                groups["Series"].append(
                    (
                        channel.get("name", ""),
                        make_entry(
                            channel,
                            stream,
                            "Series",
                            logo
                        )
                    )
                )

                stats["Series"] += 1

    # Alphabetize channels inside each group.
    for group in groups:
        groups[group].sort(
            key=lambda item: item[0].lower()
        )

    with open("playlist-v2.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")

        for group in sorted(
            groups,
            key=lambda x: GROUP_ORDER.get(x, 99)
        ):
            for _, lines in groups[group]:
                for line in lines:
                    f.write(line + "\n")

    print()
    print("========================")
    print("PLAYLIST V2 COMPLETE")
    print("========================")

    print(f"English source streams: {english_streams}")
    print()

    for group in [
        "Canada",
        "United States",
        "Other English",
        "Movies",
        "Series",
    ]:
        print(f"{group}: {stats[group]}")

    print()
    print(f"Skipped non-English: {skipped_non_english}")
    print(f"Skipped unknown metadata: {skipped_unknown}")
    print()
    print("Output: playlist-v2.m3u")
    print(f"Confirmed dead removed: {removed_count}")


if __name__ == "__main__":
    main()
