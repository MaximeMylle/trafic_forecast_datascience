"""
build_presentation.py
=====================
Generates the Dutch PowerPoint presentation for the
Gent → Mechelen Commute Risk Forecast project.

Run with:
    python build_presentation.py
"""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt
from pptx.oxml.ns import qn
from pptx.oxml import parse_xml
from lxml import etree
import copy
from pathlib import Path
import subprocess, sys

# ── auto-install if needed ───────────────────────────────────────────────────
for pkg in ["python-pptx", "lxml"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                              stdout=subprocess.DEVNULL)

# ============================================================================
# COLOUR PALETTE  — deep navy + electric teal + warm orange
# ============================================================================
C_BG        = RGBColor(0x0D, 0x1B, 0x2A)   # #0D1B2A  dark navy (slide background)
C_PANEL     = RGBColor(0x11, 0x2D, 0x4E)   # #112D4E  medium navy (content panels)
C_TEAL      = RGBColor(0x00, 0xC8, 0xA0)   # #00C8A0  electric teal (headings, accents)
C_ORANGE    = RGBColor(0xFF, 0x6B, 0x35)   # #FF6B35  warm orange (highlights)
C_WHITE     = RGBColor(0xFF, 0xFF, 0xFF)   # #FFFFFF  body text
C_MUTED     = RGBColor(0x8B, 0x9D, 0xC3)   # #8B9DC3  muted blue-grey (subtitles)
C_ACCENT2   = RGBColor(0xF7, 0xC5, 0x9F)  # #F7C59F  peach (tag chips)
C_DARK_TEXT = RGBColor(0x0D, 0x1B, 0x2A)  # for text on light badges

SLIDE_W = Inches(13.33)
SLIDE_H = Inches(7.5)


# ============================================================================
# LOW-LEVEL HELPERS
# ============================================================================

def rgb_hex(color: RGBColor) -> str:
    return f"{color[0]:02X}{color[1]:02X}{color[2]:02X}"


def set_bg(slide, color: RGBColor):
    """Fill a slide background with a solid colour."""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, left, top, width, height, fill_color, alpha=None):
    """Add a filled rectangle shape."""
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()   # no border
    return shape


def add_text_box(slide, text, left, top, width, height,
                 font_size=18, bold=False, color=C_WHITE,
                 align=PP_ALIGN.LEFT, italic=False, wrap=True):
    """Add a text box and return the text frame."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = "Calibri"
    return tf


def add_image(slide, path, left, top, width, height=None):
    """Add an image; height=None keeps aspect ratio."""
    if height:
        slide.shapes.add_picture(str(path), left, top, width, height)
    else:
        slide.shapes.add_picture(str(path), left, top, width)


def add_divider(slide, top, color=C_TEAL, thickness=Pt(2)):
    """Thin horizontal rule."""
    shape = slide.shapes.add_shape(1,
        Inches(0.4), top, Inches(12.5), int(thickness))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def heading(slide, text, top=Inches(0.28), font_size=30):
    """Standard slide heading in teal."""
    add_text_box(slide, text,
                 Inches(0.45), top, Inches(12.4), Inches(0.65),
                 font_size=font_size, bold=True, color=C_TEAL)
    add_divider(slide, top + Inches(0.62))


def sub_label(slide, text, left, top, width=Inches(3), font_size=11):
    """Small teal label / category tag."""
    add_text_box(slide, text.upper(), left, top, width, Inches(0.3),
                 font_size=font_size, bold=True, color=C_TEAL)


def bullet_tf(slide, items, left, top, width, height,
              font_size=15, color=C_WHITE, bullet_char="›"):
    """Multi-line bullet list."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.add_paragraph() if i > 0 else tf.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = f"{bullet_char}  {item}"
        run.font.size = Pt(font_size)
        run.font.color.rgb = color
        run.font.name = "Calibri"
        p.space_before = Pt(4)
    return tf


def tag_box(slide, text, left, top, width=Inches(2.2), height=Inches(0.38),
            bg=C_ORANGE, text_color=C_WHITE, font_size=13):
    """Coloured tag / badge."""
    add_rect(slide, left, top, width, height, bg)
    add_text_box(slide, text, left, top, width, height,
                 font_size=font_size, bold=True, color=text_color,
                 align=PP_ALIGN.CENTER)


def panel_box(slide, left, top, width, height):
    """Semi-dark panel background."""
    add_rect(slide, left, top, width, height, C_PANEL)


# ============================================================================
# SLIDE BUILDERS
# ============================================================================

