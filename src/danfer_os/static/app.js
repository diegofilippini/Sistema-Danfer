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
let routingTemplates = [];
let bendTimeSettings = {one:10,two:5,three:4,four_to_five:3,six_plus:2.5};
let priceTableSession = null;
let quoteSaveMode = "manual";
let quoteDirectoryHandle = null;
let selectedProductionOrders = new Set();
let selectedInvoiceQuotes = new Set();
let invoiceReadyByQuote = new Map();
let editingQuoteItemIndex = null;
let dxfImportTarget = "engineering";
let currentUser = null;
const accessModules = {
  dashboard:"Dashboard", crm:"CRM / Clientes", quotes:"Orçamentos", library:"Biblioteca Técnica",
  engineering:"Engenharia / Inteligência", bom:"Estruturas BOM", pcp:"PCP", integrations:"Integrações",
  coordination:"Status", quality:"Qualidade", maintenance:"Manutenções",
  users:"Usuários", audit:"Auditoria", system:"Backup e restauração"
  ,"quality-dashboard":"Dashboard qualidade", deviations:"Análise de desvios",
  "management-dashboard":"Dashboards gerenciais", "monthly-analysis":"Análise mensal"
};
const roleAccess = {
  administrador:Object.keys(accessModules),
  comercial:["dashboard","crm","quotes","library","engineering","integrations","coordination","management-dashboard"],
  pcp:["dashboard","library","bom","pcp","integrations","coordination","deviations","monthly-analysis"],
  engenharia:["dashboard","library","engineering","bom","coordination"],
  producao:["dashboard","pcp","quality","maintenance","coordination"],
  qualidade:["dashboard","quality","quality-dashboard","deviations","coordination"],
  analista_custos:["dashboard","pcp","engineering","library","deviations","monthly-analysis"],
  consulta:["dashboard","library","management-dashboard"]
};
const quoteUnitPriceHeader=$("#quote-item-entry")?.closest("table")?.querySelector("th:nth-child(12)");
if(quoteUnitPriceHeader)quoteUnitPriceHeader.textContent="Preço Unit";

function effectiveAccess(user=currentUser) {
  if (!user) return [];
  if (user.role === "administrador") return Object.keys(accessModules);
  return Array.isArray(user.permissions) ? user.permissions : (roleAccess[user.role] || []);
}

function applyAccess(user=currentUser) {
  const allowed = effectiveAccess(user);
  document.querySelectorAll("nav button[data-view]").forEach(button => {
    button.hidden = !allowed.includes(button.dataset.view);
  });
}

