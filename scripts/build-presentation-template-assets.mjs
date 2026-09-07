import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";

import sharp from "sharp";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const requestedTheme = (process.argv.find((value) => value.startsWith("--theme=")) ?? "--theme=default").slice("--theme=".length);
const THEMES = {
  default: {
    directory: "presentation-story-v2", packId: "presentation-story@2", displayName: "Editorial product story", status: "authored_not_wired",
    colors: { hook: "#0D4334", field: "#234D44", fieldRaised: "#2C5B50", mint: "#9DE8D2", mintSoft: "#DDF7EF", surface: "#9DE8D2", ivory: "#F3EDE1", ink: "#0A211C", inkSoft: "#173D34", coral: "#FF796C", line: "#73BDAA", white: "#FFFFFF" },
  },
  google: {
    directory: "presentation-story-google-v1", packId: "presentation-story-google@1", displayName: "Multicolor product story", status: "pre_generated_theme",
    colors: { hook: "#1A73E8", field: "#202124", fieldRaised: "#303134", mint: "#FF6666", mintSoft: "#FCE8E6", surface: "#FCE8E6", ivory: "#F8F9FA", ink: "#202124", inkSoft: "#3C4043", coral: "#FF6666", line: "#34A853", white: "#FFFFFF" },
  },
};
const THEME = THEMES[requestedTheme];
if (!THEME) throw new Error(`Unknown template theme: ${requestedTheme}`);
const PACK_DIR = path.join(
  ROOT,
  "services",
  "worker",
  "src",
  "demodirector_worker",
  "templates",
  THEME.directory,
);
const FONT_SOURCE = path.join(
  ROOT,
  "node_modules",
  "@fontsource-variable",
  "inter",
  "files",
  "inter-latin-wght-normal.woff2",
);
const FONT_LICENSE_SOURCE = path.join(
  ROOT,
  "node_modules",
  "@fontsource-variable",
  "inter",
  "LICENSE",
);

const CANVAS = { width: 2560, height: 1440 };
const PREVIEW = { width: 1280, height: 720 };
const COLORS = THEME.colors;

const FONT_TOKENS = {
  display_xl: { size: 132, line_height: 138, weight: 500, tracking: -4 },
  display_l: { size: 88, line_height: 96, weight: 500, tracking: -3 },
  heading: { size: 56, line_height: 64, weight: 600, tracking: -1.5 },
  title: { size: 40, line_height: 48, weight: 600, tracking: -0.5 },
  body: { size: 30, line_height: 42, weight: 400, tracking: 0 },
  label: { size: 22, line_height: 28, weight: 600, tracking: 4.4 },
  activity_badge: { size: 22, line_height: 30, weight: 500, tracking: 1.6 },
  activity_status: { size: 22, line_height: 30, weight: 400, tracking: 2 },
  activity_detail: { size: 34, line_height: 44, weight: 400, tracking: 0 },
  activity_heading: { size: 24, line_height: 34, weight: 400, tracking: 3.5 },
  caption: { size: 44, line_height: 54, weight: 500, tracking: -0.5 },
};

const TRANSITIONS = {
  hard_cut: {
    kind: "cut",
    duration_ms: 0,
  },
  matched_slide: {
    kind: "translate_fade",
    duration_ms: 480,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
    offset_px: [36, 0],
  },
  field_slide: {
    kind: "translate_fade",
    duration_ms: 420,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
    offset_px: [0, 28],
  },
  aperture_expand: {
    kind: "scale_fade",
    duration_ms: 560,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
    origin: "center",
    start_scale: 0.96,
  },
  focus_rise: {
    kind: "translate_fade",
    duration_ms: 520,
    easing: "cubic-bezier(0.16, 1, 0.3, 1)",
    offset_px: [0, 32],
  },
  card_stagger: {
    kind: "staggered_translate_fade",
    duration_ms: 520,
    item_stagger_ms: 160,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
    offset_px: [0, 26],
  },
  soft_crossfade: {
    kind: "crossfade",
    duration_ms: 500,
    easing: "cubic-bezier(0.4, 0, 0.2, 1)",
  },
};

function slot(id, x, y, width, height, fontToken, maxCharacters, maxLines, align = "left") {
  return {
    id,
    kind: id === "caption" ? "caption" : "text",
    rect: { x, y, width, height },
    font_token: fontToken,
    align,
    max_characters: maxCharacters,
    max_lines: maxLines,
  };
}