def slide_title(prs):
    """Slide 1 — Titel"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    set_bg(slide, C_BG)

    # big diagonal accent bar top-right
    add_rect(slide, Inches(9.5), Inches(0), Inches(4), Inches(7.5), C_PANEL)
    # teal stripe
    add_rect(slide, Inches(9.3), Inches(0), Inches(0.12), Inches(7.5), C_TEAL)

    # orange dot accent
    add_rect(slide, Inches(0.45), Inches(1.0), Inches(0.25), Inches(0.25), C_ORANGE)

    # main title
    add_text_box(slide,
                 "Gent → Mechelen",
                 Inches(0.45), Inches(1.4), Inches(8.8), Inches(1.0),
                 font_size=48, bold=True, color=C_WHITE)
    add_text_box(slide,
                 "Slimmer Pendelen met Machine Learning",
                 Inches(0.45), Inches(2.35), Inches(8.8), Inches(0.7),
                 font_size=26, bold=False, color=C_TEAL)

    # divider
    add_rect(slide, Inches(0.45), Inches(3.1), Inches(5.5), Inches(0.05), C_ORANGE)

    # sub-info
    add_text_box(slide,
                 "Auto · Trein · Thuiswerken — welke keuze is slim vandaag?",
                 Inches(0.45), Inches(3.25), Inches(8.5), Inches(0.5),
                 font_size=16, color=C_MUTED)

    # right panel content
    add_text_box(slide, "TEAM", Inches(9.65), Inches(1.2), Inches(3.4), Inches(0.4),
                 font_size=12, bold=True, color=C_TEAL)
    team = ["Laure", "Jack", "Maxime", "Marc"]
    for i, name in enumerate(team):
        add_text_box(slide, name,
                     Inches(9.65), Inches(1.65 + i*0.42), Inches(3.4), Inches(0.4),
                     font_size=18, bold=True, color=C_WHITE)

    add_text_box(slide, "DATUM", Inches(9.65), Inches(3.7), Inches(3.4), Inches(0.4),
                 font_size=12, bold=True, color=C_TEAL)
    add_text_box(slide, "23 juni 2026", Inches(9.65), Inches(4.1), Inches(3.4), Inches(0.4),
                 font_size=18, bold=True, color=C_WHITE)
    add_text_box(slide, "Syntra Mechelen", Inches(9.65), Inches(4.5), Inches(3.4), Inches(0.4),
                 font_size=14, color=C_MUTED)


def slide_doel(prs):
    """Slide 2 — Projectdoel"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Wat willen we bereiken?")

    # Big question
    add_text_box(slide,
                 "Elke ochtend één vraag beantwoorden:",
                 Inches(0.45), Inches(1.2), Inches(12), Inches(0.5),
                 font_size=18, color=C_MUTED)
    add_text_box(slide,
                 '"Hoe kom ik vandaag het best naar Mechelen?"',
                 Inches(0.45), Inches(1.65), Inches(12), Inches(0.75),
                 font_size=26, bold=True, color=C_WHITE)

    # 3 option boxes
    opts = [
        ("🚗  AUTO", "E17 → R1 ring → E19\nvia Antwerpen (~75 km)", C_ORANGE),
        ("🚆  TREIN", "Gent-Sint-Pieters → Mechelen\n~58 min, 1 overstap", C_TEAL),
        ("🏠  THUISWERKEN", "Wanneer geen enkele modus\nbetrouwbaar genoeg is", C_PANEL),
    ]
    for i, (title, body, color) in enumerate(opts):
        left = Inches(0.45 + i * 4.25)
        panel_box(slide, left, Inches(2.65), Inches(3.9), Inches(3.5))
        add_rect(slide, left, Inches(2.65), Inches(3.9), Inches(0.06), color)
        add_text_box(slide, title,
                     left + Inches(0.2), Inches(2.8), Inches(3.5), Inches(0.5),
                     font_size=18, bold=True, color=color)
        add_text_box(slide, body,
                     left + Inches(0.2), Inches(3.35), Inches(3.5), Inches(0.9),
                     font_size=14, color=C_WHITE)

    # Data scope note
    add_rect(slide, Inches(0.45), Inches(6.35), Inches(12.4), Inches(0.75), C_PANEL)
    add_text_box(slide,
                 "📅  Scope: Belgische werkdagen van januari 2021 tot heden  ·  "
                 "Data start in 2021 om COVID-lockdown (2020) te vermijden",
                 Inches(0.6), Inches(6.45), Inches(12.1), Inches(0.55),
                 font_size=13, color=C_MUTED)


def slide_team(prs):
    """Slide 3 — Team & Aanpak"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Team & Taakverdeling")

    members = [
        ("LAURE", "Verkeersdata", "Vlaams Verkeercentrum\n(reistijd E17→R1→E19)", C_ORANGE),
        ("JACK",  "Treindata",    "Infrabel punctualiteits-\ngeschiedenis 2021–2026", C_TEAL),
        ("MAXIME","Weerdata",     "Open-Meteo Archive API\n(uurlijks, 2021–heden)", RGBColor(0xA0, 0x60, 0xFF)),
        ("MARC",  "Coördinatie",  "Mockup project + pipeline\nstructuur & opzet", RGBColor(0x00, 0x99, 0xFF)),
    ]
    for i, (name, role, detail, color) in enumerate(members):
        left = Inches(0.45 + i * 3.2)
        panel_box(slide, left, Inches(1.3), Inches(3.0), Inches(4.2))
        add_rect(slide, left, Inches(1.3), Inches(3.0), Inches(0.08), color)
        # avatar circle accent
        add_rect(slide, left + Inches(0.1), Inches(1.5), Inches(0.35), Inches(0.35), color)
        add_text_box(slide, name, left + Inches(0.2), Inches(1.55), Inches(2.7), Inches(0.5),
                     font_size=20, bold=True, color=C_WHITE)
        add_text_box(slide, role, left + Inches(0.2), Inches(2.05), Inches(2.7), Inches(0.4),
                     font_size=14, bold=True, color=color)
        add_text_box(slide, detail, left + Inches(0.2), Inches(2.5), Inches(2.7), Inches(0.9),
                     font_size=12, color=C_MUTED)

    # Timeline row
    add_text_box(slide, "TIJDLIJN", Inches(0.45), Inches(5.75), Inches(12), Inches(0.35),
                 font_size=11, bold=True, color=C_TEAL)
    dates = [
        ("02/06", "Taakver-\ndeling"),
        ("09/06", "Teams-\nvergadering"),
        ("16/06", "Alignering +\npresentatie"),
        ("23/06", "Presentatie\nSyntra"),
    ]
    for i, (d, label) in enumerate(dates):
        lx = Inches(1.0 + i * 3.0)
        add_rect(slide, lx, Inches(6.15), Inches(0.15), Inches(0.15), C_ORANGE)
        add_text_box(slide, d,   lx + Inches(0.25), Inches(6.08), Inches(1.5), Inches(0.3),
                     font_size=13, bold=True, color=C_ORANGE)
        add_text_box(slide, label, lx + Inches(0.25), Inches(6.4), Inches(1.5), Inches(0.5),
                     font_size=11, color=C_MUTED)
    # timeline line
    add_rect(slide, Inches(0.9), Inches(6.22), Inches(11.5), Inches(0.04), C_PANEL)


def slide_databronnen(prs):
    """Slide 4 — Databronnen (overzicht)"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "6 Databronnen — Overzicht")

    sources = [
        ("#1", "Open-Meteo\nArchief API",    "Weerdata uurlijks\n2021 → heden",           "Gratis · geen API-sleutel", C_TEAL),
        ("#2", "holidays\n(Python pkg)",     "Belgische feestdagen\n2021 – 2028",          "Ingebouwde dataset",        C_TEAL),
        ("#3", "iRail API",                  "NMBS-verbindingen\n(schema, fallback)",      "Gratis · open source",      C_ORANGE),
        ("#4", "Infrabel",                   "Echte treinpunctualiteit\n48 maanden CSV",   "data.gov.be",               C_ORANGE),
        ("#5", "OSRM",                       "Vrije doorstroomtijd\nauto (referentie)",    "OpenStreetMap API",         RGBColor(0xA0,0x60,0xFF)),
        ("#6", "Vlaams\nVerkeercentrum",     "Gemeten reistijden\nE17 → R1 → E19",        "indicatoren.verkeers-\ncentrum.be", RGBColor(0x00,0x99,0xFF)),
    ]

    for i, (num, name, desc, url, color) in enumerate(sources):
        col = i % 3
        row = i // 3
        left = Inches(0.45 + col * 4.25)
        top  = Inches(1.25 + row * 2.85)
        panel_box(slide, left, top, Inches(4.0), Inches(2.55))
        add_rect(slide, left, top, Inches(0.55), Inches(2.55), color)
        add_text_box(slide, num, left + Inches(0.07), top + Inches(0.1),
                     Inches(0.4), Inches(0.3), font_size=13, bold=True, color=C_WHITE)
        add_text_box(slide, name,
                     left + Inches(0.65), top + Inches(0.1), Inches(3.2), Inches(0.7),
                     font_size=15, bold=True, color=C_WHITE)
        add_text_box(slide, desc,
                     left + Inches(0.65), top + Inches(0.85), Inches(3.2), Inches(0.8),
                     font_size=12, color=C_MUTED)
        add_text_box(slide, url,
                     left + Inches(0.65), top + Inches(1.8), Inches(3.2), Inches(0.55),
                     font_size=10, color=color, italic=True)