function requirePasswordChange(user) {
  if (user.must_change_password && !$("#password-dialog").open) $("#password-dialog").showModal();
  return user.must_change_password;
}

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
  if(currentUser?.role==="analista_custos"){
    const [industrial,directRequests]=await Promise.all([req("/dashboard/industrial"),req("/pcp/direct-requests")]);
    $("#metrics").innerHTML=[["Pedidos manuais",directRequests.length],["Ordens",industrial.production_orders],["Atrasadas",industrial.overdue_orders]].map(([label,value])=>`<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
    $("#orders").innerHTML=table(["OP","Prazo","Prior.","Status"],industrial.next_orders.map(order=>`<tr><td><b>${esc(order.number)}</b></td><td>${order.due_date}</td><td>${order.priority}</td><td>${pill(order.status)}</td></tr>`));
    $("#materials").innerHTML=table(["Material","Esp.","Qtd."],industrial.material_demand.map(item=>`<tr><td>${esc(item.material||"Não informado")}</td><td>${item.thickness_mm??"—"}</td><td><b>${item.total_quantity}</b></td></tr>`));
    return;
  }
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
  ensureCrmOpportunities();
  const [clients, opportunities, alerts, productionProgress] = await Promise.all([req("/commercial/clients" + (query ? `?q=${encodeURIComponent(query)}` : "")), req("/crm/opportunities" + (query ? `?q=${encodeURIComponent(query)}` : "")), req("/crm/alerts"), req("/workflows/production-progress")]);
  const progressByClient=new Map(productionProgress.map(item=>[item.client.toLocaleLowerCase("pt-BR"),item]));
  $("#clients").innerHTML = table(
    ["Cliente","Código ERP","CNPJ / CPF","Contato","Condição","Frete","Produção","Status"],
    clients.map(client => {const progress=progressByClient.get(client.name.toLocaleLowerCase("pt-BR"))||{completed:0,total:0,percent:0};return `<tr><td><b>${esc(client.name)}</b><br><small>${esc(client.email)}</small></td><td><b>${esc(client.erp_code || "—")}</b></td><td>${esc(client.document || "—")}</td><td>${esc(client.contact || "—")}<br><small>${esc(client.phone)}</small></td><td>${esc(client.payment_terms)}</td><td>${client.freight_type} · ${client.freight_payer}</td><td>${productionProgressChart(progress)}</td><td>${pill(client.active ? "ativo" : "inativo")}</td></tr>`;
    })
  );
  await loadDeliveryBoard();
}

async function loadDeliveryBoard(){const days=Number($("#delivery-board-period")?.value||7),data=await req(`/dashboard/deliveries?days=${days}`);const root=$("#delivery-board");root.dataset.days=String(days);root.innerHTML=`<div class="delivery-board-grid">${data.columns.map(column=>`<section class="delivery-day ${column.status}"><header><b>${esc(column.label)}</b><small>${esc(column.weekday||"")}</small></header><ol>${column.clients.map(item=>`<li><span>${esc(item.client)}</span><b>${item.total} OP${item.total===1?"":"s"}</b><small>${esc(item.orders.join(", "))}</small></li>`).join("")||"<li class='empty-day'>Sem entregas</li>"}</ol></section>`).join("")}</div>`;return data;}
$("#refresh-delivery-board").onclick=loadDeliveryBoard;
$("#delivery-board-period").onchange=loadDeliveryBoard;
$("#print-delivery-board").onclick=()=>{document.body.classList.add("print-delivery-board");window.print();setTimeout(()=>document.body.classList.remove("print-delivery-board"),500);};
$("#push-delivery-board").onclick=async()=>{const username=prompt("Usuário destinatário (deixe vazio para enviar a todos):","");if(username===null)return;const data=await loadDeliveryBoard(),overdue=data.columns[0].clients.reduce((sum,item)=>sum+item.total,0),today=data.columns[1].clients.reduce((sum,item)=>sum+item.total,0);await req("/notifications",{method:"POST",body:JSON.stringify({title:`Painel de entregas - ${data.days} dias`,message:`${overdue} OP(s) atrasada(s), ${today} entrega(s) para hoje. Abra o Painel do Dia para consultar clientes e datas.`,audience:username?"usuario":"todos",recipient_username:username})});alert(`Painel enviado${username?` para ${username}`:" para todos os usuários"}.`);};
function productionProgressChart(item){const color=item.percent<=20?"red":item.percent<70?"yellow":"green";return `<div class="production-progress ${color}" title="${item.completed} OP(s) concluída(s) de ${item.total}"><div><span style="width:${item.percent}%"></span></div><b>${item.percent}%</b><small>${item.completed} de ${item.total} OPs</small></div>`;}

async function quotes() {
  const filter = $("#quote-filter").value;
  const [items, clients, invoiceReady] = await Promise.all([
    req("/commercial/quotes" + (filter ? `?status=${filter}` : "")),
    req("/commercial/clients"), req("/workflows/invoice-ready")
  ]);
  const clientsById = new Map(clients.map(client => [client.id, client]));
  invoiceReadyByQuote = new Map(invoiceReady.map(item => [item.quote_id, item]));
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
    items.map(quote => {const client=clientsById.get(quote.client_id);return `<tr><td><b>${esc(quote.number)}</b><br><small>${new Date(quote.created_at).toLocaleDateString("pt-BR")}</small></td><td><b>${esc(client?.name||"Cliente não encontrado")}</b><br><small>ERP ${esc(client?.erp_code||"não informado")}</small></td><td>${esc(quote.type)}</td><td>${esc(quote.revision)}</td><td><b>${money(quote.total)}</b><br><small>Margem efetiva: ${Number(quote.effective_margin_percent||0).toFixed(2)}%</small></td><td>${pill(quote.status)}</td><td>${quoteActions(quote)}</td></tr>`;
    })
  );
}

window.moveQuote = async (id, status) => {
  try {
    await req(`/commercial/quotes/${id}/status`, {
      method: "POST", body: JSON.stringify({status})
    });
    if (status === "aprovado") {
      const [,orders]=await Promise.all([req(`/workflows/quotes/${id}/erp-order`, {method:"POST"}),req(`/workflows/quotes/${id}/production-orders`, {method:"POST"})]);
      alert(`${orders.length} OP(s) gerada(s) conforme espessura e roteiro.`);
    }
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
  const [data, libraryData] = await Promise.all([req("/boms"), req("/technical-library")]);
  const parts=new Map(libraryData.items.map(item=>[item.id,item]));
  $("#boms").innerHTML = table(
    ["Produto","Revisão","Componentes","Status","Ações"],
    data.map(item =>
      `<tr><td><b>${esc(parts.get(item.product_id)?.danfer_code||item.product_id.slice(0,8))}</b><br><small>${esc(parts.get(item.product_id)?.title||"")}</small></td><td>${esc(item.revision)}</td><td>${item.components.length}<br><small>${item.components.map(component=>`${esc(parts.get(component.part_id)?.danfer_code||component.part_id.slice(0,8))} × ${component.quantity}`).join(" · ")}</small></td><td>${pill(item.status)}</td><td><button class="action" onclick="explodeBom('${item.id}')">Explodir</button> <button class="cancel" onclick="deleteBom('${item.id}')">Excluir</button></td></tr>`
    )
  );
}
window.explodeBom=async id=>{const quantity=Number(prompt("Quantidade do produto:","1")||1),rows=await req(`/boms/${id}/explosion?quantity=${quantity}`);alert(rows.length?rows.map(row=>`Nível ${row.level}: ${row.part_id.slice(0,8)} — ${row.quantity} ${row.unit}`).join("\n"):"Estrutura sem níveis adicionais.");};
window.deleteBom=async id=>{if(!confirm("Excluir esta estrutura BOM?"))return;await req(`/boms/${id}`,{method:"DELETE"});await bom();};

async function pcp() {
  const [orders, directRequests, invoiceReady] = await Promise.all([req("/pcp/orders"), req("/pcp/direct-requests"), currentUser?.role==="analista_custos"?Promise.resolve([]):req("/workflows/invoice-ready")]);
  invoiceReadyByQuote = new Map(invoiceReady.map(item => [item.quote_id, item]));
  ensurePcpConsolidation();
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
  $("#direct-request-table").innerHTML = table(
    ["Pedido manual","Cliente / ERP","Itens","Processos","Valor","Prazo","Responsável","Status"],
    directRequests.map(item => `<tr><td><b>${esc(item.number)}</b><br><small>${esc(item.customer_order_number||"Sem pedido do cliente")}</small></td><td>${esc(item.client)}<br><small>ERP ${esc(item.customer_erp_code||"não informado")}</small></td><td>${item.items?.length||0}<br><small>${(item.items||[]).map(row=>`${esc(row.code)} · ${row.quantity} ${esc(row.unit)}`).join("<br>")||esc(item.description)}</small></td><td>${item.processes.map(esc).join(" → ")}</td><td>${money(item.total_value)}</td><td>${item.due_date}</td><td>${esc(item.requested_by||"—")}</td><td>${pill(item.status)}</td></tr>`)
  );
  selectedProductionOrders=new Set([...selectedProductionOrders].filter(id=>orders.some(order=>order.id===id)));
  $("#op-archive-table").innerHTML = `<div class="toolbar"><label><input id="select-all-ops" type="checkbox"> Selecionar todas</label><button id="print-selected-ops" type="button">Imprimir OPs selecionadas</button></div>`+table(
    ["Selecionar","OP","Prazo","Prioridade","Quantidade","Status","Ação"],
    orders.map(order => `<tr><td><input class="op-selection" type="checkbox" value="${order.id}" ${selectedProductionOrders.has(order.id)?"checked":""}></td><td><b>${esc(order.number)}</b></td><td>${order.due_date}</td><td>${order.priority}</td><td>${order.quantity}</td><td>${pill(order.status)}</td><td><button class="action" onclick="printProductionOrders(['${order.id}'])">Imprimir OP</button> ${nextOrderAction(order)}</td></tr>`)
  );
  document.querySelectorAll(".op-selection").forEach(input=>input.onchange=()=>{input.checked?selectedProductionOrders.add(input.value):selectedProductionOrders.delete(input.value);});
  $("#select-all-ops").onchange=event=>{document.querySelectorAll(".op-selection").forEach(input=>{input.checked=event.target.checked;input.checked?selectedProductionOrders.add(input.value):selectedProductionOrders.delete(input.value);});};
  $("#print-selected-ops").onclick=()=>{if(!selectedProductionOrders.size)return alert("Selecione pelo menos uma OP.");printProductionOrders([...selectedProductionOrders]);};
  selectedInvoiceQuotes=new Set([...selectedInvoiceQuotes].filter(id=>invoiceReady.some(item=>item.quote_id===id&&item.ready)));
  $("#invoice-release-table").innerHTML=`<div class="toolbar"><label><input id="select-all-invoices" type="checkbox"> Selecionar todos com saldo produzido</label><button id="invoice-selected" type="button">Enviar saldos produzidos selecionados para o ERP</button></div>`+table(["Selecionar","Orçamento","Cliente / ERP","OPs concluídas","Faturamento","Status","Ação"],invoiceReady.map(item=>`<tr><td><input class="invoice-selection" type="checkbox" value="${item.quote_id}" ${item.ready?"":"disabled"} ${selectedInvoiceQuotes.has(item.quote_id)?"checked":""}></td><td><b>${esc(item.quote_number)}</b></td><td>${esc(item.client)}<br><small>ERP ${esc(item.erp_customer_code||"não informado")}</small></td><td>${item.completed}/${item.orders}</td><td>${money(item.invoiced_total)} faturado<br><small>${money(item.remaining_total)} restante</small></td><td>${pill(item.status)}</td><td>${item.ready?`<button class="action" onclick="invoiceQuote('${item.quote_id}')">Selecionar itens</button>`:"—"}</td></tr>`));
  document.querySelectorAll(".invoice-selection").forEach(input=>input.onchange=()=>{input.checked?selectedInvoiceQuotes.add(input.value):selectedInvoiceQuotes.delete(input.value);});
  $("#select-all-invoices").onchange=event=>document.querySelectorAll(".invoice-selection:not(:disabled)").forEach(input=>{input.checked=event.target.checked;input.checked?selectedInvoiceQuotes.add(input.value):selectedInvoiceQuotes.delete(input.value);});
  $("#invoice-selected").onclick=async()=>{if(!selectedInvoiceQuotes.size)return alert("Selecione ao menos um orçamento pronto.");try{await req("/workflows/invoice-batch",{method:"POST",body:JSON.stringify({quote_ids:[...selectedInvoiceQuotes]})});selectedInvoiceQuotes.clear();alert("Orçamentos enviados ao faturamento e marcados como faturados.");await pcp();}catch(error){alert(error.message);}};
  const active = orders.filter(item => !["concluida","cancelada"].includes(item.status));
  $("#operational-flow").innerHTML = [
    ["Pedidos diretos", directRequests.filter(item => item.status !== "concluida").length],
    ["Planejadas", orders.filter(item => item.status === "planejada").length],
    ["Liberadas", orders.filter(item => item.status === "liberada").length],
    ["Em produção", orders.filter(item => item.status === "em_producao").length],
    ["Concluídas", orders.filter(item => item.status === "concluida").length],
    ["Atrasadas", active.filter(item => item.due_date < new Date().toISOString().slice(0,10)).length],
  ].map(([label,value]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
}
function quoteActions(quote){
  let actions=`<a class="action" href="${api}/commercial/quotes/${quote.id}/proposal.pdf" target="_blank">PDF</a> `;
  if(quote.status==="em_elaboracao")actions+=`<button class="action" onclick="moveQuote('${quote.id}','enviado')">Enviar</button>`;
  if(["enviado","em_negociacao"].includes(quote.status))actions+=`<button class="action" onclick="customerProposal('${quote.id}',${quote.total})">Proposta cliente</button> <button class="action" onclick="moveQuote('${quote.id}','aprovado')">Aprovar valor original</button>`;
  if(quote.status==="aguardando_aprovacao_administrativa"){
    const proposal=[...(quote.customer_proposals||[])].reverse().find(item=>item.status==="pendente");
    actions+=proposal?`<small>Cliente: ${money(proposal.proposed_total)} · margem ${Number(proposal.effective_margin_percent).toFixed(2)}%</small> `:"";
    if(proposal&&currentUser?.role==="administrador")actions+=`<button class="action" onclick="decideCustomerProposal('${quote.id}','${proposal.id}',true)">Autorizar</button> <button class="action" onclick="decideCustomerProposal('${quote.id}','${proposal.id}',false)">Recusar</button>`;
  }
  if(quote.status==="aprovado")actions+=`<button class="action" onclick="generateProductionOrders('${quote.id}')">Gerar / consultar OPs</button>`;
  if(invoiceReadyByQuote.get(quote.id)?.ready)actions+=` <button class="action" onclick="invoiceQuote('${quote.id}')">Enviar para faturamento</button>`;
  if(quote.status==="faturado")actions+=` <small>Faturamento já enviado</small>`;
  return actions;
}
window.generateProductionOrders=async id=>{try{const orders=await req(`/workflows/quotes/${id}/production-orders`,{method:"POST"});alert(orders.length?`OPs vinculadas: ${orders.map(item=>item.number).join(", ")}`:"Nenhuma OP gerada. Confira os cadastros técnicos e BOMs.");}catch(error){alert(error.message);}};
window.customerProposal=async(id,currentTotal)=>{const value=Number(prompt(`Valor original: ${money(currentTotal)}\nProposta do cliente (R$):`,String(currentTotal)));if(!value||value>=currentTotal)return alert("Informe um valor menor que o orçamento atual.");const notes=prompt("Observação da negociação:","")||"";try{const updated=await req(`/commercial/quotes/${id}/customer-proposals`,{method:"POST",body:JSON.stringify({proposed_total:value,submitted_by:currentUser?.name||"",notes})});const proposal=updated.customer_proposals.at(-1);alert(`Proposta registrada.\nMargem efetiva: ${proposal.effective_margin_percent.toFixed(2)}%\nMargem mínima: ${proposal.minimum_margin_percent.toFixed(2)}%\nAguardando autorização administrativa.`);await quotes();}catch(error){alert(error.message);}};
window.decideCustomerProposal=async(quoteId,proposalId,approved)=>{const reason=prompt(approved?"Justificativa da autorização:":"Motivo da recusa:");if(!reason)return;try{await req(`/commercial/quotes/${quoteId}/customer-proposals/${proposalId}/decision`,{method:"POST",body:JSON.stringify({approved,decided_by:currentUser?.name||"",reason})});if(approved)await Promise.all([req(`/workflows/quotes/${quoteId}/erp-order`,{method:"POST"}),req(`/workflows/quotes/${quoteId}/production-orders`,{method:"POST"})]);await quotes();}catch(error){alert(error.message);}};

function ensurePcpConsolidation() {
  if ($("#pcp-consolidated")) return;
  const root = $("#pcp");
  const block = document.createElement("div");
  block.id = "pcp-consolidated";
  block.innerHTML = `<div id="operational-flow" class="metrics compact"></div><article><div class="toolbar"><div><h2>Pedidos manuais sem orçamento</h2><small>Entrada direta pelo analista de custos, com rastreabilidade própria.</small></div><button id="new-direct-request">+ Pedido manual</button></div><div id="direct-request-table"></div></article><article><h2>Arquivo e liberação de OPs</h2><div id="op-archive-table"></div></article><article><h2>Liberação para faturamento</h2><p class="muted">Somente orçamentos com todas as OPs concluídas podem ser selecionados.</p><div id="invoice-release-table"></div></article>`;
  root.appendChild(block);
  $("#new-direct-request").onclick = createDirectRequest;
}

function nextOrderAction(order) {
  const next = {planejada:"liberada", liberada:"em_producao", em_producao:"concluida", pausada:"em_producao"}[order.status];
  return next ? `<button class="action" onclick="moveProductionOrder('${order.id}','${next}')">${{liberada:"Liberar",em_producao:"Iniciar",concluida:"Concluir"}[next] || "Retomar"}</button>` : "";
}

window.printProductionOrders=ids=>{const query=ids.map(id=>`ids=${encodeURIComponent(id)}`).join("&");window.open(`${api}/pcp/orders-print.pdf?${query}`,"_blank","noopener");};

window.moveProductionOrder = async (id, status) => {
  await req(`/pcp/orders/${id}`, {method:"PATCH", body:JSON.stringify({status})});
  await pcp();
};
window.invoiceQuote=async id=>{const info=invoiceReadyByQuote.get(id)||await req("/workflows/invoice-ready").then(rows=>rows.find(item=>item.quote_id===id));if(!info)return alert("Orçamento não encontrado para faturamento.");const items=[];for(const item of info.items.filter(row=>row.eligible_quantity>0)){const value=prompt(`${item.code} · ${item.description}\nPedido: ${item.quantity} ${item.unit}\nJá faturado: ${item.invoiced_quantity}\nDisponível produzido: ${item.eligible_quantity}\n\nQuantidade para esta remessa (0 para não enviar):`,String(item.eligible_quantity));if(value===null)return;const quantity=Number(String(value).replace(",","."));if(quantity<0||quantity>item.eligible_quantity)return alert(`Quantidade inválida para ${item.code}.`);if(quantity>0)items.push({item_id:item.item_id,quantity});}if(!items.length)return alert("Nenhum item foi selecionado.");try{await req(`/workflows/quotes/${id}/invoice`,{method:"POST",body:JSON.stringify({items})});alert("Itens enviados ao faturamento. O orçamento permanecerá como faturamento parcial enquanto houver saldo.");await Promise.all([pcp(),quotes()]);}catch(error){alert(error.message);}};

async function createDirectRequest() {
  const form=$("#manual-order-form");form.reset();form.elements.due_date.value=new Date(Date.now()+7*86400000).toISOString().slice(0,10);$("#manual-order-dialog").showModal();
}

$("#manual-order-form").onsubmit=async event=>{event.preventDefault();const form=Object.fromEntries(new FormData(event.target));try{const items=form.items_text.split(/\r?\n/).filter(Boolean).map((line,index)=>{const [code,description,quantity,unit,material,thickness,unitPrice]=line.split(";").map(value=>value.trim());if(!code||!description||!(Number(String(quantity).replace(",","."))>0))throw Error(`Item ${index+1} inválido. Use o formato indicado.`);return{code,description,quantity:Number(String(quantity).replace(",",".")),unit:unit||"un",material:material||"",thickness_mm:thickness?Number(String(thickness).replace(",",".")):null,unit_price:unitPrice?Number(String(unitPrice).replace(",",".")):0};});if(!items.length)throw Error("Informe ao menos um item.");const payload={origin:"pedido_manual_sem_orcamento",client:form.client,customer_erp_code:form.customer_erp_code,contact:form.contact,customer_order_number:form.customer_order_number,description:form.description,processes:form.processes.split(",").map(value=>value.trim()).filter(Boolean),material:form.material,due_date:form.due_date,priority:Number(form.priority),billing_unit:form.billing_unit,reason:form.reason,items};await req("/pcp/direct-requests",{method:"POST",body:JSON.stringify(payload)});$("#manual-order-dialog").close();await pcp();alert("Pedido manual registrado sem geração de orçamento.");}catch(error){event.target.querySelector(".dialog-error").textContent=error.message;}};

async function integrations() {
  const [orders, events, settings, readiness] = await Promise.all([
    req("/integrations/orders"), req("/integrations/erp/events"),
    req("/integrations/erp/settings"), req("/integrations/erp/readiness")
  ]);
  $("#imports").innerHTML = table(
    ["Empresa","Origem","Pedido","Cliente","Status"],
    orders.map(item => `<tr><td>${esc(item.company_unit).toUpperCase()}</td><td>${esc(item.source)}</td><td>${esc(item.external_id)}</td><td>${esc(item.customer)}</td><td>${pill(item.status)}</td></tr>`)
  );
  $("#erp").innerHTML = table(
    ["Empresa","Entidade","Ação","Tent.","Status / erro"],
    events.map(item => `<tr><td>${esc(item.company_unit).toUpperCase()}</td><td>${esc(item.entity)}</td><td>${esc(item.action)}</td><td>${item.attempts}</td><td>${pill(item.status)}<br><small>${esc(item.last_error)}</small></td></tr>`)
  );
  const form=$("#erp-settings-form");
  if(!form.elements.danfer_company_erp_code){form.elements.enabled.closest("label").insertAdjacentHTML("beforebegin",`<label>Empresa Danfer no ERP<input name="danfer_company_erp_code"></label><label>Empresa DF no ERP<input name="df_company_erp_code"></label><label>Série da NFe<input name="invoice_series"></label><label>Modelo fiscal<input name="invoice_model" value="55"></label>`);}
  Object.entries(settings).forEach(([key,value])=>{if(form.elements[key])form.elements[key].value=String(value);});
  $("#erp-readiness").innerHTML=pill(readiness.ready?"pronto":"configuração pendente");
  $("#erp-settings-status").textContent=readiness.pending.length?`Pendências: ${readiness.pending.join(", ")}`:"Contrato pronto para homologação.";
  $("#crm-opportunity-summary").innerHTML = [["Oportunidades",opportunities.length],["Valor",money(opportunities.reduce((sum,item)=>sum+item.value,0))],["Valor ponderado",money(opportunities.reduce((sum,item)=>sum+item.value*item.probability_percent/100,0))],["Alertas ativos",alerts.length]].map(([label,value])=>`<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#crm-alerts").innerHTML = alerts.length ? table(["Prioridade","Negociação","Cliente","Responsável","Alerta","Prazo"], alerts.map(item=>`<tr><td>${pill(item.severity)}</td><td><b>${esc(item.opportunity_number)}</b></td><td>${esc(item.client_name)}</td><td>${esc(item.owner||"—")}</td><td>${esc(item.message)}</td><td>${item.due_date||"—"}</td></tr>`)) : `<p class="muted">Nenhum alerta de CRM pendente.</p>`;
  $("#crm-opportunities").innerHTML = table(["Negociação","Cliente","Etapa","Valor","Probabilidade","Responsável","Próximo contato","Ações"], opportunities.map(item=>`<tr><td><b>${esc(item.number)}</b></td><td>${esc(item.client_name)}</td><td>${pill(item.stage)}</td><td>${money(item.value)}</td><td>${item.probability_percent}%</td><td>${esc(item.owner||"—")}</td><td>${item.next_contact||"—"}</td><td><button class="action" onclick="advanceOpportunity('${item.id}')">Avançar</button> <button class="action" onclick="addCrmActivity('${item.id}')">Atividade</button></td></tr>`));
}

$("#erp-settings-form").onsubmit=async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.target));values.enabled=values.enabled==="true";values.timeout_seconds=30;try{await req("/integrations/erp/settings",{method:"PUT",body:JSON.stringify(values)});await integrations();$("#erp-settings-status").textContent="Configuração ERP salva.";}catch(error){$("#erp-settings-status").textContent=error.message;}};

