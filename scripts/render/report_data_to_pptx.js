const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");
let SHAPE = null;

let warnIfSlideHasOverlaps = () => {};
let warnIfSlideElementsOutOfBounds = () => {};
try {
  ({
    warnIfSlideHasOverlaps,
    warnIfSlideElementsOutOfBounds,
  } = require("../../companion-skills/slides/assets/pptxgenjs_helpers/layout"));
} catch (_) {}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--help" || token === "-h") {
      args.help = true;
      continue;
    }
    if (!token.startsWith("--")) continue;
    const key = token.slice(2);
    const value = argv[i + 1];
    args[key] = value;
    i += 1;
  }
  return args;
}

function printHelp() {
  process.stdout.write(
    [
      "Usage: node report_data_to_pptx.js --data <report-data.json> [--pptx <output.pptx>]",
      "",
      "Creates a native PowerPoint deck from a newbiz2 report-data.json file.",
      "",
    ].join("\n")
  );
}

function plain(value) {
  if (value == null) return "";
  return String(value)
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s+/g, "\n")
    .trim();
}

function compact(value, limit = 170) {
  const text = plain(value);
  if (!text) return "";
  if (text.length <= limit) return text;
  const sentences = text.match(/[^.!?]+[.!?]+/g) || [];
  let built = "";
  for (const sentence of sentences) {
    const candidate = `${built} ${sentence.trim()}`.trim();
    if (candidate.length <= limit) built = candidate;
    else break;
  }
  if (built) return built;
  const words = text.split(/\s+/);
  let current = "";
  for (const word of words) {
    const candidate = `${current} ${word}`.trim();
    if (candidate.length <= limit) current = candidate;
    else break;
  }
  return `${current.replace(/[,:;]+$/, "")}.`;
}

function listify(items) {
  return (items || []).map((item) => plain(item)).filter(Boolean);
}

function pickCardBody(section, preferredTitle) {
  const cards = section?.cards || [];
  if (preferredTitle) {
    const needle = preferredTitle.toLowerCase();
    const hit = cards.find((card) => plain(card.title).toLowerCase().includes(needle));
    if (hit) return plain(hit.body);
  }
  const first = cards.find((card) => plain(card.body));
  return first ? plain(first.body) : "";
}

function ensureFile(candidate) {
  if (!candidate) return null;
  return fs.existsSync(candidate) ? candidate : null;
}

function resolveAsset(dataDir, value) {
  const text = plain(value);
  if (!text) return null;
  const candidate = path.isAbsolute(text) ? text : path.resolve(dataDir, text);
  return ensureFile(candidate);
}

const PPTX_SAFE_EXTS = new Set([".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".wmf"]);

function pptxSafeAsset(dataDir, value) {
  const candidate = resolveAsset(dataDir, value);
  if (!candidate) return null;
  const ext = path.extname(candidate).toLowerCase();
  if (PPTX_SAFE_EXTS.has(ext)) return candidate;
  if (ext === ".svg") {
    for (const suffix of [".png", ".jpg", ".jpeg", ".webp"]) {
      const companion = candidate.replace(/\.svg$/i, suffix);
      if (fs.existsSync(companion)) return companion;
    }
  }
  return null;
}

function brandAsset(dataDir, brand) {
  return (
    pptxSafeAsset(dataDir, brand?.mark_url) ||
    pptxSafeAsset(dataDir, brand?.logo_url) ||
    ensureFile(path.join(dataDir, "slide-assets", `${plain(brand?.slug)}-mark.png`)) ||
    ensureFile(path.join(dataDir, "slide-assets", `${plain(brand?.slug)}-logo.png`)) ||
    ensureFile(path.join(dataDir, "slide-assets", `${plain(brand?.slug)}-favicon.png`))
  );
}

function competitorAsset(dataDir, entry) {
  return (
    pptxSafeAsset(dataDir, entry?.logo_url) ||
    pptxSafeAsset(dataDir, entry?.competitor_logo_url) ||
    pptxSafeAsset(dataDir, entry?.badge_url) ||
    pptxSafeAsset(dataDir, entry?.mark_url)
  );
}

const C = {
  navy: "10263B",
  teal: "3AA7A3",
  slate: "5B6B7A",
  ink: "24313F",
  panel: "ECF3F8",
  panel2: "F7FAFC",
  white: "FFFFFF",
  line: "D7E3EC",
  soft: "1E4F7D",
  amber: "D28B26",
  amberSoft: "FBF4E8",
};

function addRoundBox(slide, x, y, w, h, opts = {}) {
  slide.addShape(SHAPE.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: opts.radius || 0.08,
    fill: { color: opts.fill || C.panel },
    line: { color: opts.line || C.line, width: opts.lineWidth || 1 },
  });
}

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x,
    y,
    w,
    h,
    fontFace: opts.fontFace || "Aptos",
    fontSize: opts.fontSize || 16,
    bold: opts.bold || false,
    color: opts.color || C.ink,
    margin: opts.margin != null ? opts.margin : 0.04,
    valign: opts.valign || "top",
    align: opts.align || "left",
    fit: opts.fit || "shrink",
    breakLine: false,
    bullet: opts.bullet,
  });
}