def slide_weer(prs, img_dir):
    """Slide 5 — Weerdata"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Databron 1: Weerdata — Open-Meteo")

    # left: explanation
    panel_box(slide, Inches(0.45), Inches(1.2), Inches(5.0), Inches(5.8))
    items = [
        "Gratis API, geen registratie nodig",
        "Uurlijkse data terug tot 1940",
        "Locatie: Mechelen (aankomststad)",
        "Venster: 06:00–09:00 (pendeltijd)",
        "Samengevat per dag:",
    ]
    bullet_tf(slide, items, Inches(0.65), Inches(1.4), Inches(4.6), Inches(2.6),
              font_size=14)
    vars_ = [
        "rain_total / rain_peak  (neerslag)",
        "wind_peak / wind_mean   (wind)",
        "temp_min / temp_mean    (temperatuur)",
        "humidity_max            (mist-proxy)",
        "snow_total              (sneeuwval)",
    ]
    for j, v in enumerate(vars_):
        add_text_box(slide, f"  {v}",
                     Inches(0.75), Inches(3.85 + j*0.38), Inches(4.6), Inches(0.4),
                     font_size=12, color=C_ACCENT2)

    # insight box
    add_rect(slide, Inches(0.45), Inches(6.3), Inches(5.0), Inches(0.75), C_ORANGE)
    add_text_box(slide,
                 "💡  Winter & herfst = meeste regen & vorst tijdens pendel",
                 Inches(0.55), Inches(6.4), Inches(4.8), Inches(0.55),
                 font_size=12, bold=True, color=C_WHITE)

    # right: weather overview plot
    p = img_dir / "plot_weather_overview.png"
    if p.exists():
        add_image(slide, p, Inches(5.65), Inches(1.2), Inches(7.4), Inches(5.8))


def slide_pendel_weer(prs, img_dir):
    """Slide 6 — Weerpatroon per weekdag"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Weer tijdens het Pendelvenster (06:00–09:00)")

    p = img_dir / "plot_commute_window_weather.png"
    if p.exists():
        add_image(slide, p, Inches(0.45), Inches(1.2), Inches(8.0), Inches(5.4))

    # Insight cards on the right
    panel_box(slide, Inches(8.7), Inches(1.2), Inches(4.3), Inches(2.4))
    add_text_box(slide, "INZICHT 1",
                 Inches(8.9), Inches(1.3), Inches(4.0), Inches(0.35),
                 font_size=11, bold=True, color=C_TEAL)
    add_text_box(slide,
                 "Weekdag heeft GEEN invloed op het weer — maandag is niet natter dan vrijdag.",
                 Inches(8.9), Inches(1.65), Inches(4.0), Inches(0.9),
                 font_size=13, color=C_WHITE)

    panel_box(slide, Inches(8.7), Inches(3.75), Inches(4.3), Inches(2.4))
    add_text_box(slide, "INZICHT 2",
                 Inches(8.9), Inches(3.85), Inches(4.0), Inches(0.35),
                 font_size=11, bold=True, color=C_ORANGE)
    add_text_box(slide,
                 "Weekdag-verkeerspatronen zijn 100% mensengedrag — niet het weer.",
                 Inches(8.9), Inches(4.2), Inches(4.0), Inches(0.9),
                 font_size=13, color=C_WHITE)

    p2 = img_dir / "plot_weather_by_weekday.png"
    if p2.exists():
        add_image(slide, p2, Inches(8.7), Inches(6.2), Inches(4.3), Inches(1.1))


