"""Inspect selected XML fields in a single TED notice."""

import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PUBLICATION_NUMBER = "124934-2026"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "inspection"

SELECTED_FIELDS = {
    "ID",
    "ContractFolderID",
    "VersionID",
    "NoticeTypeCode",
    "IssueDate",
    "IssueTime",
    "ChangedNoticeIdentifier",
    "ChangeReasonCode",
    "ChangeReason",
    "EndDate",
    "EndTime",
    "SubmissionDeadline",
    "ReasonCode",
    "NoticePublicationID",
    "PublicationDate",
}


def local_name(tag: str) -> str:
    """Return an XML tag name without its namespace."""
    return tag.rsplit("}", 1)[-1]


def inspect_element(
    element: ET.Element,
    path: str,
    lines: list[str],
) -> None:
    """Collect selected fields with their indexed XML paths."""
    name = local_name(element.tag)
    value = (element.text or "").strip()

    if name in SELECTED_FIELDS and value:
        attributes = f" | attributes={element.attrib}" if element.attrib else ""
        lines.append(f"{path}\n  value={value}{attributes}")

    counts: Counter[str] = Counter()

    for child in element:
        counts[child.tag] += 1
        child_name = local_name(child.tag)
        child_path = f"{path}/{child_name}[{counts[child.tag]}]"
        inspect_element(child, child_path, lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    xml_path = OUTPUT_DIR / f"{PUBLICATION_NUMBER}.xml"
    report_path = OUTPUT_DIR / f"{PUBLICATION_NUMBER}_inspection.txt"

    if xml_path.exists():
        xml_bytes = xml_path.read_bytes()
        print(f"Using local XML: {xml_path}")
    else:
        url = f"https://ted.europa.eu/en/notice/{PUBLICATION_NUMBER}/xml"
        request = Request(
            url,
            headers={
                "Accept": "application/xml",
                "User-Agent": "tender-intelligence-pipeline/0.1",
            },
        )

        try:
            with urlopen(request, timeout=60) as response:
                xml_bytes = response.read()
        except HTTPError as exc:
            print(f"Download failed: HTTP {exc.code}")
            if exc.code == 429:
                print(
                    "Rate limit reached. Retry-After: "
                    f"{exc.headers.get('Retry-After', 'not provided')}"
                )
            return
        except (URLError, TimeoutError) as exc:
            print(f"Download failed: {exc}")
            return

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        print(f"The response could not be parsed as XML: {exc}")
        return

    xml_path.write_bytes(xml_bytes)

    lines = [
        f"Publication number: {PUBLICATION_NUMBER}",
        f"Root tag: {root.tag}",
        "",
    ]
    inspect_element(root, f"/{local_name(root.tag)}", lines)

    report = "\n".join(lines)
    report_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    main()
