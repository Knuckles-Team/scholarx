"""The pack extends only the core ontology (CONN-SCHOLARX-CONNECTOR-CONTENT-R004)."""

import re
from pathlib import Path

import pytest

ONTOLOGY_DIR = Path(__file__).resolve().parents[1] / "scholarx" / "ontology"
CORE_TERMS = {
    "PaperSource",
    "ResearchCategory",
    "citationCount",
    "doi",
    "externalToolId",
}


@pytest.mark.spec("CONN-SCHOLARX-CONNECTOR-CONTENT-R004")
def test_pack_declares_no_core_term():
    declared = set()
    for ttl in ONTOLOGY_DIR.glob("*.ttl"):
        declared |= set(re.findall(r"^:([A-Za-z0-9_]+)\s+(?:a|rdf:type)\s", ttl.read_text(), re.M))
    assert declared.isdisjoint(CORE_TERMS), sorted(declared & CORE_TERMS)