def slide_kalender(prs, img_dir):
    """Slide 7 — Belgische Werkdagenkalender"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Databron 2: Belgische Werkdagenkalender")

    # left: info
    panel_box(slide, Inches(0.45), Inches(1.2), Inches(5.3), Inches(5.8))
    add_text_box(slide, "holidays Python Package",
                 Inches(0.65), Inches(1.35), Inches(5.0), Inches(0.4),
                 font_size=15, bold=True, color=C_TEAL)
    items = [
        "2 021 – 2028 (ook toekomst voor forecasts)",
        "is_workday: ma–vr EN geen feestdag",
        "is_school_holiday: juli & augustus",
        "Seizoen: meteorologisch (DJF/MAM/JJA/SON)",
    ]
    bullet_tf(slide, items, Inches(0.65), Inches(1.85), Inches(4.9), Inches(2.0),
              font_size=14)

    add_text_box(slide, "Waarom filteren?",
                 Inches(0.65), Inches(3.95), Inches(5.0), Inches(0.4),
                 font_size=14, bold=True, color=C_ORANGE)
    add_text_box(slide,
                 "Weekend & feestdagen hebben volledig andere verkeers- "
                 "en treinpatronen. Ze worden vóór modellering verwijderd.",
                 Inches(0.65), Inches(4.35), Inches(4.9), Inches(0.9),
                 font_size=13, color=C_MUTED)

    add_rect(slide, Inches(0.45), Inches(6.3), Inches(5.3), Inches(0.75), C_TEAL)
    add_text_box(slide,
                 "💡  Mei & november hebben de meeste feestdagen → lichtere pendel",
                 Inches(0.55), Inches(6.4), Inches(5.1), Inches(0.55),
                 font_size=12, bold=True, color=C_DARK_TEXT)

    p = img_dir / "plot_calendar_overview.png"
    if p.exists():
        add_image(slide, p, Inches(5.95), Inches(1.2), Inches(7.0), Inches(5.8))


def slide_infrabel(prs, img_dir):
    """Slide 8 — Treindata (Infrabel)"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Databron 4: Echte Treindata — Infrabel")

    # Left column
    panel_box(slide, Inches(0.45), Inches(1.2), Inches(5.5), Inches(5.8))
    add_text_box(slide, "Waarom Infrabel en niet iRail?",
                 Inches(0.65), Inches(1.3), Inches(5.2), Inches(0.4),
                 font_size=14, bold=True, color=C_ORANGE)
    add_text_box(slide,
                 "iRail = real-time/toekomst — geen meerjarige vertragingshistorie.\n"
                 "Infrabel publiceert de échte aankomst- en vertrektijden per stop, per trein, elke dag.",
                 Inches(0.65), Inches(1.75), Inches(5.2), Inches(1.0),
                 font_size=13, color=C_MUTED)

    items = [
        "48 maanden CSV (jan 2021 – apr 2026)",
        "Filter: vertrekken uit Gent-Sint-Pieters 06–09h",
        "Join: aankomst in Mechelen op zelfde trein",
        "Dagelijks geaggregeerd (mediaan per dag)",
    ]
    bullet_tf(slide, items, Inches(0.65), Inches(2.85), Inches(5.2), Inches(2.0),
              font_size=13)

    add_text_box(slide, "Kolommen per dag:",
                 Inches(0.65), Inches(4.95), Inches(5.2), Inches(0.35),
                 font_size=12, bold=True, color=C_TEAL)
    cols = ["train_planned_journey_min", "train_actual_journey_min",
            "train_delay_arr_median_s", "train_on_time_pct", "train_cancelled_pct"]
    for j, c in enumerate(cols):
        add_text_box(slide, f"  › {c}",
                     Inches(0.75), Inches(5.3 + j*0.33), Inches(5.0), Inches(0.35),
                     font_size=11, color=C_ACCENT2)

    # Right: infrabel overview plot
    p = img_dir / "plot_infrabel_overview.png"
    if p.exists():
        add_image(slide, p, Inches(6.1), Inches(1.2), Inches(6.9), Inches(5.8))


def slide_infrabel_weekdag(prs, img_dir):
    """Slide 9 — Treinpunctualiteit per weekdag"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Treinpunctualiteit per Weekdag")

    p = img_dir / "plot_infrabel_by_weekday.png"
    if p.exists():
        add_image(slide, p, Inches(0.45), Inches(1.2), Inches(8.0), Inches(5.6))

    # insights right
    panel_box(slide, Inches(8.7), Inches(1.2), Inches(4.3), Inches(5.6))
    add_text_box(slide, "TREIN INZICHTEN", Inches(8.9), Inches(1.35),
                 Inches(4.0), Inches(0.35), font_size=11, bold=True, color=C_TEAL)
    insights = [
        "Dinsdag & donderdag = hoogste vertragingen",
        "Beide modi (auto & trein) zijn tegelijk belast op piekmomenten",
        "On-time rate varieert sterk per maand (winter = slechter)",
        "Annuleringspercentage laag maar merkbaar bij extreme weer",
    ]
    bullet_tf(slide, insights, Inches(8.9), Inches(1.75), Inches(4.0), Inches(4.5),
              font_size=13, bullet_char="▸")


def slide_auto(prs, img_dir):
    """Slide 10 — Autorijdata"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Databron 5+6: Autorijdata — OSRM + Vlaams Verkeercentrum")

    # top: route explanation
    panel_box(slide, Inches(0.45), Inches(1.2), Inches(12.4), Inches(1.0))
    add_text_box(slide,
                 "Route: E17/A14 (Gent → Antwerpen)  ›  R1 buitenring  ›  E19/A1 (Antwerpen → Mechelen)  ·  ~75 km",
                 Inches(0.6), Inches(1.35), Inches(12.0), Inches(0.55),
                 font_size=14, bold=True, color=C_WHITE)

    # left: OSRM vs VC
    panel_box(slide, Inches(0.45), Inches(2.4), Inches(3.8), Inches(4.3))
    add_text_box(slide, "OSRM (referentie)",
                 Inches(0.65), Inches(2.55), Inches(3.5), Inches(0.4),
                 font_size=14, bold=True, color=RGBColor(0xA0,0x60,0xFF))
    items_osrm = [
        "Vrije doorstroom: ~50 min",
        "Vermenigvuldigd met weekdag- en weerfactor",
        "Enkel gebruikt als historische referentie",
    ]
    bullet_tf(slide, items_osrm, Inches(0.65), Inches(3.0), Inches(3.5), Inches(1.5),
              font_size=12)

    add_text_box(slide, "Vlaams Verkeercentrum (primair)",
                 Inches(0.65), Inches(4.6), Inches(3.5), Inches(0.4),
                 font_size=14, bold=True, color=C_ORANGE)
    items_vc = [
        "Echte gemeten reistijden per 5-min slot",
        "Maandgemiddelde 06:00–09:55",
        "Juli & augustus ontbreken (schoolvakantie)",
    ]
    bullet_tf(slide, items_vc, Inches(0.65), Inches(5.05), Inches(3.5), Inches(1.4),
              font_size=12)

    # right: plot
    p = img_dir / "plot_car_travel_model.png"
    if p.exists():
        add_image(slide, p, Inches(4.4), Inches(2.35), Inches(8.6), Inches(4.4))

    # bottom note
    add_rect(slide, Inches(0.45), Inches(6.75), Inches(3.8), Inches(0.45), C_ORANGE)
    add_text_box(slide, "car_vc_est_min = primaire voorspeldoel",
                 Inches(0.55), Inches(6.82), Inches(3.6), Inches(0.35),
                 font_size=12, bold=True, color=C_WHITE)


