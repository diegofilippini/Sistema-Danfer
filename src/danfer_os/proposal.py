from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Circle, Drawing, Polygon, Rect
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from danfer_os.models.commercial import Client, CostSettings, Quote


NAVY = colors.HexColor("#071A2E")
BLUE = colors.HexColor("#0A4775")
CYAN = colors.HexColor("#41B9F4")
INK = colors.HexColor("#17293A")
MUTED = colors.HexColor("#66798A")
LINE = colors.HexColor("#CFDAE3")
PALE = colors.HexColor("#F2F6F9")
ASSET = Path(__file__).parent / "static" / "assets" / "monumento-imigrante-caxias.jpg"
OFFICIAL_HEADER = Path(__file__).parent / "static" / "assets" / "cabecalho-oficial-danfer.png"


def brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def _header_footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    width, height = A4
    canvas.saveState()
    if document.page == 1 and OFFICIAL_HEADER.exists():
        canvas.drawImage(str(OFFICIAL_HEADER), 0, height - 42.4 * mm, width, 42.4 * mm, preserveAspectRatio=False, mask="auto")
        canvas.setFillColor(CYAN)
        canvas.rect(0, height - 43.8 * mm, width, 1.4 * mm, fill=1, stroke=0)
    elif document.page > 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 12 * mm, width, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(10 * mm, height - 8 * mm, "DANFER | ORÇAMENTO COMERCIAL")
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, 13 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(10 * mm, 7 * mm, "(54) 3027-4715  |  WhatsApp (54) 99152-5973")
    canvas.drawCentredString(width / 2, 7 * mm, "danfer.ind.br")
    canvas.drawRightString(width - 10 * mm, 7 * mm, f"QUALIDADE · TECNOLOGIA · PÁG. {document.page}")
    canvas.restoreState()


def _label_value(label: str, value: str, styles: dict) -> Paragraph:
    return Paragraph(f"<font color='#66798A' size='7'><b>{escape(label.upper())}</b></font><br/>{escape(value or '-')} ", styles["field"])


def _qr(value: str, size: float = 16 * mm) -> Drawing:
    widget = QrCodeWidget(value)
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    drawing.add(widget)
    return drawing


def _brazil_flag(width: float = 24 * mm, height: float = 15 * mm) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#169B62"), strokeColor=None))
    d.add(Polygon([width / 2, height * .1, width * .92, height / 2, width / 2, height * .9, width * .08, height / 2], fillColor=colors.HexColor("#FFDF00"), strokeColor=None))
    d.add(Circle(width / 2, height / 2, height * .23, fillColor=colors.HexColor("#002776"), strokeColor=None))
    return d


def _rs_flag(width: float = 24 * mm, height: float = 15 * mm) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, height * 2 / 3, width, height / 3, fillColor=colors.HexColor("#159447"), strokeColor=None))
    d.add(Rect(0, height / 3, width, height / 3, fillColor=colors.HexColor("#C8102E"), strokeColor=None))
    d.add(Rect(0, 0, width, height / 3, fillColor=colors.HexColor("#F7D117"), strokeColor=None))
    d.add(Circle(width / 2, height / 2, height * .15, fillColor=colors.white, strokeColor=BLUE))
    return d


