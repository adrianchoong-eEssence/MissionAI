import csv
import subprocess
from pathlib import Path

root = Path("outputs/bayu-full-folder-audit")
images = root / "images"

objects = {
    "9645": "Swimming pool overview", "9646": "Coconut cluster", "9647": "Coconut palm",
    "9648": "Air-conditioning unit and open ceiling service area", "9649": "Ballroom overview",
    "9651": "Ballroom stage", "9652": "Petal ceiling light", "9653": "Ballroom ceiling-light array",
    "9654": "Faceted silver column", "9655": "Framed orchid artwork",
    "9656": "Ink mountain painting", "9657": "Ink mountain painting", "9658": "Ink mountain painting",
    "9659": "Ink mountain painting", "9660": "Ink mountain painting",
    "9661": "Artificial flower arrangement", "9662": "Artificial flower arrangement",
    "9663": "BBR-marked iron", "9664": "Framed orchid artwork", "9665": "Green ceramic urn",
    "9666": "Green ceramic urn", "9667": "Vertical timber screen", "9668": "Silver floral wall pattern",
    "9669": "Elevator capacity sign", "9670": "Freestanding wooden cabinet", "9674": "Pool and resort panorama",
    "9681": "BPR Perak commemorative plaque", "9682": "Merchant information plaque",
    "9683": "Display rescue boat", "9684": "Garden Terrace entrance and swing",
    "9685": "Garden Terrace dining interior", "9686": "Four-point ceiling fixture",
    "9690": "Paris fragment artwork", "9691": "Numbered mailbox set",
    "9692": "Bayu Management Corporation sign", "9693": "Bayu Management Corporation sign",
    "9694": "Beach direction mural", "9695": "Swimming-pool depth warning sign",
    "9696": "Paved seafront promenade", "9697": "Outdoor swing frame", "9698": "Outdoor swing frame",
    "9699": "Outdoor climbing frame", "9700": "Building-side service walkway",
    "9701": "Horseshoe activity lane", "9702": "Beachfront lawn and shade trees",
    "9703": "Beachfront shade-tree grove", "9704": "Offshore island and headland",
    "9705": "Open sandy shoreline", "9707": "Yacht Club building view",
    "9708": "Main Entrance 60 m sign", "9709": "Exposed brick section",
    "9710": "Horizontal timber wall", "9711": "Display rescue boat",
    "9712": "Wall drainage outlet", "9713": "Wall drainage outlet",
    "9714": "Single palm beside building", "9715": "Large beachfront shade tree",
    "9716": "Beachfront tree trunk", "9717": "Tyre traverse activity",
    "9718": "Stepping-stone activity", "9719": "Upright tyre hoop", "9720": "Lawn tree and resort block",
    "9721": "Green activity platform", "9722": "Green balance beam", "9723": "Green balance beam",
    "9724": "Feel Well activity gate", "9725": "Beachfront tree grove",
    "9726": "Circular marker embedded in tree", "9727": "Bare wall-side ground feature",
    "9728": "Beachfront tree grove", "9729": "Loose leaf litter", "9730": "Termite mound",
    "9731": "Wall-mounted rope station", "9732": "Wall pipe outlet", "9733": "Yellow fire hydrant",
    "9734": "Twin instrument gauges", "9735": "Prepared buffet tray", "9736": "Decorative vase display",
    "9737": "Outdoor dome oven", "9738": "Outdoor dome oven", "9739": "Covered terrace lounge",
    "9740": "Single woven pendant lamp", "9741": "Black stage lighting rail",
    "9742": "Basket pendant-light cluster", "9743": "Decorative bottle niche",
    "9744": "Blue rabbit sculpture", "9745": "Garden boulders", "9746": "Tiki pavilion entrance",
    "9747": "Yellow flowering plant", "9748": "Red flowering plant",
    "9749": "Outdoor service unit and planter", "9750": "Habura printed reference panel",
}

existing = {
    "9646": "LAB12 — Crown Estimate", "9649": "BBO009 — Silent Assembly; BBO011 — Ground Signal",
    "9652": "LAB05 — Eight-Ray Beacon", "9654": "BBO018 — Silver Monolith",
    "9656": "LAB11 — Ink Mountain Count; LAB16 — Three-Layer World",
    "9663": "LAB03 — The BBR Relic; BBO015 — Fabric Code",
    "9669": "LAB07 — What goes up must come down; LAB14 — Capacity Reached",
    "9684": "BBO027 — Garden Terrace Signal; BBO030 — Green Guard",
    "9690": "LAB01 — The Fragment", "9691": "LAB04 — Seven Silent Boxes",
    "9694": "LAB10 — Two Arrows, One Escape; LAB15 — Arrow Relay; BBO054 — Four Dark Windows",
    "9695": "LAB08 — Deepest Point", "9702": "LAB17 — Twenty Seconds of Island",
    "9704": "LAB02 — Horizon Lock", "9734": "BBO046 — Control Panel",
    "9747": "LAB06 — Swinging Signal",
}