function addHeader(slide, title, num, badgePath, brandName) {
  slide.background = { color: C.white };
  slide.addShape(SHAPE.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 0.72,
    fill: { color: C.navy },
    line: { color: C.navy, transparency: 100 },
  });
  addText(slide, `${num}. ${title}`, 0.72, 0.13, 9.5, 0.38, {
    fontFace: "Aptos Display",
    fontSize: 24,
    bold: true,
    color: C.white,
    margin: 0,
  });
  slide.addShape(SHAPE.roundRect, {
    x: 12.05,
    y: 0.09,
    w: 0.84,
    h: 0.46,
    rectRadius: 0.06,
    fill: { color: C.white },
    line: { color: C.white, transparency: 100 },
  });
  if (badgePath) {
    slide.addImage({ path: badgePath, x: 12.22, y: 0.15, w: 0.48, h: 0.33 });
  } else {
    addText(slide, (brandName || "B").slice(0, 1).toUpperCase(), 12.28, 0.12, 0.36, 0.26, {
      fontFace: "Aptos Display",
      fontSize: 22,
      bold: true,
      color: C.navy,
      align: "center",
      margin: 0,
    });
  }
}

function finalizeSlide(slide, pptx) {
  try { warnIfSlideHasOverlaps(slide, pptx); } catch (_) {}
  try { warnIfSlideElementsOutOfBounds(slide, pptx); } catch (_) {}
}

function addBulletList(slide, items, x, y, w, lineH = 0.46, fontSize = 13, maxItems = 4) {
  listify(items).slice(0, maxItems).forEach((item, idx) => {
    addText(slide, item, x, y + idx * lineH, w, 0.3, {
      fontSize,
      margin: 0,
      bullet: { indent: 12 },
    });
  });
}