def _institutional_story(styles: dict) -> list:
    services = [
        ("LA", "Corte Laser", "Precisao, repetibilidade e acabamento em chapas."),
        ("GU", "Guilhotina", "Cortes retos rapidos para preparacao de materiais."),
        ("PL", "Corte Plasma", "Flexibilidade para chapas e geometrias robustas."),
        ("DO", "Dobra CNC", "Conformacao controlada com alta repetibilidade."),
        ("CA", "Calandragem", "Curvas, cones e cilindros sob medida."),
        ("PR", "Prensa", "Conformacao e operacoes complementares de producao."),
        ("CH", "Chanfro", "Preparacao tecnica de bordas para montagem e solda."),
        ("SO", "Solda", "Uniao e acabamento de conjuntos metalicos."),
    ]
    hero = Image(str(ASSET), width=179 * mm, height=60 * mm) if ASSET.exists() else Spacer(1, 60 * mm)
    title = Paragraph("<font color='#0A4775' size='17'><b>Transformando aço em soluções</b></font><br/><font color='#66798A' size='9'>Mais de 20 anos atendendo a indústria brasileira a partir de Caxias do Sul.</font>", styles["institutional"])
    cards = []
    for index in range(0, len(services), 2):
        row = []
        for code, name, description in services[index:index + 2]:
            row.append(Table([[
                Paragraph(f"<font color='white'><b>{code}</b></font>", styles["badge"]),
                Paragraph(f"<b>{name}</b><br/><font color='#66798A' size='7'>{description}</font>", styles["body"]),
            ]], colWidths=[14 * mm, 72 * mm], style=TableStyle([
                ("BACKGROUND", (0, 0), (0, 0), BLUE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), .4, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ])))
        cards.append(row)
    service_table = Table(cards, colWidths=[88.5 * mm, 88.5 * mm], hAlign="CENTER")
    service_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm), ("TOPPADDING", (0, 0), (-1, -1), 1 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm)]))
    capabilities = Table([
        ["LASER", "até 19,00 × 1500 × 3000 mm", "DOBRA CNC", "até 6,35 × 4000 mm"],
        ["CALANDRA", "9,53 × 2000 mm", "CALANDRA", "6,35 × 3000 mm"],
    ], colWidths=[24 * mm, 65 * mm, 24 * mm, 64 * mm])
    capabilities.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), .5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), .35, LINE), ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    closing = Table([[
        _brazil_flag(), _rs_flag(),
        Paragraph("<b>Danfer e DF - Grupo Empresarial</b><br/>Caxias do Sul - RS<br/>www.danfer.ind.br", styles["body"]),
        _qr("https://wa.me/5554991525973", 17 * mm),
        Paragraph("<b>Fale com a Danfer</b><br/>(54) 99152-5973<br/>(54) 3027-4715", styles["body"]),
    ]], colWidths=[26 * mm, 26 * mm, 72 * mm, 18 * mm, 35 * mm])
    closing.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm)]))
    credit = Paragraph("Fotografia: Ricardo André Frantz / Wikimedia Commons - CC BY-SA 3.0. Tratamento e recorte aplicados ao layout.", styles["credit"])
    return [PageBreak(), hero, Spacer(1, 4 * mm), title, Spacer(1, 4 * mm), Paragraph("NOSSOS SERVIÇOS", styles["section"]), service_table, Spacer(1, 4 * mm), Paragraph("CAPACIDADE INDUSTRIAL", styles["section"]), capabilities, Spacer(1, 4 * mm), closing, Spacer(1, 2 * mm), credit]