function ensureCrmOpportunities(){if($("#crm-opportunity-card"))return;const article=document.createElement("article");article.id="crm-opportunity-card";article.innerHTML=`<div class="toolbar"><div><h2>Centro de negociações</h2><small>Funil, atividades e próximos contatos.</small></div><button id="new-opportunity">+ Nova oportunidade</button></div><div id="crm-opportunity-summary" class="metrics compact"></div><h3>Alertas automáticos</h3><div id="crm-alerts"></div><h3>Oportunidades</h3><div id="crm-opportunities"></div>`;$("#crm").appendChild(article);$("#new-opportunity").onclick=createOpportunity;}
async function createOpportunity(){const client_name=prompt("Cliente:");if(!client_name)return;const value=Number(prompt("Valor estimado:","0")||0),owner=prompt("Responsável:",currentUser?.name||"")||"",next_contact=prompt("Próximo contato (AAAA-MM-DD):",new Date(Date.now()+2*86400000).toISOString().slice(0,10));await req("/crm/opportunities",{method:"POST",body:JSON.stringify({client_name,value,owner,next_contact})});await crm();}
window.advanceOpportunity=async id=>{const stages=["em_elaboracao","enviada","em_negociacao","aprovada"],items=await req("/crm/opportunities"),item=items.find(value=>value.id===id);if(!item)return;const next=stages[Math.min(stages.length-1,Math.max(0,stages.indexOf(item.stage)+1))];await req(`/crm/opportunities/${id}`,{method:"PATCH",body:JSON.stringify({stage:next,probability_percent:[10,35,60,100][stages.indexOf(next)]})});await crm();};
window.addCrmActivity=async id=>{const description=prompt("Resumo da atividade:");if(!description)return;const next_contact=prompt("Próximo contato (AAAA-MM-DD):",new Date(Date.now()+2*86400000).toISOString().slice(0,10));await req(`/crm/opportunities/${id}/activities`,{method:"POST",body:JSON.stringify({type:"contato",description,performed_by:currentUser?.name||"",next_contact})});await crm();};

async function coordination() {
  const [profiles, requests, messages] = await Promise.all([
    req("/billing/profiles"), req("/requests"), req("/communications/messages")
  ]);
  $("#billing-profiles").innerHTML = profiles.map(item => `<div class="metric"><b>${esc(item.unit).toUpperCase()}</b><span>${esc(item.legal_name)}${item.erp_company_code ? " · ERP " + esc(item.erp_company_code) : ""}</span></div>`).join("");
  $("#requests-table").innerHTML = table(["Número","Assunto","Destino","Previsão","Prioridade","Status"], requests.map(item => `<tr><td><b>${esc(item.number)}</b><br><small>${esc(item.company_unit).toUpperCase()}</small></td><td>${esc(item.subject)}<br><small>${esc(item.requester)}</small></td><td>${esc(item.target_department)}<br><small>${esc(item.assigned_to)}</small></td><td>${item.promised_date ? new Date(item.promised_date + "T12:00:00").toLocaleDateString("pt-BR") : "—"}</td><td>${pill(item.priority)}</td><td>${pill(item.status)}</td></tr>`));
  $("#messages-table").innerHTML = table(["Canal","Destinatário","Mensagem","Status","Ação"], messages.map(item => `<tr><td>${esc(item.channel)}</td><td>${esc(item.recipient)}</td><td>${esc(item.body)}</td><td>${pill(item.status)}</td><td>${item.action_url ? `<a class="action" href="${esc(item.action_url)}" target="_blank" rel="noopener">Abrir</a>` : ""}</td></tr>`));
}

async function quality() {
  const [data,deviationsData] = await Promise.all([req("/quality"),req("/analytics/deviations")]);
  const byOrder=new Map(deviationsData.map(item=>[item.order_number,item]));
  $("#quality-table").innerHTML = table(
    ["Tipo","Descrição","OP / orçamento","Responsável","Custo","Margem após custo","Situação","Ação"],
    data.map(item => {const impact=byOrder.get(item.production_order);return `<tr><td>${esc(item.type)}</td><td>${esc(item.description)}</td><td><b>${esc(item.production_order || "—")}</b><br><small>${esc(impact?.quote_number||"")}</small></td><td>${esc(item.responsible || "—")}</td><td>${money(item.cost)}</td><td>${impact?.actual_margin_percent==null?"—":impact.actual_margin_percent+"%"}<br><small>${impact?.margin_impact_percent==null?"":`Impacto ${impact.margin_impact_percent}%`}</small></td><td>${pill(item.resolved ? "concluida" : "aberta")}</td><td>${item.resolved ? "" : `<button class="action" onclick="resolveQuality('${item.id}')">Resolver</button>`}</td></tr>`;})
  );
}
window.resolveQuality = async id => {
  await req(`/quality/${id}/resolve`, {method:"POST"});
  await quality();
};

function ensureAnalyticsSections() {
  const main = document.querySelector("main");
  const definitions = {
    "quality-dashboard": `<div class="hero"><p>QUALIDADE</p><h2>Dashboard da qualidade</h2></div><div id="quality-kpis" class="metrics"></div><article><div id="quality-summary-table"></div></article>`,
    deviations: `<div class="hero"><p>CUSTOS</p><h2>Análise de desvios</h2><span>Compara o custo previsto na OP com apontamentos reais de material, processo, terceiros e qualidade. Valores positivos indicam estouro; a margem mostra o efeito sobre o orçamento.</span></div><article><div id="deviation-analysis-table"></div></article>`,
    "management-dashboard": `<div class="hero"><p>GESTÃO</p><h2>Dashboards gerenciais</h2><span>Clique nos indicadores para abrir os dados de origem.</span></div><div id="management-kpis" class="metrics"></div>`,
    "monthly-analysis": `<div class="hero"><p>GESTÃO DE CUSTOS</p><h2>Análise mensal</h2></div><div class="toolbar"><label>Início<input id="monthly-start" type="date"></label><label>Fim<input id="monthly-end" type="date"></label><button id="monthly-refresh">Aplicar filtros</button><button id="monthly-export">Exportar CSV</button></div><div id="monthly-kpis" class="metrics"></div><article><div id="monthly-analysis-table"></div></article>`,
    audit: `<div class="hero"><p>RASTREABILIDADE</p><h2>Auditoria</h2></div><div class="toolbar"><input id="audit-module-filter" placeholder="Filtrar módulo"><button id="audit-refresh">Atualizar</button><button id="audit-export">Exportar CSV</button></div><article><div id="audit-analysis-table"></div></article>`,
  };
  Object.entries(definitions).forEach(([id, html]) => {
    if ($("#" + id)) return;
    const section = document.createElement("section"); section.id = id; section.className = "view"; section.innerHTML = html;
    main.insertBefore(section, $("#maintenance"));
  });
  const today = new Date(), first = new Date(today.getFullYear(), today.getMonth(), 1);
  $("#monthly-start").value ||= first.toISOString().slice(0,10); $("#monthly-end").value ||= today.toISOString().slice(0,10);
  $("#monthly-refresh").onclick = monthlyAnalysis; $("#monthly-export").onclick = exportMonthlyCsv;
  $("#audit-refresh").onclick = auditAnalysis; $("#audit-export").onclick = exportAuditCsv;
}

function ensureGlobalTools(){
  if($("#global-search"))return;
  const header=document.querySelector("main > header"),tools=document.createElement("div");tools.className="global-tools";
  tools.innerHTML=`<div class="global-search-wrap"><input id="global-search" placeholder="Pesquisar cliente, orçamento, OP ou SP"><div id="global-search-results"></div></div><button id="print-current-view" type="button">Imprimir / PDF</button><button id="theme-toggle" type="button" aria-label="Alternar esquema de cores"></button><button id="enable-push" type="button">Ativar avisos</button><button id="notification-center" type="button">Notificações</button>`;
  header.appendChild(tools);
  let timer;$("#global-search").oninput=event=>{clearTimeout(timer);const q=event.target.value.trim();if(q.length<2){$("#global-search-results").innerHTML="";return}timer=setTimeout(async()=>{const data=await req(`/search?q=${encodeURIComponent(q)}`);$("#global-search-results").innerHTML=data.map(item=>`<button type="button" onclick="openGlobalSearchResult('${esc(item.type)}','${esc(item.title)}')"><b>${esc(item.type)} · ${esc(item.title)}</b><small>${esc(item.subtitle)}</small></button>`).join("")||"<small>Nenhum resultado.</small>";},250)};
  $("#notification-center").onclick=showNotifications;
  $("#print-current-view").onclick=printCurrentView;
  $("#theme-toggle").onclick=cycleTheme;
  renderThemeButton();
  $("#enable-push").onclick=enablePushNotifications;
}
function printCurrentView(){const active=document.querySelector(".view.active"),title=active?.querySelector("h2")?.textContent||document.title,previous=document.title;document.title=`Danfer - ${title}`;window.print();setTimeout(()=>document.title=previous,500);}
window.openGlobalSearchResult=async(type,title)=>{const view={cliente:"crm","orçamento":"quotes",OP:"pcp",SP:"pcp","solicitação":"coordination"}[type];if(!view)return;const button=document.querySelector(`nav button[data-view="${view}"]`);if(!button||button.hidden)return alert("Este módulo não está disponível para seu perfil.");await button.onclick();$("#global-search-results").innerHTML="";$("#global-search").value="";setTimeout(()=>{const rows=[...document.querySelectorAll(`#${view} tr`)];const row=rows.find(item=>item.textContent.includes(title));if(row){row.classList.add("search-hit");row.scrollIntoView({behavior:"smooth",block:"center"});setTimeout(()=>row.classList.remove("search-hit"),3000);}},100);};
async function chooseQuoteDirectory(mode){if(!window.showDirectoryPicker)return null;alert(mode==="import"?"Selecione a mesma pasta dos desenhos importados para salvar o orçamento em PDF.":"Selecione a pasta onde este orçamento deverá ser salvo em PDF.");return window.showDirectoryPicker({id:mode==="import"?"imported-quotes":"manual-quotes",mode:"readwrite",startIn:"documents"});}
async function saveQuotePdf(quote,directory){const response=await fetch(`${api}/commercial/quotes/${quote.id}/proposal.pdf`,{credentials:"same-origin"});if(!response.ok)throw Error("Não foi possível gerar o PDF do orçamento.");const blob=await response.blob(),filename=`${quote.number}.pdf`;if(directory){const file=await directory.getFileHandle(filename,{create:true}),writer=await file.createWritable();await writer.write(blob);await writer.close();return `PDF salvo em ${directory.name}\\${filename}`;}const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);return `PDF enviado para Downloads como ${filename}`;}
function resolveTheme(preference){return preference==="auto"?(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):preference;}
function applyTheme(preference){const theme=resolveTheme(preference);document.documentElement.dataset.theme=theme;document.documentElement.dataset.themePreference=preference;localStorage.setItem("danfer-theme",preference);const meta=document.querySelector('meta[name="theme-color"]');if(meta)meta.content=theme==="dark"?"#07131f":"#071a2e";renderThemeButton();}
function renderThemeButton(){const button=$("#theme-toggle");if(!button)return;const preference=document.documentElement.dataset.themePreference||localStorage.getItem("danfer-theme")||"auto";const labels={auto:"◐ Automático",light:"☀ Claro",dark:"☾ Escuro"};button.textContent=labels[preference];button.title=`Tema atual: ${labels[preference]}. Clique para alternar.`;}
function cycleTheme(){const current=document.documentElement.dataset.themePreference||"auto",order=["auto","light","dark"],next=order[(order.indexOf(current)+1)%order.length];applyTheme(next);}
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change",()=>{if((document.documentElement.dataset.themePreference||"auto")==="auto")applyTheme("auto");});
async function showNotifications(){if(!currentUser)return;const data=await req(`/notifications?username=${encodeURIComponent(currentUser.username)}&role=${encodeURIComponent(currentUser.role)}`);alert(data.length?data.slice(0,12).map(item=>`${item.read?"":"• "}${item.title}\n${item.message}`).join("\n\n"):"Nenhuma notificação.");await Promise.all(data.filter(item=>!item.read).map(item=>req(`/notifications/${item.id}/read`,{method:"POST"})));}
function vapidKeyBytes(value){const padding="=".repeat((4-value.length%4)%4),base64=(value+padding).replace(/-/g,"+").replace(/_/g,"/");return Uint8Array.from(atob(base64),character=>character.charCodeAt(0));}
async function enablePushNotifications(){
  if(!currentUser||!("serviceWorker" in navigator)||!("PushManager" in window)){alert("Este navegador não oferece suporte a avisos push.");return;}
  if(!window.isSecureContext){alert("Os avisos push exigem acesso HTTPS ou localhost.");return;}
  const status=await req("/push/status");
  if(!status.available){alert("O servidor ainda não possui as chaves VAPID configuradas. A central interna continua ativa.");return;}
  const permission=await Notification.requestPermission();
  if(permission!=="granted"){alert("Permissão de notificações não concedida.");return;}
  const registration=await navigator.serviceWorker.ready;
  let subscription=await registration.pushManager.getSubscription();
  if(!subscription)subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:vapidKeyBytes(status.public_key)});
  const value=subscription.toJSON();
  await req("/push/subscriptions",{method:"POST",body:JSON.stringify({username:currentUser.username,role:currentUser.role,endpoint:value.endpoint,keys:value.keys})});
  $("#enable-push").textContent="Avisos ativos";
}

