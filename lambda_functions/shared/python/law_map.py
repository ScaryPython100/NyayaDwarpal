"""
Old -> new criminal law section map (IPC -> BNS, CrPC -> BNSS), in force since 1 July 2024.

Used to ground the AI prompt and to correct citations the model gets wrong.
Keep lambda_functions/shared/law_map.py identical to this file (a unit test checks).
"""

import re
from typing import Any, Dict, List

BNS = "Bharatiya Nyaya Sanhita, 2023 (BNS)"
BNSS = "Bharatiya Nagarik Suraksha Sanhita, 2023 (BNSS)"

# IPC section -> (BNS section, short title)
IPC_TO_BNS = {
    "34": ("3(5)", "Acts done by several persons with common intention"),
    "120B": ("61", "Criminal conspiracy"),
    "302": ("103", "Murder"),
    "304": ("105", "Culpable homicide not amounting to murder"),
    "304A": ("106", "Death by negligence"),
    "304B": ("80", "Dowry death"),
    "306": ("108", "Abetment of suicide"),
    "307": ("109", "Attempt to murder"),
    "312": ("88", "Causing miscarriage"),
    "323": ("115", "Voluntarily causing hurt"),
    "324": ("118(1)", "Hurt by dangerous weapons"),
    "325": ("117", "Grievous hurt"),
    "326": ("118(2)", "Grievous hurt by dangerous weapons"),
    "341": ("126", "Wrongful restraint"),
    "342": ("127", "Wrongful confinement"),
    "354": ("74", "Assault to outrage a woman's modesty"),
    "354A": ("75", "Sexual harassment"),
    "354B": ("76", "Assault to disrobe a woman"),
    "354C": ("77", "Voyeurism"),
    "354D": ("78", "Stalking"),
    "363": ("137", "Kidnapping"),
    "376": ("64", "Rape"),
    "379": ("303", "Theft"),
    "380": ("305", "Theft in a dwelling house"),
    "384": ("308", "Extortion"),
    "392": ("309", "Robbery"),
    "395": ("310", "Dacoity"),
    "406": ("316", "Criminal breach of trust"),
    "409": ("316(5)", "Criminal breach of trust by public servant, banker or agent"),
    "411": ("317", "Receiving stolen property"),
    "415": ("318", "Cheating"),
    "417": ("318(2)", "Cheating"),
    "419": ("319", "Cheating by personation"),
    "420": ("318(4)", "Cheating and dishonestly inducing delivery of property"),
    "427": ("324", "Mischief"),
    "447": ("329", "Criminal trespass"),
    "448": ("329(4)", "House-trespass"),
    "494": ("82", "Bigamy"),
    "498A": ("85", "Cruelty by husband or his relatives"),
    "499": ("356", "Defamation"),
    "500": ("356(2)", "Defamation"),
    "503": ("351", "Criminal intimidation"),
    "504": ("352", "Intentional insult to provoke breach of peace"),
    "506": ("351(2)", "Criminal intimidation"),
    "509": ("79", "Insulting the modesty of a woman"),
}

# CrPC section -> (BNSS section, short title)
CRPC_TO_BNSS = {
    "41": ("35", "Arrest without warrant"),
    "41A": ("35(3)", "Notice of appearance before police"),
    "50": ("47", "Right to know grounds of arrest and right to bail"),
    "57": ("58", "Produced before a Magistrate within 24 hours"),
    "125": ("144", "Maintenance of wife, children and parents"),
    "154": ("173", "FIR (information in cognizable cases)"),
    "156": ("175", "Police power to investigate"),
    "161": ("180", "Examination of witnesses by police"),
    "164": ("183", "Recording of statements by a Magistrate"),
    "167": ("187", "Detention when investigation is not complete"),
    "200": ("223", "Complaint to a Magistrate"),
    "436": ("478", "Bail in bailable offences"),
    "437": ("480", "Bail in non-bailable offences"),
    "438": ("482", "Anticipatory bail"),
}

# Other laws people most often need, for the prompt
OTHER_LAWS = [
    "Code on Wages, 2019 s.17 (wages due before the 7th of next month) and s.5 (minimum wage)",
    "Consumer Protection Act, 2019 s.35 (complaint to District Consumer Commission, claims up to Rs 50 lakh)",
    "Protection of Women from Domestic Violence Act, 2005 s.12 (protection, residence and money orders)",
    "Dowry Prohibition Act, 1961 s.3 (giving or taking dowry)",
    "Negotiable Instruments Act, 1881 s.138 (cheque bounce)",
    "Sexual Harassment of Women at Workplace Act, 2013 s.9 (complaint within 3 months)",
    "Specific Relief Act, 1963 s.6 (recovering possession after illegal eviction)",
    "Transfer of Property Act, 1882 s.106 (notice to end a tenancy)",
    "Model Tenancy Act, 2021 s.11 (security deposit, only where the state adopted it)",
    "Information Technology Act, 2000 s.66C / s.66D (identity theft, online cheating)",
    "Legal Services Authorities Act, 1987 s.12 (free legal aid)",
    "Right to Information Act, 2005 s.6",
]