def build_proposal_pdf(quote: Quote, client: Client, settings: CostSettings | None = None) -> bytes:
    settings = settings or CostSettings()
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=40 * mm, bottomMargin=17 * mm, title=f"Proposta {quote.number}", author="Danfer Industrial")
    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=INK),
        "field": ParagraphStyle("field", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
        "section": ParagraphStyle("section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLUE, spaceAfter=2 * mm),
        "right": ParagraphStyle("right", parent=base["Normal"], fontName="Helvetica", fontSize=8, alignment=TA_RIGHT, textColor=INK),
        "total": ParagraphStyle("total", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=13, alignment=TA_RIGHT, textColor=colors.white),
        "center": ParagraphStyle("center", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, alignment=TA_CENTER, textColor=colors.white),
        "institutional": ParagraphStyle("institutional", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=14, alignment=TA_CENTER, textColor=INK),
        "badge": ParagraphStyle("badge", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER),
        "credit": ParagraphStyle("credit", parent=base["Normal"], fontName="Helvetica", fontSize=5.5, textColor=MUTED, alignment=TA_RIGHT),
        "small": ParagraphStyle("small", parent=base["Normal"], fontName="Helvetica", fontSize=6.5, leading=8, textColor=INK),
    }
    kind = "ORÇAMENTO DE VENDA" if quote.type.value == "venda" else "ORÇAMENTO DE SERVIÇO"
    identity = Table([[Paragraph(f"<b>{kind}</b><br/><font size='15'>{escape(quote.number)}</font>", styles["body"]), Paragraph(f"<b>REVISÃO</b><br/><font size='15'>{escape(quote.revision)}</font>", styles["right"]), Paragraph(f"<b>EMISSÃO</b><br/>{quote.created_at:%d/%m/%Y}<br/><b>VALIDADE</b><br/>{quote.valid_until:%d/%m/%Y}", styles["right"])]], colWidths=[100 * mm, 30 * mm, 49 * mm])
    identity.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), .6, LINE), ("LINEBEFORE", (1, 0), (-1, 0), .5, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm)]))
    commercial = Table([
        [_label_value("Cliente / código ERP", f"{client.erp_code} - {client.name}" if client.erp_code else client.name, styles), _label_value("Condição de pagamento", quote.payment_terms or client.payment_terms, styles), _label_value("Natureza da operação", quote.nature_operation, styles)],
        [_label_value("Solicitante", quote.requester or client.contact, styles), _label_value("Faturamento", quote.billing_unit.value.upper(), styles), _label_value("Frete", f"{quote.freight_type.value} - por conta de {quote.freight_payer.value}", styles)],
        [_label_value("Entrega prevista", quote.expected_delivery.strftime("%d/%m/%Y") if quote.expected_delivery else "A combinar", styles), _label_value("Local de entrega", client.address or "A combinar", styles), _label_value("Cenário tributário", quote.tax_scenario, styles)],
    ], colWidths=[60 * mm, 60 * mm, 59 * mm])
    commercial.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE), ("INNERGRID", (0, 0), (-1, -1), .35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm)]))
    rows = [["ITEM", "DESCRIÇÃO / MATERIAL", "PROCESSOS", "QTD.", "UNITÁRIO", "TOTAL"]]
    for item in quote.items:
        material = " | ".join(filter(None, [item.material, f"{item.thickness_mm:g} mm" if item.thickness_mm else ""]))
        processes = ", ".join(process.name for process in item.processes) or "Fornecimento"
        if item.notes:
            processes += f"<br/><font color='#66798A'>{escape(item.notes)}</font>"
        rows.append([Paragraph(f"<b>{escape(item.code)}</b>", styles["body"]), Paragraph(f"<b>{escape(item.description)}</b><br/><font color='#66798A'>{escape(material or '-')}</font>", styles["body"]), Paragraph(processes, styles["body"]), f"{item.quantity:g} {item.unit}", brl(item.unit_price), brl(item.total_price)])
    items_table = Table(rows, colWidths=[18 * mm, 56 * mm, 43 * mm, 14 * mm, 24 * mm, 24 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 6.5), ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), .35, LINE), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]), ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm), ("TOPPADDING", (0, 1), (-1, -1), .8 * mm), ("BOTTOMPADDING", (0, 1), (-1, -1), .8 * mm)]))
    tax_base = max(quote.subtotal + quote.freight_value - quote.discount_value, 0)
    financial_rows = [["Subtotal", brl(quote.subtotal)]]
    if quote.freight_value:
        financial_rows.append(["Frete", brl(quote.freight_value)])
    if quote.discount_value:
        financial_rows.append(["Desconto", f"- {brl(quote.discount_value)}"])
    if quote.type.value == "venda" and quote.ipi_percent:
        financial_rows.append([f"IPI ({quote.ipi_percent:g}%)", brl(tax_base * quote.ipi_percent / 100)])
    financial_rows.append([Paragraph("TOTAL GERAL", styles["center"]), Paragraph(brl(quote.total), styles["total"])])
    financial = Table(financial_rows, colWidths=[45 * mm, 42 * mm], hAlign="RIGHT")
    financial.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, -2), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -2), 8), ("LINEBELOW", (0, 0), (-1, -2), .35, LINE), ("BACKGROUND", (0, -1), (-1, -1), NAVY), ("TEXTCOLOR", (0, -1), (-1, -1), colors.white), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm)]))
    notes = quote.observations or "Proposta sujeita às condições comerciais apresentadas neste documento."
    conditions = f"Validade: {quote.valid_until:%d/%m/%Y}. Pagamento: {quote.payment_terms or client.payment_terms}. Frete: {quote.freight_type.value}. Informar destino da mercadoria: industrialização ou uso e consumo. Empresa enquadrada no Lucro Presumido - NCM padrão 72119090."
    contact = Table([[_qr("https://wa.me/5554991525973", 12 * mm), Paragraph("<b>WHATSAPP</b><br/>(54) 99152-5973<br/>(54) 3027-4715<br/>www.danfer.ind.br", styles["small"])], [_brazil_flag(15 * mm, 9 * mm), _rs_flag(15 * mm, 9 * mm)]], colWidths=[14 * mm, 19 * mm])
    footer_info = Table([[Paragraph(f"<b>OBSERVAÇÕES GERAIS</b><br/>{escape(notes)}", styles["small"]), Paragraph(f"<b>CONDIÇÕES COMERCIAIS</b><br/>{escape(conditions)}", styles["small"]), Paragraph(f"<b>ELABORADO POR</b><br/>{escape(quote.prepared_by)}", styles["small"]), contact]], colWidths=[52 * mm, 58 * mm, 30 * mm, 39 * mm])
    footer_info.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE), ("INNERGRID", (0, 0), (-1, -1), .35, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm), ("TOPPADDING", (0, 0), (-1, -1), 1 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm)]))
    story = [identity, Spacer(1, 1 * mm), commercial, Spacer(1, 1.5 * mm), Paragraph("ITENS DA PROPOSTA", styles["section"]), items_table, Spacer(1, 1.5 * mm), financial, Spacer(1, 1.5 * mm), footer_info]
    if settings.attach_institutional_page and quote.total >= settings.institutional_page_minimum:
        story.extend(_institutional_story(styles))
    document.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buffer.getvalue()


