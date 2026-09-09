"""Country / city / remote-scope normalisation."""

from __future__ import annotations

import re
from typing import Any

from job_scout.models.enums import RemoteScope, SourcePreference
from job_scout.models.job import GeoSnapshot, RawJobRecord
from job_scout.utils.text import collapse_ws, normalise_key

EU_EEA = {
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "HR": "Croatia",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DK": "Denmark",
    "EE": "Estonia",
    "FI": "Finland",
    "FR": "France",
    "DE": "Germany",
    "GR": "Greece",
    "HU": "Hungary",
    "IE": "Ireland",
    "IT": "Italy",
    "LV": "Latvia",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "MT": "Malta",
    "NL": "Netherlands",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SK": "Slovakia",
    "SI": "Slovenia",
    "ES": "Spain",
    "SE": "Sweden",
    "IS": "Iceland",
    "LI": "Liechtenstein",
    "NO": "Norway",
}

COUNTRY_ALIASES: dict[str, str] = {
    "south africa": "ZA",
    "rsa": "ZA",
    "za": "ZA",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "us": "US",
    "america": "US",
    "australia": "AU",
    "au": "AU",
    "united kingdom": "GB",
    "uk": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "ireland": "IE",
    "republic of ireland": "IE",
    "germany": "DE",
    "france": "FR",
    "netherlands": "NL",
    "the netherlands": "NL",
    "holland": "NL",
    "spain": "ES",
    "italy": "IT",
    "portugal": "PT",
    "sweden": "SE",
    "denmark": "DK",
    "finland": "FI",
    "norway": "NO",
    "poland": "PL",
    "belgium": "BE",
    "austria": "AT",
    "switzerland": "CH",
    "canada": "CA",
    "new zealand": "NZ",
    "india": "IN",
    "kenya": "KE",
    "nigeria": "NG",
    "ghana": "GH",
    "namibia": "NA",
    "botswana": "BW",
    "zimbabwe": "ZW",
    "mozambique": "MZ",
}
for code, name in EU_EEA.items():
    COUNTRY_ALIASES[name.lower()] = code
    COUNTRY_ALIASES[code.lower()] = code

COUNTRY_NAMES = {code: name for code, name in EU_EEA.items()}
COUNTRY_NAMES.update(
    {
        "ZA": "South Africa",
        "US": "United States",
        "AU": "Australia",
        "GB": "United Kingdom",
        "CH": "Switzerland",
        "CA": "Canada",
        "NZ": "New Zealand",
        "IN": "India",
    }
)

SA_CITIES = {
    "johannesburg",
    "pretoria",
    "cape town",
    "durban",
    "gqeberha",
    "port elizabeth",
    "bloemfontein",
    "centurion",
    "sandton",
    "midrand",
    "stellenbosch",
    "polokwane",
    "nelspruit",
    "mbombela",
    "kimberley",
    "east london",
    "soweto",
}

SA_PROVINCES = {
    "gauteng",
    "western cape",
    "kwazulu natal",
    "kwazulu-natal",
    "eastern cape",
    "free state",
    "limpopo",
    "mpumalanga",
    "north west",
    "northern cape",
}

SA_GENERIC_CENTRES = {
    "head office",
    "national",
    "various",
    "nationwide",
    "republic of south africa",
    "south african",
}

US_STATES = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}
US_STATE_ABBRS = {abbr.lower() for abbr in US_STATES.values()}

AU_STATE_ABBRS = {"nsw", "vic", "qld", "wa", "sa", "tas", "act", "nt"}
AU_STATES = {
    "new south wales",
    "victoria",
    "queensland",
    "western australia",
    "south australia",
    "tasmania",
    "australian capital territory",
    "northern territory",
}


def country_from_text(text: str | None) -> str | None:
    if not text:
        return None
    key = normalise_key(text)
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", key):
            return code
    # "Atlanta, GA" / "Denver, CO" / "Sydney, NSW" — punctuation is stripped by normalise_key.
    tokens = key.split()
    if tokens:
        last = tokens[-1]
        if last in US_STATE_ABBRS:
            return "US"
        if last in AU_STATE_ABBRS:
            return "AU"
    if any(name in key for name in US_STATES):
        return "US"
    if any(name in key for name in AU_STATES):
        return "AU"
    if any(city in key for city in SA_CITIES):
        return "ZA"
    if any(province in key for province in SA_PROVINCES):
        return "ZA"
    # SA_GENERIC_CENTRES ("Head Office", "National") are DPSA-scoped — see geo_from_raw.
    return None


def city_from_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = collapse_ws(text)
    if "," in cleaned:
        return cleaned.split(",", 1)[0].strip() or None
    key = normalise_key(cleaned)
    for city in SA_CITIES:
        if city in key:
            return city.title()
    return cleaned if cleaned and country_from_text(cleaned) is None else None


def region_from_text(text: str | None, country: str | None) -> str | None:
    if not text:
        return None
    key = normalise_key(text)
    if country == "US":
        for name, abbr in US_STATES.items():
            if name in key or re.search(rf"\b{abbr.lower()}\b", key):
                return abbr
    if country == "ZA":
        for province in (
            "gauteng",
            "western cape",
            "kwazulu natal",
            "eastern cape",
            "free state",
            "limpopo",
            "mpumalanga",
            "north west",
            "northern cape",
        ):
            if province in key:
                return province.title()
    return None