const TEMPLATES = [
  {
    id: "hook-question@2",
    slug: "01-hook-question",
    name: "Question orbit",
    role: "intro",
    motion: "field_slide",
    layout: "hook",
    copy: [
      slot("chapter", 128, 104, 650, 42, "label", 36, 1),
      slot("counter", 2180, 104, 252, 42, "label", 12, 1, "right"),
      slot("headline", 154, 314, 1720, 390, "display_xl", 56, 3),
      slot("support", 158, 774, 1080, 100, "body", 110, 2),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["THE PRODUCT STORY"],
      counter: ["01 / 09"],
      headline: ["What if every", "product could tell", "its own story?"],
      support: ["A clear demo begins with the product—not a blank slide."],
      caption: ["Start with the product moment that matters."],
    },
  },
  {
    id: "brand-promise@2",
    slug: "02-brand-promise",
    name: "Product in action",
    role: "product",
    motion: "matched_slide",
    layout: "promise",
    aperture: { x: 128, y: 424, width: 2304, height: 816, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 104, 650, 42, "label", 36, 1),
      slot("counter", 2180, 104, 252, 42, "label", 12, 1, "right"),
      slot("brand", 128, 208, 2304, 106, "display_l", 32, 1),
      slot("headline", 128, 326, 2304, 72, "heading", 90, 1),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["THE PRODUCT IN ACTION"],
      counter: ["02 / 09"],
      brand: ["DemoDirector"],
      headline: ["See the real workflow before we break it down."],
      caption: ["Follow the cursor through a real product interaction."],
    },
  },
  {
    id: "context-split@2",
    slug: "03-context-split",
    name: "Product hero split",
    role: "product",
    motion: "matched_slide",
    layout: "context",
    aperture: { x: 1000, y: 218, width: 1432, height: 1022, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 104, 650, 42, "label", 36, 1),
      slot("counter", 2180, 104, 252, 42, "label", 12, 1, "right"),
      slot("eyebrow", 190, 314, 650, 40, "label", 34, 1),
      slot("headline", 188, 402, 680, 270, "display_l", 54, 3),
      slot("body", 192, 730, 620, 190, "body", 170, 4),
      slot("callout", 192, 1030, 620, 70, "title", 42, 1),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["THE PRODUCT, IMMEDIATELY"],
      counter: ["03 / 09"],
      eyebrow: ["LIVE PRODUCT"],
      headline: ["Show the", "real workflow", "from frame one."],
      body: [
        "The story stays grounded in visible",
        "product behavior while the narrative",
        "gives every action context.",
      ],
      callout: ["No staged mockups"],
      caption: ["The product remains the hero of every chapter."],
    },
  },
  {
    id: "workflow-rail@2",
    slug: "04-workflow-rail",
    name: "Workflow trace split",
    role: "product",
    motion: "field_slide",
    layout: "workflow",
    aperture: { x: 930, y: 218, width: 1502, height: 1022, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 104, 650, 42, "label", 36, 1),
      slot("counter", 2180, 104, 252, 42, "label", 12, 1, "right"),
      slot("eyebrow", 186, 274, 570, 42, "label", 34, 1),
      slot("headline", 184, 354, 600, 184, "heading", 58, 3),
      slot("request", 212, 628, 552, 100, "body", 90, 2),
      slot("step_two", 212, 812, 552, 100, "body", 90, 2),
      slot("step_three", 212, 996, 552, 100, "body", 90, 2),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["GUIDED WORKFLOW"],
      counter: ["04 / 09"],
      eyebrow: ["ONE REQUEST"],
      headline: ["Turn intent into", "a visible plan."],
      request: ["Open the section you want to explore."],
      step_two: ["Inspect the details in context."],
      step_three: ["Return to the overview."],
      caption: ["Every step stays traceable from request to result."],
    },
  },
  {
    id: "prompt-over-product@2",
    slug: "05-prompt-over-product",
    name: "Prompt over product",
    role: "product",
    motion: "aperture_expand",
    layout: "prompt",
    aperture: { x: 128, y: 424, width: 2304, height: 816, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 86, 650, 42, "label", 36, 1),
      slot("counter", 2180, 86, 252, 42, "label", 12, 1, "right"),
      slot("prompt", 220, 232, 1840, 100, "heading", 120, 2),
      slot("status", 2070, 248, 258, 54, "label", 18, 1, "center"),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["FROM BRIEF TO BEHAVIOR"],
      counter: ["05 / 09"],
      prompt: ["Reveal the signal, then click the next action."],
      status: ["CAPTURING"],
      caption: ["A clear prompt becomes a clear product moment."],
    },
  },
  {
    id: "focus-detail@2",
    slug: "06-focus-detail",
    name: "Product activity",
    role: "product",
    motion: "focus_rise",
    layout: "focus",
    aperture: { x: 128, y: 218, width: 1400, height: 1022, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 86, 650, 42, "label", 36, 1),
      slot("counter", 2180, 86, 252, 42, "label", 12, 1, "right"),
      slot("activity_heading", 1608, 236, 824, 42, "activity_heading", 32, 1),
      ...[1, 2, 3, 4].flatMap((i) => [
        slot(`activity_${i}_label`, 1640, 350 + (i - 1) * 216, 290, 36, "activity_badge", 18, 1),
        slot(`activity_${i}_status`, 2160, 350 + (i - 1) * 216, 236, 36, "activity_status", 12, 1, "right"),
        slot(`activity_${i}_detail`, 1640, 404 + (i - 1) * 216, 752, 88, "activity_detail", 64, 2),
      ]),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["PRODUCT WALKTHROUGH"],
      counter: ["06 / 09"],
      activity_heading: ["PRODUCT ACTIVITY"],
      ...Object.fromEntries([1, 2, 3, 4].flatMap((i) => [
        [`activity_${i}_label`, [`FEATURE ${i}`]],
        [`activity_${i}_status`, ["OBSERVED"]],
        [`activity_${i}_detail`, ["Evidence-grounded product action"]],
      ])),
      caption: ["Follow the product workflow in context."],
    },
  },
  {
    id: "human-review@2",
    slug: "07-human-review",
    name: "Workflow highlights",
    role: "product",
    motion: "field_slide",
    layout: "review",
    aperture: { x: 876, y: 218, width: 1556, height: 1022, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 104, 650, 42, "label", 36, 1),
      slot("counter", 2180, 104, 252, 42, "label", 12, 1, "right"),
      slot("eyebrow", 186, 276, 570, 42, "label", 34, 1),
      slot("headline", 184, 354, 596, 190, "heading", 62, 3),
      slot("bullet_one", 226, 600, 530, 80, "body", 64, 2),
      slot("bullet_two", 226, 710, 530, 80, "body", 64, 2),
      slot("bullet_three", 226, 820, 530, 80, "body", 64, 2),
      slot("body", 188, 946, 560, 130, "body", 140, 3),
      slot("callout", 188, 1082, 560, 64, "title", 44, 1),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["WORKFLOW HIGHLIGHTS"],
      counter: ["07 / 09"],
      eyebrow: ["IN THIS WALKTHROUGH"],
      headline: ["Three steps.", "One clear result."],
      bullet_one: ["Open the search field."],
      bullet_two: ["Enter the topic."],
      bullet_three: ["Explore the result."],
      body: [
        "Important changes wait for a clear",
        "review before the story moves",
        "forward.",
      ],
      callout: ["Prepared—not published"],
      caption: ["The final decision always remains visible and human."],
    },
  },
  {
    id: "trust-cards@2",
    slug: "08-trust-cards",
    name: "Unobstructed product walkthrough",
    role: "product",
    motion: "card_stagger",
    layout: "trust",
    aperture: { x: 128, y: 190, width: 2304, height: 1050, corner_radius: 20 },
    copy: [
      slot("chapter", 128, 86, 650, 42, "label", 36, 1),
      slot("counter", 2180, 86, 252, 42, "label", 12, 1, "right"),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["TRUST, BUILT INTO THE STORY"],
      counter: ["08 / 09"],
      card_one: ["Grounded", "in real evidence"],
      card_two: ["Directed by", "typed decisions"],
      card_three: ["Safe, visible", "execution"],
      caption: ["Every contribution is clear, bounded, and inspectable."],
    },
  },
  {
    id: "brand-outro@2",
    slug: "09-brand-outro",
    name: "Brand bookend",
    role: "outro",
    motion: "soft_crossfade",
    layout: "outro",
    copy: [
      slot("chapter", 128, 104, 650, 42, "label", 36, 1),
      slot("counter", 2180, 104, 252, 42, "label", 12, 1, "right"),
      slot("brand", 542, 388, 1476, 150, "display_l", 32, 1, "center"),
      slot("headline", 420, 590, 1720, 150, "heading", 92, 2, "center"),
      slot("pillar_one", 230, 1016, 620, 94, "title", 42, 2, "center"),
      slot("pillar_two", 970, 1016, 620, 94, "title", 42, 2, "center"),
      slot("pillar_three", 1710, 1016, 620, 94, "title", 42, 2, "center"),
      slot("caption", 520, 1260, 1520, 92, "caption", 92, 2, "center"),
    ],
    preview: {
      chapter: ["MAKE THE PRODUCT MEMORABLE"],
      counter: ["09 / 09"],
      brand: ["DemoDirector"],
      headline: ["Your product. Clearly directed."],
      pillar_one: ["REAL PRODUCT"],
      pillar_two: ["CLEAR STORY"],
      pillar_three: ["VISIBLE CONTROL"],
      caption: ["Turn the next product story into a demo worth watching."],
    },
  },
];