unused_reasons = {
    "9647": "Same coconut-tree object already represented by IMG_9646.",
    "9648": "Maintenance/service area; unsuitable and potentially unsafe clue location.",
    "9653": "Repeated view of the ceiling-light object already represented by IMG_9652.",
    "9657": "Alternate shot of the ink painting already represented by IMG_9656.",
    "9658": "Alternate shot of the ink painting already represented by IMG_9656.",
    "9659": "Alternate shot of the ink painting already represented by IMG_9656.",
    "9660": "Alternate shot of the ink painting already represented by IMG_9656.",
    "9661": "Movable artificial arrangement; duplicate of IMG_9662 and not a stable venue marker.",
    "9662": "Movable artificial arrangement; duplicate of IMG_9661 and not a stable venue marker.",
    "9664": "Second orchid-art view; physical-object mechanic already represented by IMG_9655.",
    "9665": "Top-down alternate of the green urn represented by IMG_9666.",
    "9674": "Second pool overview; pool location already represented by IMG_9645.",
    "9693": "Alternate angle of the management sign represented by IMG_9692.",
    "9698": "Alternate angle of the swing frame represented by IMG_9697.",
    "9703": "Same beachfront tree zone already represented by IMG_9702.",
    "9711": "Rear view of the rescue boat represented by IMG_9683.",
    "9712": "Maintenance drainage detail; weak participant clue.",
    "9713": "Overlapping drainage detail; weak participant clue.",
    "9716": "Same beachfront tree object/zone represented by IMG_9715.",
    "9720": "Repeated lawn-tree location with no distinct stable object.",
    "9723": "Alternate angle of the balance beam represented by IMG_9722.",
    "9725": "Repeated beachfront grove with no independently distinct marker.",
    "9727": "Low-distinctness bare-ground area; unsuitable clue.",
    "9728": "Repeated beachfront grove with no independently distinct marker.",
    "9729": "Transient leaf litter, not a stable physical object.",
    "9732": "Maintenance pipe outlet; weak and unsuitable clue.",
    "9735": "Temporary buffet food; not a permanent venue object.",
    "9738": "Alternate angle of the dome oven represented by IMG_9737.",
    "9748": "Repeated flower-identification mechanic; plant may change seasonally.",
    "9749": "Service unit lacks a clear safe participant-facing landmark.",
    "9750": "Printed reference panel, not a confirmed permanent Bayu venue feature.",
}

with (root / "drive-images.tsv").open(newline="") as handle:
    drive_rows = list(csv.DictReader(handle, delimiter="\t"))
with (root / "new-candidate-links.tsv").open(newline="") as handle:
    new_rows = {row["Filename"]: row for row in csv.DictReader(handle, delimiter="\t")}

manifest = []
for row in drive_rows:
    filename = row["Filename"]
    stem = filename.removeprefix("IMG_").removesuffix(".HEIC")
    source = images / filename
    info = subprocess.check_output(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(source)], text=True
    )
    width = next(line.split(":", 1)[1].strip() for line in info.splitlines() if "pixelWidth" in line)
    height = next(line.split(":", 1)[1].strip() for line in info.splitlines() if "pixelHeight" in line)
    new = new_rows.get(filename)
    linked = existing.get(stem, "")
    status = "Used — existing" if linked else "Unused"
    if new:
        linked = f'{new["MissionID"]} — {new["ExperienceName"]}'
        status = "Used — newly mapped"
    manifest.append({
        "Drive File ID": row["DriveFileID"], "Filename": filename,
        "Parent folder": "Bayu Beach root (1rhyaWEGQQ_Q7_WgBfj-nRSVDlopBRJVK)",
        "Image dimensions": f"{width}×{height}", "Used / Unused": status,
        "Existing linked Experience": linked, "Main physical object or location": objects[stem],
        "Unused reason": unused_reasons.get(stem, ""),
    })

with (root / "bayu-drive-image-manifest.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=manifest[0].keys())
    writer.writeheader()
    writer.writerows(manifest)