def slide_auto_trein(prs, img_dir):
    """Slide 11 — Auto vs Trein vergelijking"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Auto versus Trein — per Weekdag")

    p = img_dir / "plot_car_vs_train.png"
    if p.exists():
        add_image(slide, p, Inches(0.45), Inches(1.2), Inches(8.5), Inches(5.6))

    # right: weekday factors
    panel_box(slide, Inches(9.1), Inches(1.2), Inches(4.0), Inches(5.6))
    add_text_box(slide, "WEEKDAG FACTORS (E40-corridor)",
                 Inches(9.3), Inches(1.35), Inches(3.7), Inches(0.4),
                 font_size=11, bold=True, color=C_TEAL)
    wd = [
        ("Maandag",   "×1.28", "opbouw na weekend"),
        ("Dinsdag",   "×1.35", "DRUKSTE dag"),
        ("Woensdag",  "×1.20", "rustigst"),
        ("Donderdag", "×1.33", "2e drukste"),
        ("Vrijdag",   "×1.15", "lichte ochtend"),
    ]
    for i, (day, factor, note) in enumerate(wd):
        top_i = Inches(1.85 + i * 0.9)
        color = C_ORANGE if "DRUK" in note else (C_TEAL if "rustig" in note else C_WHITE)
        add_text_box(slide, day,   Inches(9.3),  top_i, Inches(1.5), Inches(0.38),
                     font_size=13, bold=True, color=color)
        add_text_box(slide, factor, Inches(10.85), top_i, Inches(0.8), Inches(0.38),
                     font_size=13, bold=True, color=C_ORANGE)
        add_text_box(slide, note,  Inches(11.7),  top_i, Inches(1.2), Inches(0.38),
                     font_size=11, color=C_MUTED)


def slide_heatmap(prs, img_dir):
    """Slide 12 — Weerrisico Heatmap"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Weerrisicoscore per Maand × Weekdag")

    p = img_dir / "plot_weather_risk_heatmap.png"
    if p.exists():
        add_image(slide, p, Inches(0.45), Inches(1.2), Inches(8.0), Inches(5.6))

    panel_box(slide, Inches(8.7), Inches(1.2), Inches(4.3), Inches(5.6))
    add_text_box(slide, "SAMENGESTELDE RISICOSCORE",
                 Inches(8.9), Inches(1.35), Inches(4.0), Inches(0.4),
                 font_size=11, bold=True, color=C_TEAL)

    formula_items = [
        "regen ≥ 2 mm   → +2 punten",
        "wind ≥ 45 km/h → +2 punten",
        "vorst ≤ 0°C    → +1 punt",
        "sneeuw > 0 cm  → +3 punten",
        "vochtig ≥ 97%  → +1 punt",
        "─────────────────────",
        "Totaal: 0–9",
    ]
    bullet_tf(slide, formula_items, Inches(8.9), Inches(1.8), Inches(4.0), Inches(3.5),
              font_size=13, bullet_char=" ")

    add_rect(slide, Inches(8.7), Inches(5.5), Inches(4.3), Inches(0.06), C_ORANGE)
    add_text_box(slide,
                 "Jan–feb en nov–dec = hoogste risico.\n"
                 "Weekdag heeft GEEN systematisch hoger weerrisico.",
                 Inches(8.9), Inches(5.6), Inches(4.0), Inches(0.9),
                 font_size=13, color=C_WHITE)


