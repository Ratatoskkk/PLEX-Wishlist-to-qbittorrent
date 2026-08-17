"""Quality-profile scoring: what gets picked, and what gets refused and why."""

from __future__ import annotations

from conduit.config import QualityProfile, ScoredTerm
from conduit.domain import scoring
from conftest import make_release

GIB = 1024**3


def test_prefers_4k_remux_over_everything_else(profile) -> None:
    candidates = [
        make_release("Movie 2020 1080p BluRay x264 AAC-GRP"),
        make_release("Movie 2020 2160p WEB-DL DDP5.1 H.265-GRP"),
        make_release("Movie 2020 2160p UHD BluRay REMUX DV HDR10 HEVC TrueHD 7.1 Atmos-FraMeSToR"),
    ]
    ranked = scoring.rank(candidates, profile)
    winner = scoring.best(ranked, profile)
    assert winner is not None
    assert "REMUX" in winner.release.name


def test_full_disc_is_rejected_using_the_tracker_hint(profile) -> None:
    """The name says nothing; only the tracker's ``type`` reveals it is a disc."""
    release = make_release(
        "Show S03 1080p GER Blu-ray AVC DTS-HD MA 5.1-prte",
        size_bytes=224 * GIB,
        type_name="Full Disc",
        resolution_name="1080p",
    )
    result = scoring.evaluate(release, profile)
    assert not result.accepted
    assert any(r.rule == "full_disc" for r in result.rejections)


def test_full_disc_keywords_in_the_name_are_also_caught(profile) -> None:
    result = scoring.evaluate(
        make_release("Movie 2020 2160p COMPLETE BLURAY BD66-GRP", size_bytes=60 * GIB), profile
    )
    assert not result.accepted
    assert any(r.rule in ("blocked_term", "full_disc") for r in result.rejections)


def test_seeder_floor_blocks_dead_torrents(profile) -> None:
    release = make_release("Movie 2020 2160p UHD BluRay REMUX HDR HEVC-GRP", seeders=0)
    result = scoring.evaluate(release, profile)
    assert not result.accepted
    assert any(r.rule == "seeders" for r in result.rejections)


def test_size_ceiling_is_applied_per_episode_for_packs(profile) -> None:
    """A 10-episode pack is judged on GB-per-episode, not total size."""
    huge = make_release("Show S01 2160p WEB-DL DV HDR10 H.265-GRP", size_bytes=950 * GIB)
    result = scoring.evaluate(huge, profile, episode_count=10)
    assert not result.accepted
    assert any(r.rule == "size_per_episode" for r in result.rejections)

    reasonable = scoring.evaluate(
        make_release("Show S01 2160p WEB-DL DV HDR10 H.265-GRP", size_bytes=88 * GIB),
        profile,
        episode_count=10,
    )
    assert reasonable.accepted


def test_unknown_resolution_is_rejected_when_the_profile_lists_them(profile) -> None:
    result = scoring.evaluate(make_release("Some Movie 2020 BluRay x264-GRP"), profile)
    assert not result.accepted
    assert any(r.rule == "resolutions" for r in result.rejections)


def test_freeleech_and_internal_add_score(profile) -> None:
    plain = scoring.evaluate(
        make_release("Movie 2020 2160p WEB-DL DV HDR10 H.265-GRP"), profile
    )
    boosted = scoring.evaluate(
        make_release("Movie 2020 2160p WEB-DL DV HDR10 H.265-GRP",
                     freeleech=True, internal=True),
        profile,
    )
    assert boosted.score > plain.score
    assert boosted.breakdown["freeleech"] == profile.freeleech_bonus


def test_repack_beats_the_original(profile) -> None:
    original = scoring.evaluate(
        make_release("Show S01E01 2160p WEB-DL DV HDR10 H.265-GRP"), profile
    )
    repack = scoring.evaluate(
        make_release("Show S01E01 REPACK 2160p WEB-DL DV HDR10 H.265-GRP"), profile
    )
    assert repack.score > original.score


def test_required_terms_must_be_present() -> None:
    profile = QualityProfile(
        name="strict",
        resolutions=[ScoredTerm(value="2160p", score=1000)],
        sources=[ScoredTerm(value="remux", score=100)],
        required_terms=["framestor"],
        min_score=100,
    )
    ok = scoring.evaluate(
        make_release("Movie 2020 2160p UHD BluRay REMUX HDR HEVC-FraMeSToR"), profile
    )
    bad = scoring.evaluate(
        make_release("Movie 2020 2160p UHD BluRay REMUX HDR HEVC-Other"), profile
    )
    assert ok.accepted
    assert not bad.accepted
    assert bad.rejections[0].rule == "required_term_missing"


def test_min_score_gate_is_the_last_word() -> None:
    profile = QualityProfile(
        name="picky",
        resolutions=[ScoredTerm(value="1080p", score=10)],
        sources=[ScoredTerm(value="webdl", score=10)],
        min_score=5000,
    )
    result = scoring.evaluate(make_release("Movie 2020 1080p WEB-DL x264-GRP"), profile)
    assert not result.accepted
    assert result.rejections[-1].rule == "min_score"


def test_tie_break_by_seeders_when_configured() -> None:
    profile = QualityProfile(
        name="seeded",
        resolutions=[ScoredTerm(value="2160p", score=1000)],
        sources=[ScoredTerm(value="webdl", score=100)],
        min_score=100,
        seeder_bonus_per_10=0,
        tie_break="seeders",
    )
    low = make_release("A 2020 2160p WEB-DL x265-GRP", seeders=5, size_bytes=90 * GIB)
    high = make_release("B 2020 2160p WEB-DL x265-GRP", seeders=500, size_bytes=10 * GIB)
    winner = scoring.best(scoring.rank([low, high], profile), profile)
    assert winner.release.seeders == 500


def test_rejections_are_kept_for_explanation(profile) -> None:
    """The UI needs to say *why* nothing was grabbed, not just that nothing was."""
    ranked = scoring.rank(
        [make_release("Movie 2020 480p DVDRip XviD-GRP", seeders=1)], profile
    )
    assert ranked and not ranked[0].accepted
    assert ranked[0].summary()["rejections"]


def test_upgrade_needs_to_clear_a_margin(profile) -> None:
    candidate = scoring.evaluate(
        make_release("Movie 2020 2160p UHD BluRay REMUX DV HDR10 HEVC TrueHD Atmos-GRP"), profile
    )
    assert scoring.compare(candidate, candidate.score - 200, margin=50) is True
    assert scoring.compare(candidate, candidate.score - 10, margin=50) is False
