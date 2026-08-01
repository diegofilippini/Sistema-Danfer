const api = "/api/v1";
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(
  /[&<>"']/g,
  char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char])
);
const money = value => Number(value || 0).toLocaleString("pt-BR", {
  style: "currency", currency: "BRL"
});

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
}

async function integrations() {
  const [orders, events] = await Promise.all([
    req("/integrations/orders"), req("/integrations/erp/events")
  ]);
  $("#imports").innerHTML = table(
    ["Origem","Pedido","Cliente","Status"],
    orders.map(item => `<tr><td>${esc(item.source)}</td><td>${esc(item.external_id)}</td><td>${esc(item.customer)}</td><td>${pill(item.status)}</td></tr>`)
  );
  $("#erp").innerHTML = table(
    ["Entidade","Ação","Tent.","Status"],
    events.map(item => `<tr><td>${esc(item.entity)}</td><td>${esc(item.action)}</td><td>${item.attempts}</td><td>${pill(item.status)}</td></tr>`)
  );
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

const loaders = {dashboard, crm, quotes, library, bom, pcp, integrations, quality, maintenance};
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

$("#client-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    await req("/commercial/clients", {method:"POST", body:JSON.stringify(data)});
    $("#client-dialog").close(); event.target.reset(); await crm();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#new-quote").addEventListener("click", async () => {
  const clients = await req("/commercial/clients");
  $("#quote-client").innerHTML = clients.map(client =>
    `<option value="${client.id}">${esc(client.name)}</option>`
  ).join("");
  const validity = new Date(); validity.setDate(validity.getDate() + 10);
  $("#quote-form [name=valid_until]").value = validity.toISOString().slice(0,10);
});

$("#quote-form").onsubmit = async event => {
  event.preventDefault();
  const form = Object.fromEntries(new FormData(event.target));
  const processes = [];
  if (Number(form.cut_minutes)) processes.push({name:"Corte laser", minutes:Number(form.cut_minutes), hourly_rate:Number(form.cut_rate), external_cost:0});
  if (Number(form.bend_minutes)) processes.push({name:"Dobra", minutes:Number(form.bend_minutes), hourly_rate:Number(form.bend_rate), external_cost:0});
  const payload = {
    type:form.type, client_id:form.client_id, requester:form.requester,
    prepared_by:form.prepared_by,
    valid_until:form.valid_until, expected_delivery:form.expected_delivery || null,
    payment_terms:form.payment_terms, freight_type:form.freight_type,
    nature_operation:form.nature_operation, tax_scenario:form.tax_scenario,
    margin_percent:Number(form.margin_percent), ipi_percent:Number(form.ipi_percent),
    cbs_percent:Number(form.cbs_percent), ibs_percent:Number(form.ibs_percent),
    discount_value:Number(form.discount_value), observations:form.observations,
    items:[{
      code:form.item_code, description:form.item_description,
      quantity:Number(form.item_quantity), material:form.item_material,
      thickness_mm:form.item_thickness ? Number(form.item_thickness) : null,
      net_weight_kg:Number(form.item_weight), material_price_kg:Number(form.item_material_price),
      utilization_percent:Number(form.item_utilization),
      margin_percent:Number(form.item_margin_percent), notes:form.item_notes, processes
    }]
  };
  try {
    await req("/commercial/quotes", {method:"POST", body:JSON.stringify(payload)});
    $("#quote-dialog").close(); event.target.reset(); await quotes();
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