def slide_pipeline(prs):
    """Slide 13 — Data Pipeline"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Data Pipeline — Van Bron tot Model")

    # flow diagram with arrows
    steps = [
        ("Open-Meteo\nAPI",        C_TEAL),
        ("iRail / Infrabel",       C_ORANGE),
        ("Vlaams VC",               C_ORANGE),
        ("OSRM",                   RGBColor(0xA0,0x60,0xFF)),
        ("holidays\npkg",          RGBColor(0x00,0x99,0xFF)),
    ]
    for i, (label, color) in enumerate(steps):
        left = Inches(0.35 + i * 2.45)
        add_rect(slide, left, Inches(1.35), Inches(2.1), Inches(0.9), color)
        add_text_box(slide, label, left, Inches(1.45), Inches(2.1), Inches(0.75),
                     font_size=12, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)
        if i < len(steps) - 1:
            add_text_box(slide, "→", left + Inches(2.1), Inches(1.5), Inches(0.35), Inches(0.5),
                         font_size=18, bold=True, color=C_MUTED, align=PP_ALIGN.CENTER)

    # arrow down
    add_text_box(slide, "↓  build_combined_df()", Inches(4.5), Inches(2.45), Inches(4.0), Inches(0.5),
                 font_size=16, bold=True, color=C_TEAL, align=PP_ALIGN.CENTER)

    # combined dataset box
    add_rect(slide, Inches(2.5), Inches(3.1), Inches(8.2), Inches(1.0), C_PANEL)
    add_rect(slide, Inches(2.5), Inches(3.1), Inches(8.2), Inches(0.07), C_TEAL)
    add_text_box(slide,
                 "combined_workdays_features.csv  —  1 rij per Belgische werkdag, 2021 → heden",
                 Inches(2.6), Inches(3.2), Inches(8.0), Inches(0.55),
                 font_size=15, bold=True, color=C_WHITE, align=PP_ALIGN.CENTER)

    # features produced
    add_text_box(slide, "AFGELEIDE KOLOMMEN", Inches(0.45), Inches(4.3), Inches(12), Inches(0.35),
                 font_size=11, bold=True, color=C_TEAL)
    feats = [
        ("weather_risk", "0–9 samengestelde risicoscore"),
        ("car_vc_est_min", "VC-basis × weekdag × weerFactor"),
        ("car_est_min", "OSRM × weekdag × weerFactor (ref)"),
        ("car_faster_than_train", "binary target: 1 als auto sneller + 10 min buffer"),
    ]
    for i, (col, desc) in enumerate(feats):
        lx = Inches(0.45 + (i % 2) * 6.3)
        ty = Inches(4.75 + (i // 2) * 0.75)
        panel_box(slide, lx, ty, Inches(5.9), Inches(0.65))
        add_text_box(slide, col, lx + Inches(0.15), ty + Inches(0.05),
                     Inches(2.5), Inches(0.35), font_size=13, bold=True, color=C_ORANGE)
        add_text_box(slide, desc, lx + Inches(2.7), ty + Inches(0.1),
                     Inches(3.0), Inches(0.45), font_size=12, color=C_MUTED)


def slide_ml(prs):
    """Slide 14 — Machine Learning Aanpak"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Machine Learning — Aanpak")

    # 3 model cards
    models = [
        ("Model 1", "Lineaire\nRegressie",
         ["Eenvoudigste model", "Referentielijn", "Interpreteerbare coëfficiënten"],
         "Baseline — wat is de auto-reistijd?", C_MUTED),
        ("Model 2", "Random Forest\nRegressor",
         ["300 beslisbomen", "Niet-lineaire verbanden", "Wisselwerking features"],
         "Verbeterd — exactere reistijdschatting", C_TEAL),
        ("Model 3", "Random Forest\nClassifier",
         ["Binary uitvoer: auto of trein", "class_weight='balanced'", "Geeft ook zekerheids-%"],
         "Beslissing — auto of trein?", C_ORANGE),
    ]
    for i, (num, name, bullets, goal, color) in enumerate(models):
        left = Inches(0.45 + i * 4.25)
        panel_box(slide, left, Inches(1.2), Inches(3.9), Inches(5.9))
        add_rect(slide, left, Inches(1.2), Inches(3.9), Inches(0.07), color)
        add_text_box(slide, num,  left + Inches(0.2), Inches(1.3), Inches(3.5), Inches(0.3),
                     font_size=11, bold=True, color=color)
        add_text_box(slide, name, left + Inches(0.2), Inches(1.6), Inches(3.5), Inches(0.7),
                     font_size=18, bold=True, color=C_WHITE)
        bullet_tf(slide, bullets, left + Inches(0.2), Inches(2.4), Inches(3.5), Inches(1.8),
                  font_size=13)
        add_rect(slide, left + Inches(0.15), Inches(5.3), Inches(3.6), Inches(0.04), color)
        add_text_box(slide, goal, left + Inches(0.2), Inches(5.4), Inches(3.5), Inches(0.6),
                     font_size=12, italic=True, color=color)

    # split info
    add_rect(slide, Inches(0.45), Inches(7.05), Inches(12.4), Inches(0.25), C_PANEL)
    add_text_box(slide,
                 "Train/test split: 80% / 20% chronologisch (geen shuffle) — tijdreeksdata mag de toekomst niet 'zien'",
                 Inches(0.55), Inches(7.08), Inches(12.2), Inches(0.22),
                 font_size=12, color=C_MUTED)


def slide_features(prs):
    """Slide 15 — Features"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Features — Wat het Model Ziet")

    sub_label(slide, "Weer (06–09h venster)", Inches(0.45), Inches(1.25))
    weer_feats = [
        "rain_total   — totale neerslag (mm)",
        "rain_peak    — maximale neerslagintensiteit (mm/u)",
        "wind_peak    — sterkste windstoot (km/h)",
        "wind_mean    — gemiddelde windsnelheid (km/h)",
        "temp_min     — koudste uur (°C)",
        "temp_mean    — gemiddelde temperatuur (°C)",
        "humidity_max — piekluivochtigheid (mistproxy, %)",
        "snow_total   — totale sneeuwval (cm)",
    ]
    bullet_tf(slide, weer_feats, Inches(0.45), Inches(1.6), Inches(5.8), Inches(4.0),
              font_size=13, bullet_char="›")

    sub_label(slide, "Kalender & Context", Inches(6.55), Inches(1.25))
    cal_feats = [
        "weekday_num    — 0=ma … 4=vr",
        "month          — 1–12 (seizoenaliteit)",
        "is_mon         — maandagopbouw",
        "is_tue_thu     — piekmomenten di/do",
        "is_fri         — lichte vrijdagochtend",
        "is_school_holiday — zomer (licht verkeer)",
        "weather_risk   — samengestelde score 0–9",
    ]
    bullet_tf(slide, cal_feats, Inches(6.55), Inches(1.6), Inches(5.8), Inches(3.5),
              font_size=13, bullet_char="›")

    # bottom: key decision
    add_rect(slide, Inches(0.45), Inches(5.85), Inches(12.4), Inches(1.25), C_PANEL)
    add_rect(slide, Inches(0.45), Inches(5.85), Inches(0.08), Inches(1.25), C_ORANGE)
    add_text_box(slide,
                 "Alle 15 features zijn de avond vóór de rit beschikbaar via een weersforecast "
                 "— het model is volledig operationeel in de praktijk.",
                 Inches(0.65), Inches(6.0), Inches(12.0), Inches(0.85),
                 font_size=14, color=C_WHITE)


def slide_evaluatie(prs, img_dir):
    """Slide 16 — Modelresultaten"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Modelresultaten & Evaluatie")

    p = img_dir / "model_evaluation.png"
    if p.exists():
        add_image(slide, p, Inches(0.45), Inches(1.15), Inches(8.5), Inches(6.0))

    # metrics cards right
    panel_box(slide, Inches(9.15), Inches(1.15), Inches(3.9), Inches(2.65))
    add_text_box(slide, "EVALUATIEMAATSTAVEN",
                 Inches(9.35), Inches(1.25), Inches(3.6), Inches(0.35),
                 font_size=11, bold=True, color=C_TEAL)
    metrics = [
        ("MAE",  "Gemiddelde afwijking in minuten"),
        ("RMSE", "Straft grote fouten zwaarder"),
        ("R²",   "1.0 = perfect · 0.0 = geen beter dan gemiddelde"),
        ("5-fold CV", "Betrouwbaardere generalisatie-schatting"),
    ]
    for j, (m, d) in enumerate(metrics):
        add_text_box(slide, m, Inches(9.35), Inches(1.65 + j*0.57), Inches(1.0), Inches(0.4),
                     font_size=12, bold=True, color=C_ORANGE)
        add_text_box(slide, d, Inches(10.45), Inches(1.65 + j*0.57), Inches(2.5), Inches(0.45),
                     font_size=11, color=C_MUTED)

    panel_box(slide, Inches(9.15), Inches(4.0), Inches(3.9), Inches(2.4))
    add_text_box(slide, "BUSINESS VRAGEN",
                 Inches(9.35), Inches(4.1), Inches(3.6), Inches(0.35),
                 font_size=11, bold=True, color=C_TEAL)
    biz = [
        "Hoe vaak juiste modus gekozen?",
        "Risico te laat aankomen om 09:00?",
        "Gem. buffer bij aankomst?",
    ]
    bullet_tf(slide, biz, Inches(9.35), Inches(4.5), Inches(3.6), Inches(1.7),
              font_size=12, bullet_char="▸")


