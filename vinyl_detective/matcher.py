from dataclasses import dataclass


FUZZY_SCORE_CUTOFF = 85



@dataclass(frozen=True)
class MatchResult:
    release_id: int
    artist: str
    title: str
    median_price: float | None
    method: str  # "catalog_no", "barcode", or "fuzzy"
    score: float  # 0.0 to 1.0


def match_by_catalog(conn, ebay_title: str) -> MatchResult | None:
    """Tier 1: match an eBay title by extracted catalog number."""
    from vinyl_detective.ebay import extract_catalog_no_from_title
    from vinyl_detective.db import lookup_by_catalog, lookup_by_catalog_normalized

    cat_no = extract_catalog_no_from_title(ebay_title)
    if cat_no is None:
        return None

    row = lookup_by_catalog(conn, cat_no)
    if row is None:
        row = lookup_by_catalog_normalized(conn, cat_no)
    if row is None:
        return None

    return MatchResult(
        release_id=row["release_id"],
        artist=row["artist"],
        title=row["title"],
        median_price=row.get("median_price"),
        method="catalog_no",
        score=1.0,
    )  # 0.0 to 1.0


def match_by_barcode(conn, upc: str | None) -> MatchResult | None:
    """Tier 2: match by barcode/UPC."""
    if not upc:
        return None

    from vinyl_detective.db import lookup_by_barcode

    row = lookup_by_barcode(conn, upc)
    if row is None:
        return None

    return MatchResult(
        release_id=row["release_id"],
        artist=row["artist"],
        title=row["title"],
        median_price=row.get("median_price"),
        method="barcode",
        score=1.0,
    )
