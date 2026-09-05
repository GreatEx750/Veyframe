from __future__ import annotations

from demodirector_contracts import CaptionStyleConfig, NarrationSegment
from demodirector_worker.captions import CaptionService


def test_word_highlights_are_contiguous_and_keep_phrase_visible() -> None:
    from demodirector_worker.captions import word_highlights

    states = word_highlights("This explains the fit,", 100, 1700)
    assert [s.word_index for s in states] == [0, 1, 2, 3]
    assert all(s.words == ("This", "explains", "the", "fit,") for s in states)
    assert states[0].start_ms == 100 and states[-1].end_ms == 1700
    assert all(a.end_ms == b.start_ms for a, b in zip(states, states[1:], strict=False))


def test_empty_and_sub_word_duration_highlights_are_safe() -> None:
    from demodirector_worker.captions import word_highlights

    assert word_highlights("", 0, 1000) == []
    assert word_highlights("hello", 10, 10) == []
    assert all(s.end_ms > s.start_ms for s in word_highlights("a b c", 0, 1))


def test_highlight_frames_share_boundaries_without_accumulating_rounding() -> None:
    from demodirector_worker.captions import highlight_frame_window, word_highlights

    states = word_highlights("one two three four five six seven", 0, 2300)
    windows = [highlight_frame_window(state) for state in states]
    assert windows[0][0] == 0
    assert windows[-1][1] == 69
    assert all(a[1] == b[0] for a, b in zip(windows, windows[1:], strict=False))
    assert sum(end - start for start, end in windows) == 69


def test_presentation_highlights_keep_inactive_pixels_and_box_height_fixed(
    tmp_path: object,
) -> None:
    import itertools
    import subprocess
    from pathlib import Path

    from demodirector_worker.presentation_assets import AuthoredSlideRenderer, run_ffmpeg
    from PIL import Image, ImageChops

    directory = Path(str(tmp_path))
    listing = (
        AuthoredSlideRenderer(directory)
        .caption_images("This explains pygmy fit", directory, 2.3)
        .read_text()
    )
    assert listing.count("option framerate 30") == 5
    assert (
        abs(
            sum(
                float(line.split()[1])
                for line in listing.splitlines()
                if line.startswith("duration ")
            )
            - 2.3
        )
        < 0.00001
    )
    images = [Image.open(directory / f"caption-{i:03d}.png").convert("RGBA") for i in range(4)]
    bounds = []
    for img in images:
        mask = Image.new("L", img.size)
        mask.putdata(
            [
                255 if img.getpixel((x, y)) == (157, 232, 210, 255) else 0
                for y in range(img.height)
                for x in range(img.width)
            ]
        )
        bounds.append(mask.getbbox())
    assert all(box is not None for box in bounds)
    assert len({(box[1], box[3]) for box in bounds if box}) == 1
    for first, second, first_box, second_box in zip(
        images, images[1:], bounds, bounds[1:], strict=False
    ):
        difference = ImageChops.difference(first, second)
        for box in (first_box, second_box):
            assert box is not None
            difference.paste((0, 0, 0, 0), box)
        assert difference.convert("RGB").getbbox() is None
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(directory / "captions.txt"),
            "-vf",
            "fps=30",
            "-t",
            "2.3",
            "-c:v",
            "qtrle",
            "-threads",
            "2",
            str(directory / "captions.mov"),
        ],
        directory,
    )
    decoded = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(directory / "captions.mov"),
            "-f",
            "framemd5",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    hashes = [
        line.rsplit(",", 1)[1].strip()
        for line in decoded.splitlines()
        if line and not line.startswith("#")
    ]
    assert [len(list(frames)) for _, frames in itertools.groupby(hashes)] == [17, 18, 17, 17]


def test_product_renderer_draws_each_active_word_with_mint_background(tmp_path: object) -> None:
    from pathlib import Path

    from demodirector_contracts import CaptionClip
    from demodirector_worker.renderer import FFmpegRenderer

    renderer = FFmpegRenderer(Path(str(tmp_path)), Path(str(tmp_path)))
    filters = renderer._caption_filter(
        CaptionClip(id="c", scene_id="s", start_ms=0, end_ms=2000, text="This explains the fit"),
        "in",
        "out",
    )
    assert filters.count("boxcolor=0x9DE8D2") == 4
    assert "gte(t,0.500)*lt(t,1.000)" in filters


def narration(duration_ms: int = 2_400) -> NarrationSegment:
    return NarrationSegment(
        scene_id="scene-1",
        order=0,
        text="Create a polished product demo and share it with your team.",
        audio_path="narration/scene-1.wav",
        duration_ms=duration_ms,
    )


def test_captions_cover_known_narration_and_fit_audio_duration() -> None:
    track = CaptionService(max_words_per_caption=4).generate_track(
        narration(),
        CaptionStyleConfig(font_size=36, position="bottom"),
    )

    assert " ".join(clip.text for clip in track.clips) == narration().text
    assert track.clips[0].start_ms == 0
    assert track.clips[-1].end_ms == narration().duration_ms
    assert all(clip.end_ms <= track.duration_ms for clip in track.clips)
    assert track.model_validate_json(track.model_dump_json()) == track


def test_captions_can_be_disabled() -> None:
    track = CaptionService().generate_track(
        narration(),
        CaptionStyleConfig(enabled=False),
    )

    assert track.style.enabled is False
    assert track.clips == []


def test_short_audio_still_produces_valid_non_negative_timing() -> None:
    track = CaptionService(max_words_per_caption=1).generate_track(
        narration(1),
        CaptionStyleConfig(),
    )

    assert len(track.clips) == 1
    assert track.clips[0].start_ms == 0
    assert track.clips[0].end_ms == 1