def classify_remote_scope(
    location_text: str | None,
    description: str | None,
    remote_countries: list[str] | None = None,
    timezone_restrictions: list[str] | None = None,
) -> GeoSnapshot:
    blob = " ".join(filter(None, [location_text, description])).lower()
    countries = [c.upper() for c in (remote_countries or []) if c]
    extracted = _extract_country_restrictions(blob)
    for code in extracted:
        if code not in countries:
            countries.append(code)

    scope = RemoteScope.UNKNOWN
    unknown = True
    if _mentions_worldwide(blob) and not countries:
        scope = RemoteScope.WORLDWIDE
        unknown = False
    elif re.search(r"\banywhere\b", blob) and not countries:
        scope = RemoteScope.ANYWHERE
        unknown = False
    elif re.search(r"\bglobal(ly)?\b", blob) and not countries:
        scope = RemoteScope.GLOBAL
        unknown = False
    elif re.search(r"\bemes?\b|\bemea\b", blob) and not _us_only(blob, countries):
        scope = RemoteScope.EMEA
        unknown = False
    elif re.search(r"\bafrica\b", blob) and "south africa" in blob:
        scope = RemoteScope.SOUTH_AFRICA
        unknown = False
    elif re.search(r"\bafrica\b", blob):
        scope = RemoteScope.AFRICA
        unknown = False
    elif "south africa" in blob or "za residents" in blob:
        scope = RemoteScope.SOUTH_AFRICA
        unknown = False
    elif _europe_only(blob, countries):
        scope = RemoteScope.EUROPE
        unknown = False
    elif _us_only(blob, countries):
        scope = RemoteScope.US_ONLY
        unknown = False
    elif _australia_only(blob, countries):
        scope = RemoteScope.AUSTRALIA_ONLY
        unknown = False
    elif countries:
        scope = RemoteScope.OTHER_RESTRICTED
        unknown = False
        if set(countries) <= {"ZA"}:
            scope = RemoteScope.SOUTH_AFRICA
        elif set(countries) <= set(EU_EEA):
            scope = RemoteScope.EUROPE

    timezones = list(timezone_restrictions or [])
    tz_match = re.findall(r"utc\s*[+-]\s?\d{1,2}", blob)
    for item in tz_match:
        if item not in timezones:
            timezones.append(item)

    country = country_from_text(location_text)
    return GeoSnapshot(
        location_text=location_text,
        city=city_from_text(location_text),
        region=region_from_text(location_text, country),
        country_code=country,
        country_name=COUNTRY_NAMES.get(country or ""),
        remote_scope=scope,
        remote_country_restrictions=countries,
        timezone_restrictions=timezones,
        remote_eligibility_unknown=unknown,
    )


def _mentions_worldwide(blob: str) -> bool:
    return bool(re.search(r"\b(worldwide|work from anywhere|anywhere in the world)\b", blob))


def _us_only(blob: str, countries: list[str]) -> bool:
    if countries and set(countries) <= {"US"}:
        return True
    # Do not treat EEO / "eligible to work in the US" boilerplate as a hard geo lock.
    return bool(
        re.search(
            r"(us(?:a)? residents only|must be (?:located|based) in the (?:us|united states)|"
            r"(?:remote|role|position)[^\n.]{0,40}(?:us only|united states only)|"
            r"only (?:open|available) to (?:us|usa|united states) (?:residents|citizens|candidates))",
            blob,
        )
    )


def _australia_only(blob: str, countries: list[str]) -> bool:
    if countries and set(countries) <= {"AU"}:
        return True
    return bool(re.search(r"(australia only|must be .*australia|australian residents only)", blob))


def _europe_only(blob: str, countries: list[str]) -> bool:
    if countries and set(countries) <= set(EU_EEA):
        return True
    return bool(re.search(r"(europe only|eu only|eea only|must be .*europe)", blob))


def _extract_country_restrictions(blob: str) -> list[str]:
    found: list[str] = []
    if re.search(r"us(?:a)? residents only|united states only|must be .*united states", blob):
        found.append("US")
    if "south africa" in blob:
        found.append("ZA")
    if re.search(r"\baustralia\b", blob) and "only" in blob:
        found.append("AU")
    return found


def geo_from_raw(raw: RawJobRecord, description: str) -> GeoSnapshot:
    snapshot = classify_remote_scope(
        raw.location_text,
        description,
        raw.remote_countries,
        raw.timezone_restrictions,
    )
    if not snapshot.country_code:
        snapshot.country_code = country_from_text(raw.location_text)
        snapshot.country_name = COUNTRY_NAMES.get(snapshot.country_code or "")
    # DPSA / SA public-service posts are always ZA even when centre is "Head Office".
    if not snapshot.country_code and (
        raw.source_name == "dpsa_circular"
        or (raw.source_preference == SourcePreference.GOVERNMENT and "south africa" in normalise_key(raw.company or ""))
    ):
        snapshot.country_code = "ZA"
        snapshot.country_name = COUNTRY_NAMES.get("ZA")
    return snapshot


def in_target_onsite_countries(country_code: str | None, profile: dict[str, Any]) -> bool:
    allowed = set((profile.get("geographic") or {}).get("onsite_hybrid_countries") or [])
    if not country_code:
        return False
    return country_code.upper() in allowed
