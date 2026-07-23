"""
Podscan Guest sheet flattener.

Podscan exports a *different* Google Sheet each time, but always with the same
shape: a `List Info` catalog tab plus one tab per podcast, each row an episode,
with the guests packed into a `guest_raw_json` column (a JSON list of guest
objects). The Lead Management System, on the other hand, wants one lead per
guest in a stable, flat format.

This module is the contract in the middle. Given ANY Podscan sheet URL it:
  1. reads every podcast tab via the shared service-account GoogleSheetService,
  2. explodes guest_raw_json -> one record per guest per episode,
  3. dedups guests *within this sheet* on normalized name+company, accumulating
     every episode appearance onto the single surviving record,
  4. tags each guest prospect / public_figure / host_or_regular so downstream
     can filter without anyone being dropped,
  5. writes ONE canonical per-guest CSV whose columns never change.

Because the output schema is fixed, the LMS only ever writes a single mapping
spec against it -- which sheet the guests came from is invisible downstream.
Cross-*sheet* dedup (the same guest surfacing in a later export) is the LMS's
job, on the same normalized name+company key emitted here as `dedup_key`.

CLI:
    python -m podscan.sheet_flattener <sheet_url> [--out guests.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from google_utils.google_sheet import GoogleSheetService

logger = logging.getLogger(__name__)

# --- structural contract -----------------------------------------------------
CATALOG_TAB = "List Info"
# A tab must have these to be treated as a podcast tab; if Podscan changes the
# export we fail loudly rather than silently emitting garbage.
REQUIRED_COLUMNS = {"podcast_name", "episode_id", "episode_title", "guest_raw_json"}

# Canonical output columns, in order. This is the LMS contract -- do not reorder
# or rename without updating the podscan-guest mapping spec on the LMS side.
CANONICAL_COLUMNS = [
    "source",
    "dedup_key",
    "lead_tag",
    "guest_name",
    "first_name",
    "last_name",
    "company",
    "job_title",
    "industry",
    "linkedin",
    "twitter",
    "instagram",
    "website",
    "other_social",
    "appearance_count",
    "podcast_name",
    "podcast_id",
    "episode_title",
    "episode_url",
    "episode_published_at",
    "episode_id",
    "speaker_label",
    "all_appearances_json",
]

SOURCE_LABEL = "podscan-guest"

# --- tagging heuristics (tunable) --------------------------------------------
# occupation strings that mark someone as a public figure discussed on-air
# rather than a bookable prospect.
_PUBLIC_FIGURE_RX = re.compile(
    r"\b("
    r"president|ex-president|former president|vice president|"
    r"senator|congress(man|woman|person)?|representative|governor|mayor|"
    r"prime minister|secretary of|attorney general|first lady|"
    r"politician|public figure|head of state|monarch|king|queen|prince|princess|"
    r"celebrity|musician|singer|rapper|songwriter|band|"
    r"actor|actress|comedian|voice actor|performer|"
    r"athlete|quarterback|nba|nfl|mlb|olympian|footballer|boxer"
    r")\b",
    re.IGNORECASE,
)
# same person recurring on a single show this many times -> treat as host/cast,
# not a guest lead.
_HOST_MIN_APPEARANCES = 5

_NA_VALUES = {"", "n/a", "na", "none", "null", "-", "unknown"}

# Placeholder "names" the transcript analysis emits when it can't identify a
# real person — diarization labels (SPEAKER_03), numbered/lettered stand-ins
# (Guest 1, Guest A), and generic role words. These are not leads.
_JUNK_NAME_RX = re.compile(
    r"^\s*("
    r"speaker[\s_]?\d+|"
    r"guest\s*[0-9a-z]?|"
    r"host|co-?host|panelist|caller|audience|announcer|narrator|"
    r"unknown|unnamed|anonymous|multiple guests?|various|the guest|guest speaker|"
    r"n/?a"
    r")\s*$",
    re.IGNORECASE,
)


def _is_junk_name(name: str) -> bool:
    return bool(_JUNK_NAME_RX.match(name or ""))


def _clean(value: Optional[str]) -> str:
    return (value or "").strip()


def _is_na(value: Optional[str]) -> bool:
    return _clean(value).lower() in _NA_VALUES


def _norm(value: Optional[str]) -> str:
    """Deterministic normalization: lowercase, strip punctuation, collapse WS."""
    v = _clean(value).lower()
    v = re.sub(r"[^a-z0-9]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def dedup_key(name: Optional[str], company: Optional[str]) -> str:
    """Podscan identity key: normalized name + normalized company."""
    n = _norm(name)
    c = "" if _is_na(company) else _norm(company)
    return f"{n}|{c}"


def split_name(full: str) -> Tuple[str, str]:
    parts = _clean(full).split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def classify_social(urls) -> Dict[str, str]:
    """Bucket a list of social URLs by platform. First URL per bucket wins."""
    out = {"twitter": "", "linkedin": "", "instagram": "", "website": "", "other_social": ""}
    if not urls:
        return out
    if isinstance(urls, str):
        urls = [urls]
    for raw in urls:
        u = _clean(raw)
        if not u:
            continue
        host = (urlparse(u).netloc or u).lower()
        if ("twitter.com" in host or host == "x.com" or host.endswith(".x.com")) and not out["twitter"]:
            out["twitter"] = u
        elif "linkedin.com" in host and not out["linkedin"]:
            out["linkedin"] = u
        elif "instagram.com" in host and not out["instagram"]:
            out["instagram"] = u
        elif not out["website"] and host and "." in host:
            out["website"] = u
        elif not out["other_social"]:
            out["other_social"] = u
    return out


def _first_non_empty(*vals: str) -> str:
    for v in vals:
        if not _is_na(v):
            return _clean(v)
    return ""


class _GuestAgg:
    """Accumulates every appearance of one guest (one dedup_key) in this sheet."""

    __slots__ = (
        "dedup_key", "name", "company", "job_title", "industry",
        "socials", "appearances", "occupations", "podcasts",
    )

    def __init__(self, key: str, name: str):
        self.dedup_key = key
        self.name = name
        self.company = ""
        self.job_title = ""
        self.industry = ""
        self.socials = {"twitter": "", "linkedin": "", "instagram": "", "website": "", "other_social": ""}
        self.appearances: List[dict] = []
        self.occupations: List[str] = []
        self.podcasts = set()

    def add(self, *, name, company, occupation, industry, socials, appearance):
        # Prefer the first non-N/A value we see for each descriptive field.
        if not self.name and name:
            self.name = name
        self.company = _first_non_empty(self.company, "" if _is_na(company) else company)
        self.job_title = _first_non_empty(self.job_title, "" if _is_na(occupation) else occupation)
        self.industry = _first_non_empty(self.industry, "" if _is_na(industry) else industry)
        for k, v in socials.items():
            if v and not self.socials[k]:
                self.socials[k] = v
        if occupation and not _is_na(occupation):
            self.occupations.append(occupation)
        self.podcasts.add(appearance.get("podcast_name", ""))
        self.appearances.append(appearance)

    def _representative(self) -> dict:
        """Most recent appearance (by published_at) as the headline provenance."""
        def keyfn(a):
            return _clean(a.get("episode_published_at"))
        return sorted(self.appearances, key=keyfn, reverse=True)[0]

    def tag(self) -> str:
        # 1) occupation says public figure -> tag as such.
        if any(_PUBLIC_FIGURE_RX.search(o or "") for o in self.occupations):
            return "public_figure"
        # 2) no company and seen across multiple different shows -> discussed
        #    public figure (e.g. a politician quoted on several podcasts).
        if not self.company and len(self.podcasts) >= 2:
            return "public_figure"
        # 3) recurring on exactly one show, or company == that show's brand ->
        #    host/cast, not a guest lead.
        if len(self.podcasts) == 1:
            only_podcast = next(iter(self.podcasts))
            if len(self.appearances) >= _HOST_MIN_APPEARANCES:
                return "host_or_regular"
            if self.company and _norm(self.company) == _norm(only_podcast):
                return "host_or_regular"
        return "prospect"

    def to_record(self) -> dict:
        first, last = split_name(self.name)
        rep = self._representative()
        return {
            "source": SOURCE_LABEL,
            "dedup_key": self.dedup_key,
            "lead_tag": self.tag(),
            "guest_name": self.name,
            "first_name": first,
            "last_name": last,
            "company": self.company,
            "job_title": self.job_title,
            "industry": self.industry,
            "linkedin": self.socials["linkedin"],
            "twitter": self.socials["twitter"],
            "instagram": self.socials["instagram"],
            "website": self.socials["website"],
            "other_social": self.socials["other_social"],
            "appearance_count": len(self.appearances),
            "podcast_name": rep.get("podcast_name", ""),
            "podcast_id": rep.get("podcast_id", ""),
            "episode_title": rep.get("episode_title", ""),
            "episode_url": rep.get("episode_url", ""),
            "episode_published_at": rep.get("episode_published_at", ""),
            "episode_id": rep.get("episode_id", ""),
            "speaker_label": rep.get("speaker_label", ""),
            "all_appearances_json": json.dumps(self.appearances, ensure_ascii=False),
        }


def flatten_workbook(
    sheet_url: str,
    svc: Optional[GoogleSheetService] = None,
) -> List[dict]:
    """Read a Podscan workbook and return canonical per-guest records."""
    svc = svc or GoogleSheetService()
    sid = svc.extract_spreadsheet_id(sheet_url)

    ok, sheets = svc.list_sheets(sid)
    if not ok:
        raise RuntimeError(f"Could not open sheet {sid}: {sheets}")

    podcast_tabs = [s for s in sheets if s != CATALOG_TAB]
    if not podcast_tabs:
        raise RuntimeError("No podcast tabs found in workbook")

    aggs: Dict[str, _GuestAgg] = {}
    skipped_tabs: List[str] = []
    total_guest_instances = 0

    for tab in podcast_tabs:
        ok, vals = svc.get_sheet_values(sid, f"'{tab}'!A1:Z5000")
        if not ok or not vals:
            skipped_tabs.append(tab)
            continue
        header = vals[0]
        idx = {h: i for i, h in enumerate(header)}
        if not REQUIRED_COLUMNS.issubset(set(header)):
            missing = REQUIRED_COLUMNS - set(header)
            logger.warning("Tab %r missing columns %s -- skipping", tab, missing)
            skipped_tabs.append(tab)
            continue

        def cell(row, col):
            i = idx.get(col)
            return row[i] if i is not None and i < len(row) else ""

        for row in vals[1:]:
            raw = cell(row, "guest_raw_json")
            if not _clean(raw):
                continue
            try:
                guests = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not isinstance(guests, list):
                continue

            appearance_common = {
                "podcast_name": cell(row, "podcast_name"),
                "podcast_id": cell(row, "podcast_id"),
                "episode_id": cell(row, "episode_id"),
                "episode_title": cell(row, "episode_title"),
                "episode_url": cell(row, "episode_url"),
                "episode_published_at": cell(row, "published_at"),
            }

            for gu in guests:
                if not isinstance(gu, dict):
                    continue
                name = _clean(gu.get("guest_name"))
                if not name or _is_junk_name(name):
                    continue
                total_guest_instances += 1
                company = gu.get("guest_company")
                key = dedup_key(name, company)
                agg = aggs.get(key)
                if agg is None:
                    agg = aggs[key] = _GuestAgg(key, name)
                appearance = dict(appearance_common)
                appearance["speaker_label"] = gu.get("speaker_label", "")
                agg.add(
                    name=name,
                    company=company,
                    occupation=gu.get("guest_occupation"),
                    industry=gu.get("guest_industry"),
                    socials=classify_social(gu.get("guest_social_media_links")),
                    appearance=appearance,
                )

    records = [agg.to_record() for agg in aggs.values()]
    logger.info(
        "Flattened %d guest instances -> %d unique guests (%d tabs, %d skipped)",
        total_guest_instances, len(records), len(podcast_tabs), len(skipped_tabs),
    )
    if skipped_tabs:
        logger.info("Skipped tabs: %s", skipped_tabs)
    return records


def write_csv(records: List[dict], out_path: str) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANONICAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Flatten a Podscan guest sheet to a canonical per-guest CSV")
    ap.add_argument("sheet_url", help="Google Sheets URL or spreadsheet ID")
    ap.add_argument("--out", default="podscan_guests.csv", help="output CSV path")
    ap.add_argument("--summary", action="store_true", help="print tag/field summary")
    args = ap.parse_args(argv)

    records = flatten_workbook(args.sheet_url)
    write_csv(records, args.out)
    print(f"Wrote {len(records)} guests -> {args.out}")

    if args.summary:
        from collections import Counter
        tags = Counter(r["lead_tag"] for r in records)
        print("Tag split:", dict(tags))
        for f in ("company", "industry", "job_title", "linkedin", "twitter", "website"):
            print(f"  has {f}: {sum(1 for r in records if _clean(r[f]))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
