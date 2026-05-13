#!/usr/bin/env python3
"""Generate prompt scaffolding and campaign-art contracts for creative campaigns.

This script is intentionally layout-safe and deterministic enough for local bundling,
but it is not the premium art-direction path for NewBizIntel delivery. The preferred
workflow is:

1. Use this script to establish the medium, prompt, filenames, and expected asset paths.
2. Generate true raster artwork from those prompts for premium delivery by default.
3. Use local scaffold placeholders only when the report explicitly opts into scaffold mode.

The output manifest is therefore a contract for real artwork generation as much as a
record of any placeholder assets created here.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import random
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


WIDTH = 900
HEIGHT = 1600
PREMIUM_BACKEND = "imagegen"
SCAFFOLD_BACKEND = "local-scaffold"
NEGATIVE_ART_DIRECTION = (
    "Hard constraints: no words, no letters, no numbers, no captions, no labels, "
    "no typography, no readable text, no UI copy, no signage. Do not show the target "
    "brand's logo, no logos, no target brand assets, no wordmark, no colour-coded "
    "brand assets, no product marks, no app screens, no packaging, and no recognisable "
    "owned brand identity. Use abstract or symbolic "
    "forms only for company/product references."
)


STYLE_BY_KIND = {
    "drift": {
        "medium": "cinematic photograph",
        "family": "photography",
        "style": "vivid photographic realism with atmospheric industrial light, energy glow, and physical depth",
        "palette": {
            "sky_top": "#20303e",
            "sky_bottom": "#d08b56",
            "sun": "#ff7a2c",
            "glow": "#ffb15d",
            "deep": "#1b2e37",
            "mid": "#3d5e64",
            "light": "#d9e8de",
            "accent": "#6eb3ff",
        },
    },
    "control": {
        "medium": "technical diagram",
        "family": "technical-diagram",
        "style": "precise blueprint systems graphic with crisp linework, deep navy field, and luminous control nodes",
        "palette": {
            "bg": "#071524",
            "panel": "#0f2437",
            "grid": "#23425d",
            "ink": "#d6e7f7",
            "accent": "#6eb3ff",
            "highlight": "#2fe1ff",
            "soft": "#122f4a",
            "soft2": "#173652",
        },
    },
    "proof": {
        "medium": "punk pop-art poster",
        "family": "print-poster",
        "style": "bold editorial collage with zine energy, halftone texture, torn paper, stamps, and confrontational contrast",
        "palette": {
            "paper": "#f6efe4",
            "black": "#151515",
            "red": "#db2d20",
            "cream": "#fff7ed",
            "mustard": "#f0c05d",
            "pink": "#ff8d7d",
        },
    },
    "portfolio": {
        "medium": "photographed sculpture or maquette",
        "family": "sculptural-photography",
        "style": "gallery-quality sculptural terrain model with tactile material surfaces, top light, and physical relief",
        "palette": {
            "bg": "#edf2e7",
            "surface": "#d9dfcf",
            "surface2": "#eef1e7",
            "shadow": "#88957d",
            "ink": "#556252",
            "accent": "#8ba95e",
            "highlight": "#4f8d68",
        },
    },
    "generic": {
        "medium": "editorial artwork",
        "family": "editorial-artwork",
        "style": "distinctive premium campaign artwork with clear depth, texture, and a strong portrait composition",
        "palette": {
            "bg": "#f2f0ec",
            "ink": "#384148",
            "accent": "#b77d54",
        },
    },
}


SURPRISE_STYLE_LIBRARY = {
    "drift": [
        {
            "slug": "cosmic-observatory-photo",
            "medium": "cosmic long-exposure photography",
            "family": "photography",
            "style": "night-sky energy photography with observatory drama, luminous trails, and cinematic scientific atmosphere",
            "renderer": "drift",
            "palette": {
                "sky_top": "#070d22",
                "sky_bottom": "#2f1b52",
                "sun": "#ff5bcf",
                "glow": "#6b7cff",
                "deep": "#0a1024",
                "mid": "#1d365f",
                "light": "#dce8ff",
                "accent": "#89e1ff",
            },
        },
        {
            "slug": "brushstroke-heatwave",
            "medium": "gestural brushstroke painting",
            "family": "painting",
            "style": "expressive painterly strokes, hot and cool energy swells, and visible texture from top to bottom",
            "renderer": "drift",
            "palette": {
                "sky_top": "#18213a",
                "sky_bottom": "#d65a2e",
                "sun": "#ff4f1f",
                "glow": "#ffbf40",
                "deep": "#25374c",
                "mid": "#4d6d7f",
                "light": "#f0e2cb",
                "accent": "#7ec8ff",
            },
        },
        {
            "slug": "seventies-energy-advert",
            "medium": "1970s print advert illustration",
            "family": "graphic-print-collage",
            "style": "retro ad-art, sun-faded warmth, punchy circles, and optimistic analog campaign drama",
            "renderer": "drift",
            "palette": {
                "sky_top": "#3a2a21",
                "sky_bottom": "#d39a58",
                "sun": "#f35a24",
                "glow": "#ffd45c",
                "deep": "#223645",
                "mid": "#5d766f",
                "light": "#f3e6d3",
                "accent": "#f4a259",
            },
        },
        {
            "slug": "infrared-aerial-survey",
            "medium": "infrared aerial survey photography",
            "family": "photography",
            "style": "thermal-imaging landscape, hot loss signatures, and eerie operational contrast across a wide estate",
            "renderer": "drift",
            "palette": {
                "sky_top": "#241631",
                "sky_bottom": "#7a2d1e",
                "sun": "#ff6b2d",
                "glow": "#ffd166",
                "deep": "#291d3b",
                "mid": "#4e5d75",
                "light": "#efe6d8",
                "accent": "#ff9f43",
            },
        },
        {
            "slug": "noir-comic-storm-front",
            "medium": "graphic novel storm-front illustration",
            "family": "comic-art",
            "style": "high-contrast comic noir with weather-map energy, heavy shadow, and dramatic motion across the full column",
            "renderer": "drift",
            "palette": {
                "sky_top": "#101923",
                "sky_bottom": "#51606a",
                "sun": "#f2552c",
                "glow": "#ffcf5a",
                "deep": "#1d2a33",
                "mid": "#395563",
                "light": "#ece5db",
                "accent": "#7ab2ff",
            },
        },
        {
            "slug": "oil-pastel-blackout",
            "medium": "oil pastel expressionist painting",
            "family": "painting",
            "style": "thick tactile pigment, smeared light, and emotional blackout-era energy rather than clean corporate polish",
            "renderer": "drift",
            "palette": {
                "sky_top": "#1a2237",
                "sky_bottom": "#a34d32",
                "sun": "#ff5a24",
                "glow": "#ffb84d",
                "deep": "#253447",
                "mid": "#596d73",
                "light": "#f4ddc8",
                "accent": "#84b0e8",
            },
        },
        {
            "slug": "sunny-comic-energy-cascade",
            "medium": "cartoony editorial illustration",
            "family": "cartoon-illustration",
            "style": "playful comic energy, bright daylight palette, exaggerated motion, soft outlined symbols, and a full-column cascade of visible system drift",
            "renderer": "drift",
            "palette": {
                "sky_top": "#dff4ff",
                "sky_bottom": "#ffe5ba",
                "sun": "#ff8c42",
                "glow": "#ffd166",
                "deep": "#2f5d7c",
                "mid": "#67a6c9",
                "light": "#fff7ee",
                "accent": "#42c2ff",
            },
        },
        {
            "slug": "impressionist-solar-garden",
            "medium": "impressionist landscape painting",
            "family": "impressionist-painting",
            "style": "sunlit brushwork, broken colour, airy atmosphere, and lyrical energy movement that feels painterly rather than technological",
            "renderer": "drift",
            "palette": {
                "sky_top": "#b9dcff",
                "sky_bottom": "#ffd8a8",
                "sun": "#ff934f",
                "glow": "#ffe08a",
                "deep": "#5a7d5f",
                "mid": "#8ebf92",
                "light": "#fff6ea",
                "accent": "#5ba7d1",
            },
        },
        {
            "slug": "ukiyo-current-study",
            "medium": "Japanese brush-and-wash printmaking",
            "family": "brush-ink",
            "style": "ukiyo-e inspired flowing contours, brushed currents, pale paper space, and elegant directional energy instead of dark futurism",
            "renderer": "drift",
            "palette": {
                "sky_top": "#f5efe5",
                "sky_bottom": "#ead9c0",
                "sun": "#d8703f",
                "glow": "#f1c27d",
                "deep": "#304d5a",
                "mid": "#6c8f87",
                "light": "#fffaf2",
                "accent": "#6e8fb3",
            },
        },
    ],
    "control": [
        {
            "slug": "neon-schematic",
            "medium": "neon systems schematic",
            "family": "technical-diagram",
            "style": "dense futuristic circuit map with electric cyan signal paths and disciplined technical geometry",
            "renderer": "control",
            "palette": {
                "bg": "#050816",
                "panel": "#0b1630",
                "grid": "#1d3354",
                "ink": "#d8f4ff",
                "accent": "#77b7ff",
                "highlight": "#38e8ff",
                "soft": "#0d2041",
                "soft2": "#112850",
            },
        },
        {
            "slug": "brutalist-blueprint",
            "medium": "brutalist blueprint diagram",
            "family": "technical-diagram",
            "style": "spare technical plan, heavier structure, blueprint linework, and hard industrial rigor",
            "renderer": "control",
            "palette": {
                "bg": "#0b1320",
                "panel": "#12202f",
                "grid": "#3b536d",
                "ink": "#edf3ff",
                "accent": "#9cb8d8",
                "highlight": "#8fe0ff",
                "soft": "#182d46",
                "soft2": "#213857",
            },
        },
        {
            "slug": "infrared-network-map",
            "medium": "infrared technical interface",
            "family": "technical-interface",
            "style": "dark operational UI, glowing routing logic, and intense signal contrast for control systems",
            "renderer": "control",
            "palette": {
                "bg": "#12070b",
                "panel": "#201018",
                "grid": "#523142",
                "ink": "#ffe6f1",
                "accent": "#ff8aa8",
                "highlight": "#ff5f7a",
                "soft": "#311928",
                "soft2": "#3d2031",
            },
        },
        {
            "slug": "swiss-spec-sheet",
            "medium": "Swiss modernist specification plate",
            "family": "technical-diagram",
            "style": "disciplined grid logic, measured hierarchy, and hard engineering order with minimal but assertive control geometry",
            "renderer": "control",
            "palette": {
                "bg": "#edf1f6",
                "panel": "#dce4ef",
                "grid": "#9ba8b9",
                "ink": "#132235",
                "accent": "#4c7bd9",
                "highlight": "#4dd6ff",
                "soft": "#c5d1e0",
                "soft2": "#b7c6d8",
            },
        },
        {
            "slug": "chalkboard-systems-map",
            "medium": "technical chalkboard systems drawing",
            "family": "hand-drawn-diagram",
            "style": "layered planning marks, live workshop logic, and hand-drawn systems orchestration with dense operational intent",
            "renderer": "control",
            "palette": {
                "bg": "#173126",
                "panel": "#214235",
                "grid": "#406a58",
                "ink": "#eef6ef",
                "accent": "#9dd0b5",
                "highlight": "#7df0d2",
                "soft": "#284f40",
                "soft2": "#315b4a",
            },
        },
        {
            "slug": "satellite-control-atlas",
            "medium": "orbital control atlas interface",
            "family": "technical-interface",
            "style": "cartographic control surfaces, geospatial overlays, and mission-control precision rather than ordinary blueprints",
            "renderer": "control",
            "palette": {
                "bg": "#07111d",
                "panel": "#112238",
                "grid": "#244564",
                "ink": "#edf7ff",
                "accent": "#8bc5ff",
                "highlight": "#51f0ff",
                "soft": "#17304a",
                "soft2": "#1e3b59",
            },
        },
        {
            "slug": "bubble-icon-orchestration-board",
            "medium": "playful systems infographic",
            "family": "playful-infographic",
            "style": "bright control bubbles, icon-like nodes, clear orchestration pathways, and generous pale space that makes governance feel calm and understandable",
            "renderer": "control",
            "palette": {
                "bg": "#f7f5ef",
                "panel": "#e8ecf2",
                "grid": "#b8c4d3",
                "ink": "#17314b",
                "accent": "#4da6ff",
                "highlight": "#ff8c42",
                "soft": "#d6dee8",
                "soft2": "#c8d3df",
            },
        },
        {
            "slug": "cartoon-control-room",
            "medium": "cartoony control-room illustration",
            "family": "cartoon-illustration",
            "style": "friendly but precise command-centre scene with modular panels, bright shapes, and visible cause-and-effect rather than ominous glow",
            "renderer": "control",
            "palette": {
                "bg": "#eef8ff",
                "panel": "#dbeef7",
                "grid": "#9fc5da",
                "ink": "#163046",
                "accent": "#2f80ed",
                "highlight": "#f2994a",
                "soft": "#cfe4ef",
                "soft2": "#bed8e7",
            },
        },
        {
            "slug": "picasso-governance-plane",
            "medium": "Picasso-esque cubist systems painting",
            "family": "cubist-painting",
            "style": "angled planes, simplified faces and instruments, fractured system blocks, and a museum-like painterly reading of governance and supervision",
            "renderer": "control",
            "palette": {
                "bg": "#f3e7d8",
                "panel": "#e0c8b0",
                "grid": "#b19074",
                "ink": "#2f2a28",
                "accent": "#2f6db0",
                "highlight": "#d4683d",
                "soft": "#d8bea5",
                "soft2": "#cfb294",
            },
        },
    ],
    "proof": [
        {
            "slug": "punk-xerox-zine",
            "medium": "punk xerox zine poster",
            "family": "graphic-print-collage",
            "style": "chaotic photocopy collage, slashed geometry, blunt contrast, and agit-prop energy",
            "renderer": "proof",
            "palette": {
                "paper": "#f5efdf",
                "black": "#101010",
                "red": "#ef2b1f",
                "cream": "#fff8ee",
                "mustard": "#efbf4e",
                "pink": "#ff7ca3",
            },
        },
        {
            "slug": "pop-silkscreen",
            "medium": "pop-art silkscreen print",
            "family": "graphic-print-collage",
            "style": "graphic silkscreen blocks, comic-book punch, halftone rhythm, and poster-bold framing",
            "renderer": "proof",
            "palette": {
                "paper": "#fff4dd",
                "black": "#161616",
                "red": "#0057ff",
                "cream": "#fff9ef",
                "mustard": "#ff5a1f",
                "pink": "#f8d100",
            },
        },
        {
            "slug": "cubist-dossier",
            "medium": "Cubist editorial collage",
            "family": "graphic-print-collage",
            "style": "fractured document planes, angular evidence blocks, and sharp avant-garde editorial tension",
            "renderer": "proof",
            "palette": {
                "paper": "#efe7db",
                "black": "#22201e",
                "red": "#2d4abf",
                "cream": "#faf3eb",
                "mustard": "#c56b2d",
                "pink": "#b64747",
            },
        },
        {
            "slug": "risograph-manifesto",
            "medium": "risograph editorial broadside",
            "family": "graphic-print-collage",
            "style": "misregistered ink, radical print-shop texture, and manifesto-like proof stacking with visible production grit",
            "renderer": "proof",
            "palette": {
                "paper": "#f7efdf",
                "black": "#171717",
                "red": "#3957d6",
                "cream": "#fff8ef",
                "mustard": "#ff6b2c",
                "pink": "#f5427a",
            },
        },
        {
            "slug": "courtroom-evidence-wall",
            "medium": "forensic evidence-board collage",
            "family": "graphic-print-collage",
            "style": "pinned proof fragments, marked exhibits, and investigatory tension that makes claims feel cross-examined",
            "renderer": "proof",
            "palette": {
                "paper": "#ece5d8",
                "black": "#1d1c1b",
                "red": "#bb2f2f",
                "cream": "#faf5ec",
                "mustard": "#b88a3d",
                "pink": "#8f4f63",
            },
        },
        {
            "slug": "tabloid-front-page",
            "medium": "tabloid front-page print layout",
            "family": "graphic-print-collage",
            "style": "loud front-page urgency, cropped snippets, heavy blocks, and sensational proof framing with editorial aggression",
            "renderer": "proof",
            "palette": {
                "paper": "#f4eedf",
                "black": "#121212",
                "red": "#ef3326",
                "cream": "#fffaf2",
                "mustard": "#ffd044",
                "pink": "#2f5fd0",
            },
        },
        {
            "slug": "still-life-proof-photography",
            "medium": "still-life studio photography",
            "family": "still-life-photography",
            "style": "high-key photographic still life with arranged evidence objects, crisp daylight, reflective surfaces, and premium magazine calm instead of dark drama",
            "renderer": "generic",
            "palette": {
                "bg": "#fbf6ef",
                "ink": "#2f3439",
                "accent": "#e76f51",
            },
        },
        {
            "slug": "impressionist-proof-canvas",
            "medium": "impressionist evidence painting",
            "family": "impressionist-painting",
            "style": "sunlit painterly proof scene with thick visible strokes, optimistic colour vibration, and tactile evidence surfaces laid through the full portrait",
            "renderer": "generic",
            "palette": {
                "bg": "#fff4df",
                "ink": "#3c4f3d",
                "accent": "#de6b48",
            },
        },
        {
            "slug": "brush-seal-proof-scroll",
            "medium": "Japanese brush-scroll painting",
            "family": "brush-ink",
            "style": "ink-wash movement, seal-like marks, pale fibres, and elegant vertical proof stacking inspired by Japanese brushwork",
            "renderer": "generic",
            "palette": {
                "bg": "#f6f1e7",
                "ink": "#24323a",
                "accent": "#c75b39",
            },
        },
        {
            "slug": "bubble-sticker-pop",
            "medium": "bubble-and-icon pop graphic",
            "family": "playful-infographic",
            "style": "layered bubbles, sticker-like icons, bright flat colour bursts, and upbeat proof moments that feel accessible rather than severe",
            "renderer": "generic",
            "palette": {
                "bg": "#fff7ea",
                "ink": "#213547",
                "accent": "#ff7f50",
            },
        },
    ],
    "freshness": [
        {
            "slug": "baroque-freshness-still-life",
            "medium": "baroque forensic food still-life painting",
            "family": "painting",
            "style": "dramatic oil-painting realism, jewel-like fresh ingredients, kitchen light, inspection tags, chilled condensation, and rich table detail from top to bottom",
            "renderer": "generic",
            "palette": {
                "bg": "#201713",
                "ink": "#f7ead7",
                "accent": "#ff6b35",
            },
        },
        {
            "slug": "botanical-quality-ledger",
            "medium": "botanical watercolour quality ledger",
            "family": "painting",
            "style": "hand-painted ingredient studies, produce cross-sections, delivery-route notations, pale washes, and meticulous freshness evidence without any readable words",
            "renderer": "generic",
            "palette": {
                "bg": "#f6f1df",
                "ink": "#2f4d3c",
                "accent": "#e56f3c",
            },
        },
        {
            "slug": "macro-cold-chain-photograph",
            "medium": "macro food photography with cold-chain detail",
            "family": "photography",
            "style": "crisp photographic close-ups of vegetables, chilled packaging textures, ice crystals, barcode-like abstract marks, and premium editorial lighting",
            "renderer": "generic",
            "palette": {
                "bg": "#0d1b20",
                "ink": "#f7f3e8",
                "accent": "#7bdff2",
            },
        },
        {
            "slug": "clay-market-counter",
            "medium": "painted clay food-market maquette",
            "family": "sculptural-photography",
            "style": "physical clay produce, miniature crates, delivery trays, tactile packaging, and warm studio shadows like a photographed handmade model",
            "renderer": "generic",
            "palette": {
                "bg": "#efe4cf",
                "ink": "#5a3a2d",
                "accent": "#65a66b",
            },
        },
    ],
    "comparison": [
        {
            "slug": "split-tabletop-theatre",
            "medium": "photographed tabletop comparison theatre",
            "family": "sculptural-photography",
            "style": "a physical studio model with two contrasting service worlds, miniature plates, delivery props, tactile dividers, and theatrical side-lighting",
            "renderer": "portfolio",
            "palette": {
                "bg": "#ece2d5",
                "surface": "#d6bda4",
                "surface2": "#f7eee4",
                "shadow": "#826b5a",
                "ink": "#4c3d33",
                "accent": "#2d6cdf",
                "highlight": "#f15d3a",
            },
        },
        {
            "slug": "magazine-test-kitchen-photo",
            "medium": "editorial test-kitchen photography",
            "family": "photography",
            "style": "high-end magazine photography comparing meal paths through props, ingredients, utensils, score-card shapes, and crisp natural shadows without words",
            "renderer": "generic",
            "palette": {
                "bg": "#f5efe6",
                "ink": "#26333b",
                "accent": "#ff6b35",
            },
        },
        {
            "slug": "comic-comparison-court",
            "medium": "comic-panel comparison courtroom",
            "family": "comic-art",
            "style": "bold illustrated courtroom energy, split panels, exaggerated evidence props, and graphic tension between choices with no lettering",
            "renderer": "generic",
            "palette": {
                "bg": "#fff0cf",
                "ink": "#101010",
                "accent": "#ff3b30",
            },
        },
        {
            "slug": "pop-bubble-comparison-board",
            "medium": "bubble-chart pop graphic",
            "family": "playful-infographic",
            "style": "bright comparative bubbles, icon-cluster logic, playful dividers, and quick-read contrast that still feels premium and intentional",
            "renderer": "generic",
            "palette": {
                "bg": "#fff8ef",
                "ink": "#23384d",
                "accent": "#ff7a59",
            },
        },
        {
            "slug": "picasso-choice-tableau",
            "medium": "Picasso-esque still-life painting",
            "family": "cubist-painting",
            "style": "fractured tabletop forms, theatrical comparison objects, and angular storytelling that jars sharply against technical treatments",
            "renderer": "generic",
            "palette": {
                "bg": "#f2e4d3",
                "ink": "#2f2b2a",
                "accent": "#3c78b5",
            },
        },
    ],
    "portfolio": [
        {
            "slug": "clay-maquette",
            "medium": "photographed clay maquette",
            "family": "sculptural-photography",
            "style": "tactile clay forms, gallery light, and materially real terrain-scale objects",
            "renderer": "portfolio",
            "palette": {
                "bg": "#efe9df",
                "surface": "#d8c5b3",
                "surface2": "#eadccf",
                "shadow": "#8b7869",
                "ink": "#5d4f45",
                "accent": "#b86d3c",
                "highlight": "#7e9f6d",
            },
        },
        {
            "slug": "architectural-foam-model",
            "medium": "architectural foam-core model photography",
            "family": "sculptural-photography",
            "style": "clean physical model, gallery plinth sensibility, and controlled structural relief",
            "renderer": "portfolio",
            "palette": {
                "bg": "#f3f5ef",
                "surface": "#e2e7dc",
                "surface2": "#f7f9f2",
                "shadow": "#9ca694",
                "ink": "#536255",
                "accent": "#7eaf93",
                "highlight": "#668b78",
            },
        },
        {
            "slug": "land-art-relief",
            "medium": "land-art relief sculpture",
            "family": "sculpture",
            "style": "earthwork topography, carved contour arcs, and tactile landscape-scale growth movement",
            "renderer": "portfolio",
            "palette": {
                "bg": "#e9ebdf",
                "surface": "#cfd3b3",
                "surface2": "#e7ebd6",
                "shadow": "#8b9270",
                "ink": "#5c6544",
                "accent": "#7aa35b",
                "highlight": "#4d7e5f",
            },
        },
        {
            "slug": "bronze-tabletop-sculpture",
            "medium": "bronze tabletop sculpture photography",
            "family": "sculptural-photography",
            "style": "weighty cast-metal forms, museum lighting, and a sense of durable portfolio-scale infrastructure",
            "renderer": "portfolio",
            "palette": {
                "bg": "#efe7dc",
                "surface": "#aa7b57",
                "surface2": "#d1b391",
                "shadow": "#6b5240",
                "ink": "#4b3a31",
                "accent": "#5e8a7a",
                "highlight": "#c48a43",
            },
        },
        {
            "slug": "paper-cut-masterplan",
            "medium": "paper-cut masterplan relief",
            "family": "paper-art",
            "style": "layered paper topography, crisp shadows, and strategic growth pathways laid out like a physical planning model",
            "renderer": "portfolio",
            "palette": {
                "bg": "#f3f0e8",
                "surface": "#d9dcc8",
                "surface2": "#f8f5ef",
                "shadow": "#9ca08e",
                "ink": "#5f6557",
                "accent": "#7a9985",
                "highlight": "#94b06a",
            },
        },
        {
            "slug": "ceramic-terrain-installation",
            "medium": "ceramic installation photography",
            "family": "sculptural-photography",
            "style": "glazed modular terrain, handcrafted physical surfaces, and a more artistic gallery-installation reading of scale-up",
            "renderer": "portfolio",
            "palette": {
                "bg": "#eef1eb",
                "surface": "#c9d2c5",
                "surface2": "#f7faf4",
                "shadow": "#889487",
                "ink": "#4f5d52",
                "accent": "#6ea38c",
                "highlight": "#cfd9b1",
            },
        },
        {
            "slug": "matisse-paper-constellation",
            "medium": "Matisse-like paper-cut mural",
            "family": "paper-art",
            "style": "light-filled cut paper shapes, optimistic spatial rhythm, and a distinctly artistic strategic growth composition with lots of breathable pale space",
            "renderer": "portfolio",
            "palette": {
                "bg": "#fbf6ed",
                "surface": "#dde8d8",
                "surface2": "#fffaf4",
                "shadow": "#b5c0b4",
                "ink": "#35524a",
                "accent": "#4ca6a8",
                "highlight": "#f0a24f",
            },
        },
        {
            "slug": "sunlit-still-life-infrastructure",
            "medium": "sunlit still-life photography",
            "family": "still-life-photography",
            "style": "clean editorial still life of sculptural strategic objects, soft daylight, and a premium magazine sense of growth and arrangement",
            "renderer": "generic",
            "palette": {
                "bg": "#faf5ec",
                "ink": "#334640",
                "accent": "#d97a4a",
            },
        },
        {
            "slug": "brush-mountain-masterplan",
            "medium": "Japanese brush landscape painting",
            "family": "brush-ink",
            "style": "vertical brush-landscape composition, strategic pathways like mountain routes, soft mineral colour, and elegant planning calm",
            "renderer": "generic",
            "palette": {
                "bg": "#f5efe6",
                "ink": "#32424a",
                "accent": "#6b8f7f",
            },
        },
    ],
}


def slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return text or "campaign-idea"


def relative_asset_path(asset_dir: Path, path: Path) -> str:
    return path.relative_to(asset_dir.parent).as_posix()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def build_premium_art_brief(
    *,
    brand_name: str,
    brand_slug: str,
    generation_backend: str,
    delivery_mode: str,
    manifest_path: Path,
    prompt_manifest: list[dict[str, str]],
) -> str:
    lines = [
        f"# {brand_name} creative campaign artwork brief",
        "",
        f"- Brand slug: `{brand_slug}`",
        f"- Delivery mode: `{delivery_mode}`",
        f"- Generation backend: `{generation_backend}`",
        f"- Prompt manifest: `{manifest_path.name}`",
        "- Expected output: one portrait raster image per campaign idea",
        "- Recommended aspect: 9:16 portrait",
        "- Recommended minimum size: 900x1600",
        "- Hard rule: images must contain no words, letters, numbers, captions, labels, UI copy, signage, logos, wordmarks, product marks, app screens, packaging, or target-brand assets.",
        "- Style rule: each campaign idea must use a visibly different media family; avoid repeating collage/poster/vector-like treatments across a set.",
        "- Import rule: keep prompt order aligned with image order when importing a generated batch",
        "",
        "## Workflow",
        "",
        "1. Generate one final raster image for each prompt below.",
        "2. Keep the output order aligned with the numbered prompts.",
    "3. Import the resulting batch back into newbizintel using the campaign-art module.",
        "",
        "## Prompts",
        "",
    ]

    for item in prompt_manifest:
        lines.extend(
            [
                f"### {item['sequence']}. {item['title']}",
                "",
                f"- Kind: `{item['kind']}`",
                f"- Style: `{item['style_slug']}`",
                f"- Media family: `{item['style_family']}`",
                f"- Medium: `{item['medium']}`",
                f"- Expected asset path: `{item['expected_asset_path']}`",
                "",
                item["prompt"].strip(),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def motif_key(title: str, concept: str, medium: str = "") -> str:
    source = f"{medium} {title} {concept}".lower()
    if "control" in source or "layer" in source:
        return "control"
    if "proof" in source or "trust" in source or "doubt" in source or "confidence" in source:
        return "proof"
    if any(
        term in source
        for term in (
            "freshness",
            "fresh",
            "receipt",
            "recipe",
            "ingredient",
            "produce",
            "meal",
            "box",
            "delivery",
            "quality",
        )
    ):
        return "freshness"
    if any(term in source for term in ("comparison", "compare", "table", "challenger", "fair")):
        return "comparison"
    if "sculpt" in source or "maquette" in source or "relief" in source:
        return "portfolio"
    if "blueprint" in source or "diagram" in source or "technical" in source:
        return "control"
    if "pop-art" in source or "poster" in source or "zine" in source or "punk" in source:
        return "proof"
    if "photo" in source or "photograph" in source or "cinematic" in source:
        return "drift"
    if "drift" in source or "waste" in source:
        return "drift"
    if "pilot" in source or "portfolio" in source or "scale" in source:
        return "portfolio"
    return "generic"


def palette_hex_values(palette: dict | None) -> list[str]:
    if not isinstance(palette, dict):
        return []
    return [
        str(value)
        for value in palette.values()
        if isinstance(value, str) and value.startswith("#") and len(value) == 7
    ]


def classify_palette_family(
    family: str,
    slug: str,
    medium: str,
    style: str,
    palette: dict | None,
) -> str:
    text = " ".join(part for part in (family, slug, medium, style) if part).lower()
    if any(token in text for token in ("blueprint", "technical", "circuit", "cosmic", "infrared", "neon", "electric", "observatory")):
        return "cool-luminous"
    if any(token in text for token in ("sculpt", "maquette", "terrain", "botanical", "garden", "moss", "clay")):
        return "mineral-green"
    if any(token in text for token in ("poster", "zine", "collage", "comic", "graphic", "risograph", "silkscreen", "cubist", "xerox")):
        return "graphic-contrast"
    if any(token in text for token in ("ukiyo", "ink-wash", "watercolour", "impressionist", "pastel", "paper space")):
        return "airy-pastel"

    hexes = palette_hex_values(palette)
    if not hexes:
        return "warm-earth"

    hue_scores = {"warm": 0, "cool": 0, "green": 0, "neutral": 0}
    vivid = 0
    dark = 0
    light = 0
    for value in hexes:
        red = int(value[1:3], 16) / 255.0
        green = int(value[3:5], 16) / 255.0
        blue = int(value[5:7], 16) / 255.0
        hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
        if saturation >= 0.45:
            vivid += 1
        if lightness <= 0.18:
            dark += 1
        if lightness >= 0.82:
            light += 1
        if saturation <= 0.12:
            hue_scores["neutral"] += 1
        elif 0.10 <= hue <= 0.22:
            hue_scores["warm"] += 1
        elif 0.0 <= hue < 0.10 or hue > 0.92:
            hue_scores["warm"] += 1
        elif 0.22 < hue <= 0.46:
            hue_scores["green"] += 1
        elif 0.46 < hue <= 0.84:
            hue_scores["cool"] += 1
        else:
            hue_scores["cool"] += 1

    if hue_scores["green"] >= max(hue_scores["warm"], hue_scores["cool"]) and (light >= 2 or vivid >= 1):
        return "mineral-green"
    if hue_scores["cool"] >= hue_scores["warm"] + 1 and vivid >= 1:
        return "cool-luminous"
    if vivid >= 2 and dark >= 1 and light >= 1:
        return "graphic-contrast"
    if light >= max(2, len(hexes) // 2) and hue_scores["cool"] >= 1:
        return "airy-pastel"
    return "warm-earth"


def classify_profile_palette_family(profile: dict) -> str:
    return classify_palette_family(
        str(profile.get("family") or ""),
        str(profile.get("slug") or ""),
        str(profile.get("medium") or ""),
        str(profile.get("style") or ""),
        profile.get("palette"),
    )


def candidate_pool_for_kind(kind: str) -> list[dict]:
    if kind == "generic":
        pool: list[dict] = []
        for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
            pool.extend(dict(item, kind=library_kind) for item in items)
        return pool
    pool = [dict(item, kind=kind) for item in SURPRISE_STYLE_LIBRARY.get(kind, [])]
    if pool:
        return pool
    fallback_pool: list[dict] = []
    for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
        fallback_pool.extend(dict(item, kind=library_kind) for item in items)
    return fallback_pool


def full_surprise_pool() -> list[dict]:
    pool: list[dict] = []
    for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
        pool.extend(dict(item, kind=library_kind) for item in items)
    return pool


def stable_profile_sort_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("palette_family") or classify_profile_palette_family(item)),
        str(item.get("family") or item.get("kind") or ""),
        str(item.get("slug") or ""),
    )


def stable_generated_at(path: Path, payload: dict) -> str:
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if isinstance(existing, dict):
            existing_generated_at = str(existing.get("generated_at") or "").strip()
            existing_without_timestamp = dict(existing)
            existing_without_timestamp.pop("generated_at", None)
            if existing_generated_at and existing_without_timestamp == payload:
                return existing_generated_at
    return datetime.now(timezone.utc).isoformat()


def select_palette_candidate_profiles(
    kind: str,
    primary_profile: dict,
    *,
    max_candidates: int = 4,
) -> list[dict]:
    pool = candidate_pool_for_kind(kind)
    chosen: list[dict] = []
    used_slugs: set[str] = set()
    used_palette_families: set[str] = set()

    primary = dict(primary_profile)
    primary["palette_family"] = primary.get("palette_family") or classify_profile_palette_family(primary)
    chosen.append(primary)
    used_slugs.add(primary["slug"])
    used_palette_families.add(primary["palette_family"])

    ordered_pool = [dict(item) for item in pool if item.get("slug") not in used_slugs]
    for item in ordered_pool:
        item["palette_family"] = classify_profile_palette_family(item)
    ordered_pool.sort(key=stable_profile_sort_key)
    for item in ordered_pool:
        item["palette_family"] = classify_profile_palette_family(item)
        if item["palette_family"] in used_palette_families:
            continue
        chosen.append(item)
        used_slugs.add(item["slug"])
        used_palette_families.add(item["palette_family"])
        if len(chosen) >= max_candidates:
            break

    if len(chosen) < max_candidates:
        global_pool = [dict(item) for item in full_surprise_pool() if item.get("slug") not in used_slugs]
        for item in global_pool:
            item["palette_family"] = classify_profile_palette_family(item)
        global_pool.sort(key=stable_profile_sort_key)
        for item in global_pool:
            item["palette_family"] = classify_profile_palette_family(item)
            if item["palette_family"] in used_palette_families:
                continue
            chosen.append(item)
            used_slugs.add(item["slug"])
            used_palette_families.add(item["palette_family"])
            if len(chosen) >= max_candidates:
                break

    if len(chosen) < max_candidates:
        for item in ordered_pool:
            if item.get("slug") in used_slugs:
                continue
            item["palette_family"] = classify_profile_palette_family(item)
            chosen.append(item)
            used_slugs.add(item["slug"])
            if len(chosen) >= max_candidates:
                break

    return chosen


def base_profile_for_kind(kind: str) -> dict:
    profile = STYLE_BY_KIND.get(kind, STYLE_BY_KIND["generic"])
    palette = dict(profile["palette"])
    return {
        "slug": kind,
        "kind": kind,
        "medium": profile["medium"],
        "family": profile.get("family", kind),
        "style": profile["style"],
        "renderer": kind,
        "palette": palette,
        "palette_family": classify_palette_family(
            profile.get("family", kind),
            kind,
            profile["medium"],
            profile["style"],
            palette,
        ),
    }


def build_bitmap_prompt(title: str, concept: str, profile: dict) -> str:
    palette = profile.get("palette") or {}
    palette_hint = ", ".join(str(value) for value in palette.values() if isinstance(value, str) and value.startswith("#"))
    family = profile.get("family") or profile.get("slug") or "distinct-media-family"
    palette_family = str(profile.get("palette_family") or "distinct-palette-family").replace("-", " ")
    return (
        f"Create a tall portrait campaign illustration for '{title}'. "
        f"Use a {profile['medium']} treatment. "
        f"The core idea is: {concept}. "
        f"Art direction: {profile['style']}. "
        f"Make the result read unmistakably as {family}, not as generic corporate vector art. "
        f"Colour direction: {palette_hint}. "
        f"Keep the image clearly inside a {palette_family} palette family and avoid drifting into generic muddy mid-browns or ochre neutrals unless those tones are explicitly listed in the colour direction. "
        "Compose it to fill a narrow editorial column from top to bottom with a strong upper focal zone. "
        "Vary the tempo, light, and mood from other campaign ideas in the same set. "
        "Make the palette obviously different from the other campaign ideas in the same set, not just the medium or composition. "
        "Avoid generic flat corporate vector art. "
        "Make it visually distinct from the other campaign ideas and premium in finish. "
        f"{NEGATIVE_ART_DIRECTION}"
    )


def enforce_prompt_contract(prompt: str) -> str:
    prompt = (prompt or "").strip()
    if not prompt:
        return NEGATIVE_ART_DIRECTION
    prompt = re.sub(r"\s*Hard constraints:.*$", "", prompt, flags=re.IGNORECASE | re.DOTALL).strip()
    return f"{prompt} {NEGATIVE_ART_DIRECTION}"


def scaffold_allowed(delivery_mode: str, generation_backend: str) -> bool:
    return delivery_mode == "scaffold-allowed" or generation_backend in {
        SCAFFOLD_BACKEND,
        "placeholder-scaffold",
        "scaffold",
    }


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    w, h = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    top_rgb = hex_to_rgb(top)
    bottom_rgb = hex_to_rgb(bottom)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        row = tuple(
            int(top_rgb[i] * (1 - ratio) + bottom_rgb[i] * ratio) for i in range(3)
        )
        draw.line((0, y, w, y), fill=row)
    return image


def add_noise(image: Image.Image, amount: int, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    noise = Image.new("RGB", image.size)
    pixels = []
    for _ in range(image.size[0] * image.size[1]):
        value = 128 + rnd.randint(-amount, amount)
        pixels.append((value, value, value))
    noise.putdata(pixels)
    noise = noise.filter(ImageFilter.GaussianBlur(0.6))
    return Image.blend(image, noise, 0.08)


def glow_layer(size: tuple[int, int], circles: list[tuple[int, int, int, str]]) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for x, y, r, color in circles:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=hex_to_rgb(color) + (110,))
    return layer.filter(ImageFilter.GaussianBlur(36))


def film_grain(size: tuple[int, int], amount: int, seed: int, tint: tuple[int, int, int] | None = None) -> Image.Image:
    rnd = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = []
    tint = tint or (128, 128, 128)
    for _ in range(size[0] * size[1]):
        delta = rnd.randint(-amount, amount)
        alpha = rnd.randint(10, 42)
        pixels.append(
            (
                max(0, min(255, tint[0] + delta)),
                max(0, min(255, tint[1] + delta)),
                max(0, min(255, tint[2] + delta)),
                alpha,
            )
        )
    layer.putdata(pixels)
    return layer.filter(ImageFilter.GaussianBlur(0.35))


def soft_light_overlay(base: Image.Image, overlay: Image.Image, opacity: float) -> Image.Image:
    blended = ImageChops.soft_light(base.convert("RGB"), overlay.convert("RGB"))
    return Image.blend(base.convert("RGB"), blended, opacity)


def streak_overlay(size: tuple[int, int], color: str, seed: int, count: int = 18) -> Image.Image:
    rnd = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rgb = hex_to_rgb(color)
    for _ in range(count):
        x = rnd.randint(-40, size[0] + 40)
        y = rnd.randint(40, size[1] - 220)
        length = rnd.randint(140, 420)
        width = rnd.randint(4, 16)
        d.line((x, y, x + rnd.randint(-40, 40), y + length), fill=rgb + (rnd.randint(18, 44),), width=width)
    return layer.filter(ImageFilter.GaussianBlur(10))


def scanline_overlay(size: tuple[int, int], color: str, spacing: int = 3, alpha: int = 24) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rgb = hex_to_rgb(color)
    for y in range(0, size[1], spacing):
        d.line((0, y, size[0], y), fill=rgb + (alpha,), width=1)
    return layer


def rough_paper_overlay(size: tuple[int, int], seed: int) -> Image.Image:
    rnd = random.Random(seed)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(320):
        x = rnd.randint(0, size[0])
        y = rnd.randint(0, size[1])
        r = rnd.randint(1, 4)
        shade = rnd.randint(212, 244)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(shade, shade - 6, shade - 12, rnd.randint(10, 36)))
    return layer.filter(ImageFilter.GaussianBlur(0.8))


def torn_paper_block(image: Image.Image, box: tuple[int, int, int, int], fill: str, ink: str, seed: int, angle: float = 0.0) -> None:
    rnd = random.Random(seed)
    w = box[2] - box[0]
    h = box[3] - box[1]
    pad = 26
    mask = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    md = ImageDraw.Draw(mask)
    pts = []
    for x in range(0, w + pad * 2, max(18, w // 10)):
        pts.append((x, rnd.randint(0, 18)))
    for y in range(0, h + pad * 2, max(22, h // 10)):
        pts.append((w + pad * 2 - rnd.randint(0, 18), y))
    for x in range(w + pad * 2, 0, -max(18, w // 10)):
        pts.append((x, h + pad * 2 - rnd.randint(0, 18)))
    for y in range(h + pad * 2, 0, -max(22, h // 10)):
        pts.append((rnd.randint(0, 18), y))
    md.polygon(pts, fill=255)
    paper = Image.new("RGBA", mask.size, hex_to_rgb(fill) + (255,))
    edge = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    ed.bitmap((0, 0), mask.filter(ImageFilter.GaussianBlur(1.2)), fill=hex_to_rgb(ink) + (42,))
    paper.putalpha(mask)
    group = Image.alpha_composite(edge, paper)
    rotated = group.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    image.alpha_composite(rotated, (box[0] - pad, box[1] - pad))


def draw_drift_photo(palette: dict | None = None) -> Image.Image:
    p = palette or STYLE_BY_KIND["drift"]["palette"]
    base = vertical_gradient((WIDTH, HEIGHT), p["sky_top"], p["sky_bottom"]).convert("RGBA")
    haze = Image.new("RGBA", (WIDTH, HEIGHT), hex_to_rgb(p["light"]) + (0,))
    haze_draw = ImageDraw.Draw(haze)
    haze_draw.rectangle((0, 780, WIDTH, HEIGHT), fill=hex_to_rgb(p["light"]) + (70,))
    base.alpha_composite(haze)

    glow = glow_layer(
        (WIDTH, HEIGHT),
        [
            (730, 250, 120, p["sun"]),
            (640, 520, 90, p["glow"]),
            (490, 980, 110, p["glow"]),
        ],
    )
    base.alpha_composite(glow)

    structures = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(structures)
    d.polygon([(0, 980), (180, 820), (360, 940), (360, HEIGHT), (0, HEIGHT)], fill=hex_to_rgb(p["deep"]) + (255,))
    d.polygon([(250, 880), (520, 700), (760, 840), (760, HEIGHT), (250, HEIGHT)], fill=hex_to_rgb(p["mid"]) + (255,))
    d.polygon([(560, 960), (760, 820), (900, 900), (900, HEIGHT), (560, HEIGHT)], fill=hex_to_rgb(p["deep"]) + (255,))

    for start_x in range(300, 760, 44):
        d.line((start_x, 760, start_x - 150, 1260), fill=hex_to_rgb(p["light"]) + (80,), width=3)
    for y in range(840, 1300, 40):
        d.line((260, y, 760, y), fill=hex_to_rgb(p["light"]) + (60,), width=2)

    d.ellipse((84, 1090, 540, 1540), outline=hex_to_rgb(p["light"]) + (170,), width=18)
    d.ellipse((128, 1134, 496, 1496), outline=hex_to_rgb(p["accent"]) + (220,), width=10)
    d.ellipse((180, 1186, 444, 1444), outline=hex_to_rgb(p["deep"]) + (220,), width=18)
    d.ellipse((244, 1250, 380, 1386), fill=(255, 255, 255, 205))
    d.arc((180, 1186, 444, 1444), start=226, end=322, fill=hex_to_rgb(p["sun"]) + (255,), width=22)
    d.ellipse((396, 1098, 778, 1450), fill=hex_to_rgb(p["light"]) + (85,))
    d.rounded_rectangle((452, 1142, 742, 1384), radius=34, fill=(255, 247, 236, 170))
    for i, color in enumerate([p["light"], "#ffffff", p["sun"], p["light"]]):
        x = 492 + (i % 2) * 84
        y = 1186 + (i // 2) * 84
        d.rounded_rectangle((x, y, x + 52, y + 52), radius=14, fill=hex_to_rgb(color) + (220,))
    d.rounded_rectangle((690, 1154, 720, 1320), radius=14, fill=(255, 255, 255, 230))
    d.rounded_rectangle((698, 1204, 712, 1288), radius=7, fill=hex_to_rgb(p["sun"]) + (255,))

    structures = structures.filter(ImageFilter.GaussianBlur(0.6))
    base.alpha_composite(structures)
    result = add_noise(base.convert("RGB"), 18, 7)
    result = soft_light_overlay(result, vertical_gradient((WIDTH, HEIGHT), "#f8d19a", "#0d1a2f"), 0.14)
    result = Image.alpha_composite(result.convert("RGBA"), streak_overlay((WIDTH, HEIGHT), p["light"], 17, count=22)).convert("RGB")
    result = Image.alpha_composite(result.convert("RGBA"), film_grain((WIDTH, HEIGHT), 22, 23, hex_to_rgb(p["light"]))).convert("RGB")
    result = result.filter(ImageFilter.GaussianBlur(0.25))
    vignette = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    vd = ImageDraw.Draw(vignette)
    vd.rounded_rectangle((20, 20, WIDTH - 20, HEIGHT - 20), radius=46, outline=(255, 255, 255, 110), width=2)
    return Image.alpha_composite(result.convert("RGBA"), vignette).convert("RGB")


def draw_control_diagram(palette: dict | None = None) -> Image.Image:
    p = palette or STYLE_BY_KIND["control"]["palette"]
    image = Image.new("RGB", (WIDTH, HEIGHT), hex_to_rgb(p["bg"]))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((42, 42, WIDTH - 42, HEIGHT - 42), radius=30, fill=hex_to_rgb(p["panel"]), outline=hex_to_rgb(p["grid"]), width=2)
    for x in range(90, WIDTH - 40, 56):
        d.line((x, 42, x, HEIGHT - 42), fill=hex_to_rgb(p["grid"]), width=1)
    for y in range(90, HEIGHT - 40, 56):
        d.line((42, y, WIDTH - 42, y), fill=hex_to_rgb(p["grid"]), width=1)

    d.rounded_rectangle((112, 128, 788, 226), radius=14, fill=hex_to_rgb(p["grid"]))
    d.text((138, 162), "CONTROL_LAYER / ESTATE_GRAPH", fill=hex_to_rgb(p["ink"]))

    panels = [
        (158, 332, 352, 456),
        (404, 314, 612, 470),
        (642, 350, 748, 468),
        (176, 540, 366, 688),
        (408, 534, 716, 706),
    ]
    for i, box in enumerate(panels):
        color = p["soft"] if i % 2 == 0 else p["soft2"]
        d.rounded_rectangle(box, radius=18, fill=hex_to_rgb(color), outline=hex_to_rgb(p["accent"]), width=2)

    for line in [(254, 456, 254, 540), (506, 470, 506, 534), (694, 468, 694, 534), (254, 688, 254, 814), (562, 706, 562, 814)]:
        d.line(line, fill=hex_to_rgb(p["highlight"]), width=8)

    hexagon = [(450, 828), (572, 904), (572, 1052), (450, 1128), (328, 1052), (328, 904)]
    d.rounded_rectangle((236, 812, 664, 1128), radius=22, fill=(9, 23, 40), outline=hex_to_rgb(p["accent"]), width=4)
    d.polygon(hexagon, outline=hex_to_rgb(p["ink"]), width=18)
    glow = glow_layer((WIDTH, HEIGHT), [(450, 978, 120, p["highlight"])])
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    d = ImageDraw.Draw(image)
    d.ellipse((366, 894, 534, 1062), fill=hex_to_rgb(p["highlight"]))
    d.line((404, 978, 496, 978), fill=(233, 251, 255), width=16)
    d.line((450, 932, 450, 1024), fill=(233, 251, 255), width=16)
    d.ellipse((324, 852, 576, 1104), outline=hex_to_rgb(p["accent"]), width=10)

    d.text((194, 1310), "BUILDINGS  STORAGE  RENEWABLES  CARBON", fill=hex_to_rgb(p["highlight"]))
    d.line((152, 1302, 744, 1302), fill=hex_to_rgb(p["ink"]), width=3)
    image = Image.alpha_composite(image.convert("RGBA"), scanline_overlay((WIDTH, HEIGHT), p["highlight"], spacing=4, alpha=18))
    image = Image.alpha_composite(image, film_grain((WIDTH, HEIGHT), 18, 31, hex_to_rgb(p["ink"])))
    return image.convert("RGB")


def draw_proof_poster(palette: dict | None = None) -> Image.Image:
    p = palette or STYLE_BY_KIND["proof"]["palette"]
    image = Image.new("RGBA", (WIDTH, HEIGHT), hex_to_rgb(p["paper"]) + (255,))
    d = ImageDraw.Draw(image)

    for y in range(0, HEIGHT, 16):
        for x in range((y // 16) % 2 * 8, WIDTH, 16):
            d.ellipse((x, y, x + 4, y + 4), fill=hex_to_rgb(p["black"]))
    image = Image.blend(image.convert("RGB"), Image.new("RGB", (WIDTH, HEIGHT), hex_to_rgb(p["cream"])), 0.72).convert("RGBA")
    d = ImageDraw.Draw(image)

    d.polygon([(90, 180), (268, 126), (230, 286)], fill=hex_to_rgb(p["red"]))
    d.polygon([(682, 102), (836, 194), (714, 284)], fill=hex_to_rgb(p["black"]))
    torn_paper_block(image, (176, 386, 504, 904), p["cream"], p["black"], 41, angle=-1.6)
    for y in [454, 510, 600, 654, 740, 794]:
        d.line((214, y, 460 if y != 794 else 382, y), fill=hex_to_rgb(p["black"]), width=6)

    d.rounded_rectangle((550, 306, 722, 560), radius=6, fill=hex_to_rgb(p["red"]))
    d.rounded_rectangle((568, 324, 704, 542), radius=4, fill=hex_to_rgb(p["cream"]))
    d.line((586, 368, 684, 368), fill=hex_to_rgb(p["black"]), width=7)
    d.line((586, 420, 658, 420), fill=hex_to_rgb(p["black"]), width=5)

    d.polygon([(508, 648), (724, 618), (686, 838), (482, 868)], fill=hex_to_rgb(p["black"]))
    d.line((548, 704, 664, 704), fill=hex_to_rgb(p["cream"]), width=10)
    d.line((544, 754, 626, 754), fill=hex_to_rgb(p["cream"]), width=8)

    torn_paper_block(image, (194, 984, 692, 1304), p["cream"], p["black"], 53, angle=0.8)
    for y in [1050, 1102, 1172, 1224]:
        d.line((228, y, 636 if y != 1224 else 520, y), fill=hex_to_rgb(p["black"]), width=6)

    star = [
        (722, 860), (760, 832), (768, 780), (812, 808), (864, 792), (848, 842),
        (880, 886), (824, 890), (790, 932), (772, 882),
    ]
    d.polygon(star, fill=hex_to_rgb(p["red"]))
    d.line((676, 960, 704, 988, 758, 932), fill=hex_to_rgb(p["cream"]), width=18)
    d.line((138, 1368, 606, 1368), fill=hex_to_rgb(p["black"]), width=6)
    image = Image.alpha_composite(image, rough_paper_overlay((WIDTH, HEIGHT), 67))
    image = Image.alpha_composite(image, film_grain((WIDTH, HEIGHT), 20, 71, hex_to_rgb(p["paper"])))
    return image.convert("RGB")


def draw_portfolio_sculpture(palette: dict | None = None) -> Image.Image:
    p = palette or STYLE_BY_KIND["portfolio"]["palette"]
    image = Image.new("RGB", (WIDTH, HEIGHT), hex_to_rgb(p["bg"]))
    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)

    masses = [
        [(78, 468), (196, 344), (390, 326), (642, 388), (792, 350), (836, 456), (620, 648), (350, 782), (82, 652)],
        [(118, 1002), (252, 906), (486, 918), (742, 992), (834, 970), (832, 1092), (612, 1248), (308, 1344), (92, 1264)],
    ]
    for pts in masses:
        sd.polygon([(x + 18, y + 26) for x, y in pts], fill=hex_to_rgb(p["shadow"]) + (120,))
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    image = Image.alpha_composite(image.convert("RGBA"), shadow).convert("RGB")
    d = ImageDraw.Draw(image)

    for pts, fill in [
        (masses[0], p["surface"]),
        ([(110, 514), (222, 426), (410, 414), (620, 470), (742, 444), (754, 526), (596, 646), (362, 730), (146, 660)], p["surface2"]),
        (masses[1], p["surface"]),
        ([(152, 1044), (280, 972), (488, 992), (694, 1052), (768, 1030), (768, 1110), (604, 1220), (336, 1290), (144, 1230)], p["surface2"]),
    ]:
        d.polygon(pts, fill=hex_to_rgb(fill))

    for offset in [0, 28, 58, 92]:
        d.arc((124 + offset, 344 + offset, 790 - offset, 720 - offset), start=186, end=336, fill=hex_to_rgb(p["ink"]), width=3)
        d.arc((124 + offset, 916 + offset, 790 - offset, 1312 - offset), start=194, end=346, fill=hex_to_rgb(p["ink"]), width=3)

    nodes = [(208, 470), (420, 398), (694, 452), (246, 1072), (488, 1002), (724, 1080)]
    for x, y in nodes:
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=hex_to_rgb(p["ink"]))
    for a, b in [((208, 470), (420, 398)), ((420, 398), (694, 452)), ((246, 1072), (488, 1002)), ((488, 1002), (724, 1080))]:
        d.line((a[0], a[1], b[0], b[1]), fill=hex_to_rgb(p["ink"]), width=10)

    cards = [
        (180, 430, 256, 488),
        (580, 498, 678, 574),
        (292, 1090, 392, 1174),
    ]
    for x1, y1, x2, y2 in cards:
        d.rounded_rectangle((x1, y1, x2, y2), radius=12, fill=(255, 255, 255))
        d.line((x1 + 18, y1 + 44, x2 - 18, y1 + 44), fill=hex_to_rgb(p["ink"]), width=5)
    d.arc((552, 1088, 702, 1228), start=180, end=360, fill=hex_to_rgb(p["ink"]), width=10)
    d.line((626, 1088, 626, 1218), fill=hex_to_rgb(p["ink"]), width=10)
    d.ellipse((614, 1150, 638, 1174), fill=hex_to_rgb(p["highlight"]))
    image = soft_light_overlay(image, vertical_gradient((WIDTH, HEIGHT), "#ffffff", p["surface"]), 0.18)
    image = Image.alpha_composite(image.convert("RGBA"), film_grain((WIDTH, HEIGHT), 14, 89, hex_to_rgb(p["surface"]))).convert("RGB")
    image = image.filter(ImageFilter.GaussianBlur(0.35))
    return image


def draw_generic(palette: dict | None = None) -> Image.Image:
    p = palette or STYLE_BY_KIND["generic"]["palette"]
    image = Image.new("RGB", (WIDTH, HEIGHT), hex_to_rgb(p["bg"]))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((80, 80, 820, 1520), radius=34, fill=(255, 255, 255))
    d.ellipse((150, 210, 430, 490), fill=hex_to_rgb(p["accent"]))
    d.rectangle((480, 240, 710, 300), fill=hex_to_rgb(p["accent"]))
    d.line((160, 660, 760, 920), fill=hex_to_rgb(p["ink"]), width=22)
    d.rectangle((170, 1080, 760, 1280), fill=(247, 243, 237))
    return image


def build_bitmap(profile: dict) -> Image.Image:
    renderer = profile.get("renderer") or profile.get("kind") or "generic"
    palette = profile.get("palette")
    if renderer == "drift":
        return draw_drift_photo(palette)
    if renderer == "control":
        return draw_control_diagram(palette)
    if renderer == "proof":
        return draw_proof_poster(palette)
    if renderer == "portfolio":
        return draw_portfolio_sculpture(palette)
    return draw_generic(palette)


def choose_profile(
    kind: str,
    used_slugs: set[str],
    used_families: set[str],
    used_palette_families: set[str],
    surprise_mode: bool,
) -> dict:
    if not surprise_mode:
        return base_profile_for_kind(kind)

    if kind == "generic":
        pool = []
        for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
            pool.extend(dict(item, kind=library_kind) for item in items)
    else:
        pool = [dict(item, kind=kind) for item in SURPRISE_STYLE_LIBRARY.get(kind, [])]

    available = [
        item
        for item in pool
        if item["slug"] not in used_slugs
        and item.get("family") not in used_families
        and classify_profile_palette_family(item) not in used_palette_families
    ]
    if not available and kind != "generic":
        fallback_pool = []
        for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
            fallback_pool.extend(dict(item, kind=library_kind) for item in items)
        available = [
            item
            for item in fallback_pool
            if item["slug"] not in used_slugs
            and item.get("family") not in used_families
            and classify_profile_palette_family(item) not in used_palette_families
        ]

    if not available:
        available = [
            item
            for item in pool
            if item["slug"] not in used_slugs and classify_profile_palette_family(item) not in used_palette_families
        ]

    if not available:
        fallback_pool = []
        for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
            fallback_pool.extend(dict(item, kind=library_kind) for item in items)
        available = [
            item
            for item in fallback_pool
            if item["slug"] not in used_slugs and classify_profile_palette_family(item) not in used_palette_families
        ]

    if not available:
        available = [item for item in pool if item["slug"] not in used_slugs and item.get("family") not in used_families]

    if not available:
        fallback_pool = []
        for library_kind, items in SURPRISE_STYLE_LIBRARY.items():
            fallback_pool.extend(dict(item, kind=library_kind) for item in items)
        available = [item for item in fallback_pool if item["slug"] not in used_slugs and item.get("family") not in used_families]

    if not available:
        available = pool or [base_profile_for_kind(kind)]

    for item in available:
        item["palette_family"] = classify_profile_palette_family(item)
    available = sorted(available, key=stable_profile_sort_key)
    profile = available[0]
    profile = dict(profile)
    profile["palette_family"] = classify_profile_palette_family(profile)
    used_slugs.add(profile["slug"])
    used_families.add(profile.get("family", profile["slug"]))
    used_palette_families.add(profile["palette_family"])
    return profile


def output_path_for_idea(asset_dir: Path, brand_slug: str, title: str, raw_value: str) -> Path:
    if raw_value:
        value = raw_value.strip()
        if "://" not in value and not Path(value).is_absolute():
            candidate = (asset_dir.parent / Path(value)).resolve()
            if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                return candidate
    return asset_dir / f"{brand_slug}-campaign-{slugify(title)}.png"


def generate(
    data_path: Path, overwrite: bool, manifest_only: bool
) -> tuple[int, list[Path], int, Path, Path, Path]:
    base_sha256 = hashlib.sha256(data_path.read_bytes()).hexdigest().upper()
    data = json.loads(data_path.read_text(encoding="utf-8"))
    brand = data.get("brand", {})
    brand_name = brand.get("name") or data_path.parent.name
    brand_slug = slugify(brand.get("slug") or brand.get("name") or data_path.parent.name)
    asset_dir = data_path.parent / "slide-assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    section = data.get("creative_campaign_ideas", {})
    delivery_mode = str(section.get("artwork_delivery_mode") or "").strip().lower()
    if not delivery_mode:
        delivery_mode = "final-raster-required"
        section["artwork_delivery_mode"] = delivery_mode
    generation_backend = str(section.get("illustration_generation_backend") or "").strip().lower()
    if not generation_backend:
        generation_backend = PREMIUM_BACKEND if delivery_mode != "scaffold-allowed" else SCAFFOLD_BACKEND
        section["illustration_generation_backend"] = generation_backend
    allow_scaffold = scaffold_allowed(delivery_mode, generation_backend)
    style_mode = str(section.get("illustration_style_mode") or "").strip().lower()
    surprise_mode = str(section.get("illustration_style_mode") or "").strip().lower() in {
        "surprise",
        "wild",
        "shuffle",
        "random",
    }
    ideas: Iterable[dict] = section.get("ideas") or []
    written: list[Path] = []
    pending = 0
    prompt_manifest: list[dict[str, str]] = []
    used_slugs: set[str] = set()
    used_families: set[str] = set()
    used_palette_families: set[str] = set()

    for idea in ideas:
        title = (idea.get("title") or "").strip()
        if not title:
            continue
        concept = (idea.get("concept") or idea.get("addresses") or "").strip()
        existing_medium = idea.get("illustration_medium") or ""
        existing_style_name = (idea.get("illustration_style_name") or "").strip()
        existing_style_family = (idea.get("illustration_style_family") or "").strip()
        # Do not let a stale generated medium bias the next run's topic choice.
        # Old art metadata is especially dangerous when refreshing failed diversity.
        kind = motif_key(title, concept)
        if surprise_mode:
            profile = choose_profile(
                kind,
                used_slugs,
                used_families,
                used_palette_families,
                surprise_mode=True,
            )
            medium = profile["medium"]
            prompt = build_bitmap_prompt(title, concept, profile)
        else:
            profile = base_profile_for_kind(kind)
            medium = existing_medium or profile["medium"]
            profile["medium"] = medium
            if existing_style_name:
                profile["slug"] = existing_style_name
            if existing_style_family:
                profile["family"] = existing_style_family
            profile["family"] = profile.get("family", kind)
            profile["palette_family"] = classify_profile_palette_family(profile)
            prompt = idea.get("illustration_prompt") or build_bitmap_prompt(title, concept, profile)
            used_slugs.add(profile["slug"])
            used_families.add(profile.get("family", profile["slug"]))
            used_palette_families.add(profile["palette_family"])
        prompt = enforce_prompt_contract(prompt)
        destination = output_path_for_idea(asset_dir, brand_slug, title, idea.get("illustration_url") or "")
        destination.parent.mkdir(parents=True, exist_ok=True)
        palette_candidates = []
        for candidate_index, candidate_profile in enumerate(
            select_palette_candidate_profiles(kind, profile, max_candidates=4),
            start=1,
        ):
            candidate_prompt = enforce_prompt_contract(build_bitmap_prompt(title, concept, candidate_profile))
            palette_candidates.append(
                {
                    "variant_index": candidate_index,
                    "style_slug": candidate_profile["slug"],
                    "style_family": candidate_profile.get("family", candidate_profile["slug"]),
                    "palette_family": candidate_profile.get("palette_family", "warm-earth"),
                    "medium": candidate_profile["medium"],
                    "prompt": candidate_prompt,
                    "prompt_sha256": sha256_text(candidate_prompt),
                    "candidate_filename": f"{brand_slug}-campaign-{slugify(title)}--palette-{candidate_index:02d}.png",
                }
            )
        prompt_manifest.append(
            {
                "sequence": len(prompt_manifest) + 1,
                "title": title,
                "kind": kind,
                "style_slug": profile["slug"],
                "style_family": profile.get("family", profile["slug"]),
                "palette_family": profile.get("palette_family", "warm-earth"),
                "medium": medium,
                "delivery_target": "true-raster-artwork",
                "generation_backend": generation_backend,
                "generator_role": "placeholder-scaffold" if allow_scaffold else "prompt-only-premium-default",
                "expected_asset_path": relative_asset_path(asset_dir, destination),
                "expected_filename": destination.name,
                "prompt": prompt,
                "prompt_sha256": sha256_text(prompt),
                "palette_candidates": palette_candidates,
            }
        )
        idea["illustration_url"] = relative_asset_path(asset_dir, destination)
        idea["illustration_medium"] = medium
        idea["illustration_prompt"] = prompt
        idea["illustration_style_name"] = profile["slug"]
        idea["illustration_style_family"] = profile.get("family", profile["slug"])
        idea["illustration_palette_family"] = profile.get("palette_family", "warm-earth")
        idea["illustration_delivery_target"] = "true-raster-artwork"
        idea["illustration_generation_backend"] = generation_backend

        existing_asset_role = str(idea.get("illustration_asset_role") or "").strip()
        if destination.exists() and not overwrite:
            if existing_asset_role == "final-raster-artwork":
                pass
            elif style_mode == "custom-raster":
                idea["illustration_asset_role"] = "final-raster-artwork"
            elif not existing_asset_role:
                idea["illustration_asset_role"] = "unverified-existing-artwork"
            continue

        if destination.exists() and not allow_scaffold:
            if existing_asset_role == "final-raster-artwork":
                continue
            if style_mode == "custom-raster":
                idea["illustration_asset_role"] = "final-raster-artwork"
                continue
            if not existing_asset_role:
                idea["illustration_asset_role"] = "unverified-existing-artwork"
            continue

        if not destination.exists() and not allow_scaffold:
            idea["illustration_url"] = ""
            idea["illustration_asset_role"] = "pending-final-raster-artwork"
            pending += 1
            continue

        image = build_bitmap(profile)
        image.save(destination, format="PNG", optimize=True)
        idea["illustration_asset_role"] = "placeholder-scaffold"
        written.append(destination)

    manifest_path = asset_dir / f"{brand_slug}-campaign-illustration-prompts.json"
    manifest_payload = {
        "brand_name": brand_name,
        "brand_slug": brand_slug,
        "delivery_mode": delivery_mode,
        "generation_backend": generation_backend,
        "asset_dir": asset_dir.name,
        "ideas": prompt_manifest,
    }
    manifest_payload["generated_at"] = stable_generated_at(manifest_path, manifest_payload)
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    prompt_manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest().upper()
    brief_path = asset_dir / f"{brand_slug}-campaign-art-brief.md"
    brief_path.write_text(
        build_premium_art_brief(
            brand_name=brand_name,
            brand_slug=brand_slug,
            generation_backend=generation_backend,
            delivery_mode=delivery_mode,
            manifest_path=manifest_path,
            prompt_manifest=prompt_manifest,
        ),
        encoding="utf-8",
    )
    section["illustration_prompt_manifest"] = relative_asset_path(asset_dir, manifest_path)
    section["illustration_prompt_brief"] = relative_asset_path(asset_dir, brief_path)
    batch_request_path = asset_dir / f"{brand_slug}-campaign-batch-request.json"
    batch_request_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brand_name": brand_name,
        "brand_slug": brand_slug,
        "delivery_mode": delivery_mode,
        "generation_backend": generation_backend,
        "prompt_manifest_path": relative_asset_path(asset_dir, manifest_path),
        "prompt_manifest_sha256": prompt_manifest_sha256,
        "required_filename_policy": "exact-match",
        "instructions": [
            "Generate one original raster image for each idea.",
            "Use the exact expected filenames when saving the images into a batch folder.",
            "Copy this JSON into that batch folder as campaign-batch-manifest.json before import.",
            "Do not mix images from unrelated brands or old prompt sets in the same batch.",
        ],
        "ideas": [
            {
                "sequence": item["sequence"],
                "title": item["title"],
                "expected_filename": item["expected_filename"],
                "expected_asset_path": item["expected_asset_path"],
                "style_slug": item["style_slug"],
                "style_family": item["style_family"],
                "palette_family": item.get("palette_family", "warm-earth"),
                "medium": item["medium"],
                "prompt_sha256": item["prompt_sha256"],
                "palette_candidates": item.get("palette_candidates", []),
            }
            for item in prompt_manifest
        ],
    }
    batch_request_path.write_text(
        json.dumps(batch_request_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    section["illustration_batch_request"] = relative_asset_path(asset_dir, batch_request_path)
    section_key = "creative_campaign_ideas" if data.get("creative_campaign_ideas") is section else "creative_campaigns"
    patches: list[dict[str, object]] = [
        {
            "path": f"{section_key}.illustration_prompt_manifest",
            "value": relative_asset_path(asset_dir, manifest_path),
        },
        {
            "path": f"{section_key}.illustration_prompt_brief",
            "value": relative_asset_path(asset_dir, brief_path),
        },
        {
            "path": f"{section_key}.illustration_batch_request",
            "value": relative_asset_path(asset_dir, batch_request_path),
        },
    ]
    for index, idea in enumerate(ideas):
        for field in (
            "illustration_url",
            "illustration_medium",
            "illustration_prompt",
            "illustration_style_name",
            "illustration_style_family",
            "illustration_palette_family",
            "illustration_delivery_target",
            "illustration_generation_backend",
            "illustration_asset_role",
        ):
            if field in idea:
                patches.append(
                    {
                        "path": f"{section_key}.ideas[{index}].{field}",
                        "value": idea.get(field),
                    }
                )

    patch_manifest_path = asset_dir / f"{brand_slug}-campaign-report-data-patch.json"
    patch_manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "domain": "campaign-art",
                "data": data_path.name,
                "base_sha256": base_sha256,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "patches": patches,
                "source_manifest": relative_asset_path(asset_dir, manifest_path),
                "prompt_manifest_sha256": prompt_manifest_sha256,
                "batch_request": relative_asset_path(asset_dir, batch_request_path),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    if not manifest_only:
        data_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(written), written, pending, manifest_path, brief_path, batch_request_path, patch_manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate campaign-art prompt manifests and optional scaffold bitmap illustrations."
    )
    parser.add_argument("--data", required=True, help="Path to report-data.json")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing illustration files"
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Write prompt and report-data patch manifests without mutating report-data.json",
    )
    args = parser.parse_args()

    count, written, pending, manifest_path, brief_path, batch_request_path, patch_manifest_path = generate(
        Path(args.data).resolve(), overwrite=args.overwrite, manifest_only=args.manifest_only
    )
    payload = {
        "data": str(Path(args.data).resolve()),
        "generated": count,
        "pending_final_raster": pending,
        "files": [str(path) for path in written],
        "prompt_manifest": str(manifest_path),
        "prompt_brief": str(brief_path),
        "batch_request": str(batch_request_path),
        "report_data_patch_manifest": str(patch_manifest_path),
        "overwrite": bool(args.overwrite),
        "manifest_only": bool(args.manifest_only),
    }
    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