def slide_scenarios(prs, img_dir):
    """Slide 17 — 50 Scenario Voorspellingen"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "50 Scenario Voorspellingen")

    p = img_dir / "scenario_predictions.png"
    if p.exists():
        add_image(slide, p, Inches(0.45), Inches(1.15), Inches(8.8), Inches(6.1))

    # right panel
    panel_box(slide, Inches(9.45), Inches(1.15), Inches(3.6), Inches(6.1))
    add_text_box(slide, "SCENARIO DEKKING",
                 Inches(9.65), Inches(1.3), Inches(3.3), Inches(0.35),
                 font_size=11, bold=True, color=C_TEAL)
    coverage = [
        "Alle weekdagen (ma–vr)",
        "Mooi weer & regen",
        "Zwaar onweer & sneeuw",
        "IJzel (vorst zonder sneeuw)",
        "Schoolvakantie vs. schooltijd",
        "Feestdag (geen pendel)",
        "Vroege zomer, late herfst",
        "Combinaties: ma + zware regen",
    ]
    bullet_tf(slide, coverage, Inches(9.65), Inches(1.7), Inches(3.3), Inches(3.5),
              font_size=12, bullet_char="›")

    add_rect(slide, Inches(9.45), Inches(5.4), Inches(3.6), Inches(0.05), C_ORANGE)

    add_text_box(slide, "THUISWERK-TRIGGER",
                 Inches(9.65), Inches(5.5), Inches(3.3), Inches(0.35),
                 font_size=11, bold=True, color=C_ORANGE)
    add_text_box(slide,
                 "weather_risk ≥ 5\nÉN beide modi > 90 min\n→ Thuiswerken aanbevolen",
                 Inches(9.65), Inches(5.9), Inches(3.3), Inches(1.0),
                 font_size=13, color=C_WHITE)


def slide_inzichten(prs):
    """Slide 18 — Sleutelinzichten"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)
    heading(slide, "Sleutelinzichten")

    insights = [
        (C_ORANGE, "Di & do = slechtste dagen voor autorijden",
         "35% en 33% boven vrije doorstroomtijd — menselijk rijgedrag, niet het weer."),
        (C_TEAL,   "Sneeuw heeft buitensporige impact",
         "+25% reistijd — België heeft beperkte sneeuwruimcapaciteit buiten steden."),
        (C_ORANGE, "Weer is NIET afhankelijk van weekdag",
         "Maandag is niet natter dan vrijdag. Verkeerspatronen = mensengedrag."),
        (RGBColor(0xA0,0x60,0xFF), "Trein is concurrentieel",
         "Op een significant deel werkdagen is de trein sneller dan de auto (zelfs met 10 min buffer)."),
        (RGBColor(0x00,0x99,0xFF), "Januari–februari & nov–december = hoogste risicomaanden",
         "Beide vervoersmodi zijn tegelijk belast bij slechte weersomstandigheden."),
        (C_TEAL,   "Juiste route: E17 → R1 → E19 via Antwerpen",
         "Niet de directe E40. Bevestigd door VC-gegevens die overeenkomen met GPS-aanbevelingen."),
    ]
    cols = 2
    for i, (color, title, detail) in enumerate(insights):
        col = i % cols
        row = i // cols
        left = Inches(0.45 + col * 6.35)
        top  = Inches(1.3 + row * 1.9)
        panel_box(slide, left, top, Inches(6.0), Inches(1.7))
        add_rect(slide, left, top, Inches(0.07), Inches(1.7), color)
        add_text_box(slide, title, left + Inches(0.2), top + Inches(0.1),
                     Inches(5.65), Inches(0.45), font_size=14, bold=True, color=color)
        add_text_box(slide, detail, left + Inches(0.2), top + Inches(0.58),
                     Inches(5.65), Inches(0.9), font_size=12, color=C_MUTED)


