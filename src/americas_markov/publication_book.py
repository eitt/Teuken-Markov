"""Captioned A4 figure book with searchable text and vector figure masters."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape

import pandas as pd
from matplotlib.font_manager import FontProperties, findfont
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak


INK = colors.HexColor("#243746")
MUTED = colors.HexColor("#586A77")
FONT, BOLD = "PublicationSans", "PublicationSans-Bold"


def _register_fonts():
    # Matplotlib supplies portable TTFs; embedding avoids PDF viewer substitutions.
    for name, weight in ((FONT,"normal"),(BOLD,"bold")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name,findfont(FontProperties(
                family="DejaVu Sans",weight=weight))))
    pdfmetrics.registerFontFamily(FONT,normal=FONT,bold=BOLD)


def paragraph(text, size=9.5, bold=False, leading=None):
    _register_fonts()
    text=str(text).translate({ord(c):"-" for c in "‐‑‒–—−"})
    text=text.replace("→","to")
    return Paragraph(escape(text).replace("\n", "<br/>"), ParagraphStyle(
        "publication", fontName=BOLD if bold else FONT,
        fontSize=size, leading=leading or size * 1.24, textColor=INK,
        splitLongWords=True, spaceAfter=0,
    ))


def _draw_text(doc, text, x, top, width, size=9.5, bold=False):
    p = paragraph(text, size, bold)
    _, height = p.wrap(width, A4[1])
    p.drawOn(doc, x, top - height)
    return top - height


def _label(item):
    kind, number = item["id"].split("_", 1)
    return f"{kind} {int(number)}"


def _cover(items, tables):
    buf = BytesIO()
    doc = canvas.Canvas(buf, pagesize=A4)
    doc.setTitle("Executive ideology in the Americas: figures and tables")
    top = _draw_text(doc, "Executive ideology\nin the Americas", 25*mm, 270*mm,
                     160*mm, 25, True)
    top = _draw_text(doc, "Observed history, measurement sensitivity and conditional scenarios",
                     25*mm, top-8*mm, 160*mm, 12)
    note = ("Publication and dissemination figure book. All maps and charts are derived "
            "from the reproducible Teuken-Markov outputs. DPI observations end on 1 January "
            "2023; GLI source observations end on 31 December 2020. This is not a map of "
            "current governments. Left, Center and Right are source classifications, "
            "not measures of democracy or the full ideology of an individual president.")
    top = _draw_text(doc, note, 25*mm, top-12*mm, 160*mm, 10)
    caution = ("Read the evidence in order: political coverage and history, disagreement "
               "between sources, then held-out performance. Scenario bands describe "
               "conditional Monte Carlo variation; they omit parameter uncertainty. "
               "Geographical connections do not establish political influence. ENSO "
               "measures climate variability, not anthropogenic climate change. Evaluation "
               "uses revised retrospective inputs, not historical publication vintages; "
               "event-time lags do not establish availability on the forecast date.")
    top = _draw_text(doc, caution, 25*mm, top-7*mm, 160*mm, 10)
    top = _draw_text(doc, "Contents", 25*mm, top-10*mm, 160*mm, 12, True)
    for item in items + tables:
        top = _draw_text(doc, f"{_label(item)}. {item['title']}", 25*mm, top-2*mm,
                         160*mm, 9.3)
    if top < 17*mm:
        raise ValueError("Figure-book contents do not fit on the cover.")
    doc.showPage(); doc.save(); buf.seek(0)
    return PdfReader(buf)


def _figure_page(folder, item):
    master = PdfReader(folder / f"{item['stem']}_master.pdf")
    if len(master.pages) != 1:
        raise ValueError(f"{item['id']}: expected a one-page vector master")
    fig = master.pages[0]
    width, height = float(fig.mediabox.width), float(fig.mediabox.height)
    if abs(width/mm - item["width_mm"]) > .2 or abs(height/mm - item["height_mm"]) > .2:
        raise ValueError(f"{item['id']}: master size disagrees with figure metadata")
    if width > 180*mm or height > 200*mm or fig.rotation % 360:
        raise ValueError(f"{item['id']}: figure cannot be placed at its final size on A4")
    left = (A4[0]-width)/2
    bottom = 263*mm - height
    buf = BytesIO(); doc = canvas.Canvas(buf, pagesize=A4)
    _register_fonts(); doc.setFont(FONT, 9); doc.setFillColor(MUTED)
    doc.drawString(25*mm, 289*mm, "Executive ideology in the Americas")
    doc.setStrokeColor(colors.HexColor("#CDD5DC"))
    doc.line(25*mm, 285*mm, 185*mm, 285*mm)
    title_bottom = _draw_text(doc, f"{_label(item)}. {item['title']}",
                             25*mm, 281*mm, 160*mm, 12.5, True)
    if title_bottom < 266*mm:
        raise ValueError(f"{item['id']}: title overlaps figure; shorten it")
    caption = re.sub(r"^(?:Figure|Supplement|Supplementary Figure)\s+\d+\.\s*", "", item["caption"])
    source = "Source: " + item["source"]
    available = bottom - 6*mm - 17*mm
    for text_width, size in ((160*mm,9.5), (180*mm,9.5), (180*mm,9.0)):
        p, s = paragraph(caption,size), paragraph(source,size)
        hp = p.wrap(text_width,available)[1]; hs = s.wrap(text_width,available)[1]
        if hp + hs + 2*mm <= available:
            x = (A4[0]-text_width)/2; top=bottom-6*mm
            p.drawOn(doc,x,top-hp); s.drawOn(doc,x,top-hp-2*mm-hs)
            break
    else:
        raise ValueError(f"{item['id']}: caption exceeds the readable space below the figure")
    doc.showPage(); doc.save(); buf.seek(0)
    layout=PdfReader(buf); temporary=PdfWriter(clone_from=layout);page=temporary.pages[0]
    page.merge_transformed_page(fig, Transformation().translate(
        tx=left-float(fig.mediabox.left), ty=bottom-float(fig.mediabox.bottom)),
        over=True, expand=False)
    merged=BytesIO(); temporary.write(merged); merged.seek(0)
    return PdfReader(merged)


def _cell(value):
    if pd.isna(value):
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}" if value != int(value) else str(int(value))
    return str(value)


def _table_pages(folder, item):
    frame=pd.read_csv(folder/f"{item['stem']}.csv")
    if item["id"]=="Table_04":
        # Compact period labels preserve the exact source-origin dates.
        frame["Evaluation period"]=frame["Evaluation period"].map(
            lambda s: re.search(r"\(([^)]+)\)",str(s)).group(1)+
            (" (all)" if str(s).startswith("All origins") else ""))
    wide=len(frame.columns)>6 or item["id"]=="Table_06"
    page_size=landscape(A4) if wide else A4
    buf=BytesIO()
    doc=SimpleDocTemplate(buf,pagesize=page_size,leftMargin=18*mm,rightMargin=18*mm,
                          topMargin=18*mm,bottomMargin=17*mm)
    caption=item["caption"].replace("shown as an em dash here","shown as NA in this PDF")
    story=[paragraph(f"{_label(item)}. {item['title']}",13,True),Spacer(1,5*mm),
           paragraph(caption,9.5),Spacer(1,4*mm)]
    # Column allocation uses readable header/body length without shrinking text.
    weights=[]
    for col in frame.columns:
        content=[len(_cell(v)) for v in frame[col]]
        weights.append(min(45,max(10,len(str(col))*.7,
                                  sorted(content)[int(len(content)*.8)]*.6 if content else 10)))
    table_width=page_size[0]-36*mm
    widths=[w/sum(weights)*table_width for w in weights]
    if item["id"]=="Table_01":
        widths=[n*mm for n in (32,40,24,39,21,17,28,60)]
    elif item["id"]=="Table_04":
        widths=[n*mm for n in (35,73,17,23,31,23,30,29)]
    elif item["id"]=="Table_06":
        widths=[n*mm for n in (37,44,49,64,67)]
    rows=[[paragraph(str(c).replace("_"," "),8.5,True) for c in frame.columns]]
    rows.extend([[paragraph(_cell(v),8.5) for v in row]
                 for row in frame.itertuples(index=False,name=None)])
    table_style=TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#E8EEF3")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F6F8FA")]),
        ("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,0),.5,colors.HexColor("#8495A3")),
        ("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
    ])
    def styled_table(body):
        result=Table(body,colWidths=widths,repeatRows=1,hAlign="LEFT")
        result.setStyle(table_style)
        return result
    if item["id"]=="Table_06":
        # Balance the long definitions instead of leaving one orphan row.
        midpoint=1+(len(rows)-1+1)//2
        story += [styled_table(rows[:midpoint]),PageBreak(),
                  styled_table([rows[0],*rows[midpoint:]])]
    else:
        story.append(styled_table(rows))
    story += [Spacer(1,5*mm),paragraph("Source: "+item["source"],9)]
    def continued(c, document):
        c.saveState();_register_fonts();c.setFont(FONT,9);c.setFillColor(MUTED)
        c.drawString(18*mm,page_size[1]-10*mm,
                     f"{_label(item)}. {item['title']} (continued)")
        c.restoreState()
    doc.build(story,onLaterPages=continued)
    buf.seek(0);return PdfReader(buf)


def build_book(folder: Path, figures: list[dict], tables: list[dict], destination: Path|None=None):
    """Keep vector masters at declared final dimensions; never scale to fit."""
    folder=Path(folder); destination=Path(destination or folder/"Americas_Figures_and_Tables_English.pdf")
    writer=PdfWriter()
    sections=[("Reading guide",_cover(figures,tables))]
    sections += [(f"{_label(item)}. {item['title']}",_figure_page(folder,item)) for item in figures]
    table_folder=folder/"tables"
    sections += [(f"{_label(item)}. {item['title']}",_table_pages(table_folder,item)) for item in tables]
    for label,reader in sections:
        index=len(writer.pages)
        for page in reader.pages: writer.add_page(page)
        writer.add_outline_item(label,index)
    total=len(writer.pages)
    for index,page in enumerate(writer.pages):
        buf=BytesIO();c=canvas.Canvas(buf,pagesize=(float(page.mediabox.width),float(page.mediabox.height)))
        _register_fonts();c.setFont(FONT,8);c.setFillColor(MUTED)
        c.drawRightString(float(page.mediabox.width)-18*mm,8*mm,f"{index+1} / {total}")
        c.save();buf.seek(0); page.merge_page(PdfReader(buf).pages[0]);page.compress_content_streams()
    writer.add_metadata({"/Title":"Executive ideology in the Americas: figures and tables",
                         "/Subject":"Observed data, held-out evaluation and conditional scenarios"})
    writer.compress_identical_objects()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open("wb") as stream:writer.write(stream)
    return destination