function ensureAdminSystemTools(){
  if(currentUser?.role!=="administrador"||$("#system-admin-card"))return;
  const card=document.createElement("article");card.id="system-admin-card";card.innerHTML=`<div class="toolbar"><div><h2>Backup e restauração</h2><small>Cópia completa dos dados persistidos no servidor.</small></div><div><a class="action" href="${api}/system/backup">Baixar backup</a> <label class="action">Restaurar<input id="restore-system-file" type="file" accept=".zip" hidden></label></div></div><p id="system-admin-status"></p>`;$("#maintenance").appendChild(card);$("#restore-system-file").onchange=async event=>{const file=event.target.files[0];if(!file)return;if(!confirm("Restaurar este backup? Uma cópia de segurança será criada antes da alteração."))return;const response=await fetch(api+"/system/restore",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/zip"},body:file});const result=await response.json();$("#system-admin-status").textContent=response.ok?`Restauração concluída. Reinicie o sistema. Backup anterior: ${result.pre_restore_backup}`:(result.detail||"Falha na restauração.");};
}

async function qualityDashboard() {
  const data = await req("/analytics/quality");
  $("#quality-kpis").innerHTML = [["Ocorrências",data.total],["Abertas",data.open],["Resolvidas",data.resolved],["Custo total",money(data.total_cost)]].map(([label,value]) => `<button class="metric dashboard-link" onclick="openDashboardSource('quality')"><b>${value}</b><span>${label}</span><small>Abrir ocorrências</small></button>`).join("");
  $("#quality-summary-table").innerHTML = table(["Tipo","Quantidade"], data.by_type.map(item => `<tr><td>${esc(item.type)}</td><td><b>${item.total}</b></td></tr>`));
}

async function deviations() {
  const data = await req("/analytics/deviations");
  $("#deviation-analysis-table").innerHTML = table(["OP / orçamento","Previsto","Realizado","Desvio","Margem prevista","Margem efetiva","Impacto","Status","Motivo"], data.map(item => `<tr><td><b>${esc(item.order_number)}</b><br><small>${esc(item.quote_number||"")}</small></td><td>${money(item.estimated_total_cost)}</td><td>${money(item.actual_total_cost)}</td><td>${money(item.variance_value)}<br><small>${item.variance_percent ?? "—"}%</small></td><td>${item.estimated_margin_percent==null?"—":item.estimated_margin_percent+"%"}</td><td>${item.actual_margin_percent==null?"—":item.actual_margin_percent+"%"}</td><td>${item.margin_impact_percent==null?"—":item.margin_impact_percent+"%"}</td><td>${pill(item.status)}</td><td>${esc(item.reason)}</td></tr>`));
}

async function managementDashboard() {
  const data = await req("/analytics/management");
  $("#management-kpis").innerHTML = [["Orçamentos",data.quotes,"quotes"],["Aprovados",data.approved_quotes,"quotes"],["Conversão",data.conversion_percent+"%","quotes"],["Receita projetada",money(data.projected_revenue),"quotes"],["OPs ativas",data.active_orders,"pcp"],["OPs atrasadas",data.late_orders,"pcp"],["Custo qualidade",money(data.quality_cost),"quality"]].map(([label,value,view]) => `<button class="metric dashboard-link" onclick="openDashboardSource('${view}')"><b>${value}</b><span>${label}</span><small>Apurar dados</small></button>`).join("");
}
window.openDashboardSource=async view=>{const button=document.querySelector(`nav button[data-view="${view}"]`);if(button&&!button.hidden)await button.onclick();};

let lastMonthlyRows = [], lastAuditRows = [];
async function monthlyAnalysis() {
  const data = await req(`/analytics/monthly?start=${$("#monthly-start").value}&end=${$("#monthly-end").value}`); lastMonthlyRows = data.rows;
  $("#monthly-kpis").innerHTML = [["Ordens",data.orders],["Previsto",money(data.estimated)],["Realizado",money(data.actual)],["Desvio",money(data.variance)]].map(([label,value]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#monthly-analysis-table").innerHTML = table(["OP","Data","Status","Previsto","Realizado","Desvio","%"], data.rows.map(item => `<tr><td><b>${esc(item.order)}</b></td><td>${item.date}</td><td>${pill(item.status)}</td><td>${money(item.estimated)}</td><td>${money(item.actual)}</td><td>${money(item.variance)}</td><td>${item.variance_percent ?? "—"}</td></tr>`));
}
async function auditAnalysis() { const module = $("#audit-module-filter").value.trim(); lastAuditRows = await req("/audit" + (module ? `?module=${encodeURIComponent(module)}` : "")); $("#audit-analysis-table").innerHTML = table(["Data","Módulo","Ação","Entidade","Detalhes"], lastAuditRows.map(item => `<tr><td>${new Date(item.created_at).toLocaleString("pt-BR")}</td><td>${esc(item.module)}</td><td>${esc(item.action)}</td><td>${esc(item.entity_id)}</td><td>${esc(item.details)}</td></tr>`)); }
function downloadCsv(name, headers, rows) { const csv = [headers,...rows].map(row => row.map(value => `"${String(value ?? "").replaceAll('"','""')}"`).join(";")).join("\n"); const link=document.createElement("a"); link.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"})); link.download=name; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000); }
function exportMonthlyCsv(){downloadCsv("analise_mensal_danfer.csv",["OP","Data","Status","Previsto","Realizado","Desvio","Percentual"],lastMonthlyRows.map(item=>[item.order,item.date,item.status,item.estimated,item.actual,item.variance,item.variance_percent]));}
function exportAuditCsv(){downloadCsv("auditoria_danfer.csv",["Data","Módulo","Ação","Entidade","Detalhes"],lastAuditRows.map(item=>[item.created_at,item.module,item.action,item.entity_id,item.details]));}

async function renderUserAccess() {
  let card = $("#user-access-card");
  if (!card) {
    card = document.createElement("article");
    card.id = "user-access-card";
    card.innerHTML = `<div class="toolbar"><div><h2>Usuários e permissões</h2><small>Perfil, situação e módulos liberados por usuário.</small></div></div><div id="user-access-table"></div>`;
    $("#maintenance").insertBefore(card, $("#maintenance-table").closest("article"));
  }
  card.hidden = currentUser?.role !== "administrador";
  if (card.hidden) return;
  const users = await req("/auth/users");
  $("#user-access-table").innerHTML = users.map(user => {
    const selected = new Set(Array.isArray(user.permissions) ? user.permissions : (roleAccess[user.role] || []));
    const checks = Object.entries(accessModules).map(([key,label]) => `<label class="form-check"><input type="checkbox" data-user-permission="${key}" ${selected.has(key) ? "checked" : ""} ${user.role === "administrador" ? "disabled" : ""}> ${esc(label)}</label>`).join("");
    return `<section class="user-access-row" data-user-id="${user.id}"><div class="toolbar"><div><b>${esc(user.name)}</b><br><small>${esc(user.username)}</small></div><div><select data-user-role ${user.role === "administrador" ? "disabled" : ""}>${Object.keys(roleAccess).map(role => `<option value="${role}" ${role === user.role ? "selected" : ""}>${role}</option>`).join("")}</select> <label><input type="checkbox" data-user-active ${user.active ? "checked" : ""} ${user.role === "administrador" ? "disabled" : ""}> Ativo</label></div></div><div class="permission-grid">${checks}</div><button type="button" data-save-user-access ${user.role === "administrador" ? "disabled" : ""}>Salvar acessos</button></section>`;
  }).join("");
  document.querySelectorAll("[data-save-user-access]").forEach(button => button.onclick = async () => {
    const row = button.closest("[data-user-id]");
    const permissions = [...row.querySelectorAll("[data-user-permission]:checked")].map(input => input.dataset.userPermission);
    await req(`/auth/users/${row.dataset.userId}`, {method:"PATCH", body:JSON.stringify({role:row.querySelector("[data-user-role]").value, active:row.querySelector("[data-user-active]").checked, permissions})});
    button.textContent = "Acessos salvos";
    setTimeout(() => button.textContent = "Salvar acessos", 1600);
  });
}

async function maintenance() {
  const data = await req("/maintenance");
  const settingsCard = $("#cost-settings-card");
  settingsCard.hidden = currentUser?.role !== "administrador";
  $("#routing-settings-card").hidden = currentUser?.role !== "administrador";
  if (currentUser?.role === "administrador") {
    await renderCrmAlertSettings();
    const form = $("#cost-settings-form");
    const nestingFields = [
      ["default_nesting_gap_mm", "Folga padrão nesting (mm)"],
      ["alternative_sheet_width_mm", "Largura chapa alternativa (mm)"],
      ["alternative_sheet_length_mm", "Comprimento chapa alternativa (mm)"],
      ["alternative_minimum_gain_percent", "Ganho mínimo alternativa (%)"],
      ["default_laser_cutting_speed_mm_min", "Velocidade padrão do laser (mm/min)"],
      ["default_laser_piercing_seconds", "Tempo padrão por perfuração (s)"],
      ["minimum_effective_margin_percent", "Margem efetiva mínima para propostas (%)"],
      ["bend_time_1_piece_minutes", "Dobra padrão — 1 peça (min/peça)"],
      ["bend_time_2_pieces_minutes", "Dobra padrão — 2 peças (min/peça)"],
      ["bend_time_3_pieces_minutes", "Dobra padrão — 3 peças (min/peça)"],
      ["bend_time_4_to_5_pieces_minutes", "Dobra padrão — 4 a 5 peças (min/peça)"],
      ["bend_time_6_plus_pieces_minutes", "Dobra sugerida — 6 ou mais (min/peça)"],
      ["sale_industrialization_price_review_days", "Revisão — venda para industrialização (dias)"],
      ["sale_consumption_price_review_days", "Revisão — venda para uso e consumo (dias)"],
      ["industrialization_price_review_days", "Revisão — industrialização (dias)"],
      ["third_party_material_price_review_days", "Revisão — material de terceiros (dias)"],
    ];
    const action = form.querySelector(".wide");
    nestingFields.forEach(([name, label]) => {
      if (form.elements[name]) return;
      const field = document.createElement("label");
      field.textContent = label;
      field.innerHTML += `<input name="${name}" type="number" min="0" step=".1">`;
      form.insertBefore(field, action);
    });
    const settings = await req("/commercial/settings/costs");
    Object.entries(settings).forEach(([name, value]) => {
      if (form.elements[name] && typeof value !== "object") form.elements[name].value = typeof value === "boolean" ? Number(value) : value;
    });
    routingTemplates = await req("/catalogs/routing-templates");
    $("#routing-template-table").innerHTML = table(
      ["Roteiro", "Sequência", "Status"],
      routingTemplates.map(item => `<tr><td><b>${esc(item.name)}</b><br><small>${esc(item.description)}</small></td><td>${item.steps.map(step => `${step.operation_erp_code} · ${esc(step.process)} (${step.default_minutes} min)`).join(" → ")}</td><td>${pill(item.active ? "ativo" : "inativo")}</td></tr>`)
    );
    await renderOperationCostSettings();
    await renderMaterialCostSettings();
    await renderRecoveredMaintenance();
    await renderPriceReviewCenter();
  }
  await renderUserAccess();
  ensureAdminSystemTools();
  renderMaintenanceSubmenus();
  $("#maintenance-table").innerHTML = table(
    ["Ordem","Equipamento","Tipo","Data","Responsável","Status"],
    data.map(item => `<tr><td><b>${esc(item.number)}</b></td><td>${esc(item.equipment)}</td><td>${esc(item.type)}</td><td>${item.scheduled_date || "—"}</td><td>${esc(item.responsible || "—")}</td><td>${pill(item.status)}</td></tr>`)
  );
}

ensureAnalyticsSections();
ensureGlobalTools();
const loaders = {dashboard, crm, quotes, library, engineering, bom, pcp, integrations, coordination, quality, maintenance, "quality-dashboard":qualityDashboard, deviations, "management-dashboard":managementDashboard, "monthly-analysis":monthlyAnalysis, audit:auditAnalysis};
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
  const opener = $(openSelector);
  if (opener) opener.onclick = () => $(dialogSelector).showModal();
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
dialogControls("#import-price-table", "#price-table-dialog", ".close-price-table");
dialogControls("#new-dxf", "#dxf-dialog", ".close-dxf");
if ($("#new-dxf")) $("#new-dxf").addEventListener("click",async()=>{dxfImportTarget="engineering";await populateDxfMaterials();});
$("#import-quote-dxf").onclick=async()=>{dxfImportTarget="quote";await populateDxfMaterials();$("#quote-dialog").close();$("#dxf-dialog").showModal();};
document.querySelectorAll(".close-dxf").forEach(button=>button.addEventListener("click",()=>{if(dxfImportTarget==="quote"&&!$("#quote-dialog").open)$("#quote-dialog").showModal();}));
async function populateDxfMaterials(){if(!quoteMaterialCatalog.length)quoteMaterialCatalog=await req("/catalogs/quote-materials");$("#dxf-material").innerHTML='<option value="">Selecionar material…</option>'+quoteMaterialCatalog.map(item=>`<option value="${item.id}">${esc(item.description)} · ${item.thickness_mm} mm</option>`).join("");}
let pdfReturnToQuote=false;
$("#new-pdf-drawing").onclick=()=>{pdfReturnToQuote=$("#quote-dialog").open;if(pdfReturnToQuote)$("#quote-dialog").close();$("#pdf-drawing-dialog").showModal();};
document.querySelectorAll(".close-pdf-drawing").forEach(button=>button.onclick=()=>{$("#pdf-drawing-dialog").close();if(pdfReturnToQuote)$("#quote-dialog").showModal();});
dialogControls("#new-nesting", "#nesting-dialog", ".close-nesting");
document.querySelectorAll(".close-bom").forEach(button=>button.onclick=()=>$("#bom-dialog").close());
$("#new-bom").onclick=async()=>{const data=await req("/technical-library");$("#bom-product").innerHTML=data.items.map(item=>`<option value="${item.id}">${esc(item.danfer_code)} — ${esc(item.title)}</option>`).join("");$("#bom-dialog").showModal();};
$("#new-quality").addEventListener("click",async()=>{const orders=await req("/pcp/orders");$("#quality-production-order").innerHTML=orders.map(order=>`<option value="${esc(order.number)}">${esc(order.number)} — ${esc(order.client_name||"Sem cliente")}</option>`).join("");});
dialogControls("#new-work-log", "#work-log-dialog", ".close-work-log");
document.querySelectorAll(".close-manual-order").forEach(button=>button.onclick=()=>$("#manual-order-dialog").close());
document.querySelectorAll(".close-invoiced-history").forEach(button=>button.onclick=()=>$("#invoiced-history-dialog").close());
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
  ["thickness_mm", "price_per_kg", "density_kg_m3", "unit_conversion_factor"].forEach(key => data[key] = Number(data[key]));
  try {
    await req("/catalogs/materials", {method:"POST", body:JSON.stringify(data)});
    $("#material-dialog").close(); event.target.reset(); await engineering();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

let analyzedPdfDrawing=null;
$("#analyze-pdf-drawing").onclick=async()=>{const form=$("#pdf-drawing-form"),file=form.elements.pdf_file.files[0];if(!file)return form.querySelector(".dialog-error").textContent="Selecione um arquivo PDF.";try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(",")[1]);reader.onerror=reject;reader.readAsDataURL(file);});analyzedPdfDrawing=await req("/engineering/pdf/analyze",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:content})});if(analyzedPdfDrawing.width_mm)form.elements.width_mm.value=analyzedPdfDrawing.width_mm;if(analyzedPdfDrawing.height_mm)form.elements.height_mm.value=analyzedPdfDrawing.height_mm;if(!form.elements.description.value)form.elements.description.value=file.name.replace(/\.pdf$/i,"");$("#pdf-drawing-analysis").innerHTML=`<div class="notice"><b>${esc(analyzedPdfDrawing.source_type)} · ${analyzedPdfDrawing.page_count} página(s)</b><p>${analyzedPdfDrawing.dimensions.length?analyzedPdfDrawing.dimensions.map(item=>`${esc(item.kind)}: ${item.value_mm} mm (${item.confidence_percent}% confiança)`).join(" · "):"Nenhuma cota reconhecida automaticamente."}</p>${analyzedPdfDrawing.warnings.map(item=>`<small>⚠ ${esc(item)}</small>`).join("<br>")}</div>`;$("#use-pdf-drawing").disabled=false;form.querySelector(".dialog-error").textContent="";}catch(error){form.querySelector(".dialog-error").textContent=error.message;}};
$("#pdf-drawing-form").onsubmit=async event=>{event.preventDefault();const form=Object.fromEntries(new FormData(event.target));if(!analyzedPdfDrawing)return event.target.querySelector(".dialog-error").textContent="Analise o PDF antes de aplicar.";try{const item=await req("/engineering/pdf/confirm-quote-item",{method:"POST",body:JSON.stringify({filename:analyzedPdfDrawing.filename,code:form.code,description:form.description,quantity:Number(form.quantity),material:form.material,thickness_mm:Number(form.thickness_mm),width_mm:Number(form.width_mm),height_mm:Number(form.height_mm),cut_length_mm:form.cut_length_mm?Number(form.cut_length_mm):null,confirmed:form.confirmed==="true"})});pendingQuoteItems.push({...item,margin_percent:30});$("#pdf-drawing-dialog").close();$("#quote-dialog").showModal();renderPendingQuoteItems();analyzedPdfDrawing=null;pdfReturnToQuote=false;event.target.reset();}catch(error){event.target.querySelector(".dialog-error").textContent=error.message;}};

