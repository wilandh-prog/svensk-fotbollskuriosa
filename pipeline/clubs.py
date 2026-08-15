"""Club-name canonicalization.

Canonical identity is the club's short common name (what fans and
league tables use). Wikipedia article titles and openfootball's
city-suffixed names are folded onto it via ALIASES. Unknown names fall
back to the Wikipedia article title (stable across a century of
display variation), else the display text as-is.
"""
from __future__ import annotations

# alias (casefolded) -> canonical club name
ALIASES: dict[str, str] = {
    "gais göteborg": "GAIS",
    "gais": "GAIS",
    "aik solna": "AIK",
    "aik fotboll": "AIK",
    "djurgårdens if fotboll": "Djurgårdens IF",
    "djurgårdens if fotbollförening": "Djurgårdens IF",
    "djurgården": "Djurgårdens IF",
    "trelleborg ff": "Trelleborgs FF",
    "enköpings sk fotboll": "Enköpings SK",
    "gefle if fotboll": "Gefle IF",
    "sandvikens if fotboll": "Sandvikens IF",
    "västra frölunda if fotboll": "Västra Frölunda IF",
    "västerås sk fk": "Västerås SK",
    "västerås ik fotboll": "Västerås IK",
    "redbergslids ik fotboll": "Redbergslids IK",
    "motala aif fk": "Motala AIF",
    "sandvikens aik fk": "Sandvikens AIK",
    "brynäs if fk": "Brynäs IF",
    "ifk malmö fk": "IFK Malmö",
    "ifk malmö fotboll": "IFK Malmö",
    "if saab (fotboll)": "IF Saab",
    "hammarby if fotboll": "Hammarby IF",
    "hammarby fotboll": "Hammarby IF",
    "hammarby": "Hammarby IF",
    "brommapojkarna": "IF Brommapojkarna",
    "häcken": "BK Häcken",
    "elfsborg": "IF Elfsborg",
    "öster": "Östers IF",
    "örebro sk fotboll": "Örebro SK",
    "örgryte is fotboll": "Örgryte IS",
    "ik sirius fk": "IK Sirius",
    "ik sirius fotboll": "IK Sirius",
    "västerås sk fotboll": "Västerås SK",
    "malmö ff (herrfotboll)": "Malmö FF",
    "varbergs bois": "Varbergs BoIS FC",
    "varberg": "Varbergs BoIS FC",
    "ifk norrköping (herrfotboll)": "IFK Norrköping",
}


def canonical_name(display: str, wiki_link: str | None = None) -> str:
    """Resolve a display name (+ optional wiki link title) to canonical form."""
    for candidate in (display, wiki_link):
        if not candidate:
            continue
        key = candidate.casefold().strip()
        if key in ALIASES:
            return ALIASES[key]
    import re

    name = (wiki_link or display).strip()
    # strip Wikipedia disambiguation qualifiers: "X (fotbollsklubb)" etc.
    name = re.sub(r"\s*\((?:herr)?fotboll(?:sklubb)?\)$", "", name, flags=re.I)
    return name
