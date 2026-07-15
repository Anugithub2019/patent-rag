#!/usr/bin/env python3

import os
import xml.etree.ElementTree as ET

INPUT_FILE = "ipa251211.xml"
OUTPUT_DIR = "patents"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Reading APPXML...")

with open(
    INPUT_FILE,
    "r",
    encoding="utf-8",
    errors="ignore"
) as f:
    content = f.read()

parts = content.split(
    '<?xml version="1.0" encoding="UTF-8"?>'
)

parts = [
    p.strip()
    for p in parts
    if "<us-patent-application" in p
]

print(f"Found {len(parts)} patents")

for idx, part in enumerate(parts, start=1):

    xml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + part
    )

    try:
        root = ET.fromstring(xml_text)

    except Exception as e:
        print(f"Skip patent {idx}: {e}")
        continue

    # =====================
    # Patent ID
    # =====================

    patent_id = f"patent_{idx}"

    doc_number = root.find(
        ".//publication-reference/document-id/doc-number"
    )

    kind = root.find(
        ".//publication-reference/document-id/kind"
    )

    if doc_number is not None:

        patent_id = (
            "US"
            + doc_number.text.strip()
        )

        if (
            kind is not None
            and kind.text
        ):
            patent_id += kind.text.strip()

    # =====================
    # Title
    # =====================

    title = ""

    title_elem = root.find(
        ".//invention-title"
    )

    if title_elem is not None:

        title = " ".join(
            t.strip()
            for t in title_elem.itertext()
            if t.strip()
        )

    # =====================
    # Abstract
    # =====================

    abstract = ""

    abstract_elem = root.find(
        ".//abstract"
    )

    if abstract_elem is not None:

        abstract = " ".join(
            t.strip()
            for t in abstract_elem.itertext()
            if t.strip()
        )

    # =====================
    # Description
    # =====================

    description = ""

    description_elem = root.find(
        ".//description"
    )

    if description_elem is not None:

        description = " ".join(
            t.strip()
            for t in description_elem.itertext()
            if t.strip()
        )

    # =====================
    # Claims
    # =====================

    claims = []

    claims_elem = root.find(
        ".//claims"
    )

    if claims_elem is not None:

        for elem in claims_elem.iter():

            if elem.tag.endswith(
                "claim-text"
            ):

                text = " ".join(
                    t.strip()
                    for t in elem.itertext()
                    if t.strip()
                )

                if text:
                    claims.append(text)

    # =====================
    # Inventors
    # =====================

    inventors = []

    for inv in root.findall(
        ".//inventor"
    ):

        first = inv.find(
            ".//first-name"
        )

        last = inv.find(
            ".//last-name"
        )

        name = ""

        if (
            first is not None
            and first.text
        ):
            name += (
                first.text.strip()
                + " "
            )

        if (
            last is not None
            and last.text
        ):
            name += last.text.strip()

        if name.strip():
            inventors.append(
                name.strip()
            )

    # =====================
    # Applicants
    # =====================

    applicants = []

    for org in root.findall(
        ".//orgname"
    ):

        text = " ".join(
            t.strip()
            for t in org.itertext()
            if t.strip()
        )

        if text:
            applicants.append(text)

    # =====================
    # CPC
    # =====================

    cpcs = []

    for cpc in root.findall(
        ".//classification-cpc"
    ):

        try:

            section = cpc.find(
                "section"
            ).text

            clazz = cpc.find(
                "class"
            ).text

            subclass = cpc.find(
                "subclass"
            ).text

            group = cpc.find(
                "main-group"
            ).text

            cpcs.append(
                f"{section}{clazz}{subclass} {group}"
            )

        except:
            pass

    # =====================
    # Build Output
    # =====================

    output = []

    output.append(
        f"PATENT_ID:\n{patent_id}\n"
    )

    output.append(
        f"TITLE:\n{title}\n"
    )

    output.append(
        f"ABSTRACT:\n{abstract}\n"
    )

    output.append(
        "INVENTORS:\n"
        + "\n".join(inventors)
        + "\n"
    )

    output.append(
        "APPLICANTS:\n"
        + "\n".join(applicants)
        + "\n"
    )

    output.append(
        "CPC:\n"
        + "\n".join(
            sorted(
                set(cpcs)
            )
        )
        + "\n"
    )

    claims_text = ""

    for i, claim in enumerate(
        claims,
        start=1
    ):

        claims_text += (
            f"\nClaim {i}\n"
            f"{claim}\n"
        )

    output.append(
        "CLAIMS:\n"
        + claims_text
        + "\n"
    )

    output.append(
        "DESCRIPTION:\n"
        + description
    )

    output_text = (
        "\n"
        + "=" * 80
        + "\n"
    ).join(output)

    output_file = os.path.join(
        OUTPUT_DIR,
        f"{patent_id}.txt"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(output_text)

    if idx % 100 == 0:

        print(
            f"Processed {idx}/{len(parts)}"
        )

print(
    f"\nDone. Saved to {OUTPUT_DIR}/"
)