$("#dxf-form").onsubmit = async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  try {
    const files = [...event.target.elements.dxf_file.files,...event.target.elements.dxf_folder.files].filter((file,index,all)=>file.name.toLocaleLowerCase().endsWith(".dxf")&&all.findIndex(other=>other.name===file.name&&other.size===file.size)===index);
    if(!files.length)throw Error("Selecione pelo menos um arquivo DXF ou uma pasta com desenhos.");
    const uploads = await Promise.all(files.map(file => new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({filename:file.name, content_base64:String(reader.result).split(",")[1]});
      reader.onerror = reject;
      reader.readAsDataURL(file);
    })));
    const selectedMaterial=quoteMaterialCatalog.find(item=>item.id===values.material_id);
    if(!selectedMaterial)throw Error("Selecione o material e a espessura configurados nas Manutenções.");
    const thickness = Number(selectedMaterial.thickness_mm);
    lastDxfDrafts = await req("/engineering/dxf/quote-drafts", {method:"POST", body:JSON.stringify({
      uploads, material_id:values.material_id, material:selectedMaterial.description, thickness_mm:thickness
    })});
    await Promise.all(uploads.map((upload, index) => req("/engineering/dxf/register", {method:"POST", body:JSON.stringify({
      ...upload, danfer_code:`${values.danfer_code}-${String(index + 1).padStart(3, "0")}`,
      customer_code:values.customer_code, customer:values.customer, material:selectedMaterial.description,
      thickness_mm:thickness, revision:values.revision
    })})));
    $("#dxf-dialog").close(); event.target.reset();
    if(dxfImportTarget==="quote"){
      pendingQuoteItems.push(...lastDxfDrafts.map(item=>({...item,margin_percent:30,material_id:values.material_id})));
      renderPendingQuoteItems();$("#quote-dialog").showModal();
    }else{await engineering();renderDxfDrafts();}
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

function renderDxfDrafts() {
  $("#dxf-drafts").innerHTML = lastDxfDrafts.length ? table(
    ["Código","Descrição","Qtd.","Peso","Corte","Ação"],
    lastDxfDrafts.map((item, index) => `<tr><td><b>${esc(item.code)}</b></td><td>${esc(item.description)}</td><td>${item.quantity}</td><td>${item.net_weight_kg} kg</td><td>${item.cut_length_mm} mm</td><td>${index === 0 ? '<button class="action" id="use-dxf-drafts">Usar lote no orçamento</button>' : ''}</td></tr>`)
  ) : '<div class="empty">Importe arquivos DXF para preparar itens de orçamento.</div>';
  if ($("#use-dxf-drafts")) $("#use-dxf-drafts").onclick = () => {
    $("#new-quote").click();
    quoteSaveMode = "import";
    pendingQuoteItems = lastDxfDrafts.map(item => ({...item, margin_percent:30}));
    renderPendingQuoteItems();
  };
}

function renderMaintenanceSubmenus(){const root=$("#maintenance"),orders=$("#maintenance-table")?.closest("article");if(orders)orders.id="maintenance-orders-card";let nav=$("#maintenance-submenus");if(!nav){nav=document.createElement("div");nav.id="maintenance-submenus";nav.className="maintenance-submenus";root.querySelector(":scope > .toolbar").insertAdjacentElement("afterend",nav);}const groups=[
  ["commercial","Comercial e custos",["cost-settings-card","price-review-center"]],
  ["production","Produção e roteiros",["routing-settings-card","operation-cost-settings-card","recovered-maintenance-card"]],
  ["materials","Materiais e nesting",["material-cost-settings-card"]],
  ["crm","CRM e alertas",["crm-alert-settings-card"]],
  ["users","Usuários e permissões",["user-access-card"]],
  ["system","Sistema e backup",["system-admin-card"]],
  ["orders","Ordens de manutenção",["maintenance-orders-card"]],
];const active=nav.dataset.active||"commercial";nav.innerHTML=groups.map(([key,label])=>`<button type="button" data-maint-group="${key}" class="${key===active?"active":""}">${label}</button>`).join("");const show=key=>{nav.dataset.active=key;nav.querySelectorAll("button").forEach(button=>button.classList.toggle("active",button.dataset.maintGroup===key));groups.forEach(([group,,ids])=>ids.forEach(id=>{const card=$("#"+id);if(card)card.hidden=group!==key;}));};nav.querySelectorAll("button").forEach(button=>button.onclick=()=>show(button.dataset.maintGroup));show(active);}

async function renderOperationCostSettings(){let card=$("#operation-cost-settings-card");if(!card){card=document.createElement("article");card.id="operation-cost-settings-card";card.innerHTML=`<div class="toolbar"><div><h2>Centros de trabalho e valores por processo</h2><small>Valores administrativos aplicados automaticamente aos novos cálculos.</small></div></div><div id="operation-cost-settings"></div>`;$("#maintenance").insertBefore(card,$("#routing-settings-card"));}const operations=await req("/catalogs/operations");$("#operation-cost-settings").innerHTML=table(["ERP","Processo","Método","Valor","Unidade","Ação"],operations.map(item=>`<tr data-operation-code="${item.erp_code}"><td>${item.erp_code}</td><td><input data-operation-name value="${esc(item.name)}"></td><td><select data-operation-mode><option value="tempo" ${item.pricing_mode==="tempo"?"selected":""}>Tempo</option><option value="peso" ${item.pricing_mode==="peso"?"selected":""}>Peso</option><option value="fixo" ${item.pricing_mode==="fixo"?"selected":""}>Fixo</option></select></td><td><input data-operation-rate type="number" min="0" step=".01" value="${item.pricing_mode==="peso"?item.weight_rate:item.pricing_mode==="fixo"?item.fixed_cost:item.hourly_rate}"></td><td data-operation-unit>${item.pricing_mode==="peso"?"R$/kg":item.pricing_mode==="fixo"?"R$/operação":"R$/h"}</td><td><button type="button" data-save-operation>Salvar</button></td></tr>`));document.querySelectorAll("[data-operation-mode]").forEach(select=>select.onchange=()=>{select.closest("tr").querySelector("[data-operation-unit]").textContent=select.value==="peso"?"R$/kg":select.value==="fixo"?"R$/operação":"R$/h";});document.querySelectorAll("[data-save-operation]").forEach(button=>button.onclick=async()=>{const row=button.closest("tr"),mode=row.querySelector("[data-operation-mode]").value,rate=Number(row.querySelector("[data-operation-rate]").value),payload={name:row.querySelector("[data-operation-name]").value,pricing_mode:mode,hourly_rate:mode==="tempo"?rate:0,weight_rate:mode==="peso"?rate:0,fixed_cost:mode==="fixo"?rate:0};await req(`/catalogs/operations/${row.dataset.operationCode}`,{method:"PATCH",body:JSON.stringify(payload)});button.textContent="Salvo";setTimeout(()=>button.textContent="Salvar",1200);});}

async function renderMaterialCostSettings(){let card=$("#material-cost-settings-card");if(!card){card=document.createElement("article");card.id="material-cost-settings-card";card.innerHTML=`<div class="toolbar"><div><h2>Materiais e parâmetros de corte</h2><small>Preço, densidade e velocidades configuráveis por espessura.</small></div><div><button id="add-material-setting" type="button">+ Adicionar linha</button> <button id="export-material-settings" type="button">Exportar CSV</button></div></div><div id="material-cost-settings" class="wide-admin-table"></div>`;$("#maintenance").insertBefore(card,$("#operation-cost-settings-card"));}const materials=await req("/catalogs/materials");const row=item=>`<tr data-material-id="${item.id||""}"><td><input data-mat-description value="${esc(item.description||"")}" placeholder="Material"></td><td><input data-mat-thickness type="number" min=".01" step=".01" value="${item.thickness_mm||""}"></td><td><input data-mat-density type="number" min="1" step="1" value="${item.density_kg_m3||7850}"></td><td><input data-mat-price type="number" min="0" step=".01" value="${item.price_per_kg??""}"></td><td><input data-mat-laser type="number" min="0" step=".1" value="${item.laser_speed_mm_min||0}"></td><td><input data-mat-plasma type="number" min="0" step=".1" value="${item.plasma_speed_mm_min||0}"></td><td><input data-mat-spec value="${esc(item.specification||"")}"></td><td><input data-mat-erp value="${esc(item.erp_code||"")}" placeholder="ERP"></td><td><label><input data-mat-active type="checkbox" ${item.active!==false?"checked":""}> Ativo</label></td><td><button type="button" data-save-material>${item.id?"Salvar":"Criar"}</button> ${item.id?'<button type="button" class="cancel" data-delete-material>Excluir</button>':""}</td></tr>`;const render=()=>{$("#material-cost-settings").innerHTML=table(["Material","Esp. mm","Densidade kg/m³","R$/kg","Laser mm/min","Plasma mm/min","Especificação","ERP","Status","Ações"],materials.map(row));bind();};const payload=current=>({erp_code:current.querySelector("[data-mat-erp]").value,description:current.querySelector("[data-mat-description]").value,specification:current.querySelector("[data-mat-spec]").value,thickness_mm:Number(current.querySelector("[data-mat-thickness]").value),price_per_kg:Number(current.querySelector("[data-mat-price]").value),density_kg_m3:Number(current.querySelector("[data-mat-density]").value),laser_speed_mm_min:Number(current.querySelector("[data-mat-laser]").value),plasma_speed_mm_min:Number(current.querySelector("[data-mat-plasma]").value),active:current.querySelector("[data-mat-active]").checked});const bind=()=>{document.querySelectorAll("[data-save-material]").forEach(button=>button.onclick=async()=>{const current=button.closest("tr"),id=current.dataset.materialId;await req(id?`/catalogs/materials/${id}`:"/catalogs/materials",{method:id?"PATCH":"POST",body:JSON.stringify(payload(current))});await renderMaterialCostSettings();});document.querySelectorAll("[data-delete-material]").forEach(button=>button.onclick=async()=>{if(!confirm("Excluir este material da tabela?"))return;await req(`/catalogs/materials/${button.closest("tr").dataset.materialId}`,{method:"DELETE"});await renderMaterialCostSettings();});};render();$("#add-material-setting").onclick=()=>{materials.push({id:"",density_kg_m3:7850,active:true,laser_speed_mm_min:0,plasma_speed_mm_min:0});render();};$("#export-material-settings").onclick=()=>{const headers=["ERP","Material","Especificação","Espessura mm","Densidade kg/m3","Preço kg","Laser mm/min","Plasma mm/min","Ativo"],lines=[headers,...materials.filter(item=>item.id).map(item=>[item.erp_code,item.description,item.specification,item.thickness_mm,item.density_kg_m3,item.price_per_kg,item.laser_speed_mm_min,item.plasma_speed_mm_min,item.active?"sim":"não"])],blob=new Blob([lines.map(values=>values.map(value=>`"${String(value??"").replaceAll('"','""')}"`).join(";")).join("\n")],{type:"text/csv;charset=utf-8"}),link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download="materiais-danfer.csv";link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);};}

