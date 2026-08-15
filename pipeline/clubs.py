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
    "gefle if ff": "Gefle IF",
    # the league API drops or adds suffixes on many club names
    "helsingborg": "Helsingborgs IF",
    "helsingborg if": "Helsingborgs IF",
    "falkenberg": "Falkenbergs FF",
    "östersund": "Östersunds FK",
    "jönköpings södra": "Jönköpings Södra IF",
    "jönköping södra if": "Jönköpings Södra IF",
    "akropolis": "Akropolis IF",
    "västerås": "Västerås SK",
    "halmstad bk": "Halmstads BK",
    "vasalund": "Vasalunds IF",
    "dalkurd": "Dalkurd FF",
    "enköpings sk fk": "Enköpings SK",
    "bodens bk ff": "Bodens BK",
    "ik frej täby": "IK Frej",
    "athletic fc united": "Nordic United FC",
    # women's clubs (kept apart from the men's clubs by the ns column,
    # so short display names are safe): article renames folded together
    "aik fotboll damer": "AIK",
    "djurgårdens if dam": "Djurgårdens IF",
    "djurgårdens if damfotbollsförening": "Djurgårdens IF",
    "hammarby fotboll (damer)": "Hammarby IF",
    "hammarby if dff": "Hammarby IF",
    "hammarby if fotboll (damer)": "Hammarby IF",
    "if brommapojkarna (damer)": "IF Brommapojkarna",
    "if limhamn bunkeflo (damer)": "IF Limhamn Bunkeflo",
    "fc rosengård (damfotboll)": "FC Rosengård",
    "linköping fc": "Linköpings FC",
    "kopparbergs/göteborg fc": "BK Häcken FF",
    "kristianstad/wä dff": "Kristianstads DFF",
    "ifk norrköping (herrfotboll)": "IFK Norrköping",
}


# Women's football names that would otherwise collide with a *different*
# men's club: the league API calls BK Häcken FF simply "BK Häcken", and
# IFK Norrköping DFK "IFK Norrköping". Consulted only for ns="dam".
DAM_ALIASES: dict[str, str] = {
    "bk häcken": "BK Häcken FF",
    "göteborg fc": "BK Häcken FF",
    "ifk norrköping": "IFK Norrköping DFK",
    "ik uppsala": "IK Uppsala Fotboll",
    "kristianstad dff": "Kristianstads DFF",
    "fc rosengård malmö": "FC Rosengård",
    "ldb fc malmö": "FC Rosengård",
    "aik dff": "AIK",
    "djurgårdens if dff": "Djurgårdens IF",
    "piteå if dff": "Piteå IF Dam",
    "östers if": "Östers IF Dam",
    "tyresö": "Tyresö FF",
    "älvsjö aik ff": "Älvsjö AIK",
    "umeå ik": "Umeå IK FF",
    "umeå södra dff": "Umeå Södra FF",
    "alingsås if": "Alingsås IF FF",
    "jitex mölndal bk": "Jitex BK",
    "holmalunds if alingsås": "Holmalunds IF",
}


def canonical_name(display: str, wiki_link: str | None = None, ns: str = "herr") -> str:
    """Resolve a display name (+ optional wiki link title) to canonical form.

    `ns` selects the club namespace ("herr"/"dam"); several women's teams
    share a name with an unrelated men's club, so the namespace decides.
    """
    tables = ([DAM_ALIASES, ALIASES] if ns == "dam" else [ALIASES])
    for candidate in (display, wiki_link):
        if not candidate:
            continue
        key = candidate.casefold().strip()
        for table in tables:
            if key in table:
                return table[key]
    import re

    name = (wiki_link or display).strip()
    # strip Wikipedia disambiguation qualifiers: "X (fotbollsklubb)",
    # "X (damer)" etc. — the namespace already keeps the teams apart
    name = re.sub(r"\s*\((?:herr|dam)?fotboll(?:sklubb)?\)$", "", name, flags=re.I)
    name = re.sub(r"\s*\((?:damer|herrar|dam|herr)\)$", "", name, flags=re.I)
    return name