const SCHEDULE = [
  [0, 3000, "hook-question@2", "hard_cut"],
  [3000, 13000, "brand-promise@2", "matched_slide"],
  [13000, 28000, "context-split@2", "matched_slide"],
  [28000, 45000, "workflow-rail@2", "field_slide"],
  [45000, 61000, "prompt-over-product@2", "aperture_expand"],
  [61000, 78000, "focus-detail@2", "focus_rise"],
  [78000, 98000, "human-review@2", "field_slide"],
  [98000, 115000, "trust-cards@2", "card_stagger"],
  [115000, 120000, "brand-outro@2", "soft_crossfade"],
];

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function svgShell(content, fontData = null) {
  const fontFace = fontData
    ? `@font-face{font-family:'Inter';font-style:normal;font-weight:100 900;src:url(data:font/woff2;base64,${fontData}) format('woff2');}`
    : "";
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${CANVAS.width}" height="${CANVAS.height}" viewBox="0 0 ${CANVAS.width} ${CANVAS.height}">
  <style>${fontFace}text{font-family:'Inter','Arial',sans-serif;font-variant-ligatures:none}</style>
  ${content}
</svg>`;
}

function metadataRail() {
  return `
    <path d="M128 176H2432" stroke="${COLORS.line}" stroke-width="2" opacity="0.7"/>
    <circle cx="128" cy="176" r="6" fill="${COLORS.mint}"/>
    <circle cx="2432" cy="176" r="6" fill="${COLORS.mint}"/>
  `;
}

function captionFrame() {
  return `
    <rect x="500" y="1252" width="1560" height="104" rx="8" fill="${COLORS.ink}" fill-opacity="0.94" stroke="${COLORS.mint}" stroke-opacity="0.72" stroke-width="2"/>
  `;
}

function backgroundMarkup(template) {
  const base = template.layout === "promise" || template.layout === "outro" ? COLORS.surface : template.layout === "hook" ? COLORS.hook : COLORS.field;
  const grain = `<pattern id="grain-${template.slug}" width="48" height="48" patternUnits="userSpaceOnUse"><circle cx="3" cy="3" r="1" fill="${template.layout === "promise" || template.layout === "outro" ? COLORS.ink : COLORS.mint}" opacity="0.07"/></pattern>`;
  let decoration = "";
  if (template.layout === "hook") {
    decoration = `
      <circle cx="2100" cy="720" r="386" fill="none" stroke="${COLORS.mint}" stroke-width="2" opacity="0.38"/>
      <circle cx="2100" cy="720" r="258" fill="none" stroke="${COLORS.mint}" stroke-width="2" opacity="0.22"/>
      <path d="M1832 438L2248 1012M1778 878L2356 584" stroke="${COLORS.mint}" stroke-width="2" opacity="0.18"/>
      <circle cx="2362" cy="506" r="17" fill="${COLORS.coral}"/>
      <circle cx="1798" cy="914" r="12" fill="${COLORS.mint}"/>
    `;
  } else if (template.layout === "promise") {
    decoration = `
      <path d="M128 176H2432" stroke="${COLORS.ink}" stroke-width="2" opacity="0.72"/>
    `;
  } else if (template.layout === "context") {
    decoration = `
      <rect x="128" y="218" width="782" height="1022" rx="20" fill="${COLORS.ivory}"/>
      <rect x="160" y="252" width="718" height="72" rx="8" fill="${COLORS.mintSoft}"/>
      <path d="M160 970H878" stroke="${COLORS.ink}" stroke-width="2" opacity="0.18"/>
      <rect x="160" y="1002" width="718" height="150" rx="10" fill="${COLORS.mint}"/>
    `;
  } else if (template.layout === "workflow") {
    decoration = `
      <rect x="128" y="218" width="730" height="1022" rx="20" fill="${COLORS.ink}" fill-opacity="0.9" stroke="${COLORS.line}" stroke-width="2"/>
      ${[0, 1, 2].map((index) => `<rect x="184" y="${600 + index * 184}" width="618" height="148" rx="12" fill="${COLORS.fieldRaised}"/>`).join("")}
    `;
  } else if (template.layout === "prompt") {
    decoration = `
      <rect x="128" y="190" width="2304" height="190" rx="18" fill="${COLORS.mint}"/>
      <rect x="2030" y="236" width="334" height="98" rx="10" fill="${COLORS.ink}"/>
      <circle cx="2084" cy="285" r="10" fill="${COLORS.coral}"/>
    `;
  } else if (template.layout === "focus") {
    decoration = `
      <path d="M1608 290H2432" stroke="${COLORS.mint}" stroke-width="2" opacity="0.8"/>
      ${[0, 1, 2, 3].map((i) => `
        <rect x="1608" y="${320 + i * 216}" width="824" height="200" rx="10" fill="#104638" stroke="${COLORS.mint}" stroke-width="3"/>
        <rect x="1638" y="${346 + i * 216}" width="308" height="44" rx="6" fill="${COLORS.mint}"/>
      `).join("")}
    `;
  } else if (template.layout === "review") {
    decoration = `
      <rect x="128" y="218" width="676" height="1022" rx="20" fill="${COLORS.mint}"/>
      ${[0, 1, 2].map((index) => `<circle cx="198" cy="${621 + index * 110}" r="6" fill="${COLORS.ink}"/>`).join("")}
    `;
  } else if (template.layout === "outro") {
    decoration = `
      <rect x="128" y="218" width="2304" height="620" rx="24" fill="${COLORS.white}"/>
      <rect x="128" y="218" width="18" height="620" rx="9" fill="${COLORS.mint}"/>
      <path d="M128 176H2432M128 940H2432M128 1174H2432" stroke="${COLORS.ink}" stroke-width="2" opacity="0.72"/>
      <path d="M920 940V1174M1640 940V1174" stroke="${COLORS.ink}" stroke-width="2" opacity="0.3"/>
      <rect x="1178" y="286" width="204" height="76" rx="8" fill="${COLORS.ink}"/>
      <path d="M1230 324H1330M1280 300V348" stroke="${COLORS.mint}" stroke-width="8" stroke-linecap="round"/>
    `;
  }
  return `
    <defs>${grain}</defs>
    <rect width="2560" height="1440" fill="${base}"/>
    <rect width="2560" height="1440" fill="url(#grain-${template.slug})"/>
    ${decoration}
  `;
}

function productMockMarkup(template) {
  if (!template.aperture) return "";
  const { x, y, width, height, corner_radius: radius } = template.aperture;
  const dashboard = `
    <svg x="${x}" y="${y}" width="${width}" height="${height}" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
      <rect width="1600" height="900" fill="#0D1214"/>
      <rect width="1600" height="76" fill="#141C1F"/>
      <circle cx="34" cy="38" r="8" fill="#FF796C"/><circle cx="60" cy="38" r="8" fill="#F0C65A"/><circle cx="86" cy="38" r="8" fill="#5FD58A"/>
      <rect x="122" y="22" width="880" height="34" rx="8" fill="#222C30"/>
      <rect x="0" y="76" width="228" height="824" fill="#101719"/>
      <rect x="26" y="108" width="176" height="46" rx="8" fill="#243238"/>
      ${[0, 1, 2, 3, 4, 5].map((index) => `<rect x="34" y="${190 + index * 70}" width="${110 + (index % 3) * 24}" height="18" rx="5" fill="#78949B" opacity="${index === 1 ? 0.9 : 0.48}"/>`).join("")}
      <rect x="264" y="112" width="340" height="36" rx="8" fill="#F1F5F4" opacity="0.94"/>
      <rect x="264" y="166" width="540" height="20" rx="5" fill="#7B8B8F" opacity="0.5"/>
      ${[0, 1, 2].map((index) => `<rect x="${264 + index * 420}" y="236" width="382" height="172" rx="14" fill="#182226" stroke="#334348" stroke-width="2"/><rect x="${292 + index * 420}" y="270" width="170" height="18" rx="5" fill="#90A5AA" opacity="0.72"/><rect x="${292 + index * 420}" y="318" width="140" height="52" rx="7" fill="${index === 1 ? COLORS.mint : "#F1F5F4"}" opacity="0.94"/>`).join("")}
      <rect x="264" y="446" width="758" height="350" rx="14" fill="#182226" stroke="#334348" stroke-width="2"/>
      <path d="M310 724C394 662 440 700 522 620S670 604 738 530S866 586 962 494" fill="none" stroke="${COLORS.mint}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M310 742H970M310 680H970M310 618H970M310 556H970M310 494H970" stroke="#29373B" stroke-width="2"/>
      <rect x="1054" y="446" width="486" height="350" rx="14" fill="#182226" stroke="#334348" stroke-width="2"/>
      ${[0, 1, 2, 3].map((index) => `<rect x="1090" y="${494 + index * 62}" width="${380 - index * 32}" height="26" rx="7" fill="${index === 0 ? COLORS.coral : COLORS.mint}" opacity="${0.92 - index * 0.12}"/>`).join("")}
      <rect x="1258" y="110" width="282" height="76" rx="12" fill="${COLORS.mint}"/>
      <circle cx="1368" cy="558" r="24" fill="none" stroke="${COLORS.coral}" stroke-width="9"/>
      <path d="M1368 514L1382 546L1416 556L1384 570L1374 604L1360 572L1326 562L1358 548Z" fill="${COLORS.white}" stroke="${COLORS.ink}" stroke-width="3"/>
    </svg>
  `;
  return `
    <clipPath id="product-clip-${template.slug}"><rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${radius}"/></clipPath>
    <g clip-path="url(#product-clip-${template.slug})">${dashboard}</g>
  `;
}

function foregroundMarkup(template) {
  let layout = "";
  if (template.aperture) {
    const { x, y, width, height, corner_radius: radius } = template.aperture;
    layout += `<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${radius}" fill="none" stroke="${COLORS.mint}" stroke-width="3"/>`;
  }
  if (template.layout === "hook") {
    layout += `
      <rect x="154" y="972" width="266" height="62" rx="31" fill="none" stroke="${COLORS.mint}" stroke-width="2"/>
      <rect x="446" y="1048" width="312" height="62" rx="31" fill="none" stroke="${COLORS.mint}" stroke-width="2"/>
      <rect x="784" y="972" width="252" height="62" rx="31" fill="${COLORS.mint}"/>
    `;
  }
  return `
    ${metadataRail()}
    ${layout}
    ${captionFrame()}
  `;
}