async function renderCrmAlertSettings() {
  let card = $("#crm-alert-settings-card");
  if (!card) {
    card = document.createElement("article");
    card.id = "crm-alert-settings-card";
    card.innerHTML = `<h2>Alertas do CRM</h2><small>Regras automáticas para acompanhamento comercial.</small><form id="crm-alert-settings-form" class="form-grid"><label>Alertas ativos<select name="enabled"><option value="true">Sim</option><option value="false">Não</option></select></label><label>Dias sem interação no orçamento<input name="stale_quote_days" type="number" min="1" max="90" required></label><label>Antecedência do próximo contato (dias)<input name="upcoming_contact_days" type="number" min="0" max="30" required></label><div class="wide"><button>Salvar alertas</button> <span id="crm-alert-settings-status"></span></div></form>`;
    $("#maintenance").appendChild(card);
    $("#crm-alert-settings-form").onsubmit = async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.target));
      const saved = await req("/crm/alert-settings", {method:"PUT", body:JSON.stringify({enabled:values.enabled === "true", stale_quote_days:Number(values.stale_quote_days), upcoming_contact_days:Number(values.upcoming_contact_days)})});
      $("#crm-alert-settings-status").textContent = `Salvo: ${saved.stale_quote_days} dia(s) sem interação.`;
    };
  }
  const settings = await req("/crm/alert-settings");
  const form = $("#crm-alert-settings-form");
  form.elements.enabled.value = String(settings.enabled);
  form.elements.stale_quote_days.value = settings.stale_quote_days;
  form.elements.upcoming_contact_days.value = settings.upcoming_contact_days;
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
    const payload = {parts};
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
  data.credit_limit=Number(data.credit_limit||0);
  try {
    await req("/commercial/clients", {method:"POST", body:JSON.stringify(data)});
    $("#client-dialog").close(); event.target.reset(); await crm();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#new-quote").addEventListener("click", async () => {
  quoteSaveMode = "manual";
  quoteDirectoryHandle = null;
  pendingQuoteItems = [];
  editingQuoteItemIndex = null;
  renderPendingQuoteItems();
  const [clients, materials, templates, bendTimes, paymentTerms] = await Promise.all([
    req("/commercial/clients"), req("/catalogs/quote-materials"),
    req("/catalogs/quote-routing-templates"), req("/commercial/quote-bend-times"),
    req("/maintenance-config/paymentTerms")
  ]);
  quoteMaterialCatalog = materials;
  routingTemplates = templates;
  bendTimeSettings = bendTimes;
  $("#quote-material-options").innerHTML = '<option value="">Selecionar material…</option>' + materials.map(item => `<option value="${item.id}">${esc(item.description)} · ${item.thickness_mm} mm</option>`).join("");
  const activePaymentTerms=paymentTerms.filter(item=>String(item.ativo||"Sim").toLocaleLowerCase("pt-BR")!=="não");
  $("#quote-payment-terms").innerHTML=activePaymentTerms.map(item=>`<option value="${esc(item.descricao)}">${esc(item.descricao)}</option>`).join("");
  const defaultPayment=activePaymentTerms.find(item=>String(item.codigo).toLocaleUpperCase("pt-BR")==="28DDL")||activePaymentTerms[0];
  if(defaultPayment) $("#quote-payment-terms").value=defaultPayment.descricao;
  $("#quote-client").innerHTML = clients.map(client =>
    `<option value="${client.id}">${client.erp_code ? esc(client.erp_code) + " — " : ""}${esc(client.name)}</option>`
  ).join("");
  $("#quote-routing-template").innerHTML = '<option value="">Selecionar roteiro…</option>' + templates.map(template => `<option value="${template.id}">${esc(template.name)}</option>`).join("");
  const validity = new Date(); validity.setDate(validity.getDate() + 10);
  $("#quote-form [name=valid_until]").value = validity.toISOString().slice(0,10);
  const delivery = new Date(); delivery.setDate(delivery.getDate() + 7);
  $("#quote-form [name=expected_delivery]").value = delivery.toISOString().slice(0,10);
  $("#quote-form [name=freight_type]").value = "FOB";
  renderPendingQuoteItems();
});

$("#quote-form [name=item_material_id]").addEventListener("change", event => {
  const selected = quoteMaterialCatalog.find(item => item.id === event.target.value);
  if (!selected) return;
  $("#quote-form [name=item_thickness]").value = selected.thickness_mm;
});

function quoteItemFromForm(form) {
  const template = routingTemplates.find(item => item.id === form.routing_template_id);
  const selectedMaterial = quoteMaterialCatalog.find(item => item.id === form.item_material_id);
  const processes = (template?.steps || []).map((step, index) => ({
    name:step.process,
    minutes:Number(form[`process_minutes_${index}`] || step.default_minutes),
    hourly_rate:0,
    external_cost:0
  }));
  return {
    code:form.item_code, description:form.item_description,
    quantity:Number(form.item_quantity), material:selectedMaterial?.description || "",
    material_id:selectedMaterial?.id || null,
    thickness_mm:selectedMaterial?.thickness_mm ?? (form.item_thickness ? Number(form.item_thickness) : null),
    width_mm:form.item_width ? Number(form.item_width) : null,
    length_mm:form.item_length ? Number(form.item_length) : null,
    net_weight_kg:Number(form.item_weight),
    cut_length_mm:Number(form.item_cut_length || 0),
    piercings:Number(form.item_piercings || 0),
    laser_estimated_minutes:Number(form.laser_estimated_minutes || 0),
    laser_additional_minutes:Number(form.laser_additional_minutes || 0),
    laser_additional_reason:form.laser_additional_reason || "",
    bend_estimated_minutes:Number(form.bend_estimated_minutes || 0),
    bend_additional_minutes:Number(form.bend_additional_minutes || 0),
    bend_additional_reason:form.bend_additional_reason || "",
    nesting_mode:form.nesting_mode,
    utilization_percent:form.nesting_mode === "forcar_ncav" && form.item_utilization ? Number(form.item_utilization) : undefined,
    margin_percent:Number(form.item_margin_percent),
    notes:form.item_notes, processes,
    routing_template_id:form.routing_template_id || null,
    routing_template_name:template?.name || "Sem roteiro"
  };
}

async function engineering() {
  const params=new URLSearchParams();
  [["q","engineering-search"],["process","engineering-process"],["min_weight_kg","engineering-min-weight"],["max_weight_kg","engineering-max-weight"],["min_actual_minutes","engineering-min-time"],["max_actual_minutes","engineering-max-time"]].forEach(([key,id])=>{const value=$("#"+id)?.value.trim();if(value)params.set(key,value);});
  const rows=await req("/workflows/engineering-intelligence?"+params.toString());
  $("#engineering-library").innerHTML=rows.length?table(["Item","Cliente / origem","Processos validados","Qtd.","Peso","Tempo real","Custo real da OP","Conclusão"],rows.map(item=>`<tr><td><b>${esc(item.code)}</b><br><small>${esc(item.description)}</small></td><td>${esc(item.client||"—")}<br><small>OP ${esc(item.order_number)} · Orçamento ${esc(item.quote_number||"—")}</small></td><td>${item.processes.map(process=>pill(process)).join(" ")}</td><td>${item.quantity}</td><td>${item.total_weight_kg} kg<br><small>${item.unit_weight_kg} kg/un.</small></td><td><b>${item.actual_minutes} min</b><br><small>${item.actual_minutes_per_unit} min/un.</small></td><td>${money(item.actual_order_cost)}</td><td>${new Date(item.completed_at).toLocaleDateString("pt-BR")}</td></tr>`)):'<div class="empty">Nenhum item concluído atende aos filtros. A biblioteca só aprende com OPs encerradas e com tempo real apontado.</div>';
}
$("#engineering-apply").onclick=engineering;
$("#engineering-clear").onclick=()=>{["engineering-search","engineering-process","engineering-min-weight","engineering-max-weight","engineering-min-time","engineering-max-time"].forEach(id=>$("#"+id).value="");engineering();};

function fileBase64(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(",",2)[1]);reader.onerror=()=>reject(reader.error);reader.readAsDataURL(file);});}
function guessPriceColumn(columns,terms){return columns.find(column=>terms.some(term=>column.toLocaleLowerCase("pt-BR").includes(term)))||"";}
$("#preview-price-table").onclick=async()=>{const form=$("#price-table-form"),file=form.elements.price_file.files[0];if(!file)return alert("Selecione a tabela de preços.");try{const preview=await req("/catalogs/materials/price-table/preview",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:await fileBase64(file),header_row:Number(form.elements.header_row.value||1)})});priceTableSession=preview.session_id;const optional='<option value="">Não utilizar</option>',options=preview.columns.map(column=>`<option value="${esc(column)}">${esc(column)}</option>`).join("");["erp_code_column","price_column"].forEach(name=>form.elements[name].innerHTML=options);["description_column","thickness_column","specification_column","density_column"].forEach(name=>form.elements[name].innerHTML=optional+options);form.elements.erp_code_column.value=guessPriceColumn(preview.columns,["erp","codigo","código","cod."]);form.elements.price_column.value=guessPriceColumn(preview.columns,["preço","preco","price","valor"]);form.elements.description_column.value=guessPriceColumn(preview.columns,["descrição","descricao","material","produto"]);form.elements.thickness_column.value=guessPriceColumn(preview.columns,["espessura","thickness","mm"]);form.elements.specification_column.value=guessPriceColumn(preview.columns,["especificação","especificacao","spec"]);form.elements.density_column.value=guessPriceColumn(preview.columns,["densidade","density"]);$("#price-table-preview").innerHTML=`<p><b>${preview.total_rows}</b> linhas encontradas. Confira o mapeamento antes de gravar.</p>${table(preview.columns,preview.rows.slice(0,8).map(row=>`<tr>${row.map(cell=>`<td>${esc(cell)}</td>`).join("")}</tr>`))}`;$("#apply-price-table").disabled=false;}catch(error){form.querySelector(".dialog-error").textContent=error.message;}};
$("#price-table-form").onsubmit=async event=>{event.preventDefault();if(!priceTableSession)return;const form=Object.fromEntries(new FormData(event.target));if(!confirm("Confirmar a criação/atualização dos preços apresentados?"))return;try{const result=await req(`/catalogs/materials/price-table/${priceTableSession}/apply`,{method:"POST",body:JSON.stringify({erp_code_column:form.erp_code_column,price_column:form.price_column,description_column:form.description_column,thickness_column:form.thickness_column,specification_column:form.specification_column,density_column:form.density_column,create_missing:form.create_missing==="true"})});alert(`Importação concluída.\nCriados: ${result.created}\nAtualizados: ${result.updated}\nSem alteração: ${result.unchanged}\nInválidos: ${result.invalid}${result.errors.length?"\n\n"+result.errors.slice(0,8).join("\n"):""}`);$("#price-table-dialog").close();event.target.reset();priceTableSession=null;$("#apply-price-table").disabled=true;await engineering();}catch(error){event.target.querySelector(".dialog-error").textContent=error.message;}};

