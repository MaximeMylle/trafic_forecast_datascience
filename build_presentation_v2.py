# -*- coding: utf-8 -*-
"""
build_presentation_v2.py
========================
Rebuilds the Gent→Mechelen deck with (1) a clean editorial / Swiss-minimal style
(white space, serif titles, one navy accent, hairline rules — no cards, emoji or
gradients) and (2) the honest findings from 01_data_exploration_combined_v2.ipynb.

Output: Gent_Mechelen_Presentatie_v2.pptx  (the original file is left untouched).
"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ── palette ──────────────────────────────────────────────────────────────────
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
INK    = RGBColor(0x1A, 0x1A, 0x1A)
GREY   = RGBColor(0x6E, 0x74, 0x7C)
ACCENT = RGBColor(0x1F, 0x3A, 0x5F)   # deep navy — the single accent
AUTO   = RGBColor(0xC0, 0x39, 0x2B)   # car  (matches the notebook plots: red)
TREIN  = RGBColor(0x2E, 0x7D, 0x32)   # train (matches the notebook plots: green)
HAIR   = RGBColor(0xDE, 0xDE, 0xDB)

SERIF = "Georgia"     # titles — gives a human, editorial feel (broadly available)
SANS  = "Arial"       # everything else

FIG = Path("data/processed")
LEFT = Inches(0.92)
CW   = Inches(11.49)   # content width (13.33 - 2*0.92)

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


# ── helpers ──────────────────────────────────────────────────────────────────
_PAGE = [0]   # auto page counter so inserting slides never needs renumbering


def slide():
    _PAGE[0] += 1
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = WHITE
    return s


def textbox(s, l, t, w, h, anchor=MSO_ANCHOR.TOP):
    tb = s.shapes.add_textbox(l, t, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def para(tf, runs, size, color, bold=False, font=SANS, align=PP_ALIGN.LEFT,
         space_after=6, space_before=0, line=1.05, first=False):
    """runs = str or list of (text, color|None, bold|None) tuples for mixed styling."""
    p = tf.paragraphs[0] if first and not tf.paragraphs[0].runs else tf.add_paragraph()
    p.alignment = align
    p.space_after = Pt(space_after)
    p.space_before = Pt(space_before)
    p.line_spacing = line
    if isinstance(runs, str):
        runs = [(runs, color, bold)]
    for text, c, b in runs:
        r = p.add_run(); r.text = text
        r.font.size = Pt(size); r.font.name = font
        r.font.color.rgb = c if c is not None else color
        r.font.bold = b if b is not None else bold
    return p


def rule(s, l, t, w, color=ACCENT, h=Pt(3)):
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
    ln.fill.solid(); ln.fill.fore_color.rgb = color
    ln.line.fill.background()
    ln.shadow.inherit = False
    return ln


def kicker(s, text):
    tf = textbox(s, LEFT, Inches(0.60), CW, Inches(0.3))
    para(tf, text.upper(), 12.5, ACCENT, bold=True, first=True, space_after=0)


def title(s, text, size=33):
    tf = textbox(s, LEFT, Inches(0.92), CW, Inches(0.95))
    para(tf, text, size, INK, font=SERIF, first=True, space_after=0, line=1.0)
    rule(s, LEFT, Inches(1.74), Inches(1.5))


def footer(s):
    tf = textbox(s, LEFT, Inches(7.04), Inches(6), Inches(0.3))
    para(tf, "Gent → Mechelen · slimmer pendelen met ML", 9.5, GREY, first=True, space_after=0)
    tn = textbox(s, Inches(11.4), Inches(7.04), Inches(1.6), Inches(0.3))
    para(tn, str(_PAGE[0]), 9.5, GREY, align=PP_ALIGN.RIGHT, first=True, space_after=0)


def fit_image(s, path, box_l, box_t, box_w, box_h):
    pic = s.shapes.add_picture(str(path), box_l, box_t)
    scale = min(box_w / pic.width, box_h / pic.height)
    pic.width = int(pic.width * scale); pic.height = int(pic.height * scale)
    pic.left = box_l + int((box_w - pic.width) / 2)
    pic.top  = box_t + int((box_h - pic.height) / 2)
    return pic


def takeaway(s, runs, y=2.02, size=16):
    tf = textbox(s, LEFT, Inches(y), CW, Inches(0.7))
    para(tf, runs, size, INK, first=True, line=1.15, space_after=0)


def image_slide(kick, ttl, img, take):
    s = slide(); kicker(s, kick); title(s, ttl)
    takeaway(s, take)
    fit_image(s, FIG / img, LEFT, Inches(2.78), CW, Inches(4.05))
    footer(s)
    return s


# ── 1 · TITLE ────────────────────────────────────────────────────────────────
s = slide()
rule(s, LEFT, Inches(2.35), Inches(2.4))
tf = textbox(s, LEFT, Inches(2.55), Inches(11.0), Inches(1.5))
para(tf, "GENT  →  MECHELEN", 14, ACCENT, bold=True, first=True, space_after=10)
para(tf, "Slimmer pendelen — wat de data écht zegt", 40, INK, font=SERIF, space_after=0, line=1.0)
tf2 = textbox(s, LEFT, Inches(4.45), Inches(11.0), Inches(0.8))
para(tf2, "Auto, trein of thuiswerken? Een eerlijk verhaal over een machine-learning model.",
     17, GREY, first=True, space_after=0)
tf3 = textbox(s, LEFT, Inches(6.35), Inches(11.5), Inches(0.8))
para(tf3, "Laure · Jack · Maxime · Marc", 14, INK, bold=True, first=True, space_after=3)
para(tf3, "Syntra Mechelen — 23 juni 2026", 12.5, GREY)

# ── 2 · DE VRAAG ───────────────────────────────────────────────────────────
s = slide(); kicker(s, "De vraag"); title(s, "Elke ochtend één keuze")
opts = [("AUTO", AUTO, "E17 → R1-ring → E19, via Antwerpen  (~75 km)"),
        ("TREIN", TREIN, "Gent-Sint-Pieters → Mechelen  (~58 min)"),
        ("THUISWERKEN", GREY, "wanneer geen enkele modus betrouwbaar genoeg is")]
y = 2.35
for label, col, desc in opts:
    rule(s, LEFT, Inches(y + 0.04), Inches(0.18), col, h=Pt(20))
    tf = textbox(s, Inches(1.25), Inches(y - 0.12), CW, Inches(0.8))
    para(tf, [(label + "    ", col, True), (desc, INK, False)], 21, INK, font=SERIF, first=True, space_after=0)
    y += 1.15
tf = textbox(s, LEFT, Inches(6.2), CW, Inches(0.6))
para(tf, "Doel: 's avonds beslissen om de volgende ochtend om 09:00 in Mechelen te zijn.",
     14, GREY, first=True, space_after=0)
footer(s)

# ── 3 · DE DATA ────────────────────────────────────────────────────────────
s = slide(); kicker(s, "De data"); title(s, "Zeven bronnen, één rij per werkdag")
sources = [
    ("Weer", "Open-Meteo — uurlijks, 2021 → nu", INK),
    ("Kalender", "holidays — feestdagen & schoolvakanties", INK),
    ("Trein (schema)", "iRail — dienstregeling (fallback)", INK),
    ("Trein (echt)", "Infrabel — punctualiteit 2021–2026", INK),
    ("Auto (referentie)", "OSRM — vrije doorstroomtijd", INK),
    ("Auto (schatting)", "Vlaams Verkeercentrum — maandgemiddelde", INK),
    ("Auto (gemeten) — NIEUW", "AWV-verkeerstellingen 2025 (Marc)", ACCENT),
]
y = 2.25
for i, (lab, desc, col) in enumerate(sources):
    tf = textbox(s, LEFT, Inches(y), Inches(11.0), Inches(0.45))
    para(tf, [(f"{i+1}   ", GREY, False), (lab + "   ", col, True), (desc, GREY, False)],
         15.5, INK, first=True, space_after=0)
    y += 0.50
rule(s, LEFT, Inches(y + 0.05), CW, HAIR, h=Pt(1))
tf = textbox(s, LEFT, Inches(y + 0.18), CW, Inches(0.5))
para(tf, [("build_combined_df()", ACCENT, True),
          ("  →  combined_workdays_features.csv", GREY, False)], 14, GREY, first=True, space_after=0)
footer(s)

# ── 4 · LES 1 — LEAKAGE ──────────────────────────────────────────────────────
s = slide(); kicker(s, "Les 1 — de valkuil"); title(s, "Een R² van 0,99 was geen succes")
tf = textbox(s, LEFT, Inches(2.15), Inches(7.2), Inches(3.2))
para(tf, "Ons eerste auto-doel was een fórmule van dezelfde gegevens:",
     17, INK, first=True, space_after=10, line=1.2)
para(tf, [("car_est_min  =  OSRM × weekdagfactor × weerfactor", ACCENT, True)], 16, ACCENT, space_after=12)
para(tf, "Het model leerde dus gewoon zijn eigen formule terug. Het 'voorspelde' "
         "niets nieuws — dat heet target leakage.", 17, INK, space_after=0, line=1.2)
# big stat block (no card — just type)
tf2 = textbox(s, Inches(8.5), Inches(2.3), Inches(4.0), Inches(2.6))
para(tf2, "R² 0,99", 46, INK, font=SERIF, first=True, space_after=2)
para(tf2, "MAE 0,1 min", 22, GREY, font=SERIF, space_after=10)
para(tf2, "te mooi om waar te zijn", 14, AUTO, bold=True)
footer(s)

# ── 5 · SYNTHETISCH vs GEMETEN (detail) ──────────────────────────────────────
def _col(s, x, w, head, hcol, mono, bullets):
    tf = textbox(s, Inches(x), Inches(2.30), Inches(w), Inches(4.1))
    para(tf, head, 16, hcol, bold=True, first=True, space_after=3)
    para(tf, mono, 13.5, ACCENT, bold=True, space_after=11)
    for b in bullets:
        para(tf, [("›  ", hcol, False), (b, INK, False)], 14, INK, space_after=8, line=1.12)

s = slide(); kicker(s, "Het verschil"); title(s, "Synthetisch vs. gemeten — wat is het?")
rule(s, Inches(6.62), Inches(2.25), Pt(1.3), HAIR, h=Inches(4.15))   # vertical divider
_col(s, 0.92, 5.3, "SYNTHETISCH — onze formule", INK, "car_est_min · car_vc_est_min",
     ["= OSRM-basis × weekdagfactor × weerfactor",
      "Geen meting — een regel die we zélf schreven",
      "Beweegt enkel met weekdag & weer",
      "Gemiddeld ~44 min"])
_col(s, 7.05, 5.3, "GEMETEN — Marc, 2025", ACCENT, "car_real_min",
     ["AWV-lussen tellen échte auto's → volume → reistijd (BPR-model)",
      "Een echte dagmeting, per werkdag",
      "Beweegt met het werkelijke verkeer",
      "Gemiddeld ~96 min"])
rule(s, LEFT, Inches(6.60), CW, HAIR, h=Pt(1))
tf = textbox(s, LEFT, Inches(6.72), CW, Inches(0.5))
para(tf, [("Het verschil:  ", INK, True),
          ("correlatie r ≈ 0,01 (andere dagpatronen)  ·  ~2× hoger niveau  ·  "
           "de formule veroorzaakte de R²-leakage, de meting niet.", GREY, False)],
     13, GREY, first=True, space_after=0)
footer(s)

# ── 6 · LES 2 — ECHTE DATA ───────────────────────────────────────────────────
image_slide("Les 2 — echte data", "Gemeten verkeer vs. onze formule",
            "plot_v2_synth_vs_real.png",
            [("Formule ~44 min   vs   gemeten ~96 min", INK, True),
             ("   ·   correlatie r ≈ 0,01 — twee verschillende werelden.", GREY, False)])

# ── 6 · DE FLIP ──────────────────────────────────────────────────────────────
image_slide("Het gevolg", "De auto wint niet — de trein wel",
            "plot_v2_advice_rederived.png",
            [("Formule: auto bijna élke dag.   ", INK, True),
             ("Gemeten: de trein wint op ~91% van de werkdagen.", TREIN, True)])

# ── 7 · LES 3 — EERLIJK MODEL ────────────────────────────────────────────────
image_slide("Les 3 — eerlijk model", "Met echte data: eerlijk maar bescheiden",
            "plot_v2_honest_metrics.png",
            [("Echt doel → R² ≈ 0 · gemiddelde fout ~9 min op een rit van ~94 min. ", INK, True),
             ("Weer + kalender voorspellen de dagvariatie nauwelijks.", GREY, False)])

# ── 8 · KALENDER ─────────────────────────────────────────────────────────────
image_slide("Wat telt écht", "Kalender vóór weer",
            "plot_v2_holiday_gradient.png",
            [("Feestdag 60 · brugdag 81 · schoolvakantie 90 · gewone dag 96 min. ", INK, True),
             ("'is_public_holiday' is de #1 feature; weer is zwak.", GREY, False)])

# ── 9 · BUFFER ───────────────────────────────────────────────────────────────
image_slide("Betrouwbaarheid", "Hoeveel buffer is realistisch?",
            "plot_v2_buffer.png",
            [("10 min ≈ 90% op tijd voor de auto. ", INK, True),
             ("Per modus: auto 14 min, trein 6 min voor ~95%.", GREY, False)])

# ── 10 · EVOLUTIE ────────────────────────────────────────────────────────────
image_slide("Eerlijkheid", "Hoe onze cijfers 'verbeterden'",
            "plot_v2_evolution.png",
            [("De R² daalde naarmate we eerlijker werden. ", INK, True),
             ("Lagere R² = minder zelfbedrog, niet een slechter model.", GREY, False)])

# ── 11 · 50 SCENARIO'S ───────────────────────────────────────────────────────
WFH = RGBColor(0xFB, 0x8C, 0x00)   # orange — matches the notebook advice plot
s = slide(); kicker(s, "50 scenario's"); title(s, "Het model getest op 50 situaties")
takeaway(s, [("Elke weekdag × weertype — van ideale vrijdag tot sneeuwstorm. Aanbeveling per dag:", INK, True)])
# three big stat numbers (no cards — just type)
xx = 0.92
for lab, val, col in [("trein", 40, TREIN), ("auto", 2, AUTO), ("thuiswerken", 8, WFH)]:
    tf = textbox(s, Inches(xx), Inches(2.85), Inches(3.6), Inches(1.4))
    para(tf, f"{val}", 50, col, font=SERIF, first=True, space_after=0, line=1.0)
    para(tf, f"× {lab}", 15, GREY, space_before=2)
    xx += 3.65
# short explanation per mode
ex = [
    ("Trein — de standaard", TREIN, "o.a. ideale vrijdag, typische dinsdag, zomervakantie"),
    ("Auto — enkel rustige vrijdagen", AUTO, "vrijdag + (mot)regen: lichtste spits, auto nét competitief"),
    ("Thuiswerken — zwaar weer", WFH, "sneeuw(storm), winterstorm, orkaan  ·  + feestdagen"),
]
yy = 4.95
for head, col, desc in ex:
    rule(s, LEFT, Inches(yy + 0.05), Inches(0.18), col, h=Pt(15))
    tf = textbox(s, Inches(1.25), Inches(yy - 0.07), Inches(11.0), Inches(0.55))
    para(tf, [(head + "  —  ", col, True), (desc, GREY, False)], 14.5, INK, first=True, space_after=0)
    yy += 0.6
footer(s)

# ── · 50 CASES — RESULTATEN ──────────────────────────────────────────────────
import pandas as pd
s = slide(); kicker(s, "50 scenario's — resultaten"); title(s, "Een greep uit de 50 gevallen")
MODE_COL = {"trein": TREIN, "auto": AUTO, "thuiswerken": WFH}
COLS = [(0.92, 5.5, "SCENARIO"), (6.6, 1.8, "AUTO-TIJD"), (8.6, 1.5, "RISICO"), (10.2, 2.2, "ADVIES")]
hy = 2.18
for x, w, htxt in COLS:
    para(textbox(s, Inches(x), Inches(hy), Inches(w), Inches(0.3)), htxt, 11.5, GREY, bold=True, first=True, space_after=0)
rule(s, LEFT, Inches(hy + 0.32), CW, INK, h=Pt(1.2))
csvp = FIG / "scenario_predictions_2025_real.csv"
pick = [1, 2, 3, 7, 17, 30, 11, 44, 4, 16, 49]
ry = hy + 0.52
if csvp.exists():
    sc = pd.read_csv(csvp); sc["num"] = sc["name"].str.extract(r"^(\d+)").astype(int)
    for n in pick:
        r = sc[sc.num == n].iloc[0]
        car  = f"{r['car_pred_min']:.0f} min" if pd.notna(r["car_pred_min"]) else "—"
        risk = str(int(r["weather_risk"])) if pd.notna(r["weather_risk"]) else "—"
        nm   = r["name"].split(".", 1)[1].strip()
        mode = r["mode_recommended"]
        cells = [(nm, INK, False), (car, INK, False), (risk, GREY, False), (mode, MODE_COL.get(mode, INK), True)]
        for (x, w, _), (val, c, b) in zip(COLS, cells):
            para(textbox(s, Inches(x), Inches(ry), Inches(w), Inches(0.32)), val, 13, c, bold=b, first=True, space_after=0)
        rule(s, LEFT, Inches(ry + 0.30), CW, HAIR, h=Pt(0.75))
        ry += 0.345
para(textbox(s, LEFT, Inches(ry + 0.06), CW, Inches(0.3)),
     "Volledige set van 50: scenario_predictions_2025_real.png / .csv", 11, GREY, first=True, space_after=0)
footer(s)

# ── 12 · CONCLUSIE ───────────────────────────────────────────────────────────
s = slide(); kicker(s, "Conclusie"); title(s, "Wat we écht weten")
pts = [
    ("Neem de trein op ~9 van de 10 werkdagen.", "De auto wint enkel op rustige dagen (vakantie / feestdag)."),
    ("Het model is kalender-eerst, weer-licht.", "Het is een planningshulp, geen exacte minuut-voorspeller."),
    ("Eerlijkheid boven een hoge R².", "De 0,99 was leakage; ~9 min fout is de waarheid."),
    ("Beperkingen.", "1 jaar echte auto-data · gemeten reistijd is zelf een model (60–120 min geklemd) · dagniveau blijft deels onvoorspelbaar."),
]
y = 2.2
for head, body in pts:
    rule(s, LEFT, Inches(y + 0.05), Inches(0.18), ACCENT, h=Pt(16))
    tf = textbox(s, Inches(1.25), Inches(y - 0.06), Inches(11.0), Inches(1.0))
    para(tf, head, 18, INK, bold=True, font=SERIF, first=True, space_after=3, line=1.05)
    para(tf, body, 14.5, GREY, line=1.15, space_after=0)
    y += 1.12
footer(s)

# ── 12 · CLOSING ─────────────────────────────────────────────────────────────
s = slide()
rule(s, LEFT, Inches(2.7), Inches(2.4))
tf = textbox(s, LEFT, Inches(2.95), Inches(11), Inches(2))
para(tf, "Bedankt — vragen?", 40, INK, font=SERIF, first=True, space_after=14)
para(tf, [("Volledige analyse: ", GREY, False),
          ("01_data_exploration_combined_v2.ipynb", ACCENT, True)], 15, GREY)
tf2 = textbox(s, LEFT, Inches(6.35), Inches(11), Inches(0.6))
para(tf2, "Laure · Jack · Maxime · Marc", 13, GREY, first=True, space_after=0)

out = Path("Gent_Mechelen_Presentatie_v2.pptx")
prs.save(out)
print(f"Saved {out}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
