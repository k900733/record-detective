from vinyl_detective.matcher import MatchResult, FUZZY_SCORE_CUTOFF


def test_match_result_fields():
    result = MatchResult(
        release_id=12345,
        artist="Art Blakey",
        title="Moanin'",
        median_price=45.50,
        method="catalog_no",
        score=1.0,
    )
    assert result.release_id == 12345
    assert result.artist == "Art Blakey"
    assert result.title == "Moanin'"
    assert result.median_price == 45.50
    assert result.method == "catalog_no"
    assert result.score == 1.0


def test_match_result_none_price():
    result = MatchResult(
        release_id=1,
        artist="X",
        title="Y",
        median_price=None,
        method="fuzzy",
        score=0.9,
    )
    assert result.median_price is None


def test_fuzzy_score_cutoff():
    assert FUZZY_SCORE_CUTOFF == 85