# Common situations and the right citations, for the prompt
COMMON_SITUATIONS = [
    "online / OTP / UPI fraud or fake call: BNS 318(4) cheating and BNS 319 cheating by personation, IT Act s.66D; report at once on 1930 or cybercrime.gov.in",
    "phone or bag snatched: BNS 304 snatching; stolen: BNS 303 theft",
    "police refuse FIR: BNSS 173 (Zero FIR, e-FIR), then complaint to SP under BNSS 173(4), then Magistrate under BNSS 175(3)",
    "landlord keeps security deposit: civil recovery (Indian Contract Act, 1872 s.73), Model Tenancy Act s.11 where adopted; not a consumer case",
    "salary not paid: Code on Wages, 2019 s.17; complaint to the Labour Commissioner",
    "dowry harassment or beating by husband: BNS 85, Domestic Violence Act s.12, Dowry Prohibition Act s.3",
]

_BNS_NUMBERS = {new.split("(")[0] for new, _ in IPC_TO_BNS.values()}
_BNSS_NUMBERS = {new.split("(")[0] for new, _ in CRPC_TO_BNSS.values()}
_NEW_CODE_YEAR = re.compile(r"2023")

_OLD_IPC = re.compile(r"(?:\bIPC\b|Indian Penal Code|भारतीय दंड संहिता|दंड संहिता)", re.I)
_OLD_CRPC = re.compile(r"(?:\bCrPC\b|\bCr\.P\.C\b|Code of Criminal Procedure|दंड प्रक्रिया संहिता)", re.I)
_NEW_BNS = re.compile(r"(?:\bBNS\b|Bharatiya Nyaya Sanhita|भारतीय न्याय संहिता)", re.I)
_NEW_BNSS = re.compile(r"(?:\bBNSS\b|Bharatiya Nagarik Suraksha Sanhita|नागरिक सुरक्षा संहिता)", re.I)
_FORMERLY = re.compile(r"(IPC|CrPC)\s*(?:section|sec\.?|s\.)?\s*(\d+[A-Z]?)", re.I)
_NUMBER = re.compile(r"(\d+)\s*-?\s*([A-Z])?\b")


def _normalize(number: str, letter: str = "") -> str:
    return f"{number}{(letter or '').upper()}"


def reference_table() -> str:
    """Compact old -> new list for the AI prompt"""
    ipc = "; ".join(f"IPC {old} -> BNS {new} {title}" for old, (new, title) in IPC_TO_BNS.items())
    crpc = "; ".join(f"CrPC {old} -> BNSS {new} {title}" for old, (new, title) in CRPC_TO_BNSS.items())
    return (f"{ipc}.\n{crpc}.\nOther laws: " + "; ".join(OTHER_LAWS) + ".\n"
            + "Common situations: " + "; ".join(COMMON_SITUATIONS) + ".")


def _old_reference(section: Dict[str, Any]):
    """Return ('IPC'|'CrPC', number) when the citation refers to an old-code section"""
    act = str(section.get("act", ""))
    number_text = str(section.get("section", ""))
    # Not the description: it may mention an old section while citing another Act
    combined = f"{act} {number_text}"

    formerly = _FORMERLY.search(combined)
    if formerly:
        return formerly.group(1).upper().replace("CRPC", "CrPC"), formerly.group(2).upper()

    match = _NUMBER.search(number_text)
    if not match:
        return None
    number = _normalize(match.group(1), match.group(2))
    if _OLD_CRPC.search(act):
        return "CrPC", number
    if _OLD_IPC.search(act) and not _NEW_BNS.search(act):
        # "Penal Code, 2023" with a new BNS number is really a BNS citation (handled later)
        if _NEW_CODE_YEAR.search(act) and (number not in IPC_TO_BNS or number in _BNS_NUMBERS):
            return None
        return "IPC", number
    return None


def fix_sections(sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rewrite citations of repealed IPC/CrPC sections (or wrong new numbers) to the correct BNS/BNSS section"""
    fixed = []
    for section in sections:
        if not isinstance(section, dict):
            fixed.append(section)
            continue
        reference = _old_reference(section)
        if reference:
            code, number = reference
            table, new_act = (IPC_TO_BNS, BNS) if code == "IPC" else (CRPC_TO_BNSS, BNSS)
            if number in table:
                new_number, title = table[number]
                section = dict(section)
                section["act"] = new_act
                section["section"] = f"Section {new_number} (formerly {code} {number})"
                if not section.get("description"):
                    section["description"] = title
        else:
            section = _fix_new_code_act(section)
        fixed.append(section)
    return fixed


def _fix_new_code_act(section: Dict[str, Any]) -> Dict[str, Any]:
    """Fix the act name when a 2023 code is cited with a number that belongs to the other code"""
    act = str(section.get("act", ""))
    is_new_code = _NEW_BNS.search(act) or _NEW_BNSS.search(act) or (
        _NEW_CODE_YEAR.search(act) and (_OLD_IPC.search(act) or _OLD_CRPC.search(act)))
    if not is_new_code:
        return section
    match = _NUMBER.search(str(section.get("section", "")))
    if not match:
        return section
    number = match.group(1)
    in_bns, in_bnss = number in _BNS_NUMBERS, number in _BNSS_NUMBERS
    claims_bnss = bool(_NEW_BNSS.search(act)) or bool(_OLD_CRPC.search(act))
    if in_bns and not in_bnss and act != BNS and (claims_bnss or not _NEW_BNS.search(act)):
        return dict(section, act=BNS)
    if in_bnss and not in_bns and act != BNSS and not claims_bnss:
        return dict(section, act=BNSS)
    return section