function textAnchor(align) {
  return align === "center" ? "middle" : align === "right" ? "end" : "start";
}

function textX(slotDefinition) {
  if (slotDefinition.align === "center") return slotDefinition.rect.x + slotDefinition.rect.width / 2;
  if (slotDefinition.align === "right") return slotDefinition.rect.x + slotDefinition.rect.width;
  return slotDefinition.rect.x;
}

function slotColor(template, slotDefinition) {
  if (slotDefinition.id === "caption") return COLORS.ivory;
  if (template.layout === "promise" || template.layout === "outro") return COLORS.ink;
  if (template.layout === "context" && !["chapter", "counter", "caption"].includes(slotDefinition.id)) return COLORS.ink;
  if (template.layout === "review" && !["chapter", "counter", "caption"].includes(slotDefinition.id)) return COLORS.ink;
  if (template.layout === "prompt" && ["prompt"].includes(slotDefinition.id)) return COLORS.ink;
  if (template.layout === "focus" && slotDefinition.id.endsWith("_label")) return COLORS.ink;
  if (template.layout === "focus" && (slotDefinition.id.endsWith("_status") || slotDefinition.id === "activity_heading")) return COLORS.mint;
  if (template.layout === "trust" && slotDefinition.id.startsWith("card_")) return COLORS.ink;
  return slotDefinition.font_token === "label" ? COLORS.mint : COLORS.ivory;
}