def slide_demo(prs):
    """Slide 19 — Live Demo"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)

    # big accent
    add_rect(slide, Inches(0), Inches(0), Inches(13.33), Inches(2.1), C_PANEL)
    add_rect(slide, Inches(0), Inches(2.05), Inches(13.33), Inches(0.08), C_TEAL)

    add_text_box(slide, "LIVE DEMO",
                 Inches(0.45), Inches(0.3), Inches(12.4), Inches(0.6),
                 font_size=16, bold=True, color=C_TEAL)
    add_text_box(slide,
                 "gent_mechelen_commute_risk_forecast.ipynb",
                 Inches(0.45), Inches(0.85), Inches(12.4), Inches(0.8),
                 font_size=34, bold=True, color=C_WHITE)

    steps = [
        ("1", "Snelle Run cel uitvoeren",
         "Laadt gecachede resultaten → toont backtest KPI's & aanbevelingen direct"),
        ("2", "Dag-voorspelling",
         "Geef morgenochtend weersgegevens in → model geeft modus + vertrektijd"),
        ("3", "Risicokalender 2026–2027",
         "Heatmap van 'rode dagen' — ideaal voor langetermijnplanning"),
        ("4", "50 Scenario's bekijken",
         "scenario_predictions.png — alle combinaties van weekdag × weer"),
    ]
    for i, (num, title, detail) in enumerate(steps):
        left = Inches(0.45 + (i % 2) * 6.35)
        top  = Inches(2.35 + (i // 2) * 2.3)
        panel_box(slide, left, top, Inches(6.0), Inches(2.1))
        add_rect(slide, left, top, Inches(0.55), Inches(2.1), C_TEAL)
        add_text_box(slide, num, left + Inches(0.07), top + Inches(0.65),
                     Inches(0.4), Inches(0.6), font_size=22, bold=True, color=C_WHITE,
                     align=PP_ALIGN.CENTER)
        add_text_box(slide, title, left + Inches(0.7), top + Inches(0.15),
                     Inches(5.2), Inches(0.5), font_size=15, bold=True, color=C_WHITE)
        add_text_box(slide, detail, left + Inches(0.7), top + Inches(0.7),
                     Inches(5.2), Inches(1.15), font_size=12, color=C_MUTED)


def slide_conclusie(prs):
    """Slide 20 — Conclusie"""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_bg(slide, C_BG)

    add_rect(slide, Inches(0), Inches(0), Inches(0.12), Inches(7.5), C_TEAL)
    add_rect(slide, Inches(9.5), Inches(0), Inches(3.83), Inches(7.5), C_PANEL)
    add_rect(slide, Inches(9.38), Inches(0), Inches(0.12), Inches(7.5), C_ORANGE)

    add_text_box(slide, "Conclusie", Inches(0.4), Inches(0.5), Inches(9.0), Inches(0.7),
                 font_size=14, bold=True, color=C_TEAL)
    add_text_box(slide,
                 "Van ruwe data\nnaar slimme pendelbeslissing",
                 Inches(0.4), Inches(1.1), Inches(8.8), Inches(1.4),
                 font_size=36, bold=True, color=C_WHITE)
    add_rect(slide, Inches(0.4), Inches(2.6), Inches(5.0), Inches(0.06), C_ORANGE)

    summary = [
        "6 databronnen geïntegreerd in 1 pipeline",
        "1 000+ Belgische werkdagen als trainingsdata",
        "3 ML-modellen getraind & geëvalueerd",
        "50 realistische scenario's gedemonstreerd",
        "Operationeel: geeft vertrekadvies de avond ervoor",
    ]
    bullet_tf(slide, summary, Inches(0.4), Inches(2.85), Inches(8.8), Inches(3.0),
              font_size=16, bullet_char="✓")

    # right panel: vervolgstappen
    add_text_box(slide, "VERVOLGSTAPPEN", Inches(9.65), Inches(1.0), Inches(3.4), Inches(0.4),
                 font_size=12, bold=True, color=C_ORANGE)
    nexts = [
        "Real-time forecast integratie",
        "Push-notificatie 's ochtends",
        "Uitbreiden naar andere trajecten",
        "Live verkeersdata (DATEX II)",
    ]
    bullet_tf(slide, nexts, Inches(9.65), Inches(1.5), Inches(3.4), Inches(3.5),
              font_size=13, bullet_char="→")

    add_text_box(slide, "Bedankt voor jullie aandacht!",
                 Inches(0.4), Inches(6.5), Inches(8.8), Inches(0.6),
                 font_size=18, bold=True, color=C_TEAL)


# ============================================================================
# MAIN
# ============================================================================

def build():
    prs = Presentation()
    prs.slide_width  = SLIDE_W
    prs.slide_height = SLIDE_H

    img_dir = Path("data/processed")

    print("Building slides …")
    slide_title(prs);           print("  1/20 — Titelpagina")
    slide_doel(prs);            print("  2/20 — Projectdoel")
    slide_team(prs);            print("  3/20 — Team & Tijdlijn")
    slide_databronnen(prs);     print("  4/20 — Databronnen overzicht")
    slide_weer(prs, img_dir);   print("  5/20 — Weerdata")
    slide_pendel_weer(prs, img_dir); print("  6/20 — Weerpatroon pendel")
    slide_kalender(prs, img_dir);    print("  7/20 — Kalender")
    slide_infrabel(prs, img_dir);    print("  8/20 — Infrabel treindata")
    slide_infrabel_weekdag(prs, img_dir); print("  9/20 — Trein per weekdag")
    slide_auto(prs, img_dir);   print(" 10/20 — Autodata")
    slide_auto_trein(prs, img_dir);  print(" 11/20 — Auto vs Trein")
    slide_heatmap(prs, img_dir); print(" 12/20 — Weerrisico heatmap")
    slide_pipeline(prs);         print(" 13/20 — Data pipeline")
    slide_ml(prs);               print(" 14/20 — ML aanpak")
    slide_features(prs);         print(" 15/20 — Features")
    slide_evaluatie(prs, img_dir); print(" 16/20 — Modelresultaten")
    slide_scenarios(prs, img_dir); print(" 17/20 — 50 scenarios")
    slide_inzichten(prs);         print(" 18/20 — Sleutelinzichten")
    slide_demo(prs);              print(" 19/20 — Live demo")
    slide_conclusie(prs);         print(" 20/20 — Conclusie")

    out = Path("Gent_Mechelen_Presentatie.pptx")
    prs.save(str(out))
    print(f"\nOpgeslagen: {out.resolve()}")
    return out


if __name__ == "__main__":
    build()