# Modelo oficial aprovado em 01/08/2026, baseado no orçamento de referência 002-026.
def build_proposal_pdf(quote: Quote, client: Client, settings: CostSettings | None = None) -> bytes:
    settings = settings or CostSettings()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=10 * mm, leftMargin=10 * mm,
        topMargin=48 * mm, bottomMargin=18 * mm,
        title=f"Orçamento {quote.number}", author=quote.prepared_by or "Danfer Industrial",
    )
    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle("ref-body", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.3, textColor=INK),
        "bold": ParagraphStyle("ref-bold", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=9.5, textColor=INK),
        "label": ParagraphStyle("ref-label", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=6.7, leading=8, textColor=colors.HexColor("#0065A5"), spaceAfter=2 * mm),
        "white": ParagraphStyle("ref-white", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=11, textColor=colors.white),
        "white_small": ParagraphStyle("ref-white-small", parent=base["Normal"], fontName="Helvetica", fontSize=6.2, leading=9, textColor=colors.white),
        "section": ParagraphStyle("ref-section", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=10, textColor=colors.HexColor("#0065A5"), spaceAfter=2 * mm),
        "total_label": ParagraphStyle("ref-total-label", parent=base["Normal"], fontName="Helvetica", fontSize=11, textColor=colors.white),
        "total": ParagraphStyle("ref-total", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=14, alignment=TA_RIGHT, textColor=colors.white),
        "center": ParagraphStyle("ref-center", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7, alignment=TA_CENTER, textColor=colors.white),
        "institutional": ParagraphStyle("institutional-ref", parent=base["Normal"], fontName="Helvetica", fontSize=9, leading=14, alignment=TA_CENTER, textColor=INK),
        "badge": ParagraphStyle("badge-ref", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, alignment=TA_CENTER),
        "credit": ParagraphStyle("credit-ref", parent=base["Normal"], fontName="Helvetica", fontSize=5.5, textColor=MUTED, alignment=TA_RIGHT),
    }

    def field(label: str, value: str, dark: bool = False) -> Table:
        content = [Paragraph(label.upper(), styles["white"] if dark else styles["label"]), Paragraph(escape(value or "-"), styles["white_small"] if dark else styles["bold"])]
        table = Table([[content]], colWidths=[None])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#083B70") if dark else colors.HexColor("#F6F8FA")),
            ("BOX", (0, 0), (-1, -1), .45, colors.HexColor("#C8D7E3")),
            ("LINEBEFORE", (0, 0), (0, -1), 2.2, CYAN if dark else colors.HexColor("#0870B5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
        ]))
        return table

    delivery = quote.expected_delivery.strftime("%d/%m/%Y") if quote.expected_delivery else "A combinar"
    validity_days = max((quote.valid_until - quote.created_at.date()).days, 0)
    top = Table([[
        field("Cliente / código ERP", f"{client.erp_code} - {client.name}" if client.erp_code else client.name), field("Solicitante", quote.requester or client.contact),
        field("Emissão", quote.created_at.strftime("%d/%m/%Y")), field("Entrega prevista", delivery),
        field("Orçamento", f"{quote.number}\nVálido por {validity_days} dias", True),
    ]], colWidths=[52 * mm, 42 * mm, 29 * mm, 30 * mm, 32 * mm])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm)]))
    second = Table([[
        field("Condição de pagamento", quote.payment_terms or client.payment_terms),
        field("Frete", quote.freight_type.value.upper()), field("Tipo", quote.type.value.title()),
        field("IPI", f"{quote.ipi_percent:.2f}%".replace(".", ",")),
    ]], colWidths=[62 * mm, 47 * mm, 40 * mm, 36 * mm])
    second.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1 * mm)]))

    rows = [["ITEM", "DESCRIÇÃO / CÓDIGO", "MATERIAL / ESPESSURA", "PROCESSOS", "QTD.", "VALOR UNIT.", "VALOR TOTAL"]]
    for index, item in enumerate(quote.items, 1):
        material = " | ".join(filter(None, [item.material, f"{item.thickness_mm:g} mm" if item.thickness_mm else ""])) or "-"
        processes = " · ".join(process.name for process in item.processes) or "Fornecimento"
        rows.append([str(index), Paragraph(f"<b>{escape(item.description)}</b><br/><font color='#60788A'>{escape(item.code)}</font>", styles["body"]), escape(material), Paragraph(escape(processes), styles["body"]), f"{item.quantity:g}", brl(item.unit_price), Paragraph(f"<b>{brl(item.total_price)}</b>", styles["body"])])
    items = Table(rows, colWidths=[12 * mm, 37 * mm, 40 * mm, 42 * mm, 12 * mm, 21 * mm, 21 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#073767")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 6.2),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#C9D7E2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F8")]),
        ("FONTSIZE", (0, 1), (-1, -1), 7.2), ("TOPPADDING", (0, 0), (-1, -1), .8 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), .8 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))

    tax_base = max(quote.subtotal + quote.freight_value - quote.discount_value, 0)
    ipi_value = tax_base * quote.ipi_percent / 100 if quote.type.value == "venda" else 0
    financial_rows = [["Subtotal", brl(quote.subtotal)]]
    if quote.freight_value: financial_rows.append(["Frete", brl(quote.freight_value)])
    if quote.discount_value: financial_rows.append(["Desconto", f"- {brl(quote.discount_value)}"])
    if quote.ipi_percent: financial_rows.append([f"IPI ({quote.ipi_percent:.2f}%)".replace(".", ","), brl(ipi_value)])
    financial_rows.append([Paragraph("VALOR FINAL", styles["total_label"]), Paragraph(brl(quote.total), styles["total"])])
    financial = Table(financial_rows, colWidths=[35 * mm, 42 * mm], hAlign="RIGHT")
    financial.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -2), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -2), 8), ("LINEBELOW", (0, 0), (-1, -2), .4, LINE), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#073767")), ("TEXTCOLOR", (0, -1), (-1, -1), colors.white), ("LINEBEFORE", (0, -1), (0, -1), 3, CYAN), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm)]))

    conditions = Paragraph("<b>CONDIÇÕES COMERCIAIS</b><br/><br/>• Materiais novos e conforme especificação informada.<br/>• Prazo sujeito à análise técnica, disponibilidade e aprovação da proposta.<br/>• Alterações de projeto poderão impactar prazo e valor.<br/>• Medidas consideradas em milímetros nos documentos técnicos.", styles["body"])
    cond_table = Table([[conditions]], colWidths=[108 * mm])
    cond_table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm)]))
    summary = Table([[cond_table, financial]], colWidths=[108 * mm, 77 * mm])
    summary.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    notes = escape(quote.observations or "Todos os materiais serão novos e de primeira qualidade. Medidas em milímetros (mm). Alterações no projeto poderão impactar o prazo e o valor.")
    observations = Table([[Paragraph(f"<font color='#0065A5'><b>OBSERVAÇÕES GERAIS</b></font><br/><br/>{notes}", styles["body"])]], colWidths=[185 * mm])
    observations.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))
    prepared = Paragraph(f"<font color='#0065A5'><b>ORÇAMENTO ELABORADO POR</b></font><br/><br/>{escape(quote.prepared_by or 'Administrador Danfer')}<br/><br/>Danfer - Transformando aço em soluções", styles["body"])
    contact = Table([[prepared, Paragraph("<font color='#0065A5'><b>DÚVIDAS? FALE CONOSCO</b></font>", styles["body"]), _qr("https://wa.me/5554991525973", 24 * mm)]], colWidths=[115 * mm, 42 * mm, 28 * mm])
    contact.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))
    warning = Table([[Paragraph("<b>ATENÇÃO:</b> retirada dos materiais mediante identificação do cliente e referência do pedido/orçamento.  |  Empresa enquadrada no <b>Lucro Presumido - NCM padrão 72119090.</b>  |  Sempre informar o destino da mercadoria: industrialização ou uso e consumo.", styles["white_small"])]], colWidths=[185 * mm])
    warning.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#073767")), ("LINEBEFORE", (0, 0), (0, -1), 3, CYAN), ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm)]))

    story = [top, Spacer(1, 2 * mm), second, Spacer(1, 3 * mm), items, Spacer(1, 4 * mm), summary, Spacer(1, 3 * mm), observations, Spacer(1, 3 * mm), contact, Spacer(1, 2 * mm), warning]
    if settings.attach_institutional_page and quote.total >= settings.institutional_page_minimum:
        story.extend(_institutional_story(styles))
    document.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buffer.getvalue()