function createDeck(data, dataPath, outPath) {
  const dataDir = path.dirname(dataPath);
  const brand = data.brand || {};
  const badge = brandAsset(dataDir, brand);

  const pptx = new PptxGenJS();
  SHAPE = pptx.ShapeType;
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "OpenAI Codex";
  pptx.company = "OpenAI";
  pptx.subject = `${plain(brand.name)} new-business intelligence`;
  pptx.title = `${plain(brand.name)} New-Business Intelligence`;
  pptx.lang = "en-GB";
  pptx.theme = {
    headFontFace: "Aptos Display",
    bodyFontFace: "Aptos",
    lang: "en-GB",
  };

  const cover = pptx.addSlide();
  cover.background = { color: C.navy };
  addRoundBox(cover, 0.82, 1.02, 0.86, 1.12, { fill: C.white, line: C.white });
  if (badge) {
    cover.addImage({ path: badge, x: 0.98, y: 1.28, w: 0.52, h: 0.58 });
  }
  addText(cover, `${plain(brand.name)} New-Business Intelligence`, 2.02, 1.56, 9.8, 0.6, {
    fontFace: "Aptos Display",
    fontSize: 29,
    bold: true,
    color: C.white,
    margin: 0,
  });
  addText(cover, compact(data.cover?.summary || data.executive_summary?.overall_recommendation, 240), 2.02, 2.56, 10.0, 1.3, {
    fontSize: 17,
    color: C.white,
    margin: 0,
  });
  addRoundBox(cover, 2.02, 4.20, 4.3, 1.28, { fill: C.soft, line: C.soft });
  addText(cover, "Focus", 2.18, 4.34, 1.0, 0.18, {
    fontSize: 15,
    fontFace: "Aptos Display",
    bold: true,
    color: C.teal,
    margin: 0,
  });
  addText(cover, compact(data.cover?.scope || data.executive_summary?.cards?.[0]?.body, 135), 2.18, 4.58, 3.8, 0.62, {
    fontSize: 14.2,
    color: C.white,
    margin: 0,
  });
  addRoundBox(cover, 6.62, 4.20, 4.9, 1.28, { fill: C.soft, line: C.soft });
  addText(cover, "Competitive set", 6.78, 4.34, 2.0, 0.18, {
    fontSize: 15,
    fontFace: "Aptos Display",
    bold: true,
    color: C.teal,
    margin: 0,
  });
  addText(cover, compact((data.cover?.competitors || []).join(", "), 110), 6.78, 4.58, 4.3, 0.44, {
    fontSize: 14.2,
    color: C.white,
    margin: 0,
  });
  addText(cover, `${plain(brand.website)} | Report date: ${plain(brand.date)}`, 2.02, 6.30, 6.5, 0.18, {
    fontSize: 11,
    color: "DCE4EC",
    margin: 0,
  });
  finalizeSlide(cover, pptx);

  const snapshot = pptx.addSlide();
  addHeader(snapshot, "Company Snapshot", 2, badge, plain(brand.name));
  addText(snapshot, compact(data.company_snapshot?.summary, 185), 0.88, 0.98, 11.6, 0.4, {
    fontSize: 16.5,
    color: C.slate,
    margin: 0,
  });
  const snapshotItems = (data.company_snapshot?.items || []).slice(0, 6);
  let top = 1.72;
  snapshotItems.forEach((item, idx) => {
    addRoundBox(snapshot, 0.95, top, 11.1, 0.72, { fill: idx % 2 ? C.panel2 : C.panel });
    addText(snapshot, `${plain(item.label)}: ${compact(item.value, 175)}`, 1.14, top + 0.14, 10.6, 0.38, {
      fontSize: 14.2,
      margin: 0,
    });
    top += 0.82;
  });
  finalizeSlide(snapshot, pptx);

  const exec = pptx.addSlide();
  addHeader(exec, "Executive Summary", 3, badge, plain(brand.name));
  addRoundBox(exec, 0.88, 0.96, 11.45, 0.78, { fill: "E6F5F3", line: "B7E5DF" });
  addText(exec, plain(data.executive_summary?.overall_recommendation), 1.02, 1.09, 11.0, 0.26, {
    fontSize: 14.2,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  const cards = data.executive_summary?.cards || [];
  const positions = [[0.88, 2.00], [4.16, 2.00], [7.44, 2.00], [0.88, 4.22], [4.16, 4.22], [7.44, 4.22]];
  cards.slice(0, 6).forEach((card, idx) => {
    const [x, y] = positions[idx];
    addRoundBox(exec, x, y, 2.86, 1.86, { fill: idx < 3 ? C.panel : C.panel2 });
    addText(exec, plain(card.title), x + 0.14, y + 0.12, 2.42, 0.28, {
      fontFace: "Aptos Display",
      fontSize: 13.5,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    addText(exec, compact(card.body, 150), x + 0.14, y + 0.48, 2.52, 1.08, {
      fontSize: 12.5,
      margin: 0,
    });
  });
  finalizeSlide(exec, pptx);

  const comp = pptx.addSlide();
  addHeader(comp, "Competitive Landscape", 4, badge, plain(brand.name));
  addText(comp, compact(data.competitive_landscape?.why_each_competitor_matters, 190), 0.90, 0.98, 11.4, 0.34, {
    fontSize: 15.8,
    color: C.slate,
    margin: 0,
  });
  let compTop = 1.60;
  (data.competitive_landscape?.table || []).slice(0, 5).forEach((entry, idx) => {
    addRoundBox(comp, 0.90, compTop, 11.45, 1.02, { fill: idx % 2 ? C.panel2 : C.panel });
    const competitorLogo = competitorAsset(dataDir, entry);
    if (competitorLogo) {
      comp.addImage({ path: competitorLogo, x: 1.08, y: compTop + 0.16, w: 0.42, h: 0.28 });
    }
    addText(comp, plain(entry.display_name || entry.competitor), 1.58, compTop + 0.12, 0.88, 0.22, {
      fontFace: "Aptos Display",
      fontSize: 12.8,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    addText(comp, compact(entry.why_it_matters, 124), 2.58, compTop + 0.12, 2.42, 0.6, { fontSize: 10.7, margin: 0 });
    addText(comp, compact(entry.positioning_pattern, 114), 5.18, compTop + 0.12, 2.42, 0.6, { fontSize: 10.7, margin: 0 });
    addText(comp, compact(entry.implication, 128), 7.88, compTop + 0.12, 3.04, 0.6, { fontSize: 10.7, margin: 0 });
    compTop += 1.16;
  });
  finalizeSlide(comp, pptx);

  const seo = pptx.addSlide();
  addHeader(seo, "SEO Priorities", 5, badge, plain(brand.name));
  addRoundBox(seo, 0.88, 0.96, 11.45, 0.58, { fill: C.panel });
  addText(seo, compact(pickCardBody(data.seo_audit, "biggest seo opportunity") || pickCardBody(data.seo_audit), 180), 1.04, 1.10, 11.0, 0.22, {
    fontSize: 14.3,
    color: C.navy,
    margin: 0,
  });
  const issues = data.seo_audit?.priority_issues || [];
  const seoPos = [[0.88, 1.82], [6.68, 1.82], [0.88, 4.02], [6.68, 4.02]];
  issues.slice(0, 4).forEach((issue, idx) => {
    const [x, y] = seoPos[idx];
    addRoundBox(seo, x, y, 5.0, 1.80, { fill: idx % 2 ? C.panel2 : C.panel });
    addText(seo, compact(issue.issue, 72), x + 0.14, y + 0.12, 4.6, 0.22, {
      fontFace: "Aptos Display",
      fontSize: 13.4,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    addText(seo, `Evidence: ${compact(issue.evidence, 105)}`, x + 0.14, y + 0.48, 4.56, 0.34, { fontSize: 11.2, margin: 0 });
    addText(seo, `Fix: ${compact(issue.recommended_fix, 105)}`, x + 0.14, y + 0.94, 4.56, 0.42, { fontSize: 11.2, color: C.teal, margin: 0 });
  });
  finalizeSlide(seo, pptx);

  const rep = pptx.addSlide();
  addHeader(rep, "Brand Reputation", 6, badge, plain(brand.name));
  addRoundBox(rep, 0.88, 0.96, 11.45, 0.60, { fill: "EEF8F7", line: "CBECE7" });
  addText(rep, compact(pickCardBody(data.brand_reputation, "trust") || pickCardBody(data.brand_reputation), 185), 1.04, 1.09, 11.0, 0.26, {
    fontSize: 13.5,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  addRoundBox(rep, 0.88, 1.88, 5.22, 4.72, { fill: C.panel });
  addText(rep, "Signals", 1.04, 2.02, 1.4, 0.18, {
    fontFace: "Aptos Display",
    fontSize: 13.5,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  addBulletList(rep, [
    data.brand_reputation?.cards?.[1]?.body,
    data.brand_reputation?.cards?.[3]?.body,
    ...(data.brand_reputation?.platform_readout || []).map((x) => typeof x === "object" ? x.summary || x.readout : x),
  ], 1.04, 2.36, 4.7, 0.82, 12.2, 4);
  addRoundBox(rep, 6.32, 1.88, 6.01, 4.72, { fill: C.panel2 });
  addText(rep, "Influential News", 6.48, 2.02, 2.2, 0.18, {
    fontFace: "Aptos Display",
    fontSize: 13.5,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  let newsTop = 2.30;
  (data.brand_reputation?.influential_news || []).slice(0, 4).forEach((item, idx) => {
    addRoundBox(rep, 6.48, newsTop, 5.62, 0.88, { fill: idx % 2 ? C.panel : C.white });
    addText(rep, `${plain(item.date)} | ${plain(item.source)}`, 6.64, newsTop + 0.12, 1.56, 0.18, {
      fontSize: 9.8,
      bold: true,
      color: C.slate,
      margin: 0,
    });
    addText(rep, compact(item.headline || item.why_it_matters, 118), 8.38, newsTop + 0.12, 3.34, 0.42, {
      fontSize: 10.0,
      margin: 0,
    });
    newsTop += 0.96;
  });
  finalizeSlide(rep, pptx);

  const content = pptx.addSlide();
  addHeader(content, "Content Strategy", 7, badge, plain(brand.name));
  addRoundBox(content, 0.88, 0.96, 11.45, 0.56, { fill: C.panel });
  addText(content, compact(data.content_strategy?.response_to_findings, 180), 1.04, 1.08, 11.0, 0.22, {
    fontSize: 14.5,
    color: C.navy,
    margin: 0,
  });
  const contentCards = data.content_strategy?.cards || [];
  const contentPos = [[0.88, 1.76], [6.10, 1.76], [0.88, 3.60], [6.10, 3.60]];
  contentCards.slice(0, 4).forEach((card, idx) => {
    const [x, y] = contentPos[idx];
    addRoundBox(content, x, y, 5.02, 1.54, { fill: idx % 2 ? C.panel2 : C.panel });
    addText(content, plain(card.title), x + 0.16, y + 0.12, 4.5, 0.2, {
      fontFace: "Aptos Display",
      fontSize: 13.2,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    addText(content, compact(card.body, 145), x + 0.16, y + 0.40, 4.7, 0.84, {
      fontSize: 12.1,
      margin: 0,
    });
  });
  finalizeSlide(content, pptx);

  const campaigns = pptx.addSlide();
  addHeader(campaigns, "Creative Campaign Ideas", 8, badge, plain(brand.name));
  addText(campaigns, compact(plain(data.creative_campaign_ideas?.ideas?.[0]?.concept) || "Four campaign routes shaped by the strongest commercial and messaging opportunities in the report.", 185), 0.90, 0.98, 11.4, 0.34, {
    fontSize: 15.7,
    color: C.slate,
    margin: 0,
  });
  const ideas = data.creative_campaign_ideas?.ideas || [];
  const ideaPos = [[0.88, 1.60], [6.70, 1.60], [0.88, 4.20], [6.70, 4.20]];
  ideas.slice(0, 4).forEach((idea, idx) => {
    const [x, y] = ideaPos[idx];
    addRoundBox(campaigns, x, y, 5.0, 2.26, { fill: idx % 2 ? C.amberSoft : C.panel2 });
    const art = resolveAsset(dataDir, idea.illustration_url);
    if (art) {
      campaigns.addImage({ path: art, x: x + 0.14, y: y + 0.16, w: 1.24, h: 1.86 });
    }
    addText(campaigns, plain(idea.title), x + 1.52, y + 0.12, 3.2, 0.32, {
      fontFace: "Aptos Display",
      fontSize: 14.2,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    const body = [
      `Concept: ${compact(idea.concept, 78)}`,
      `Activation: ${compact(idea.activation, 84)}`,
      compact(idea.why_it_will_work || idea.intended_effect || idea.press_angle, 76),
    ].filter(Boolean).join(" ");
    addText(campaigns, body, x + 1.52, y + 0.46, 3.18, 1.42, {
      fontSize: 11.1,
      margin: 0,
    });
  });
  finalizeSlide(campaigns, pptx);

  const roadmap = pptx.addSlide();
  addHeader(roadmap, "30 / 60 / 90 Day Plan", 9, badge, plain(brand.name));
  addText(roadmap, "A practical rollout that turns the report into a clearer commercial story, stronger proof, and more useful buyer-stage content.", 0.90, 0.98, 11.4, 0.34, {
    fontSize: 16.0,
    color: C.slate,
    margin: 0,
  });
  const timelines = data.opportunities?.timelines || [];
  const xs = [0.92, 4.42, 7.92];
  timelines.slice(0, 3).forEach((block, idx) => {
    addRoundBox(roadmap, xs[idx], 1.62, 3.02, 4.88, {
      fill: idx === 0 ? C.panel : idx === 1 ? C.panel2 : C.amberSoft,
    });
    addText(roadmap, plain(block.title), xs[idx] + 0.16, 1.80, 1.9, 0.22, {
      fontFace: "Aptos Display",
      fontSize: 14.3,
      bold: true,
      color: idx === 2 ? C.amber : C.navy,
      margin: 0,
    });
    addBulletList(roadmap, block.items, xs[idx] + 0.18, 2.20, 2.58, 1.06, 11.8, 3);
  });
  finalizeSlide(roadmap, pptx);

  const closing = pptx.addSlide();
  addHeader(closing, "Closing Takeaways", 10, badge, plain(brand.name));
  addRoundBox(closing, 0.88, 0.96, 11.45, 0.62, { fill: "EAF5FF", line: "C8E2FF" });
  addText(closing, compact(data.executive_summary?.overall_recommendation || data.content_strategy?.cards?.[3]?.body, 205), 1.04, 1.09, 11.0, 0.28, {
    fontSize: 15.0,
    bold: true,
    color: C.navy,
    margin: 0,
  });
  const closeItems = [
    ["Positioning", data.executive_summary?.cards?.[1]?.body],
    ["Growth lever", data.executive_summary?.cards?.[5]?.body],
    ["Content move", data.content_strategy?.cards?.[3]?.body],
    ["Next step", data.agency_opportunity?.overall_recommendation || data.executive_summary?.overall_recommendation],
  ];
  const closePos = [[0.88, 2.00], [6.05, 2.00], [0.88, 4.20], [6.05, 4.20]];
  closeItems.forEach(([title, body], idx) => {
    const [x, y] = closePos[idx];
    addRoundBox(closing, x, y, 5.15, 1.72, { fill: idx % 2 ? C.panel2 : C.panel });
    addText(closing, title, x + 0.16, y + 0.12, 1.8, 0.22, {
      fontFace: "Aptos Display",
      fontSize: 13.8,
      bold: true,
      color: C.navy,
      margin: 0,
    });
    addText(closing, compact(body, 165), x + 0.16, y + 0.46, 4.72, 0.86, {
      fontSize: 12.3,
      margin: 0,
    });
  });
  finalizeSlide(closing, pptx);

  return pptx.writeFile({ fileName: outPath });
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help || !args.data) {
    printHelp();
    process.exit(args.help ? 0 : 1);
  }

  const dataPath = path.resolve(args.data);
  const outPath = path.resolve(args.pptx || path.join(path.dirname(dataPath), "newbizintel-slides.pptx"));
  const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
  await createDeck(data, dataPath, outPath);
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
