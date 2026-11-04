from tender_intelligence.predecessors import download_predecessor
from tender_intelligence.preparation import prepare_notice
from tender_intelligence.ted_client import fetch_notice_xml


PUBLICATION_NUMBERS = (
    "722762-2026",
    "724862-2026",
    "737957-2026",
    "749573-2026",
)


def main() -> None:
    for publication_number in PUBLICATION_NUMBERS:
        xml_content = fetch_notice_xml(publication_number)
        current = prepare_notice(
            xml_content,
            expected_publication_number=publication_number,
        ).notice

        result = download_predecessor(current)

        if result is None:
            raise ValueError(
                f"Expected a predecessor for {publication_number}"
            )

        predecessor = result.bundle.notice
        print(
            f"Verified: {current.publication_number} "
            f"-> {predecessor.publication_number}; "
            f"reference: {current.reference_type}; "
            f"lots: {len(result.bundle.lots)}"
        )


if __name__ == "__main__":
    main()