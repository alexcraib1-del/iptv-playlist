import xml.etree.ElementTree as ET

INPUT_FILE = "guide.xml"
OUTPUT_FILE = "guide.xml"


def base_id(xmltv_id):
    """Convert Channel.ca@SD -> Channel.ca."""
    if not xmltv_id:
        return xmltv_id

    return xmltv_id.split("@", 1)[0]


def main():
    print()
    print("========================")
    print("NORMALIZING EPG IDS")
    print("========================")

    tree = ET.parse(INPUT_FILE)
    root = tree.getroot()

    changed_channels = 0
    changed_programmes = 0

    seen_channels = set()

    # Normalize <channel id="...">
    for channel in list(root.findall("channel")):
        old_id = channel.get("id")
        new_id = base_id(old_id)

        if old_id != new_id:
            channel.set("id", new_id)
            changed_channels += 1

        # Prevent duplicate channel definitions if two
        # feed IDs ever collapse to the same base ID.
        if new_id in seen_channels:
            root.remove(channel)
        else:
            seen_channels.add(new_id)

    # Normalize <programme channel="...">
    for programme in root.findall("programme"):
        old_id = programme.get("channel")
        new_id = base_id(old_id)

        if old_id != new_id:
            programme.set("channel", new_id)
            changed_programmes += 1

    ET.indent(tree, space="  ")

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )

    print(
        f"Channel IDs normalized: "
        f"{changed_channels}"
    )

    print(
        f"Programme IDs normalized: "
        f"{changed_programmes}"
    )

    print(
        f"Unique EPG channels: "
        f"{len(seen_channels)}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