function renderPendingQuoteItems() {
  const materialOptions=item=>quoteMaterialCatalog.map(material=>`<option value="${material.id}" ${material.id===(item.material_id||quoteMaterialCatalog.find(candidate=>candidate.description===item.material&&Number(candidate.thickness_mm)===Number(item.thickness_mm))?.id)?"selected":""}>${esc(material.description)} · ${material.thickness_mm} mm</option>`).join("");
  const routeOptions=item=>'<option value="">Sem roteiro</option>'+routingTemplates.map(route=>`<option value="${route.id}" ${route.id===item.routing_template_id?"selected":""}>${esc(route.name)}</option>`).join("");
  const nestingOptions=item=>[["automatico","Automático"],["forcar_ncav","NcAv"],["desabilitado","Desabilitado"]].map(([value,label])=>`<option value="${value}" ${value===(item.nesting_mode||"automatico")?"selected":""}>${label}</option>`).join("");
  const hasLaser=item=>(item.processes||[]).some(process=>process.name.toLocaleLowerCase("pt-BR").includes("laser"))||String(item.routing_template_name||"").toLocaleLowerCase("pt-BR").includes("laser");
  $("#pending-quote-items").innerHTML = pendingQuoteItems.map((item, index) => `<tr><td>${index + 1}</td><td><input data-inline-code="${index}" value="${esc(item.code)}"></td><td><input data-inline-description="${index}" value="${esc(item.description)}"></td><td><input data-inline-quantity="${index}" type="number" min=".01" step=".01" value="${item.quantity}"></td><td><select data-inline-material="${index}">${materialOptions(item)}</select></td><td><input data-inline-width="${index}" type="number" min="0" step=".1" value="${item.width_mm||""}"></td><td><input data-inline-length="${index}" type="number" min="0" step=".1" value="${item.length_mm||""}"></td><td><input data-inline-margin="${index}" type="number" min="0" max="99.99" step=".1" value="${item.margin_percent??30}"></td><td><select data-inline-nesting="${index}">${nestingOptions(item)}</select></td><td><select data-inline-route="${index}">${routeOptions(item)}</select></td><td><input data-inline-laser-additional="${index}" type="number" min="0" step=".1" value="${item.laser_additional_minutes||0}" ${hasLaser(item)?"":"disabled"}></td><td class="quote-price-cell" title="${item.unit_price?`Unitário: ${money(item.unit_price)}`:"Preço calculado ao incluir"}">${item.total_price!==undefined?money(item.total_price):"Calculando…"}</td><td class="quote-row-actions"><button type="button" class="icon-action update" data-update-inline="${index}" title="Atualizar item" aria-label="Atualizar item">↻</button><button type="button" class="icon-action" data-edit-item="${index}" title="Editar detalhes" aria-label="Editar detalhes">✎</button><button type="button" class="icon-action danger" data-remove-item="${index}" title="Excluir item" aria-label="Excluir item">×</button></td></tr>`).join("");
  const quantity = pendingQuoteItems.reduce((sum, item) => sum + Number(item.quantity), 0);
  $("#quote-item-count").textContent = pendingQuoteItems.length;
  $("#quote-summary-count").textContent = pendingQuoteItems.length;
  $("#quote-summary-quantity").textContent = quantity.toLocaleString("pt-BR");
  $("#quote-summary-delivery").textContent = $("#quote-form [name=expected_delivery]").value || "—";
  document.querySelectorAll("[data-remove-item]").forEach(button => button.onclick = () => {
    pendingQuoteItems.splice(Number(button.dataset.removeItem), 1);
    resetQuoteItemEditor();
    renderPendingQuoteItems();
  });
  document.querySelectorAll("[data-edit-item]").forEach(button => button.onclick = () => editQuoteItem(Number(button.dataset.editItem)));
  document.querySelectorAll("[data-update-inline]").forEach(button=>button.onclick=()=>{const index=Number(button.dataset.updateInline),item=pendingQuoteItems[index],material=quoteMaterialCatalog.find(value=>value.id===$(`[data-inline-material="${index}"]`).value),route=routingTemplates.find(value=>value.id===$(`[data-inline-route="${index}"]`).value);item.code=$(`[data-inline-code="${index}"]`).value;item.description=$(`[data-inline-description="${index}"]`).value;item.quantity=Number($(`[data-inline-quantity="${index}"]`).value);item.width_mm=Number($(`[data-inline-width="${index}"]`).value)||null;item.length_mm=Number($(`[data-inline-length="${index}"]`).value)||null;item.margin_percent=Number($(`[data-inline-margin="${index}"]`).value);item.nesting_mode=$(`[data-inline-nesting="${index}"]`).value;item.laser_additional_minutes=Number($(`[data-inline-laser-additional="${index}"]`).value)||0;item.net_weight_kg=0;item.cut_length_mm=0;item.laser_estimated_minutes=0;if(material){item.material_id=material.id;item.material=material.description;item.thickness_mm=material.thickness_mm;}if(route&&route.id!==item.routing_template_id){item.routing_template_id=route.id;item.routing_template_name=route.name;item.processes=route.steps.map(step=>({name:step.process,minutes:Number(step.default_minutes),hourly_rate:0,external_cost:0}));}renderPendingQuoteItems();});
  document.querySelectorAll("[data-update-inline]").forEach(button=>button.addEventListener("click",()=>setTimeout(refreshPendingPrices,0)));
  document.querySelectorAll("[data-remove-item]").forEach(button=>button.addEventListener("click",()=>setTimeout(refreshPendingPrices,0)));
}

function renderProcessTimes(templateId, values = [], item = {}) {
  const template = routingTemplates.find(value => value.id === templateId);
  const hasLaser = template?.steps.some(step => step.process.toLocaleLowerCase("pt-BR").includes("laser"));
  const laserInput=$("#quote-laser-additional");
  laserInput.disabled=!hasLaser;
  laserInput.value=hasLaser?(item.laser_additional_minutes||laserInput.value||0):0;
  const laserFields = hasLaser ? `<small class="span-2 muted">O perímetro e o tempo-base são calculados automaticamente. Na grade, preencha somente um eventual tempo adicional de laser.</small>` : "";
  const hasBend = template?.steps.some(step => step.process.toLocaleLowerCase("pt-BR").includes("dobra"));
  const quantity = Number(item.quantity || $("#quote-form [name=item_quantity]").value || 1);
  const bendSuggested = quantity<=1?bendTimeSettings.one:quantity<=2?bendTimeSettings.two:quantity<=3?bendTimeSettings.three:quantity<=5?bendTimeSettings.four_to_five:bendTimeSettings.six_plus;
  const bendEstimate = item.bend_estimated_minutes || bendSuggested;
  const bendFields = hasBend ? `<label>Tempo padrão de dobra por peça (min)<input name="bend_estimated_minutes" type="number" min="0" step=".1" value="${bendEstimate}" ${quantity<6?"readonly":""}></label><label>Dobra adicional por peça (min)<input name="bend_additional_minutes" type="number" min="0" step=".1" value="${item.bend_additional_minutes || 0}"></label><label class="span-2">Motivo da dobra adicional<input name="bend_additional_reason" value="${esc(item.bend_additional_reason || "")}" placeholder="Ex.: geometria complexa, múltiplas regulagens ou conferência especial"></label><small class="span-2 muted">Sugestão para ${quantity} peça(s): ${bendSuggested} min por peça. Em lotes de 6 ou mais, o tempo-base pode ser ajustado pelo orçamentista.</small>` : "";
  $("#quote-process-times").innerHTML = template ? `<div class="process-time-grid">${template.steps.map((step,index) => step.process.toLocaleLowerCase("pt-BR").includes("laser")?"":`<label>${step.operation_erp_code} · ${esc(step.process)} (min)<input name="process_minutes_${index}" type="number" min="0" step=".1" value="${values.find(value=>value.name===step.process)?.minutes ?? (step.process.toLocaleLowerCase("pt-BR").includes("dobra")?bendEstimate:step.default_minutes)}"></label>`).join("")}${laserFields}${bendFields}</div>` : '<small class="muted">Selecione um roteiro para incluir os processos no cálculo.</small>';
}

function resetQuoteItemEditor() {
  editingQuoteItemIndex = null;
  $("#add-quote-item").textContent = "＋";
  $("#add-quote-item").title = "Incluir no orçamento";
  $("#add-quote-item").setAttribute("aria-label","Incluir no orçamento");
  $("#cancel-item-edit").classList.add("hidden");
  ["item_code","item_description","item_material_id","item_thickness","item_weight","item_width","item_length","item_notes","item_utilization"].forEach(name => $("#quote-form [name=" + name + "]").value = "");
  $("#quote-form [name=item_quantity]").value = 1;
  $("#quote-form [name=item_margin_percent]").value = 30;
  $("#quote-form [name=nesting_mode]").value = "automatico";
  $("#quote-form [name=routing_template_id]").value = "";
  $("#quote-laser-additional").value = 0;
  $("#quote-laser-additional").disabled = true;
  $("#quote-routing-search").value = "";
  $(".ncav-field").classList.add("hidden");
  renderProcessTimes("");
}

function editQuoteItem(index) {
  const item = pendingQuoteItems[index];
  editingQuoteItemIndex = index;
  const form = $("#quote-form");
  const materialId=item.material_id||quoteMaterialCatalog.find(material=>material.description===item.material&&Number(material.thickness_mm)===Number(item.thickness_mm))?.id||"";
  const values = {item_code:item.code,item_description:item.description,item_quantity:item.quantity,item_material_id:materialId,item_thickness:item.thickness_mm,item_weight:item.net_weight_kg,item_width:item.width_mm,item_length:item.length_mm,item_margin_percent:item.margin_percent,item_utilization:item.utilization_percent,item_notes:item.notes,nesting_mode:item.nesting_mode,routing_template_id:item.routing_template_id};
  Object.entries(values).forEach(([name, value]) => { if (form.elements[name]) form.elements[name].value = value ?? ""; });
  $("#add-quote-item").textContent = "↻";
  $("#add-quote-item").title = `Atualizar item ${index + 1}`;
  $("#add-quote-item").setAttribute("aria-label",`Atualizar item ${index + 1}`);
  $("#cancel-item-edit").classList.remove("hidden");
  $(".ncav-field").classList.toggle("hidden", item.nesting_mode !== "forcar_ncav");
  renderProcessTimes(item.routing_template_id, item.processes, item);
}

$("#quote-routing-template").onchange = event => renderProcessTimes(event.target.value);
function routingInitials(name){return name.split("+").map(part=>part.trim()[0]||"").join("").toLocaleUpperCase("pt-BR");}
$("#quote-routing-search").oninput=event=>{const query=event.target.value.trim().toLocaleUpperCase("pt-BR");if(!query)return;const matches=routingTemplates.filter(template=>routingInitials(template.name).startsWith(query)||template.name.toLocaleUpperCase("pt-BR").startsWith(query));if(matches.length===1||matches.some(template=>routingInitials(template.name)===query)){const selected=matches.find(template=>routingInitials(template.name)===query)||matches[0];$("#quote-routing-template").value=selected.id;renderProcessTimes(selected.id);}};
function syncCommercialOperation(){const operation=$("#quote-commercial-operation").value,isService=operation==="industrializacao"||operation==="industrializacao_material_terceiros";$("#quote-form").elements.type.value=isService?"servico":"venda";$("#consult-service-history").disabled=!isService;$("#service-history-suggestion").innerHTML=isService?'<small class="muted">A consulta usará somente OPs concluídas com tempo real.</small>':'<small class="muted">Venda possui cálculo previsível; o histórico consultivo é reservado aos serviços.</small>';}
$("#quote-commercial-operation").onchange=syncCommercialOperation;
syncCommercialOperation();
$("#consult-service-history").onclick=async()=>{const form=$("#quote-form"),template=routingTemplates.find(item=>item.id===form.elements.routing_template_id.value),quantity=Number(form.elements.item_quantity.value),unitWeight=Number(form.elements.item_weight.value);if(!template||!quantity)return $("#service-history-suggestion").innerHTML='<div class="notice">Informe quantidade e selecione um roteiro para consultar.</div>';try{const result=await req("/workflows/service-price-suggestion",{method:"POST",body:JSON.stringify({commercial_operation:form.elements.commercial_operation.value,quantity,total_weight_kg:quantity*unitWeight,routing_steps:template.steps.map(step=>step.process)})});$("#service-history-suggestion").innerHTML=result.sample_count?`<div class="notice"><b>Sugestão histórica: ${money(result.suggested_value)}</b><p>${result.sample_count} OP(s) concluída(s) · ${result.suggested_minutes} min reais médios · confiança ${result.confidence_percent}%</p><small>Faixa cobrada: ${money(result.minimum_value)} a ${money(result.maximum_value)}. Consulta apenas; nenhum valor foi aplicado automaticamente.</small></div>`:`<div class="notice"><b>Sem amostra suficiente</b><p>${esc(result.reason)}</p></div>`;}catch(error){$("#service-history-suggestion").innerHTML=`<div class="notice">${esc(error.message)}</div>`;}};
$("#consult-invoiced-history").onclick=async()=>{const code=$("#quote-form").elements.item_code.value.trim();if(!code)return alert("Informe o código do item para consultar o histórico faturado.");try{const result=await req(`/workflows/invoiced-cost-history?item_code=${encodeURIComponent(code)}`);const summary=result.sample_count?`<div class="metrics compact"><div class="metric"><b>${result.sample_count}</b><span>Faturamentos</span></div><div class="metric"><b>${result.total_invoiced_quantity}</b><span>Quantidade faturada</span></div><div class="metric"><b>${money(result.weighted_unit_cost)}</b><span>Custo unitário médio</span></div><div class="metric"><b>${money(result.suggested_unit_price)}</b><span>Preço sugerido · margem ${result.standard_margin_percent}%</span></div></div>`:`<div class="empty">Nenhum faturamento registrado para o item ${esc(code)}.</div>`;const history=result.sample_count?table(["Data / remessa","Orçamento","Cliente / ERP","Quantidade","Custo estimado","Custo real","Preço cobrado","Margem efetiva"],result.history.map(row=>`<tr><td>${new Date(row.invoiced_at).toLocaleString("pt-BR")}<br><small>Remessa ${row.invoice_sequence}</small></td><td><b>${esc(row.quote_number)}</b></td><td>${esc(row.client)}<br><small>ERP ${esc(row.erp_customer_code||"não informado")}</small></td><td>${row.quantity} ${esc(row.unit)}</td><td>${money(row.estimated_unit_cost)}</td><td>${money(row.actual_unit_cost)}</td><td><b>${money(row.unit_price)}</b></td><td>${Number(row.effective_margin_percent).toFixed(2)}%</td></tr>`)):"";$("#invoiced-history-content").innerHTML=summary+history;$("#invoiced-history-dialog").showModal();}catch(error){alert(error.message);}};
$("#quote-nesting-mode").onchange = event => $(".ncav-field").classList.toggle("hidden", event.target.value !== "forcar_ncav");
$("#quote-form [name=expected_delivery]").onchange = renderPendingQuoteItems;
$("#cancel-item-edit").onclick = resetQuoteItemEditor;

