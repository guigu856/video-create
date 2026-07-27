"""关键帧 / 转场 / 滤镜能力的单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from components.video_editor import (
    Clip,
    ClipCreate,
    ClipFilter,
    Keyframe,
    Track,
    Transform,
    Transition,
    VideoEditorService,
)
from components.video_editor.expressions import is_dynamic, resolve_property
from components.video_editor.models import Asset, Canvas, EditorProject, MediaMetadata
from components.video_editor.render import compile_render_plan


def test_resolve_property_constant_when_no_keyframes() -> None:
    assert resolve_property([], "x", 1920, 0) == "1920"
    assert not is_dynamic(resolve_property([], "x", 1920, 0))


def test_resolve_property_single_point_is_constant() -> None:
    keyframes = [Keyframe(time=1, x=500)]
    assert resolve_property(keyframes, "x", 100, 0) == "100"


def test_resolve_property_two_points_builds_linear_segment() -> None:
    keyframes = [Keyframe(time=0, x=100), Keyframe(time=1, x=500)]
    expression = resolve_property(keyframes, "x", 100, 5)
    assert is_dynamic(expression)
    assert "if(lt(t\\,5)" in expression
    assert "100+(400)*(t-5)/(1)" in expression


def test_resolve_property_holds_final_value_and_falls_back_to_base() -> None:
    keyframes = [
        Keyframe(time=0, width=640),
        Keyframe(time=0.8, width=1920),
        Keyframe(time=3, width=1920),
    ]
    expression = resolve_property(keyframes, "width", 640, 4.55)
    assert expression.startswith("if(lt(t\\,4.55)\\,640\\,")
    assert "1920" in expression


def test_keyframe_requires_at_least_one_property() -> None:
    with pytest.raises(ValidationError):
        Keyframe(time=0)


def test_clip_keyframes_must_be_ordered_and_in_range() -> None:
    base = {"kind": "media", "asset_id": "a1", "timeline_start": 0, "duration": 2}
    with pytest.raises(ValidationError):
        ClipCreate(**base, keyframes=[Keyframe(time=1, x=1), Keyframe(time=0, x=0)])
    with pytest.raises(ValidationError):
        ClipCreate(**base, keyframes=[Keyframe(time=0, x=0), Keyframe(time=5, x=1)])


def test_text_clip_rejects_keyframes_and_transition() -> None:
    with pytest.raises(ValidationError):
        ClipCreate(
            kind="text",
            text="hi",
            timeline_start=0,
            duration=1,
            keyframes=[Keyframe(time=0, x=0), Keyframe(time=1, x=1)],
        )
    with pytest.raises(ValidationError):
        ClipCreate(
            kind="text",
            text="hi",
            timeline_start=0,
            duration=1,
            transition_in=Transition(effect="fade", duration=0.5),
        )


def test_clip_filter_validates_params_by_kind() -> None:
    ClipFilter(kind="eq", params={"contrast": 1.1})
    with pytest.raises(ValidationError):
        ClipFilter(kind="eq", params={"bogus": 1})
    with pytest.raises(ValidationError):
        ClipFilter(kind="lut", params={})


def _media_clip(**overrides) -> Clip:
    data = {
        "id": "clip_1",
        "kind": "media",
        "asset_id": "asset_video",
        "timeline_start": 0,
        "duration": 2,
        "source_in": 0,
        "transform": Transform(width=320, height=180),
    }
    data.update(overrides)
    return Clip(**data)


def _project(clips: list[Clip], project_dir: Path) -> EditorProject:
    assets_dir = project_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    (assets_dir / "v.mp4").write_bytes(b"video")
    return EditorProject(
        id="project_effects_000001",
        name="能力测试",
        canvas=Canvas(width=320, height=180, fps=25),
        assets=[
            Asset(
                id="asset_video",
                kind="video",
                name="视频",
                path="assets/v.mp4",
                metadata=MediaMetadata(duration=10, width=320, height=180, video_codec="h264"),
            )
        ],
        tracks=[Track(id="t1", media_domain="visual", name="主轨", clips=clips)],
    )


def test_render_keyframes_emit_dynamic_scale_and_overlay(tmp_path: Path) -> None:
    clip = _media_clip(
        keyframes=[
            Keyframe(time=0, x=0, width=160, height=90, opacity=0),
            Keyframe(time=0.5, opacity=1),
            Keyframe(time=1.5, x=160, width=320, height=180),
        ]
    )
    plan = compile_render_plan(_project([clip], tmp_path), tmp_path, tmp_path / "o.mp4")
    assert "eval=frame" in plan.filtergraph
    assert "geq=" in plan.filtergraph
    assert "overlay=x=if(lt(t" in plan.filtergraph


def test_render_static_clip_keeps_plain_scale(tmp_path: Path) -> None:
    clip = _media_clip()
    plan = compile_render_plan(_project([clip], tmp_path), tmp_path, tmp_path / "o.mp4")
    assert "scale=320:180" in plan.filtergraph
    assert "eval=frame" not in plan.filtergraph


def test_render_filters_insert_nodes(tmp_path: Path) -> None:
    clip = _media_clip(filters=[ClipFilter(kind="eq", params={"saturation": 0.0})])
    plan = compile_render_plan(_project([clip], tmp_path), tmp_path, tmp_path / "o.mp4")
    assert "eq=saturation=0.0" in plan.filtergraph


def test_render_transition_builds_xfade_chain(tmp_path: Path) -> None:
    first = _media_clip(id="c1", timeline_start=0, duration=2)
    second = _media_clip(
        id="c2",
        timeline_start=1.5,
        duration=2,
        transition_in=Transition(effect="wipeleft", duration=0.5),
    )
    plan = compile_render_plan(_project([first, second], tmp_path), tmp_path, tmp_path / "o.mp4")
    assert "xfade=transition=wipeleft:duration=0.5:offset=1.5" in plan.filtergraph
    assert plan.duration == 3.5


def test_transition_requires_matching_overlap(tmp_path: Path) -> None:
    first = _media_clip(id="c1", timeline_start=0, duration=2)
    bad = _media_clip(
        id="c2",
        timeline_start=1.0,
        duration=2,
        transition_in=Transition(effect="fade", duration=0.5),
    )
    with pytest.raises(ValidationError):
        _project([first, bad], tmp_path)


def test_transition_first_clip_rejected(tmp_path: Path) -> None:
    only = _media_clip(transition_in=Transition(effect="fade", duration=0.5))
    with pytest.raises(ValidationError):
        _project([only], tmp_path)


def test_transition_rejects_keyframes_on_members(tmp_path: Path) -> None:
    first = _media_clip(
        id="c1",
        timeline_start=0,
        duration=2,
        keyframes=[Keyframe(time=0, x=0), Keyframe(time=1, x=10)],
    )
    second = _media_clip(
        id="c2",
        timeline_start=1.5,
        duration=2,
        transition_in=Transition(effect="fade", duration=0.5),
    )
    with pytest.raises(ValidationError):
        _project([first, second], tmp_path)


def test_clip_update_keyframes_and_transition_roundtrip(tmp_path: Path) -> None:
    service = VideoEditorService(tmp_path)
    project = service.create("命令测试")
    project = service.apply(
        project.id,
        {"expected_revision": 0, "commands": [
            {"type": "track.add", "media_domain": "visual", "name": "主轨"},
        ]},
    )
    track_id = project.tracks[0].id
    project = service.apply(
        project.id,
        {
            "expected_revision": 1,
            "commands": [
                {"type": "asset.add", "asset": {
                    "kind": "video", "name": "v", "path": "assets/v.mp4",
                    "metadata": {
                        "duration": 10, "width": 320, "height": 180, "video_codec": "h264",
                    },
                }},
            ],
        },
    )
    asset_id = project.assets[0].id
    project = service.apply(
        project.id,
        {
            "expected_revision": 2,
            "commands": [
                {"type": "clip.add", "track_id": track_id, "clip": {
                    "kind": "media", "asset_id": asset_id, "timeline_start": 0,
                    "duration": 2, "source_in": 0,
                    "transform": {"width": 320, "height": 180},
                }},
            ],
        },
    )
    clip_id = project.tracks[0].clips[0].id

    updated = service.apply(
        project.id,
        {
            "expected_revision": 3,
            "commands": [
                {"type": "clip.update", "track_id": track_id, "clip_id": clip_id,
                 "changes": {"keyframes": [
                     {"time": 0, "opacity": 0}, {"time": 0.5, "opacity": 1},
                 ]}},
            ],
        },
    )
    assert len(updated.tracks[0].clips[0].keyframes) == 2

    cleared = service.apply(
        project.id,
        {
            "expected_revision": 4,
            "commands": [
                {"type": "clip.update", "track_id": track_id, "clip_id": clip_id,
                 "changes": {"keyframes": []}},
            ],
        },
    )
    assert cleared.tracks[0].clips[0].keyframes == []
