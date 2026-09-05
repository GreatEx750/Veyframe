from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Final, Literal

PresentationRole = Literal["intro", "product", "outro"]
TransitionName = Literal[
    "stagger-tags",
    "palette-cut",
    "split-reveal",
    "prompt-sequence",
    "focus-reveal",
    "review-reveal",
    "stagger-cards",
    "brand-hold",
]
PaletteToken = Literal[
    "canvas.pine",
    "canvas.mint",
    "ink.dark",
    "ink.light",
    "surface.ivory",
    "surface.mint",
    "accent.coral",
    "accent.mint",
    "outline.dark",
    "outline.mint",
]
CopyAlignment = Literal["left", "center"]

PRESENTATION_PACK_ID: Final = "presentation-story@1"
PRESENTATION_RENDER_RECIPE_VERSION: Final = "presentation-story-render-v1"
PRESENTATION_DURATION_MS: Final = 120_000
INTRO_END_MS: Final = 5_000
OUTRO_START_MS: Final = 115_000

PRESENTATION_TEMPLATE_IDS: Final = (
    "hook-question@1",
    "brand-reveal@1",
    "product-split@1",
    "guided-workflow@1",
    "template-populate@1",
    "review-gate@1",
    "constraints-three-up@1",
    "brand-outro@1",
)

_FORBIDDEN_RUNTIME_FIELD_PARTS: Final = frozenset({"code", "expression", "path"})
_ALLOWED_PALETTE_TOKENS: Final = frozenset(
    {
        "canvas.pine",
        "canvas.mint",
        "ink.dark",
        "ink.light",
        "surface.ivory",
        "surface.mint",
        "accent.coral",
        "accent.mint",
        "outline.dark",
        "outline.mint",
    }
)
_ALLOWED_TRANSITIONS: Final = frozenset(
    {
        "stagger-tags",
        "palette-cut",
        "split-reveal",
        "prompt-sequence",
        "focus-reveal",
        "review-reveal",
        "stagger-cards",
        "brand-hold",
    }
)
_PALETTE_HEX: Final[Mapping[PaletteToken, str]] = MappingProxyType(
    {
        "canvas.pine": "173D34",
        "canvas.mint": "98E3CD",
        "ink.dark": "102B25",
        "ink.light": "F7F2E8",
        "surface.ivory": "F7F2E8",
        "surface.mint": "DFF8F0",
        "accent.coral": "FF6B5F",
        "accent.mint": "98E3CD",
        "outline.dark": "102B25",
        "outline.mint": "98E3CD",
    }
)


