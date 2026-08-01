const api = "/api/v1";
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(
  /[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char])
);
const money = value => Number(value || 0).toLocaleString("pt-BR", {
  style: "currency", currency: "BRL"
});
let pendingQuoteItems = [];
let lastDxfDrafts = [];
let quoteMaterialCatalog = [];

async function req(path, options = {}) {
  const response = await fetch(api + path, {
    credentials: "same-origin",
    headers: {"Content-Type":"application/json", ...(options.headers || {})},
    ...options
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw Error(Array.isArray(payload.detail)
      ? payload.detail.map(item => item.msg).join("; ")
      : payload.detail || `Erro ${response.status}`);
  }
  return response.status === 204 ? null : response.json();
}

function table(headers, rows) {
  if (!rows.length) return '<div class="empty">Nenhum registro encontrado</div>';
  return `<table class="table"><thead><tr>${headers.map(item => `<th>${item}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table>`;
}

function pill(value) {
  const green = ["ativa","ativo","concluida","enviado","importado","aprovado"];
  const amber = ["planejada","rascunho","pendente","com_advertencias","em_elaboracao","em_negociacao","aberta"];
  const css = green.includes(value) ? "green" : amber.includes(value) ? "amber" : "";
  return `<span class="pill ${css}">${esc(value).replaceAll("_", " ")}</span>`;
}

async function dashboard() {
  const [industrial, quotes, clients, quality] = await Promise.all([
    req("/dashboard/industrial"),
    req("/commercial/quotes"),
    req("/commercial/clients"),
    req("/quality?resolved=false")
  ]);
  const quoteValue = quotes.reduce((sum, quote) => sum + quote.total, 0);
  const cards = [
    ["Orçamentos", quotes.length],
    ["Carteira", money(quoteValue)],
    ["Clientes", clients.length],
    ["Ordens", industrial.production_orders],
    ["Atrasadas", industrial.overdue_orders],
    ["Qualidade aberta", quality.length]
  ];
  $("#metrics").innerHTML = cards.map(([label, value]) =>
    `<div class="metric"><b>${value}</b><span>${label}</span></div>`
  ).join("");
  $("#orders").innerHTML = table(
    ["OP","Prazo","Prior.","Status"],
    industrial.next_orders.map(order =>
      `<tr><td><b>${esc(order.number)}</b></td><td>${order.due_date}</td><td>${order.priority}</td><td>${pill(order.status)}</td></tr>`
    )
  );
  $("#materials").innerHTML = table(
    ["Material","Esp.","Qtd."],
    industrial.material_demand.map(item =>
      `<tr><td>${esc(item.material || "Não informado")}</td><td>${item.thickness_mm ?? "—"}</td><td><b>${item.total_quantity}</b></td></tr>`
    )
  );
}

async function crm(query = "") {
  const clients = await req("/commercial/clients" + (query ? `?q=${encodeURIComponent(query)}` : ""));
  $("#clients").innerHTML = table(
    ["Cliente","CNPJ / CPF","Contato","Condição","Frete","Status"],
    clients.map(client =>
      `<tr><td><b>${esc(client.name)}</b><br><small>${esc(client.email)}</small></td><td>${esc(client.document || "—")}</td><td>${esc(client.contact || "—")}<br><small>${esc(client.phone)}</small></td><td>${esc(client.payment_terms)}</td><td>${client.freight_type} · ${client.freight_payer}</td><td>${pill(client.active ? "ativo" : "inativo")}</td></tr>`
    )
  );
}

async function quotes() {
  const filter = $("#quote-filter").value;
  const items = await req("/commercial/quotes" + (filter ? `?status=${filter}` : ""));
  const totals = [
    ["Quantidade", items.length],
    ["Valor total", money(items.reduce((sum, quote) => sum + quote.total, 0))],
    ["Margem bruta", money(items.reduce((sum, quote) => sum + quote.gross_profit, 0))],
    ["Aprovados", items.filter(quote => quote.status === "aprovado").length]
  ];
  $("#quote-summary").innerHTML = totals.map(([label, value]) =>
    `<div class="metric"><b>${value}</b><span>${label}</span></div>`
  ).join("");
  $("#quotes-table").innerHTML = table(
    ["Orçamento","Cliente","Tipo","Revisão","Total","Status","Ações"],
    items.map(quote =>
      `<tr><td><b>${esc(quote.number)}</b><br><small>${new Date(quote.created_at).toLocaleDateString("pt-BR")}</small></td><td><code>${quote.client_id.slice(0, 8)}</code></td><td>${esc(quote.type)}</td><td>${esc(quote.revision)}</td><td><b>${money(quote.total)}</b></td><td>${pill(quote.status)}</td><td><a class="action" href="${api}/commercial/quotes/${quote.id}/proposal.pdf" target="_blank">PDF</a> ${quote.status === "em_elaboracao" ? `<button class="action" onclick="moveQuote('${quote.id}','enviado')">Enviar</button>` : ""}${["enviado","em_negociacao"].includes(quote.status) ? `<button class="action" onclick="moveQuote('${quote.id}','aprovado')">Aprovar</button>` : ""}</td></tr>`
    )
  );
}

window.moveQuote = async (id, status) => {
  try {
    await req(`/commercial/quotes/${id}/status`, {
      method: "POST", body: JSON.stringify({status})
    });
    await quotes();
  } catch (error) {
    alert(error.message);
  }
};

async function library(query = "") {
  const data = await req("/technical-library" + (query ? `?q=${encodeURIComponent(query)}` : ""));
  $("#parts").innerHTML = table(
    ["Código","Descrição","Cliente","Material","Rev.","Status"],
    data.items.map(part =>
      `<tr><td><b>${esc(part.danfer_code)}</b><br><small>${esc(part.customer_code)}</small></td><td>${esc(part.title)}</td><td>${esc(part.customer || "—")}</td><td>${esc(part.material || "—")}${part.thickness_mm ? ` · ${part.thickness_mm} mm` : ""}</td><td>${esc(part.revision)}</td><td>${pill(part.status)}</td></tr>`
    )
  );
}

async function bom() {
  // Os catálogos ficam em uma tela própria, mas compartilham a Biblioteca Técnica.
  const data = await req("/boms");
  $("#boms").innerHTML = table(
    ["Produto","Revisão","Componentes","Status"],
    data.map(item =>
      `<tr><td><code>${item.product_id.slice(0,8)}</code></td><td>${esc(item.revision)}</td><td>${item.components.length}</td><td>${pill(item.status)}</td></tr>`
    )
  );
}

async function pcp() {
  const orders = await req("/pcp/orders");
  const groups = [
    ["planejada","Planejadas"],["liberada","Liberadas"],
    ["em_producao","Em produção"],["concluida","Concluídas"]
  ];
  $("#kanban").innerHTML = groups.map(([status, label]) =>
    `<div class="lane"><h3>${label} · ${orders.filter(order => order.status === status).length}</h3>${orders.filter(order => order.status === status).map(order => `<div class="card"><b>${esc(order.number)}</b><small>Prazo ${order.due_date} · ${order.quantity} un</small></div>`).join("")}</div>`
  ).join("");
  const start = $("#capacity-start").value || new Date().toISOString().slice(0,10);
  $("#capacity-start").value = start;
  const capacity = await req(`/pcp/capacity/daily?start=${start}&days=7`);
  $("#capacity-table").innerHTML = table(
    ["Data","Operação","Disponível","Planejado","Uso","Situação"],
    capacity.filter(item => item.planned_minutes || item.overloaded).map(item => `<tr><td>${new Date(item.date + "T12:00:00").toLocaleDateString("pt-BR")}</td><td>${item.operation_erp_code} · ${esc(item.operation)}</td><td>${item.available_minutes} min</td><td><b>${item.planned_minutes} min</b><br><small>${esc(item.orders.join(", "))}</small></td><td>${item.utilization_percent}%</td><td>${pill(item.overloaded ? "sobrecarregada" : "planejada")}</td></tr>`)
  );
  const costs = await Promise.all(orders.map(order => req(`/pcp/orders/${order.id}/costs`)));
  $("#cost-variance-table").innerHTML = table(
    ["OP","Estimado","Realizado","Variação","%"],
    costs.map(item => `<tr><td><b>${esc(item.order_number)}</b></td><td>${money(item.estimated_total_cost)}</td><td>${money(item.actual_total_cost)}</td><td>${money(item.variance_value)}</td><td>${item.variance_percent == null ? "—" : item.variance_percent + "%"}</td></tr>`)
  );
}

async function integrations() {
  const [orders, events] = await Promise.all([
    req("/integrations/orders"), req("/integrations/erp/events")
  ]);
  $("#imports").innerHTML = table(
    ["Empresa","Origem","Pedido","Cliente","Status"],
    orders.map(item => `<tr><td>${esc(item.company_unit).toUpperCase()}</td><td>${esc(item.source)}</td><td>${esc(item.external_id)}</td><td>${esc(item.customer)}</td><td>${pill(item.status)}</td></tr>`)
  );
  $("#erp").innerHTML = table(
    ["Empresa","Entidade","Ação","Tent.","Status / erro"],
    events.map(item => `<tr><td>${esc(item.company_unit).toUpperCase()}</td><td>${esc(item.entity)}</td><td>${esc(item.action)}</td><td>${item.attempts}</td><td>${pill(item.status)}<br><small>${esc(item.last_error)}</small></td></tr>`)
  );
}

async function coordination() {
  const [profiles, requests, messages] = await Promise.all([
    req("/billing/profiles"), req("/requests"), req("/communications/messages")
  ]);
  $("#billing-profiles").innerHTML = profiles.map(item => `<div class="metric"><b>${esc(item.unit).toUpperCase()}</b><span>${esc(item.legal_name)}${item.erp_company_code ? " · ERP " + esc(item.erp_company_code) : ""}</span></div>`).join("");
  $("#requests-table").innerHTML = table(["Número","Assunto","Destino","Prioridade","Status"], requests.map(item => `<tr><td><b>${esc(item.number)}</b><br><small>${esc(item.company_unit).toUpperCase()}</small></td><td>${esc(item.subject)}<br><small>${esc(item.requester)}</small></td><td>${esc(item.target_department)}</td><td>${pill(item.priority)}</td><td>${pill(item.status)}</td></tr>`));
  $("#messages-table").innerHTML = table(["Canal","Destinatário","Mensagem","Status","Ação"], messages.map(item => `<tr><td>${esc(item.channel)}</td><td>${esc(item.recipient)}</td><td>${esc(item.body)}</td><td>${pill(item.status)}</td><td>${item.action_url ? `<a class="action" href="${esc(item.action_url)}" target="_blank" rel="noopener">Abrir</a>` : ""}</td></tr>`));
}

async function quality() {
  const data = await req("/quality");
  $("#quality-table").innerHTML = table(
    ["Tipo","Descrição","OP","Responsável","Custo","Situação","Ação"],
    data.map(item => `<tr><td>${esc(item.type)}</td><td>${esc(item.description)}</td><td>${esc(item.production_order || "—")}</td><td>${esc(item.responsible || "—")}</td><td>${money(item.cost)}</td><td>${pill(item.resolved ? "concluida" : "aberta")}</td><td>${item.resolved ? "" : `<button class="action" onclick="resolveQuality('${item.id}')">Resolver</button>`}</td></tr>`)
  );
}
window.resolveQuality = async id => {
  await req(`/quality/${id}/resolve`, {method:"POST"});
  await quality();
};

async function maintenance() {
  const data = await req("/maintenance");
  $("#maintenance-table").innerHTML = table(
    ["Ordem","Equipamento","Tipo","Data","Responsável","Status"],
    data.map(item => `<tr><td><b>${esc(item.number)}</b></td><td>${esc(item.equipment)}</td><td>${esc(item.type)}</td><td>${item.scheduled_date || "—"}</td><td>${esc(item.responsible || "—")}</td><td>${pill(item.status)}</td></tr>`)
  );
}

const loaders = {dashboard, crm, quotes, library, engineering, bom, pcp, integrations, coordination, quality, maintenance};
document.querySelectorAll("nav button").forEach(button => {
  button.onclick = async () => {
    document.querySelectorAll("nav button,.view").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    $("#" + button.dataset.view).classList.add("active");
    $("#title").textContent = button.querySelector("span").textContent;
    await loaders[button.dataset.view]();
  };
});

function dialogControls(openSelector, dialogSelector, closeSelector) {
  $(openSelector).onclick = () => $(dialogSelector).showModal();
  document.querySelectorAll(closeSelector).forEach(button => {
    button.onclick = () => $(dialogSelector).close();
  });
}
dialogControls("#new", "#dialog", ".close");
dialogControls("#new-client", "#client-dialog", ".close-client");
dialogControls("#new-quote", "#quote-dialog", ".close-quote");
dialogControls("#new-quality", "#quality-dialog", ".close-quality");
dialogControls("#new-maintenance", "#maintenance-dialog", ".close-maintenance");
dialogControls("#new-material", "#material-dialog", ".close-material");
dialogControls("#new-dxf", "#dxf-dialog", ".close-dxf");
dialogControls("#new-nesting", "#nesting-dialog", ".close-nesting");
dialogControls("#new-work-log", "#work-log-dialog", ".close-work-log");
dialogControls("#new-request", "#request-dialog", ".close-request");
dialogControls("#new-message", "#message-dialog", ".close-message");

$("#refresh-capacity").onclick = pcp;
$("#new-work-log").addEventListener("click", async () => {
  const orders = await req("/pcp/orders");
  $("#work-log-order").innerHTML = orders.map(order => `<option value="${order.id}">${esc(order.number)}</option>`).join("");
});

$("#search").oninput = event => library(event.target.value);
$("#client-search").oninput = event => crm(event.target.value);
$("#quote-filter").onchange = quotes;

$("#part-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (data.thickness_mm) data.thickness_mm = Number(data.thickness_mm);
  else delete data.thickness_mm;
  try {
    await req("/technical-library", {method:"POST", body:JSON.stringify(data)});
    $("#dialog").close(); event.target.reset(); await library();
  } catch (error) { $("#error").textContent = error.message; }
};

$("#material-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  ["thickness_mm", "price_per_kg", "density_kg_m3"].forEach(key => data[key] = Number(data[key]));
  try {
    await req("/catalogs/materials", {method:"POST", body:JSON.stringify(data)});
    $("#material-dialog").close(); event.target.reset(); await engineering();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#dxf-form").onsubmit = async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  try {
    const files = [...event.target.elements.dxf_file.files];
    const uploads = await Promise.all(files.map(file => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({filename:file.name, content_base64:String(reader.result).split(",")[1]});
      reader.onerror = reject;
      reader.readAsDataURL(file);
    })));
    const thickness = Number(values.thickness_mm);
    lastDxfDrafts = await req("/engineering/dxf/quote-drafts", {method:"POST", body:JSON.stringify({
      uploads, material:values.material, thickness_mm:thickness,
      material_price_kg:Number(values.material_price_kg || 0)
    })});
    await Promise.all(uploads.map((upload, index) => req("/engineering/dxf/register", {method:"POST", body:JSON.stringify({
      ...upload, danfer_code:`${values.danfer_code}-${String(index + 1).padStart(3, "0")}`,
      customer_code:values.customer_code, customer:values.customer, material:values.material,
      thickness_mm:thickness, revision:values.revision
    })})));
    $("#dxf-dialog").close(); event.target.reset(); await engineering();
    renderDxfDrafts();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

function renderDxfDrafts() {
  $("#dxf-drafts").innerHTML = lastDxfDrafts.length ? table(
    ["Código","Descrição","Qtd.","Peso","Corte","Ação"],
    lastDxfDrafts.map((item, index) => `<tr><td><b>${esc(item.code)}</b></td><td>${esc(item.description)}</td><td>${item.quantity}</td><td>${item.net_weight_kg} kg</td><td>${item.cut_length_mm} mm</td><td>${index === 0 ? '<button class="action" id="use-dxf-drafts">Usar lote no orçamento</button>' : ''}</td></tr>`)
  ) : '<div class="empty">Importe arquivos DXF para preparar itens de orçamento.</div>';
  if ($("#use-dxf-drafts")) $("#use-dxf-drafts").onclick = () => {
    $("#new-quote").click();
    pendingQuoteItems = lastDxfDrafts.map(item => ({...item, margin_percent:30}));
    renderPendingQuoteItems();
  };
}

$("#nesting-form").onsubmit = async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  try {
    const parts = values.parts.split(/\r?\n/).filter(Boolean).map((line, index) => {
      const [code, width, height, quantity = "1"] = line.split(";").map(value => value.trim());
      if (!code || !Number(width) || !Number(height) || !Number(quantity)) throw Error(`Linha ${index + 1} inválida.`);
      return {code, width_mm:Number(width), height_mm:Number(height), quantity:Number(quantity), allow_rotation:true};
    });
    const payload = {parts, gap_mm:Number(values.gap_mm), edge_margin_mm:Number(values.edge_margin_mm), alternative_minimum_gain_percent:Number(values.alternative_minimum_gain_percent)};
    const plan = await req("/engineering/nesting/plan", {method:"POST", body:JSON.stringify(payload)});
    const previewResponse = await fetch(api + "/engineering/nesting/preview.svg", {method:"POST", credentials:"same-origin", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    if (!previewResponse.ok) throw Error("Não foi possível gerar a prévia do nesting.");
    const previewUrl = URL.createObjectURL(await previewResponse.blob());
    $("#nesting-result").innerHTML = `<div class="nesting-summary"><b>${esc(plan.selected_sheet.name)}</b><span>Ocupação ${plan.utilization_percent}% · Perda ${plan.waste_percent}% · ${esc(plan.selection_reason)}</span></div><img class="nesting-preview" src="${previewUrl}" alt="Prévia do nesting"><div class="comparison">${plan.comparison.map(item => `<span>${esc(item.sheet.name)}: ${item.placed_count} posicionadas, ${item.unplaced_count} pendentes, ${item.utilization_percent}%</span>`).join("")}</div>`;
    $("#nesting-dialog").close();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#client-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    await req("/commercial/clients", {method:"POST", body:JSON.stringify(data)});
    $("#client-dialog").close(); event.target.reset(); await crm();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#new-quote").addEventListener("click", async () => {
  pendingQuoteItems = [];
  renderPendingQuoteItems();
  const [clients, materials] = await Promise.all([req("/commercial/clients"), req("/catalogs/materials?active=true")]);
  quoteMaterialCatalog = materials;
  $("#quote-material-options").innerHTML = materials.map(item => `<option value="${esc(item.description)}">${esc(item.erp_code)} · ${item.thickness_mm} mm · ${money(item.price_per_kg)}</option>`).join("");
  $("#quote-client").innerHTML = clients.map(client =>
    `<option value="${client.id}">${esc(client.name)}</option>`
  ).join("");
  const validity = new Date(); validity.setDate(validity.getDate() + 10);
  $("#quote-form [name=valid_until]").value = validity.toISOString().slice(0,10);
});

$("#quote-form [name=item_material]").addEventListener("change", event => {
  const selected = quoteMaterialCatalog.find(item => item.description.toLocaleLowerCase("pt-BR") === event.target.value.toLocaleLowerCase("pt-BR"));
  if (!selected) return;
  $("#quote-form [name=item_thickness]").value = selected.thickness_mm;
  $("#quote-form [name=item_material_price]").value = selected.price_per_kg;
});

function quoteItemFromForm(form) {
  const processes = [];
  if (Number(form.cut_minutes)) processes.push({name:"Corte laser", minutes:Number(form.cut_minutes), hourly_rate:Number(form.cut_rate), external_cost:0});
  if (Number(form.bend_minutes)) processes.push({name:"Dobra", minutes:Number(form.bend_minutes), hourly_rate:Number(form.bend_rate), external_cost:0});
  if (Number(form.roll_value)) processes.push(form.roll_pricing_mode === "peso"
    ? {name:"Calandra", minutes:0, hourly_rate:0, pricing_mode:"peso", weight_rate:Number(form.roll_value), external_cost:0}
    : {name:"Calandra", minutes:Number(form.roll_value), hourly_rate:150, pricing_mode:"tempo", external_cost:0});
  return {
    code:form.item_code, description:form.item_description,
    quantity:Number(form.item_quantity), material:form.item_material,
    thickness_mm:form.item_thickness ? Number(form.item_thickness) : null,
    net_weight_kg:Number(form.item_weight), material_price_kg:Number(form.item_material_price),
    utilization_percent:Number(form.item_utilization), margin_percent:Number(form.item_margin_percent),
    notes:form.item_notes, processes
  };
}

async function engineering() {
  const [materials, operations] = await Promise.all([req("/catalogs/materials"), req("/catalogs/operations")]);
  $("#material-catalog").innerHTML = table(["ERP","Material","Esp.","Preço/kg","Status"], materials.map(item => `<tr><td><b>${esc(item.erp_code)}</b></td><td>${esc(item.description)}<br><small>${esc(item.specification)}</small></td><td>${item.thickness_mm} mm</td><td>${money(item.price_per_kg)}</td><td>${pill(item.active ? "ativo" : "inativo")}</td></tr>`));
  $("#operation-catalog").innerHTML = table(["Código","Operação","Custeio","Valor hora"], operations.map(item => `<tr><td><b>${item.erp_code}</b></td><td>${esc(item.name)}</td><td>${esc(item.pricing_mode)}</td><td>${money(item.hourly_rate)}</td></tr>`));
  renderDxfDrafts();
}

function renderPendingQuoteItems() {
  $("#pending-quote-items").innerHTML = pendingQuoteItems.map((item, index) =>
    `<div class="pending-item"><span><b>${esc(item.code)}</b> · ${esc(item.description)} · ${item.quantity} un</span><button type="button" data-remove-item="${index}">Remover</button></div>`
  ).join("");
  document.querySelectorAll("[data-remove-item]").forEach(button => button.onclick = () => {
    pendingQuoteItems.splice(Number(button.dataset.removeItem), 1);
    renderPendingQuoteItems();
  });
}

$("#add-quote-item").onclick = () => {
  const form = Object.fromEntries(new FormData($("#quote-form")));
  if (!form.item_code || !form.item_description || !Number(form.item_quantity)) {
    $("#quote-form .dialog-error").textContent = "Preencha código, descrição e quantidade do item.";
    return;
  }
  pendingQuoteItems.push(quoteItemFromForm(form));
  renderPendingQuoteItems();
  ["item_code","item_description","item_material","item_thickness","item_notes"].forEach(name => $("#quote-form [name=" + name + "]").value = "");
  $("#quote-form .dialog-error").textContent = "";
};

$("#quote-form").onsubmit = async event => {
  event.preventDefault();
  const form = Object.fromEntries(new FormData(event.target));
  const currentItem = form.item_code && form.item_description ? quoteItemFromForm(form) : null;
  const items = [...pendingQuoteItems, ...(currentItem ? [currentItem] : [])];
  if (!items.length) {
    event.target.querySelector(".dialog-error").textContent = "Adicione pelo menos um item à proposta.";
    return;
  }
  const payload = {
    type:form.type, billing_unit:form.billing_unit, client_id:form.client_id, requester:form.requester,
    prepared_by:form.prepared_by,
    valid_until:form.valid_until, expected_delivery:form.expected_delivery || null,
    payment_terms:form.payment_terms, freight_type:form.freight_type,
    nature_operation:form.nature_operation, tax_scenario:form.tax_scenario,
    margin_percent:Number(form.margin_percent), ipi_percent:Number(form.ipi_percent),
    cbs_percent:Number(form.cbs_percent), ibs_percent:Number(form.ibs_percent),
    discount_value:Number(form.discount_value), observations:form.observations,
    items
  };
  try {
    await req("/commercial/quotes", {method:"POST", body:JSON.stringify(payload)});
    $("#quote-dialog").close(); event.target.reset(); pendingQuoteItems = []; await quotes();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#quality-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  data.cost = Number(data.cost);
  await req("/quality", {method:"POST", body:JSON.stringify(data)});
  $("#quality-dialog").close(); event.target.reset(); await quality();
};

$("#maintenance-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (!data.scheduled_date) delete data.scheduled_date;
  await req("/maintenance", {method:"POST", body:JSON.stringify(data)});
  $("#maintenance-dialog").close(); event.target.reset(); await maintenance();
};

$("#work-log-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  const orderId = data.order_id; delete data.order_id;
  ["minutes", "quantity", "unit_cost"].forEach(key => data[key] = Number(data[key]));
  if (data.operation_erp_code) data.operation_erp_code = Number(data.operation_erp_code); else delete data.operation_erp_code;
  if (data.amount) data.amount = Number(data.amount); else delete data.amount;
  try {
    await req(`/pcp/orders/${orderId}/logs`, {method:"POST", body:JSON.stringify(data)});
    $("#work-log-dialog").close(); event.target.reset(); await pcp();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#request-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (!data.due_date) delete data.due_date;
  try {
    await req("/requests", {method:"POST", body:JSON.stringify(data)});
    $("#request-dialog").close(); event.target.reset(); await coordination();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#message-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    await req("/communications/messages", {method:"POST", body:JSON.stringify(data)});
    $("#message-dialog").close(); event.target.reset(); await coordination();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#login-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    const login = await req("/auth/login", {method:"POST", body:JSON.stringify(data)});
    $("#login-screen").classList.add("hidden");
    $("#status").textContent = `● ${login.user.name}`;
    await dashboard();
  } catch (error) { $("#login-error").textContent = error.message; }
};

(async () => {
  try {
    const user = await req("/auth/me");
    $("#login-screen").classList.add("hidden");
    $("#status").textContent = `● ${user.name}`;
    await dashboard();
  } catch {
    $("#status").textContent = "● Aguardando login";
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js");
})();
