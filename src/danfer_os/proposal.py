from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from danfer_os.models.commercial import Client, Quote


NAVY = colors.HexColor("#071A2E")
BLUE = colors.HexColor("#0A4775")
CYAN = colors.HexColor("#41B9F4")
INK = colors.HexColor("#17293A")
MUTED = colors.HexColor("#66798A")
LINE = colors.HexColor("#CFDAE3")
PALE = colors.HexColor("#F2F6F9")


def brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


def _header_footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 36 * mm, width, 36 * mm, fill=1, stroke=0)
    canvas.setFillColor(CYAN)
    canvas.rect(0, height - 36 * mm, 5 * mm, 36 * mm, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.roundRect(14 * mm, height - 29 * mm, 20 * mm, 20 * mm, 3 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-BoldOblique", 24)
    canvas.drawCentredString(24 * mm, height - 23 * mm, "D")
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(39 * mm, height - 18 * mm, "DANFER")
    canvas.setFillColor(colors.HexColor("#AFC5D8"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(39 * mm, height - 24 * mm, "CORTE LASER | DOBRA CNC | CALANDRAGEM")
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawRightString(width - 14 * mm, height - 17 * mm, "TRANSFORMANDO ACO EM SOLUCOES")
    canvas.setFillColor(colors.HexColor("#AFC5D8"))
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(width - 14 * mm, height - 23 * mm, "PROPOSTA COMERCIAL PROFISSIONAL")
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(1.2)
    canvas.line(14 * mm, 14 * mm, width - 14 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(14 * mm, 9 * mm, "Danfer Industrial | Qualidade | Tecnologia | Compromisso | Confianca")
    canvas.drawRightString(width - 14 * mm, 9 * mm, f"Pagina {document.page}")
    canvas.restoreState()


def _label_value(label: str, value: str, styles: dict) -> Paragraph:
    return Paragraph(f"<font color='#66798A' size='7'><b>{escape(label.upper())}</b></font><br/>{escape(value or '-')} ", styles["field"])


def _whatsapp_qr() -> Drawing:
    widget = QrCodeWidget("https://wa.me/5554991525973")
    x1, y1, x2, y2 = widget.getBounds()
    size = 16 * mm
    drawing = Drawing(
        size, size,
        transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0],
    )
    drawing.add(widget)
    return drawing


def build_proposal_pdf(quote: Quote, client: Client) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=40 * mm,
        bottomMargin=17 * mm,
        title=f"Proposta {quote.number}",
        author="Danfer Industrial",
    )
    base = getSampleStyleSheet()
    styles = {
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=INK),
        "field": ParagraphStyle("field", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
        "section": ParagraphStyle("section", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLUE, spaceAfter=3 * mm),
        "right": ParagraphStyle("right", parent=base["Normal"], fontName="Helvetica", fontSize=8, alignment=TA_RIGHT, textColor=INK),
        "total": ParagraphStyle("total", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=13, alignment=TA_RIGHT, textColor=colors.white),
        "center": ParagraphStyle("center", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, alignment=TA_CENTER, textColor=colors.white),
    }
    kind = "ORCAMENTO DE VENDA" if quote.type.value == "venda" else "ORCAMENTO DE SERVICO"
    identity = Table(
        [[Paragraph(f"<b>{kind}</b><br/><font size='15'>{escape(quote.number)}</font>", styles["body"]),
          Paragraph(f"<b>REVISAO</b><br/><font size='15'>{escape(quote.revision)}</font>", styles["right"]),
          Paragraph(f"<b>EMISSAO</b><br/>{quote.created_at:%d/%m/%Y}<br/><b>VALIDADE</b><br/>{quote.valid_until:%d/%m/%Y}", styles["right"])]],
        colWidths=[100 * mm, 30 * mm, 49 * mm],
    )
    identity.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("LINEBEFORE", (1, 0), (-1, 0), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    commercial = Table([
        [_label_value("Cliente", client.name, styles), _label_value("Condicao de pagamento", quote.payment_terms or client.payment_terms, styles), _label_value("Natureza da operacao", quote.nature_operation, styles)],
        [_label_value("Solicitante", quote.requester or client.contact, styles), _label_value("Faturamento", quote.billing_unit.value.upper(), styles), _label_value("Frete", f"{quote.freight_type.value} - por conta de {quote.freight_payer.value}", styles)],
        [_label_value("Entrega prevista", quote.expected_delivery.strftime("%d/%m/%Y") if quote.expected_delivery else "A combinar", styles), _label_value("Local de entrega", client.address or "A combinar", styles), _label_value("Cenario tributario", quote.tax_scenario, styles)],
    ], colWidths=[60 * mm, 60 * mm, 59 * mm])
    commercial.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
    ]))
    rows = [["ITEM", "DESCRICAO / MATERIAL", "PROCESSOS / OBSERVACOES", "QTD.", "MARGEM", "UNITARIO", "TOTAL"]]
    for item in quote.items:
        material = " | ".join(filter(None, [item.material, f"{item.thickness_mm:g} mm" if item.thickness_mm else ""]))
        processes = ", ".join(process.name for process in item.processes) or "Fornecimento"
        if item.notes:
            processes += f"<br/><font color='#66798A'>{escape(item.notes)}</font>"
        if item.costing_warnings:
            processes += "<br/><font color='#B06A00'>" + escape(" | ".join(item.costing_warnings)) + "</font>"
        margin = item.margin_percent if item.margin_percent is not None else quote.margin_percent
        rows.append([
            Paragraph(f"<b>{escape(item.code)}</b>", styles["body"]),
            Paragraph(f"<b>{escape(item.description)}</b><br/><font color='#66798A'>{escape(material or '-')}</font>", styles["body"]),
            Paragraph(processes, styles["body"]), f"{item.quantity:g} {item.unit}", f"{margin:g}%", brl(item.unit_price), brl(item.total_price),
        ])
    items_table = Table(rows, colWidths=[18 * mm, 43 * mm, 36 * mm, 13 * mm, 13 * mm, 28 * mm, 28 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 1.5 * mm), ("BOTTOMPADDING", (0, 1), (-1, -1), 1.5 * mm),
    ]))
    tax_base = max(quote.subtotal + quote.freight_value - quote.discount_value, 0)
    cbs = tax_base * quote.cbs_percent / 100
    ibs = tax_base * quote.ibs_percent / 100
    ipi = tax_base * quote.ipi_percent / 100
    financial_rows = [["Subtotal", brl(quote.subtotal)]]
    if quote.freight_value:
        financial_rows.append(["Frete", brl(quote.freight_value)])
    if quote.discount_value:
        financial_rows.append(["Desconto", f"- {brl(quote.discount_value)}"])
    if quote.type.value == "venda" and quote.ipi_percent:
        financial_rows.append([f"IPI ({quote.ipi_percent:g}%)", brl(ipi)])
    financial_rows.append([Paragraph("TOTAL GERAL", styles["center"]), Paragraph(brl(quote.total), styles["total"])])
    financial = Table(financial_rows, colWidths=[45 * mm, 42 * mm], hAlign="RIGHT")
    financial.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -2), 8), ("LINEBELOW", (0, 0), (-1, -2), 0.35, LINE),
        ("BACKGROUND", (0, -1), (-1, -1), NAVY), ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    notes = quote.observations or "Proposta sujeita as condicoes comerciais apresentadas neste documento."
    conditions = f"Validade: {quote.valid_until:%d/%m/%Y}. Pagamento: {quote.payment_terms or client.payment_terms}. Frete: {quote.freight_type.value}. Informe se a operacao e industrializacao ou uso e consumo. Empresa enquadrada no Lucro Presumido - NCM padrao 72119090."
    contact = Table([[
        _whatsapp_qr(),
        Paragraph("<b>WHATSAPP</b><br/><font size='6'>(54) 99152-5973<br/>(54) 3027-4715<br/>www.danfer.ind.br</font>", styles["body"]),
    ]], colWidths=[17 * mm, 22 * mm])
    footer_info = Table([[
        Paragraph(f"<b>OBSERVACOES GERAIS</b><br/><font size='7'>{escape(notes)}</font>", styles["body"]),
        Paragraph(f"<b>CONDICOES COMERCIAIS</b><br/><font size='7'>{escape(conditions)}</font>", styles["body"]),
        Paragraph(f"<b>ELABORADO POR</b><br/><font size='7'>{escape(quote.prepared_by)}</font>", styles["body"]),
        contact,
    ]], colWidths=[52 * mm, 58 * mm, 30 * mm, 39 * mm])
    footer_info.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]))
    story = [identity, Spacer(1, 2 * mm), commercial, Spacer(1, 3 * mm), Paragraph("ITENS DA PROPOSTA", styles["section"]), items_table, Spacer(1, 3 * mm), financial, Spacer(1, 3 * mm), footer_info]
    document.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return buffer.getvalue()
