"""
Tests for correcting repealed IPC/CrPC citations to BNS/BNSS
"""

from pathlib import Path

import pytest

from law_map import IPC_TO_BNS, fix_sections, reference_table

SHARED_DIR = Path(__file__).resolve().parents[2] / "lambda_functions" / "shared"


def test_layer_copy_matches():
    assert (SHARED_DIR / "law_map.py").read_text() == (SHARED_DIR / "python" / "law_map.py").read_text()


@pytest.mark.parametrize("section,expected_act,expected_section", [
    # Model gave the right old number but invented a new one
    ({"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "Section 380 (formerly IPC 379)"},
     "Bharatiya Nyaya Sanhita, 2023 (BNS)", "Section 303 (formerly IPC 379)"),
    # Old code cited as if current, in Hindi
    ({"act": "भारतीय दंड संहिता, 2023", "section": "धारा 498-A"},
     "Bharatiya Nyaya Sanhita, 2023 (BNS)", "Section 85 (formerly IPC 498A)"),
    ({"act": "Indian Penal Code, 1860", "section": "Section 420"},
     "Bharatiya Nyaya Sanhita, 2023 (BNS)", "Section 318(4) (formerly IPC 420)"),
    ({"act": "Code of Criminal Procedure, 1973", "section": "Section 154"},
     "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)", "Section 173 (formerly CrPC 154)"),
])
def test_old_citations_are_corrected(section, expected_act, expected_section):
    fixed = fix_sections([section])[0]
    assert fixed["act"] == expected_act
    assert fixed["section"] == expected_section


@pytest.mark.parametrize("section", [
    {"act": "Consumer Protection Act, 2019", "section": "Section 35", "description": "Unlike IPC 420, this is civil"},
    {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "Section 303"},
    {"act": "Indian Penal Code", "section": "Section 999"},  # unknown: left alone
])
def test_other_citations_are_unchanged(section):
    assert fix_sections([section])[0] == section


def test_reference_table_lists_key_sections():
    table = reference_table()
    assert "IPC 420 -> BNS 318(4)" in table
    assert "CrPC 154 -> BNSS 173" in table
    assert len(IPC_TO_BNS) > 40


@pytest.mark.parametrize("section,expected_act", [
    ({"act": "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)", "section": "Section 303"}, "Bharatiya Nyaya Sanhita, 2023 (BNS)"),
    ({"act": "भारतीय दंड संहिता, 2023", "section": "धारा 85"}, "Bharatiya Nyaya Sanhita, 2023 (BNS)"),
    ({"act": "Bharatiya Nyaya Sanhita, 2023", "section": "Section 173"}, "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)"),
])
def test_new_code_act_name_is_corrected(section, expected_act):
    assert fix_sections([section])[0]["act"] == expected_act


def test_correct_new_code_citation_is_unchanged():
    section = {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)", "section": "Section 173"}
    assert fix_sections([section])[0] == section