function currentQuotePayload(items=pendingQuoteItems){
  const form=Object.fromEntries(new FormData($("#quote-form")));
  return {type:form.type,commercial_operation:form.commercial_operation,billing_unit:form.billing_unit,client_id:form.client_id,requester:form.requester,prepared_by:form.prepared_by,valid_until:form.valid_until,expected_delivery:form.expected_delivery||null,payment_terms:form.payment_terms,freight_type:form.freight_type,discount_value:Number(form.discount_value||0),observations:form.observations,items};
}
async function refreshPendingPrices(){
  if(!pendingQuoteItems.length)return;
  try{
    const preview=await req("/commercial/quotes/preview",{method:"POST",body:JSON.stringify(currentQuotePayload())});
    pendingQuoteItems=pendingQuoteItems.map((item,index)=>({...item,unit_price:preview.items[index].unit_price,total_price:preview.items[index].unit_price,line_total_price:preview.items[index].total_price,total_cost:preview.items[index].total_cost}));
    $("#quote-entry-price").textContent="—";
    renderPendingQuoteItems();
  }catch(error){$("#quote-entry-price").textContent="Erro";$("#quote-entry-price").title=error.message;}
}

$("#add-quote-item").onclick = () => {
  const form = Object.fromEntries(new FormData($("#quote-form")));
  if (!form.item_code || !form.item_description || !Number(form.item_quantity) || !form.item_material_id) {
    $("#quote-form .dialog-error").textContent = "Preencha código, descrição, quantidade e selecione o material configurado.";
    return;
  }
  const item = quoteItemFromForm(form);
  if (editingQuoteItemIndex === null) pendingQuoteItems.push(item);
  else pendingQuoteItems[editingQuoteItemIndex] = item;
  renderPendingQuoteItems();
  resetQuoteItemEditor();
  refreshPendingPrices();
  $("#quote-form .dialog-error").textContent = "";
};

$("#quote-form").onsubmit = async event => {
  event.preventDefault();
  const form = Object.fromEntries(new FormData(event.target));
  const items = [...pendingQuoteItems];
  if (!items.length) {
    event.target.querySelector(".dialog-error").textContent = "Adicione pelo menos um item à proposta.";
    return;
  }
  const payload = currentQuotePayload(items);
  try {
    try{quoteDirectoryHandle=await chooseQuoteDirectory(quoteSaveMode);}catch(error){if(error.name==="AbortError")return;throw error;}
    const quote=await req("/commercial/quotes", {method:"POST", body:JSON.stringify(payload)});
    const savedMessage=await saveQuotePdf(quote,quoteDirectoryHandle);
    $("#quote-dialog").close(); event.target.reset(); pendingQuoteItems = []; await quotes();alert(`${quote.number} salvo com sucesso.\n${savedMessage}`);
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

$("#bom-form").onsubmit=async event=>{event.preventDefault();const values=Object.fromEntries(new FormData(event.target));try{const libraryData=await req("/technical-library"),byCode=new Map(libraryData.items.map(item=>[item.danfer_code.toLocaleLowerCase("pt-BR"),item]));const components=values.components_text.split(/\r?\n/).filter(Boolean).map((line,index)=>{const [code,quantity,unit="un",scrap="0"]=line.split(";").map(value=>value.trim()),part=byCode.get(code.toLocaleLowerCase("pt-BR"));if(!part)throw Error(`Linha ${index+1}: componente ${code} não encontrado na Biblioteca Técnica.`);return{part_id:part.id,quantity:Number(String(quantity).replace(",",".")),unit,scrap_percent:Number(String(scrap).replace(",","."))};});await req("/boms",{method:"POST",body:JSON.stringify({product_id:values.product_id,revision:values.revision,status:values.status,components})});$("#bom-dialog").close();event.target.reset();await bom();}catch(error){event.target.querySelector(".dialog-error").textContent=error.message;}};

$("#routing-template-form").onsubmit = async event => {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.target));
  try {
    const steps = values.steps.split(/\r?\n/).filter(Boolean).map((line, index) => {
      const [code, process, minutes] = line.split(";").map(value => value.trim());
      if (!Number(code) || !process || Number.isNaN(Number(minutes))) throw Error(`Etapa ${index + 1} inválida.`);
      return {operation_erp_code:Number(code), process, default_minutes:Number(minutes)};
    });
    await req("/catalogs/routing-templates", {method:"POST", body:JSON.stringify({
      name:values.name, description:values.description, steps, active:true
    })});
    event.target.reset();
    await maintenance();
  } catch (error) { alert(error.message); }
};

$("#cost-settings-form").onsubmit = async event => {
  event.preventDefault();
  const current = await req("/commercial/settings/costs");
  const values = Object.fromEntries(new FormData(event.target));
  Object.entries(values).forEach(([key, value]) => current[key] = Number(value));
  await req("/commercial/settings/costs", {method:"PUT", body:JSON.stringify(current)});
  $("#cost-settings-status").textContent = "Parâmetros salvos.";
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
    currentUser = login.user;
    applyAccess(login.user);
    $("#login-screen").classList.add("hidden");
    $("#status").textContent = `● ${login.user.name}`;
    if (requirePasswordChange(login.user)) return;
    await dashboard();
  } catch (error) { $("#login-error").textContent = error.message; }
};

$("#password-form").onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  if (data.new_password !== data.confirm_password) {
    event.target.querySelector(".dialog-error").textContent = "A confirmação da nova senha não confere.";
    return;
  }
  delete data.confirm_password;
  try {
    await req("/auth/change-password", {method:"POST", body:JSON.stringify(data)});
    $("#password-dialog").close(); event.target.reset(); await dashboard();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

async function renderPriceReviewCenter(){let card=$("#price-review-center");if(!card){card=document.createElement("article");card.id="price-review-center";card.innerHTML=`<div class="toolbar"><div><h2>Revisão de preços produzidos</h2><small>Somente itens de OPs concluídas. O histórico original nunca é alterado.</small></div><button type="button" id="filter-price-reviews">Filtrar</button></div><div class="form-grid"><label>Cliente<select id="price-review-client"><option value="">Todos</option></select></label><label>Modalidade<select id="price-review-type"><option value="">Venda e serviço</option><option value="venda">Venda</option><option value="servico">Serviço</option></select></label><label>Produzido desde<input id="price-review-start" type="date"></label><label>Produzido até<input id="price-review-end" type="date"></label><label><input id="price-review-expired" type="checkbox"> Somente vencidos</label></div><div id="price-review-table"></div>`;$("#maintenance").insertBefore(card,$("#maintenance-table").closest("article"));}const clients=await req("/commercial/clients"),select=$("#price-review-client");if(select.options.length===1)select.insertAdjacentHTML("beforeend",clients.map(item=>`<option value="${item.id}">${esc(item.name)}</option>`).join(""));const load=async()=>{const params=new URLSearchParams();if(select.value)params.set("client_id",select.value);if($("#price-review-type").value)params.set("type",$("#price-review-type").value);if($("#price-review-start").value)params.set("start",$("#price-review-start").value);if($("#price-review-end").value)params.set("end",$("#price-review-end").value);if($("#price-review-expired").checked)params.set("expired_only","true");const rows=await req(`/workflows/price-reviews?${params}`);$("#price-review-table").innerHTML=rows.length?table(["Cliente","Item / origem","Último lote","Validade","Preço histórico","Referência atual","Ação"],rows.map((item,index)=>`<tr><td>${esc(item.client)}<br><small>${esc(item.quote_type)}</small></td><td><b>${esc(item.item_code)}</b> · ${esc(item.description)}<br><small>${esc(item.quote_number)} / ${esc(item.order_number)}</small></td><td>${item.quantity} pç · ${item.total_weight_kg} kg<br><small>${item.produced_on}</small></td><td>${item.validity_days} dias<br>${pill(item.expired?"vencido":"vigente")}</td><td>${money(item.historical_unit_price)}</td><td>${money(item.current_reference_price)}${item.last_adjustment_date?`<br><small>${item.last_adjustment_date}</small>`:""}</td><td><button type="button" data-price-review="${index}">Reajustar</button></td></tr>`)):'<div class="empty">Nenhum item produzido encontrado para os filtros.</div>';document.querySelectorAll("[data-price-review]").forEach(button=>button.onclick=async()=>{const item=rows[Number(button.dataset.priceReview)],value=prompt(`Novo preço unitário para ${item.item_code}:`,item.current_reference_price);if(value===null)return;const newPrice=Number(String(value).replace(",","."));if(!(newPrice>0))return alert("Informe um preço válido.");const reason=prompt("Motivo do reajuste:",item.expired?"Revisão por validade vencida":"Revisão administrativa");if(!reason)return;await req("/commercial/price-adjustments",{method:"POST",body:JSON.stringify({client_id:item.client_id,item_code:item.item_code,commercial_operation:item.commercial_operation,previous_unit_price:item.current_reference_price,new_unit_price:newPrice,reason,effective_date:new Date().toISOString().slice(0,10)})});await load();});};$("#filter-price-reviews").onclick=load;await load();}

const recoveredMaintenanceLabels={paymentTerms:"Condições de pagamento",commercialParameters:"Parâmetros comerciais v0.51",laserParameters:"Laser",models:"Modelos de fabricação",processes:"Processos",standardSheets:"Chapas padrão",utilizationIncrements:"Aproveitamento automático",largePieceLossRules:"Perda peça unitária",taxScenarios:"Tributação",operationNatures:"Operações e ERP",crmStages:"CRM · Etapas",crmActivities:"CRM · Atividades",crmLossReasons:"CRM · Motivos",crmRules:"CRM · Regras"};
async function renderRecoveredMaintenance(){let card=$("#recovered-maintenance-card");if(!card){card=document.createElement("article");card.id="recovered-maintenance-card";card.innerHTML=`<div class="toolbar"><div><h2>Cadastros recuperados da v0.51</h2><small>Configurações administrativas consolidadas a partir da versão de referência.</small></div><button type="button" id="reset-recovered-maintenance" class="cancel">Restaurar v0.51</button></div><div id="recovered-maintenance-tabs" class="maintenance-tabs"></div><div id="recovered-maintenance-editor"></div>`;$("#maintenance").insertBefore(card,$("#material-cost-settings-card")||$("#routing-settings-card"));}const categories=await req("/maintenance-config/categories"),names=Object.keys(recoveredMaintenanceLabels).filter(name=>categories[name]!==undefined);let active=card.dataset.activeCategory||names[0];const tabs=$("#recovered-maintenance-tabs"),editor=$("#recovered-maintenance-editor");tabs.innerHTML=names.map(name=>`<button type="button" data-maint-category="${name}" class="${name===active?"active":""}">${recoveredMaintenanceLabels[name]} <small>${categories[name]}</small></button>`).join("");const open=async name=>{card.dataset.activeCategory=name;tabs.querySelectorAll("button").forEach(button=>button.classList.toggle("active",button.dataset.maintCategory===name));const rows=await req(`/maintenance-config/${name}`),keys=[...new Set(rows.flatMap(row=>Object.keys(row)))];const input=(value,key,index)=>`<input data-recovered-row="${index}" data-recovered-key="${esc(key)}" value="${esc(value??"")}">`;editor.innerHTML=`<div class="table-wrap wide-admin-table"><table><thead><tr>${keys.map(key=>`<th>${esc(key)}</th>`).join("")}<th>Ação</th></tr></thead><tbody>${rows.map((row,index)=>`<tr>${keys.map(key=>`<td>${input(row[key],key,index)}</td>`).join("")}<td><button type="button" class="cancel" data-remove-recovered>Excluir</button></td></tr>`).join("")}</tbody></table></div><p><button type="button" id="add-recovered-row">+ Adicionar linha</button> <button type="button" id="save-recovered-maintenance">Salvar ${recoveredMaintenanceLabels[name]}</button> <span id="recovered-maintenance-status"></span></p>`;const bindRemove=()=>editor.querySelectorAll("[data-remove-recovered]").forEach(button=>button.onclick=()=>button.closest("tr").remove());bindRemove();$("#add-recovered-row").onclick=()=>{editor.querySelector("tbody").insertAdjacentHTML("beforeend",`<tr>${keys.map(key=>`<td>${input("",key,rows.length)}</td>`).join("")}<td><button type="button" class="cancel" data-remove-recovered>Excluir</button></td></tr>`);bindRemove();};$("#save-recovered-maintenance").onclick=async()=>{const saved=[...editor.querySelectorAll("tbody tr")].map(tr=>Object.fromEntries([...tr.querySelectorAll("input")].map(field=>{const original=rows[Number(field.dataset.recoveredRow)]?.[field.dataset.recoveredKey],value=field.value;return [field.dataset.recoveredKey,typeof original==="number"?Number(value):value]})));await req(`/maintenance-config/${name}`,{method:"PUT",body:JSON.stringify(saved)});$("#recovered-maintenance-status").textContent="Cadastro salvo.";await renderRecoveredMaintenance();};};tabs.querySelectorAll("button").forEach(button=>button.onclick=()=>open(button.dataset.maintCategory));$("#reset-recovered-maintenance").onclick=async()=>{if(!confirm("Restaurar todos os cadastros aos valores recuperados da v0.51?"))return;await req("/maintenance-config/reset/v051",{method:"POST"});card.dataset.activeCategory="";await renderRecoveredMaintenance();};await open(active);}

(async () => {
  try {
    const user = await req("/auth/me");
    currentUser = user;
    applyAccess(user);
    $("#login-screen").classList.add("hidden");
    $("#status").textContent = `● ${user.name}`;
    if (requirePasswordChange(user)) return;
    await dashboard();
  } catch {
    $("#status").textContent = "● Aguardando login";
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js");
})();