function textMarkup(template, slotDefinition, lines) {
  const token = FONT_TOKENS[slotDefinition.font_token];
  const x = textX(slotDefinition);
  const anchor = textAnchor(slotDefinition.align);
  const color = slotColor(template, slotDefinition);
  const baseline = slotDefinition.rect.y + token.size;
  const content = lines
    .slice(0, slotDefinition.max_lines)
    .map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : token.line_height}">${escapeXml(line)}</tspan>`)
    .join("");
  return `<text data-slot="${slotDefinition.id}" x="${x}" y="${baseline}" text-anchor="${anchor}" fill="${color}" font-size="${token.size}" font-weight="${token.weight}" letter-spacing="${token.tracking}px">${content}</text>`;
}

function copyMarkup(template) {
  return template.copy
    .map((slotDefinition) => textMarkup(template, slotDefinition, template.preview[slotDefinition.id] ?? []))
    .join("\n");
}

function sourceSvg(template, fontData) {
  return svgShell(`
    <g id="background">${backgroundMarkup(template)}</g>
    <g id="product-slot">${productMockMarkup(template)}</g>
    <g id="foreground">${foregroundMarkup(template)}</g>
    <g id="copy-slots">${copyMarkup(template)}</g>
  `, fontData);
}

function backgroundSvg(template) {
  return svgShell(`<g id="background">${backgroundMarkup(template)}</g>`);
}