@dataclass(frozen=True, slots=True)
class Aperture:
    """A normalized, authored product aperture within a 16:9 composition."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.w, self.h)
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("aperture values must be normalized between 0 and 1")
        if self.w <= 0 or self.h <= 0:
            raise ValueError("aperture width and height must be positive")
        if self.x + self.w > 1 or self.y + self.h > 1:
            raise ValueError("aperture must remain inside the composition")


@dataclass(frozen=True, slots=True)
class PaletteTokenRoles:
    canvas: PaletteToken
    ink: PaletteToken
    surface: PaletteToken
    accent: PaletteToken
    outline: PaletteToken

    def __post_init__(self) -> None:
        for role, token in (
            ("canvas", self.canvas),
            ("ink", self.ink),
            ("surface", self.surface),
            ("accent", self.accent),
            ("outline", self.outline),
        ):
            if not token.startswith(f"{role}."):
                raise ValueError(f"palette role {role} must use a {role} token")


def _palette_values(palette: PaletteTokenRoles) -> tuple[PaletteToken, ...]:
    return (
        palette.canvas,
        palette.ink,
        palette.surface,
        palette.accent,
        palette.outline,
    )


@dataclass(frozen=True, slots=True)
class CopyLayout:
    """Authored normalized copy geometry; no model may supply these values."""

    x: float
    y: float
    panel_width: float
    panel_height: float
    alignment: CopyAlignment

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.panel_width, self.panel_height)
        if any(not 0 <= value <= 1 for value in values):
            raise ValueError("copy layout values must be normalized between 0 and 1")
        if self.x + self.panel_width > 1 or self.y + self.panel_height > 1:
            raise ValueError("copy layout must remain inside the composition")
        if self.alignment not in {"left", "center"}:
            raise ValueError(f"unsupported copy alignment: {self.alignment}")


@dataclass(frozen=True, slots=True)
class AuthoredTransition:
    """Trusted motion recipe stored with the versioned presentation pack."""

    name: TransitionName
    duration_ms: int
    product_offset_x: float = 0
    product_offset_y: float = 0
    copy_offset_x: float = 0
    copy_offset_y: float = 0

    def __post_init__(self) -> None:
        if self.name not in _ALLOWED_TRANSITIONS:
            raise ValueError(f"unsupported transition: {self.name}")
        if not 0 <= self.duration_ms <= 2_000:
            raise ValueError("transition duration must be between zero and 2000 ms")
        offsets = (
            self.product_offset_x,
            self.product_offset_y,
            self.copy_offset_x,
            self.copy_offset_y,
        )
        if any(not -0.1 <= value <= 0.1 for value in offsets):
            raise ValueError("transition offsets must remain inside the authored motion bounds")


@dataclass(frozen=True, slots=True)
class PresentationTemplate:
    id: str
    role: PresentationRole
    requires_product: bool
    aperture: Aperture
    max_title_chars: int
    max_body_chars: int
    copy_layout: CopyLayout
    transition: AuthoredTransition
    palette: PaletteTokenRoles

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("template id must not be empty")
        if self.max_title_chars <= 0 or self.max_body_chars <= 0:
            raise ValueError("template character limits must be positive")
        if self.transition.name not in _ALLOWED_TRANSITIONS:
            raise ValueError(f"unsupported transition: {self.transition.name}")
        if any(token not in _ALLOWED_PALETTE_TOKENS for token in _palette_values(self.palette)):
            raise ValueError("template palette contains an unsupported token")


@dataclass(frozen=True, slots=True)
class PresentationPack:
    id: str
    render_recipe_version: Literal["presentation-story-render-v1"]
    aspect_width: int
    aspect_height: int
    templates: tuple[PresentationTemplate, ...]


@dataclass(frozen=True, slots=True)
class PresentationScheduleEntry:
    template_id: str
    role: PresentationRole
    requires_product: bool
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


_AUTHORED_SCHEDULE: Final = (
    PresentationScheduleEntry("hook-question@1", "intro", False, 0, 3_000),
    PresentationScheduleEntry("brand-reveal@1", "intro", False, 3_000, 5_000),
    PresentationScheduleEntry("product-split@1", "product", True, 5_000, 15_000),
    PresentationScheduleEntry("guided-workflow@1", "product", True, 15_000, 25_000),
    PresentationScheduleEntry("template-populate@1", "product", True, 25_000, 35_000),
    PresentationScheduleEntry("review-gate@1", "product", True, 35_000, 45_000),
    PresentationScheduleEntry(
        "constraints-three-up@1", "product", True, 45_000, 55_000
    ),
    PresentationScheduleEntry("product-split@1", "product", True, 55_000, 65_000),
    PresentationScheduleEntry("guided-workflow@1", "product", True, 65_000, 75_000),
    PresentationScheduleEntry("template-populate@1", "product", True, 75_000, 85_000),
    PresentationScheduleEntry("review-gate@1", "product", True, 85_000, 95_000),
    PresentationScheduleEntry(
        "constraints-three-up@1", "product", True, 95_000, 105_000
    ),
    PresentationScheduleEntry("product-split@1", "product", True, 105_000, 115_000),
    PresentationScheduleEntry("brand-outro@1", "outro", False, 115_000, 120_000),
)


_DARK_PALETTE: Final = PaletteTokenRoles(
    canvas="canvas.pine",
    ink="ink.light",
    surface="surface.ivory",
    accent="accent.mint",
    outline="outline.mint",
)
_LIGHT_PALETTE: Final = PaletteTokenRoles(
    canvas="canvas.mint",
    ink="ink.dark",
    surface="surface.ivory",
    accent="accent.coral",
    outline="outline.dark",
)

_PRESENTATION_PACK: Final = PresentationPack(
    id=PRESENTATION_PACK_ID,
    render_recipe_version=PRESENTATION_RENDER_RECIPE_VERSION,
    aspect_width=16,
    aspect_height=9,
    templates=(
        PresentationTemplate(
            id="hook-question@1",
            role="intro",
            requires_product=False,
            aperture=Aperture(x=0.05, y=0.08, w=0.90, h=0.84),
            max_title_chars=72,
            max_body_chars=120,
            copy_layout=CopyLayout(0.50, 0.50, 0, 0, "center"),
            transition=AuthoredTransition(
                "stagger-tags", 450, copy_offset_y=0.035
            ),
            palette=_DARK_PALETTE,
        ),
        PresentationTemplate(
            id="brand-reveal@1",
            role="intro",
            requires_product=False,
            aperture=Aperture(x=0.05, y=0.08, w=0.90, h=0.84),
            max_title_chars=48,
            max_body_chars=96,
            copy_layout=CopyLayout(0.50, 0.50, 0, 0, "center"),
            transition=AuthoredTransition("palette-cut", 0),
            palette=_LIGHT_PALETTE,
        ),
        PresentationTemplate(
            id="product-split@1",
            role="product",
            requires_product=True,
            aperture=Aperture(x=0.42, y=0.11, w=0.53, h=0.70),
            max_title_chars=64,
            max_body_chars=180,
            copy_layout=CopyLayout(0.05, 0.16, 0.28, 0.24, "left"),
            transition=AuthoredTransition(
                "split-reveal",
                450,
                product_offset_x=0.018,
                copy_offset_x=-0.012,
            ),
            palette=_DARK_PALETTE,
        ),
        PresentationTemplate(
            id="guided-workflow@1",
            role="product",
            requires_product=True,
            aperture=Aperture(x=0.40, y=0.11, w=0.55, h=0.70),
            max_title_chars=56,
            max_body_chars=220,
            copy_layout=CopyLayout(0.05, 0.16, 0.28, 0.26, "left"),
            transition=AuthoredTransition(
                "prompt-sequence",
                450,
                product_offset_y=0.024,
                copy_offset_y=-0.018,
            ),
            palette=_DARK_PALETTE,
        ),
        PresentationTemplate(
            id="template-populate@1",
            role="product",
            requires_product=True,
            aperture=Aperture(x=0.05, y=0.25, w=0.90, h=0.56),
            max_title_chars=72,
            max_body_chars=220,
            copy_layout=CopyLayout(0.05, 0.10, 0.74, 0.15, "left"),
            transition=AuthoredTransition(
                "focus-reveal", 450, product_offset_y=-0.018
            ),
            palette=_DARK_PALETTE,
        ),
        PresentationTemplate(
            id="review-gate@1",
            role="product",
            requires_product=True,
            aperture=Aperture(x=0.35, y=0.11, w=0.60, h=0.67),
            max_title_chars=56,
            max_body_chars=240,
            copy_layout=CopyLayout(0.05, 0.16, 0.25, 0.24, "left"),
            transition=AuthoredTransition(
                "review-reveal", 450, product_offset_x=-0.018
            ),
            palette=_DARK_PALETTE,
        ),
        PresentationTemplate(
            id="constraints-three-up@1",
            role="product",
            requires_product=True,
            aperture=Aperture(x=0.05, y=0.13, w=0.90, h=0.68),
            max_title_chars=52,
            max_body_chars=180,
            copy_layout=CopyLayout(0.05, 0.82, 0.72, 0.13, "left"),
            transition=AuthoredTransition(
                "stagger-cards", 450, copy_offset_y=0.025
            ),
            palette=_DARK_PALETTE,
        ),
        PresentationTemplate(
            id="brand-outro@1",
            role="outro",
            requires_product=False,
            aperture=Aperture(x=0.05, y=0.08, w=0.90, h=0.84),
            max_title_chars=48,
            max_body_chars=120,
            copy_layout=CopyLayout(0.50, 0.50, 0, 0, "center"),
            transition=AuthoredTransition("brand-hold", 0),
            palette=_LIGHT_PALETTE,
        ),
    ),
)


def _validate_no_runtime_fields(value: object) -> None:
    if not is_dataclass(value) or isinstance(value, type):
        return
    for field in fields(value):
        name_parts = frozenset(field.name.lower().split("_"))
        if name_parts & _FORBIDDEN_RUNTIME_FIELD_PARTS:
            raise ValueError(f"runtime field is forbidden in presentation registry: {field.name}")
        child = getattr(value, field.name)
        if is_dataclass(child):
            _validate_no_runtime_fields(child)
        elif isinstance(child, tuple):
            for item in child:
                _validate_no_runtime_fields(item)


def _validate_pack(pack: PresentationPack) -> None:
    if pack.id != PRESENTATION_PACK_ID:
        raise ValueError(f"unsupported presentation pack id: {pack.id}")
    if pack.render_recipe_version != PRESENTATION_RENDER_RECIPE_VERSION:
        raise ValueError("presentation pack render recipe version is unsupported")
    if (pack.aspect_width, pack.aspect_height) != (16, 9):
        raise ValueError("presentation pack aspect ratio must be 16:9")
    template_ids = tuple(template.id for template in pack.templates)
    if template_ids != PRESENTATION_TEMPLATE_IDS:
        raise ValueError("presentation templates must use the authored ids and order")
    if len(set(template_ids)) != len(template_ids):
        raise ValueError("presentation template ids must be unique")

    for index, template in enumerate(pack.templates):
        if index < 2:
            if template.role != "intro" or template.requires_product:
                raise ValueError("intro templates must be the only non-product opening templates")
            if template.copy_layout.alignment != "center":
                raise ValueError("intro templates must use centered copy")
        elif index == len(pack.templates) - 1:
            if template.role != "outro" or template.requires_product:
                raise ValueError("the outro template must not require product footage")
            if template.copy_layout.alignment != "center":
                raise ValueError("the outro template must use centered copy")
        elif template.role != "product" or not template.requires_product:
            raise ValueError("every middle template must require product footage")
        elif template.copy_layout.alignment != "left":
            raise ValueError("product templates must use left-aligned copy")

        aperture = template.aperture
        aperture_values = (aperture.x, aperture.y, aperture.w, aperture.h)
        if any(not 0 <= value <= 1 for value in aperture_values):
            raise ValueError(f"template aperture is not normalized: {template.id}")
        if aperture.w <= 0 or aperture.h <= 0:
            raise ValueError(f"template aperture has no area: {template.id}")
        if aperture.x + aperture.w > 1 or aperture.y + aperture.h > 1:
            raise ValueError(f"template aperture is out of bounds: {template.id}")
        if template.max_title_chars <= 0 or template.max_body_chars <= 0:
            raise ValueError(f"template character limits must be positive: {template.id}")
        if template.transition.name not in _ALLOWED_TRANSITIONS:
            raise ValueError(f"unsupported transition: {template.transition.name}")
        if any(
            token not in _ALLOWED_PALETTE_TOKENS
            for token in _palette_values(template.palette)
        ):
            raise ValueError(f"unsupported palette token in template: {template.id}")

    _validate_no_runtime_fields(pack)


_validate_pack(_PRESENTATION_PACK)
_PRESENTATION_PACKS: Final[Mapping[str, PresentationPack]] = MappingProxyType(
    {PRESENTATION_PACK_ID: _PRESENTATION_PACK}
)


def resolve_presentation_pack(pack_id: str) -> PresentationPack:
    """Resolve the one production-owned presentation pack by its exact versioned id."""

    try:
        pack = _PRESENTATION_PACKS[pack_id]
    except KeyError as exc:
        raise ValueError(f"unknown presentation pack id: {pack_id}") from exc
    _validate_pack(pack)
    return pack


def resolve_palette_color(token: PaletteToken) -> str:
    """Resolve a trusted palette token used by an authored template."""

    try:
        return _PALETTE_HEX[token]
    except KeyError as exc:
        raise ValueError(f"unknown presentation palette token: {token}") from exc


def build_presentation_schedule(duration_ms: int) -> tuple[PresentationScheduleEntry, ...]:
    """Return the pre-authored deterministic 120-second presentation schedule."""

    if type(duration_ms) is not int or duration_ms != PRESENTATION_DURATION_MS:
        raise ValueError(
            f"presentation duration must be exactly {PRESENTATION_DURATION_MS} ms"
        )

    pack = resolve_presentation_pack(PRESENTATION_PACK_ID)
    result = tuple(entry for entry in _AUTHORED_SCHEDULE)
    _validate_schedule(result, pack)
    return result


def _validate_schedule(
    schedule: tuple[PresentationScheduleEntry, ...],
    pack: PresentationPack,
) -> None:
    if not schedule or schedule[0].start_ms != 0:
        raise ValueError("presentation schedule must start at zero")
    if schedule[-1].end_ms != PRESENTATION_DURATION_MS:
        raise ValueError("presentation schedule must cover the full duration")
    if any(entry.start_ms >= entry.end_ms for entry in schedule):
        raise ValueError("presentation schedule entries must have positive duration")
    if any(
        left.end_ms != right.start_ms
        for left, right in zip(schedule, schedule[1:], strict=False)
    ):
        raise ValueError("presentation schedule must be contiguous")
    if schedule[1].end_ms != INTRO_END_MS:
        raise ValueError("authored intro must cover exactly the first five seconds")
    if schedule[-1].start_ms != OUTRO_START_MS:
        raise ValueError("authored outro must cover exactly the last five seconds")

    product_templates = pack.templates[2:-1]
    middle = schedule[2:-1]
    expected_ids = tuple(
        product_templates[index % len(product_templates)].id for index in range(len(middle))
    )
    if tuple(entry.template_id for entry in middle) != expected_ids:
        raise ValueError("middle templates must follow the fixed authored cycle")
    if any(not entry.requires_product or entry.role != "product" for entry in middle):
        raise ValueError("every middle schedule entry must require product footage")
