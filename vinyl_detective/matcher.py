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