function foregroundSvg(template) {
  return svgShell(`<g id="foreground">${foregroundMarkup(template)}</g>`);
}

const CRC_TABLE = Array.from({ length: 256 }, (_, tableIndex) => {
  let value = tableIndex;
  for (let bit = 0; bit < 8; bit += 1) {
    value = (value & 1) === 1 ? 0xEDB88320 ^ (value >>> 1) : value >>> 1;
  }
  return value >>> 0;
});

function crc32(buffer) {
  let value = 0xFFFFFFFF;
  for (const byte of buffer) {
    value = CRC_TABLE[(value ^ byte) & 0xFF] ^ (value >>> 8);
  }
  return (value ^ 0xFFFFFFFF) >>> 0;
}

function pngChunk(type, payload) {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  length.writeUInt32BE(payload.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([typeBuffer, payload])));
  return Buffer.concat([length, typeBuffer, payload, checksum]);
}

function grayscaleMaskPng(template) {
  const { x, y, width, height, corner_radius: radius } = template.aperture;
  const stride = CANVAS.width + 1;
  const pixels = Buffer.alloc(stride * CANVAS.height);
  for (let row = y; row < y + height; row += 1) {
    const localY = row - y + 0.5;
    const cornerDistance = localY < radius
      ? radius - localY
      : localY > height - radius
        ? localY - (height - radius)
        : 0;
    const inset = cornerDistance > 0
      ? Math.max(0, Math.ceil(radius - Math.sqrt(radius * radius - cornerDistance * cornerDistance)))
      : 0;
    const rowStart = row * stride + 1;
    pixels.fill(255, rowStart + x + inset, rowStart + x + width - inset);
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(CANVAS.width, 0);
  ihdr.writeUInt32BE(CANVAS.height, 4);
  ihdr[8] = 8;
  ihdr[9] = 0;
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", ihdr),
    pngChunk("IDAT", deflateSync(pixels, { level: 9 })),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

async function hashFile(filePath) {
  return createHash("sha256").update(await readFile(filePath)).digest("hex");
}

function toPosix(relativePath) {
  return relativePath.split(path.sep).join("/");
}

async function renderTemplate(template, fontData) {
  const folder = path.join(PACK_DIR, "slides", template.slug);
  await mkdir(folder, { recursive: true });

  const sourcePath = path.join(folder, "source.svg");
  const backgroundPath = path.join(folder, "background.png");
  const foregroundPath = path.join(folder, "foreground.png");
  const previewPath = path.join(folder, "preview.png");
  await writeFile(sourcePath, sourceSvg(template, fontData), "utf8");
  await writeFile(backgroundPath, await sharp(Buffer.from(backgroundSvg(template)))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toBuffer());
  await writeFile(foregroundPath, await sharp(Buffer.from(foregroundSvg(template)))
    .ensureAlpha()
    .png({ compressionLevel: 9, adaptiveFiltering: true, colourType: 6 })
    .toBuffer());
  await writeFile(previewPath, await sharp(Buffer.from(sourceSvg(template, fontData)))
    .resize(PREVIEW.width, PREVIEW.height, { fit: "fill" })
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toBuffer());

  const assets = {
    source_svg: toPosix(path.relative(PACK_DIR, sourcePath)),
    background_png: toPosix(path.relative(PACK_DIR, backgroundPath)),
    foreground_png: toPosix(path.relative(PACK_DIR, foregroundPath)),
    preview_png: toPosix(path.relative(PACK_DIR, previewPath)),
  };
  if (template.aperture) {
    const maskPath = path.join(folder, "product-mask.png");
    await writeFile(maskPath, grayscaleMaskPng(template));
    assets.product_mask_png = toPosix(path.relative(PACK_DIR, maskPath));
  }
  return assets;
}

async function buildContactSheet(previews, fontData) {
  const cells = previews.map(({ template, previewPath }, index) => {
    const column = index % 3;
    const row = Math.floor(index / 3);
    const x = 230 + column * 720;
    const y = 118 + row * 430;
    const png = previewPath.toString("base64");
    return `
      <rect x="${x - 10}" y="${y - 10}" width="680" height="391" rx="14" fill="${COLORS.white}" opacity="0.12"/>
      <image href="data:image/png;base64,${png}" x="${x}" y="${y}" width="660" height="371" preserveAspectRatio="none"/>
      <text x="${x}" y="${y + 405}" fill="${COLORS.ivory}" font-size="24" font-weight="600">${String(index + 1).padStart(2, "0")}  ${escapeXml(template.name)}</text>
    `;
  }).join("");
  const sheet = svgShell(`
    <rect width="2560" height="1440" fill="${COLORS.ink}"/>
    <text x="128" y="68" fill="${COLORS.mint}" font-size="28" font-weight="600" letter-spacing="5">${escapeXml(THEME.displayName.toUpperCase())} · 2560 × 1440 MASTERS</text>
    ${cells}
  `, fontData);
  const outputPath = path.join(PACK_DIR, "contact-sheet.png");
  await writeFile(outputPath, await sharp(Buffer.from(sheet))
    .png({ compressionLevel: 9, adaptiveFiltering: true })
    .toBuffer());
  return outputPath;
}

async function main() {
  await mkdir(path.join(PACK_DIR, "shared"), { recursive: true });
  const fontBuffer = await readFile(FONT_SOURCE);
  const fontData = fontBuffer.toString("base64");
  await copyFile(FONT_SOURCE, path.join(PACK_DIR, "shared", "inter-latin-variable.woff2"));
  await copyFile(FONT_LICENSE_SOURCE, path.join(PACK_DIR, "shared", "INTER-LICENSE.txt"));

  const tokens = {
    schema_version: 1,
    canvas: CANVAS,
    preview_canvas: PREVIEW,
    safe_area: { x: 128, y: 86, width: 2304, height: 1270 },
    typography: {
      family: "Inter",
      source: "shared/inter-latin-variable.woff2",
      tokens: FONT_TOKENS,
    },
    palette: COLORS,
    geometry: {
      corner_radius_px: 20,
      rule_width_px: 2,
      caption_safe_height_px: 120,
    },
  };
  const motion = {
    schema_version: 1,
    pack_id: THEME.packId,
    policy: {
      allow_only_listed_presets: true,
      arbitrary_expressions: false,
      arbitrary_javascript: false,
      model_generated_geometry: false,
      model_generated_timing: false,
    },
    presets: TRANSITIONS,
  };
  await writeFile(path.join(PACK_DIR, "tokens.json"), `${JSON.stringify(tokens, null, 2)}\n`, "utf8");
  await writeFile(path.join(PACK_DIR, "motion.json"), `${JSON.stringify(motion, null, 2)}\n`, "utf8");

  const assetsByTemplate = new Map();
  const previews = [];
  for (const template of TEMPLATES) {
    const assets = await renderTemplate(template, fontData);
    assetsByTemplate.set(template.id, assets);
    previews.push({
      template,
      previewPath: await readFile(path.join(PACK_DIR, assets.preview_png)),
    });
  }
  await buildContactSheet(previews, fontData);

  const manifestTemplates = TEMPLATES.map((template) => {
    const entry = {
      id: template.id,
      name: template.name,
      folder: `slides/${template.slug}`,
      role: template.role,
      requires_product: template.role === "product",
      assets: assetsByTemplate.get(template.id),
      copy_slots: template.copy,
      motion_preset: template.motion,
      ...(["workflow", "focus", "review", "trust"].includes(template.layout)
        ? { visual_revision: template.layout === "focus" ? "product-activity-v2" : "clear-product-2026-09-05" } : {}),
      ...(template.layout === "focus" ? { activity_panel: true } : {}),
    };
    if (template.aperture) {
      entry.product_aperture = {
        ...template.aperture,
        fit: "contain_over_blur",
      };
    }
    return entry;
  });
  const manifest = {
    schema_version: 1,
    pack_id: THEME.packId,
    display_name: THEME.displayName,
    status: THEME.status,
    theme: requestedTheme,
    canvas: {
      ...CANVAS,
      color_space: "sRGB",
      safe_area: { x: 128, y: 86, width: 2304, height: 1270 },
    },
    preview_canvas: PREVIEW,
    contact_sheet_png: "contact-sheet.png",
    tokens: "tokens.json",
    motion: "motion.json",
    typography: tokens.typography,
    palette: COLORS,
    transition_presets: TRANSITIONS,
    schedule: SCHEDULE.map(([startMs, endMs, templateId, transitionPreset]) => ({
      start_ms: startMs,
      end_ms: endMs,
      template_id: templateId,
      transition_preset: transitionPreset,
    })),
    templates: manifestTemplates,
    safety: {
      asset_paths_are_pack_relative: true,
      runtime_layers_are_copy_free: true,
      product_fit_is_fixed: "contain_over_blur",
      arbitrary_urls: false,
      arbitrary_expressions: false,
      arbitrary_javascript: false,
      arbitrary_shell_commands: false,
    },
    integrity: { algorithm: "sha256", files: {} },
  };

  const hashTargets = [
    "contact-sheet.png",
    "tokens.json",
    "motion.json",
    "shared/inter-latin-variable.woff2",
    "shared/INTER-LICENSE.txt",
    ...manifestTemplates.flatMap((template) => Object.values(template.assets)),
  ];
  for (const relativePath of [...new Set(hashTargets)].sort()) {
    manifest.integrity.files[relativePath] = await hashFile(path.join(PACK_DIR, relativePath));
  }
  await writeFile(path.join(PACK_DIR, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

await main();
