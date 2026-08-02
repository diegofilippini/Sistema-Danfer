from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from danfer_os.models.pcp import ProductionOrder


LOGO = Path(__file__).parent / "static" / "assets" / "v051-oficiais" / "logo_danfer.png"


def _text(canvas: Canvas, x: float, y: float, value: str, size: float = 7, bold: bool = False) -> None:
    canvas.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    canvas.drawString(x, y, str(value))


def _fit(canvas: Canvas, x: float, y: float, value: str, width: float, size: float = 7, bold: bool = False) -> None:
    font = "Helvetica-Bold" if bold else "Helvetica"
    text = str(value)
    while text and stringWidth(text, font, size) > width:
        text = text[:-1]
    if text != str(value):
        text = text[:-2] + "..."
    canvas.setFont(font, size)
    canvas.drawString(x, y, text)


def _box(canvas: Canvas, x: float, y: float, width: float, height: float, line: float = .6) -> None:
    canvas.setLineWidth(line)
    canvas.rect(x, y, width, height, stroke=1, fill=0)


def _order_block(canvas: Canvas, order: ProductionOrder, x: float, y: float, width: float, height: float,
                 item_start: int = 0, max_items: int = 15) -> None:
    pad = 3 * mm
    top = y + height
    _box(canvas, x, y, width, height, .9)
    if LOGO.exists():
        canvas.drawImage(str(LOGO), x + pad, top - 17 * mm, 23 * mm, 13 * mm, preserveAspectRatio=True, mask="auto")
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawCentredString(x + width / 2, top - 8 * mm, "ORDEM DE PRODUÇÃO")
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawCentredString(x + width / 2, top - 12 * mm, "VENDA")
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawRightString(x + width - pad, top - 7 * mm, f"OP Nº  {order.number}")
    canvas.setFont("Helvetica-Bold", 6.5)
    canvas.drawRightString(x + width - pad, top - 12 * mm, f"Orçamento {order.source_quote_number or '-'}")
    canvas.line(x + pad, top - 18 * mm, x + width - pad, top - 18 * mm)

    info_y = top - 43 * mm
    info_h = 21 * mm
    right_w = 34 * mm
    _box(canvas, x + pad, info_y, width - 2 * pad - right_w - 2 * mm, info_h)
    _text(canvas, x + 2 * pad, info_y + info_h - 5 * mm, f"CLIENTE: {order.client_name or '-'}", 6.5, True)
    _text(canvas, x + 2 * pad, info_y + info_h - 10 * mm, "RESPONSÁVEL: PCP", 6.5, True)
    _box(canvas, x + width - pad - right_w, info_y, right_w, info_h)
    canvas.drawCentredString(x + width - pad - right_w / 2, info_y + info_h - 5 * mm, "PRIORIDADE")
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(x + width - pad - right_w / 2, info_y + info_h - 11 * mm, {1:"URGENTE",2:"ALTA",3:"NORMAL",4:"BAIXA",5:"BAIXA"}.get(order.priority,"NORMAL"))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(x + width - pad - right_w / 2, info_y + 3 * mm, order.due_date.strftime("%d/%m/%Y"))

    strip_y = info_y - 10 * mm
    cells = [("MATERIAL", order.material or "-"), ("ESPESSURA", f"{order.thickness_mm:g} mm" if order.thickness_mm is not None else "-"),
             ("QTDE. PEÇAS", f"{order.quantity:g}"), ("PESO TOTAL", f"{sum(i.unit_weight_kg*i.quantity for i in order.production_items):.2f} kg")]
    cell_w = (width - 2 * pad) / 4
    for index, (label, value) in enumerate(cells):
        cx = x + pad + index * cell_w
        _box(canvas, cx, strip_y, cell_w, 8 * mm)
        _fit(canvas, cx + 2 * mm, strip_y + 3 * mm, f"{label}: {value}", cell_w - 4 * mm, 5.8, label != "MATERIAL")

    route_y = strip_y - 11 * mm
    _box(canvas, x + pad, route_y, width - 2 * pad, 9 * mm)
    _text(canvas, x + 2 * pad, route_y + 5 * mm, "PROCESSOS DA ROTA (SEQUÊNCIA)", 7.5, True)
    route_text = "   ".join(f"{i}  [X] {step}" for i, step in enumerate(order.routing_steps, 1)) or "Sem roteiro informado"
    _fit(canvas, x + 2 * pad, route_y + 2 * mm, route_text, width - 4 * pad, 5.5)

    items = order.production_items[item_start:item_start + max_items]
    table_top = route_y - 8 * mm
    _text(canvas, x + pad, table_top + 3 * mm, "ITENS QUE COMPÕEM ESTA OP", 7.5, True)
    row_h = 4.2 * mm
    columns = [10, 31, 65, 15, 24, 25]
    scale = (width - 2 * pad) / (sum(columns) * mm)
    widths = [value * mm * scale for value in columns]
    headers = ["ITEM", "CÓDIGO", "DESCRIÇÃO DA PEÇA", "QTDE.", "PESO UNIT.", "PESO TOTAL"]
    cursor_y = table_top - row_h
    cursor_x = x + pad
    for label, col_w in zip(headers, widths):
        _box(canvas, cursor_x, cursor_y, col_w, row_h)
        _fit(canvas, cursor_x + 1 * mm, cursor_y + 1.4 * mm, label, col_w - 2 * mm, 5.2, True)
        cursor_x += col_w
    for row_index, item in enumerate(items, item_start + 1):
        cursor_y -= row_h
        values = [row_index, item.code, item.description, f"{item.quantity:g}", f"{item.unit_weight_kg:.3f}", f"{item.unit_weight_kg*item.quantity:.3f}"]
        cursor_x = x + pad
        for value, col_w in zip(values, widths):
            _box(canvas, cursor_x, cursor_y, col_w, row_h)
            _fit(canvas, cursor_x + 1 * mm, cursor_y + 1.3 * mm, value, col_w - 2 * mm, 5.2)
            cursor_x += col_w

    follow_top = cursor_y - 7 * mm
    _text(canvas, x + pad, follow_top + 3 * mm, "ACOMPANHAMENTO DE PRODUÇÃO", 7.5, True)
    process_rows = order.routing_steps[:6]
    follow_h = 4.3 * mm
    follow_width = width - 2 * pad - 36 * mm
    fcols = [10, 28, 23, 23, 34, 38, 24]
    fscale = follow_width / (sum(fcols) * mm)
    fwidths = [value * mm * fscale for value in fcols]
    fy = follow_top - follow_h
    fx = x + pad
    for label, col_w in zip(["SEQ.","ETAPA","INÍCIO","TÉRMINO","OPERADOR","MÁQUINA/SETOR","STATUS"], fwidths):
        _box(canvas, fx, fy, col_w, follow_h); _fit(canvas, fx + .7 * mm, fy + 1.4 * mm, label, col_w - mm, 4.8, True); fx += col_w
    for seq, step in enumerate(process_rows, 1):
        fy -= follow_h; fx = x + pad
        for value, col_w in zip([seq, step, "", "", "", "", "[ ]"], fwidths):
            _box(canvas, fx, fy, col_w, follow_h); _fit(canvas, fx + .7 * mm, fy + 1.4 * mm, value, col_w - mm, 4.8); fx += col_w
    dispatch_x = x + width - pad - 34 * mm
    dispatch_y = max(y + 20 * mm, follow_top - 30 * mm)
    _box(canvas, dispatch_x, dispatch_y, 34 * mm, follow_top - dispatch_y)
    _text(canvas, dispatch_x + 2 * mm, follow_top - 5 * mm, "CONFERÊNCIA /", 7, True)
    _text(canvas, dispatch_x + 2 * mm, follow_top - 9 * mm, "EXPEDIÇÃO", 7, True)
    for idx, label in enumerate(["[ ] CONFERIDO", "[ ] EMBALADO", "[ ] EXPEDIDO"]):
        _text(canvas, dispatch_x + 2 * mm, follow_top - (14 + idx * 5) * mm, f"{label}   Data: ___/___/___", 4.8)

    notes_y = y + 8 * mm
    _box(canvas, x + pad, notes_y, width - 2 * pad, 9 * mm)
    _fit(canvas, x + 2 * pad, notes_y + 3.2 * mm, f"OBSERVAÇÕES: {order.notes or 'Sem observações.'}", width - 4 * pad, 5.5, True)


def build_production_orders_pdf(orders: list[ProductionOrder]) -> bytes:
    buffer = BytesIO()
    single = len(orders) == 1
    page_size = landscape(A4) if single else A4
    canvas = Canvas(buffer, pagesize=page_size)
    width, height = page_size
    if single:
        order = orders[0]
        for start in range(0, max(len(order.production_items), 1), 15):
            _order_block(canvas, order, 8 * mm, 8 * mm, width - 16 * mm, height - 16 * mm, start, 15)
            canvas.showPage()
    else:
        blocks = [(order, start) for order in orders for start in range(0, max(len(order.production_items), 1), 15)]
        block_h = (height - 18 * mm) / 2
        for index, (order, start) in enumerate(blocks):
            if index and index % 2 == 0:
                canvas.showPage()
            slot = index % 2
            y = height - 7 * mm - (slot + 1) * block_h - slot * 4 * mm
            _order_block(canvas, order, 7 * mm, y, width - 14 * mm, block_h, start, 15)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()
