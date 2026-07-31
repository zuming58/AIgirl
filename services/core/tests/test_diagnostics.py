from xinyu_core.diagnostics import recommend_profile


def test_recommends_high_quality_profile_for_16gb_gpu() -> None:
    recommendation = recommend_profile(16_384, 31.8)

    assert recommendation.name == "high_quality_16gb"
    assert "局部实时口型" in recommendation.avatar_strategy
    assert all("2.5D" not in note for note in recommendation.notes)


def test_compatibility_profile_keeps_high_quality_assets() -> None:
    recommendation = recommend_profile(0, 15.5)

    assert recommendation.name == "cpu_compatibility"
    assert "高质量预制状态视频" in recommendation.avatar_strategy
    assert "不使用低质量 2.5D" in recommendation.notes[0]
