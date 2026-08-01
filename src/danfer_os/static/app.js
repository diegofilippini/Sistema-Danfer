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
let editingQuoteItemIndex = null;
let currentUser = null;
const accessModules = {
  dashboard:"Dashboard", crm:"CRM / Clientes", quotes:"OrÃ§amentos", library:"Biblioteca TÃ©cnica",
  engineering:"Engenharia / DXF", bom:"Estruturas BOM", pcp:"PCP", integrations:"IntegraÃ§Ãµes",
  coordination:"SolicitaÃ§Ãµes / ComunicaÃ§Ã£o", quality:"Qualidade", maintenance:"ManutenÃ§Ãµes",
  users:"UsuÃ¡rios", audit:"Auditoria", system:"Backup e restauraÃ§Ã£o"
  ,"quality-dashboard":"Dashboard qualidade", deviations:"AnÃ¡lise de desvios",
  "management-dashboard":"Dashboards gerenciais", "monthly-analysis":"AnÃ¡lise mensal"
};
const roleAccess = {
  administrador:Object.keys(accessModules),
  comercial:["dashboard","crm","quotes","library","engineering","integrations","coordination","management-dashboard"],
  pcp:["dashboard","library","bom","pcp","integrations","coordination","deviations","monthly-analysis"],
  engenharia:["dashboard","library","engineering","bom","coordination"],
  producao:["dashboard","pcp","quality","maintenance","coordination"],
  qualidade:["dashboard","quality","quality-dashboard","deviations","coordination"],
  consulta:["dashboard","library","management-dashboard"]
};

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
  const [clients, opportunities, alerts] = await Promise.all([req("/commercial/clients" + (query ? `?q=${encodeURIComponent(query)}` : "")), req("/crm/opportunities" + (query ? `?q=${encodeURIComponent(query)}` : "")), req("/crm/alerts")]);
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
      `<tr><td><b>${esc(quote.number)}</b><br><small>${new Date(quote.created_at).toLocaleDateString("pt-BR")}</small></td><td><code>${quote.client_id.slice(0, 8)}</code></td><td>${esc(quote.type)}</td><td>${esc(quote.revision)}</td><td><b>${money(quote.total)}</b><br><small>Margem efetiva: ${Number(quote.effective_margin_percent||0).toFixed(2)}%</small></td><td>${pill(quote.status)}</td><td>${quoteActions(quote)}</td></tr>`
    )
  );
}

window.moveQuote = async (id, status) => {
  try {
    await req(`/commercial/quotes/${id}/status`, {
      method: "POST", body: JSON.stringify({status})
    });
    if (status === "aprovado") {
      await req(`/workflows/quotes/${id}/erp-order`, {method:"POST"});
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
  const [orders, directRequests] = await Promise.all([req("/pcp/orders"), req("/pcp/direct-requests")]);
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
    ["SolicitaÃ§Ã£o","Cliente","DescriÃ§Ã£o","Processos","Prazo","Prioridade","Status"],
    directRequests.map(item => `<tr><td><b>${esc(item.number)}</b></td><td>${esc(item.client)}</td><td>${esc(item.description)}</td><td>${item.processes.map(esc).join(" â†’ ")}</td><td>${item.due_date}</td><td>${item.priority}</td><td>${pill(item.status)}</td></tr>`)
  );
  $("#op-archive-table").innerHTML = table(
    ["OP","Prazo","Prioridade","Quantidade","Status","AÃ§Ã£o"],
    orders.map(order => `<tr><td><b>${esc(order.number)}</b></td><td>${order.due_date}</td><td>${order.priority}</td><td>${order.quantity}</td><td>${pill(order.status)}</td><td>${nextOrderAction(order)}</td></tr>`)
  );
  const active = orders.filter(item => !["concluida","cancelada"].includes(item.status));
  $("#operational-flow").innerHTML = [
    ["Pedidos diretos", directRequests.filter(item => item.status !== "concluida").length],
    ["Planejadas", orders.filter(item => item.status === "planejada").length],
    ["Liberadas", orders.filter(item => item.status === "liberada").length],
    ["Em produÃ§Ã£o", orders.filter(item => item.status === "em_producao").length],
    ["ConcluÃ­das", orders.filter(item => item.status === "concluida").length],
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
  return actions;
}
window.customerProposal=async(id,currentTotal)=>{const value=Number(prompt(`Valor original: ${money(currentTotal)}\nProposta do cliente (R$):`,String(currentTotal)));if(!value||value>=currentTotal)return alert("Informe um valor menor que o orçamento atual.");const notes=prompt("Observação da negociação:","")||"";try{const updated=await req(`/commercial/quotes/${id}/customer-proposals`,{method:"POST",body:JSON.stringify({proposed_total:value,submitted_by:currentUser?.name||"",notes})});const proposal=updated.customer_proposals.at(-1);alert(`Proposta registrada.\nMargem efetiva: ${proposal.effective_margin_percent.toFixed(2)}%\nMargem mínima: ${proposal.minimum_margin_percent.toFixed(2)}%\nAguardando autorização administrativa.`);await quotes();}catch(error){alert(error.message);}};
window.decideCustomerProposal=async(quoteId,proposalId,approved)=>{const reason=prompt(approved?"Justificativa da autorização:":"Motivo da recusa:");if(!reason)return;try{await req(`/commercial/quotes/${quoteId}/customer-proposals/${proposalId}/decision`,{method:"POST",body:JSON.stringify({approved,decided_by:currentUser?.name||"",reason})});await quotes();}catch(error){alert(error.message);}};

function ensurePcpConsolidation() {
  if ($("#pcp-consolidated")) return;
  const root = $("#pcp");
  const block = document.createElement("div");
  block.id = "pcp-consolidated";
  block.innerHTML = `<div id="operational-flow" class="metrics compact"></div><article><div class="toolbar"><h2>Pedidos diretos (SP)</h2><button id="new-direct-request">+ Pedido direto</button></div><div id="direct-request-table"></div></article><article><h2>Arquivo e liberaÃ§Ã£o de OPs</h2><div id="op-archive-table"></div></article>`;
  root.appendChild(block);
  $("#new-direct-request").onclick = createDirectRequest;
}

function nextOrderAction(order) {
  const next = {planejada:"liberada", liberada:"em_producao", em_producao:"concluida", pausada:"em_producao"}[order.status];
  return next ? `<button class="action" onclick="moveProductionOrder('${order.id}','${next}')">${{liberada:"Liberar",em_producao:"Iniciar",concluida:"Concluir"}[next] || "Retomar"}</button>` : "";
}

window.moveProductionOrder = async (id, status) => {
  await req(`/pcp/orders/${id}`, {method:"PATCH", body:JSON.stringify({status})});
  await pcp();
};

async function createDirectRequest() {
  const client = prompt("Cliente do pedido direto:"); if (!client) return;
  const description = prompt("DescriÃ§Ã£o do serviÃ§o:"); if (!description) return;
  const processes = (prompt("Processos separados por vÃ­rgula:", "Corte Laser, Dobra") || "").split(",").map(value => value.trim()).filter(Boolean); if (!processes.length) return;
  const due_date = prompt("Prazo (AAAA-MM-DD):", new Date(Date.now() + 7 * 86400000).toISOString().slice(0,10)); if (!due_date) return;
  await req("/pcp/direct-requests", {method:"POST", body:JSON.stringify({client, description, processes, due_date, priority:3})});
  await pcp();
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
  $("#crm-opportunity-summary").innerHTML = [["Oportunidades",opportunities.length],["Valor",money(opportunities.reduce((sum,item)=>sum+item.value,0))],["Valor ponderado",money(opportunities.reduce((sum,item)=>sum+item.value*item.probability_percent/100,0))],["Alertas ativos",alerts.length]].map(([label,value])=>`<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#crm-alerts").innerHTML = alerts.length ? table(["Prioridade","Negociação","Cliente","Responsável","Alerta","Prazo"], alerts.map(item=>`<tr><td>${pill(item.severity)}</td><td><b>${esc(item.opportunity_number)}</b></td><td>${esc(item.client_name)}</td><td>${esc(item.owner||"—")}</td><td>${esc(item.message)}</td><td>${item.due_date||"—"}</td></tr>`)) : `<p class="muted">Nenhum alerta de CRM pendente.</p>`;
  $("#crm-opportunities").innerHTML = table(["NegociaÃ§Ã£o","Cliente","Etapa","Valor","Probabilidade","ResponsÃ¡vel","PrÃ³ximo contato","AÃ§Ãµes"], opportunities.map(item=>`<tr><td><b>${esc(item.number)}</b></td><td>${esc(item.client_name)}</td><td>${pill(item.stage)}</td><td>${money(item.value)}</td><td>${item.probability_percent}%</td><td>${esc(item.owner||"â€”")}</td><td>${item.next_contact||"â€”"}</td><td><button class="action" onclick="advanceOpportunity('${item.id}')">AvanÃ§ar</button> <button class="action" onclick="addCrmActivity('${item.id}')">Atividade</button></td></tr>`));
}

function ensureCrmOpportunities(){if($("#crm-opportunity-card"))return;const article=document.createElement("article");article.id="crm-opportunity-card";article.innerHTML=`<div class="toolbar"><div><h2>Centro de negociaÃ§Ãµes</h2><small>Funil, atividades e prÃ³ximos contatos.</small></div><button id="new-opportunity">+ Nova oportunidade</button></div><div id="crm-opportunity-summary" class="metrics compact"></div><h3>Alertas automáticos</h3><div id="crm-alerts"></div><h3>Oportunidades</h3><div id="crm-opportunities"></div>`;$("#crm").appendChild(article);$("#new-opportunity").onclick=createOpportunity;}
async function createOpportunity(){const client_name=prompt("Cliente:");if(!client_name)return;const value=Number(prompt("Valor estimado:","0")||0),owner=prompt("ResponsÃ¡vel:",currentUser?.name||"")||"",next_contact=prompt("PrÃ³ximo contato (AAAA-MM-DD):",new Date(Date.now()+2*86400000).toISOString().slice(0,10));await req("/crm/opportunities",{method:"POST",body:JSON.stringify({client_name,value,owner,next_contact})});await crm();}
window.advanceOpportunity=async id=>{const stages=["em_elaboracao","enviada","em_negociacao","aprovada"],items=await req("/crm/opportunities"),item=items.find(value=>value.id===id);if(!item)return;const next=stages[Math.min(stages.length-1,Math.max(0,stages.indexOf(item.stage)+1))];await req(`/crm/opportunities/${id}`,{method:"PATCH",body:JSON.stringify({stage:next,probability_percent:[10,35,60,100][stages.indexOf(next)]})});await crm();};
window.addCrmActivity=async id=>{const description=prompt("Resumo da atividade:");if(!description)return;const next_contact=prompt("PrÃ³ximo contato (AAAA-MM-DD):",new Date(Date.now()+2*86400000).toISOString().slice(0,10));await req(`/crm/opportunities/${id}/activities`,{method:"POST",body:JSON.stringify({type:"contato",description,performed_by:currentUser?.name||"",next_contact})});await crm();};

async function coordination() {
  const [profiles, requests, messages] = await Promise.all([
    req("/billing/profiles"), req("/requests"), req("/communications/messages")
  ]);
  $("#billing-profiles").innerHTML = profiles.map(item => `<div class="metric"><b>${esc(item.unit).toUpperCase()}</b><span>${esc(item.legal_name)}${item.erp_company_code ? " · ERP " + esc(item.erp_company_code) : ""}</span></div>`).join("");
  $("#requests-table").innerHTML = table(["Número","Assunto","Destino","Previsão","Prioridade","Status"], requests.map(item => `<tr><td><b>${esc(item.number)}</b><br><small>${esc(item.company_unit).toUpperCase()}</small></td><td>${esc(item.subject)}<br><small>${esc(item.requester)}</small></td><td>${esc(item.target_department)}<br><small>${esc(item.assigned_to)}</small></td><td>${item.promised_date ? new Date(item.promised_date + "T12:00:00").toLocaleDateString("pt-BR") : "—"}</td><td>${pill(item.priority)}</td><td>${pill(item.status)}</td></tr>`));
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

function ensureAnalyticsSections() {
  const main = document.querySelector("main");
  const definitions = {
    "quality-dashboard": `<div class="hero"><p>QUALIDADE</p><h2>Dashboard da qualidade</h2></div><div id="quality-kpis" class="metrics"></div><article><div id="quality-summary-table"></div></article>`,
    deviations: `<div class="hero"><p>CUSTOS</p><h2>AnÃ¡lise de desvios</h2></div><article><div id="deviation-analysis-table"></div></article>`,
    "management-dashboard": `<div class="hero"><p>GESTÃƒO</p><h2>Dashboards gerenciais</h2></div><div id="management-kpis" class="metrics"></div>`,
    "monthly-analysis": `<div class="hero"><p>GESTÃƒO DE CUSTOS</p><h2>AnÃ¡lise mensal</h2></div><div class="toolbar"><label>InÃ­cio<input id="monthly-start" type="date"></label><label>Fim<input id="monthly-end" type="date"></label><button id="monthly-refresh">Aplicar filtros</button><button id="monthly-export">Exportar CSV</button></div><div id="monthly-kpis" class="metrics"></div><article><div id="monthly-analysis-table"></div></article>`,
    audit: `<div class="hero"><p>RASTREABILIDADE</p><h2>Auditoria</h2></div><div class="toolbar"><input id="audit-module-filter" placeholder="Filtrar mÃ³dulo"><button id="audit-refresh">Atualizar</button><button id="audit-export">Exportar CSV</button></div><article><div id="audit-analysis-table"></div></article>`,
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
  tools.innerHTML=`<div class="global-search-wrap"><input id="global-search" placeholder="Pesquisar cliente, orÃ§amento, OP ou SP"><div id="global-search-results"></div></div><button id="enable-push" type="button">Ativar avisos</button><button id="notification-center" type="button">NotificaÃ§Ãµes</button>`;
  header.appendChild(tools);
  let timer;$("#global-search").oninput=event=>{clearTimeout(timer);const q=event.target.value.trim();if(q.length<2){$("#global-search-results").innerHTML="";return}timer=setTimeout(async()=>{const data=await req(`/search?q=${encodeURIComponent(q)}`);$("#global-search-results").innerHTML=data.map(item=>`<button type="button"><b>${esc(item.type)} Â· ${esc(item.title)}</b><small>${esc(item.subtitle)}</small></button>`).join("")||"<small>Nenhum resultado.</small>";},250)};
  $("#notification-center").onclick=showNotifications;
  $("#enable-push").onclick=enablePushNotifications;
}
async function showNotifications(){if(!currentUser)return;const data=await req(`/notifications?username=${encodeURIComponent(currentUser.username)}&role=${encodeURIComponent(currentUser.role)}`);alert(data.length?data.slice(0,12).map(item=>`${item.read?"":"â€¢ "}${item.title}\n${item.message}`).join("\n\n"):"Nenhuma notificaÃ§Ã£o.");await Promise.all(data.filter(item=>!item.read).map(item=>req(`/notifications/${item.id}/read`,{method:"POST"})));}
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
  const card=document.createElement("article");card.id="system-admin-card";card.innerHTML=`<div class="toolbar"><div><h2>Backup e restauraÃ§Ã£o</h2><small>CÃ³pia completa dos dados persistidos no servidor.</small></div><div><a class="action" href="${api}/system/backup">Baixar backup</a> <label class="action">Restaurar<input id="restore-system-file" type="file" accept=".zip" hidden></label></div></div><p id="system-admin-status"></p>`;$("#maintenance").appendChild(card);$("#restore-system-file").onchange=async event=>{const file=event.target.files[0];if(!file)return;if(!confirm("Restaurar este backup? Uma cÃ³pia de seguranÃ§a serÃ¡ criada antes da alteraÃ§Ã£o."))return;const response=await fetch(api+"/system/restore",{method:"POST",credentials:"same-origin",headers:{"Content-Type":"application/zip"},body:file});const result=await response.json();$("#system-admin-status").textContent=response.ok?`RestauraÃ§Ã£o concluÃ­da. Reinicie o sistema. Backup anterior: ${result.pre_restore_backup}`:(result.detail||"Falha na restauraÃ§Ã£o.");};
}

async function qualityDashboard() {
  const data = await req("/analytics/quality");
  $("#quality-kpis").innerHTML = [["OcorrÃªncias",data.total],["Abertas",data.open],["Resolvidas",data.resolved],["Custo total",money(data.total_cost)]].map(([label,value]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#quality-summary-table").innerHTML = table(["Tipo","Quantidade"], data.by_type.map(item => `<tr><td>${esc(item.type)}</td><td><b>${item.total}</b></td></tr>`));
}

async function deviations() {
  const data = await req("/analytics/deviations");
  $("#deviation-analysis-table").innerHTML = table(["OP","Previsto","Realizado","Desvio","%","Prazo","Status","Motivo"], data.map(item => `<tr><td><b>${esc(item.order_number)}</b></td><td>${money(item.estimated_total_cost)}</td><td>${money(item.actual_total_cost)}</td><td>${money(item.variance_value)}</td><td>${item.variance_percent ?? "â€”"}%</td><td>${item.due_date}</td><td>${pill(item.status)}</td><td>${esc(item.reason)}</td></tr>`));
}

async function managementDashboard() {
  const data = await req("/analytics/management");
  $("#management-kpis").innerHTML = [["OrÃ§amentos",data.quotes],["Aprovados",data.approved_quotes],["ConversÃ£o",data.conversion_percent+"%"],["Receita projetada",money(data.projected_revenue)],["OPs ativas",data.active_orders],["OPs atrasadas",data.late_orders],["Custo qualidade",money(data.quality_cost)]].map(([label,value]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
}

let lastMonthlyRows = [], lastAuditRows = [];
async function monthlyAnalysis() {
  const data = await req(`/analytics/monthly?start=${$("#monthly-start").value}&end=${$("#monthly-end").value}`); lastMonthlyRows = data.rows;
  $("#monthly-kpis").innerHTML = [["Ordens",data.orders],["Previsto",money(data.estimated)],["Realizado",money(data.actual)],["Desvio",money(data.variance)]].map(([label,value]) => `<div class="metric"><b>${value}</b><span>${label}</span></div>`).join("");
  $("#monthly-analysis-table").innerHTML = table(["OP","Data","Status","Previsto","Realizado","Desvio","%"], data.rows.map(item => `<tr><td><b>${esc(item.order)}</b></td><td>${item.date}</td><td>${pill(item.status)}</td><td>${money(item.estimated)}</td><td>${money(item.actual)}</td><td>${money(item.variance)}</td><td>${item.variance_percent ?? "â€”"}</td></tr>`));
}
async function auditAnalysis() { const module = $("#audit-module-filter").value.trim(); lastAuditRows = await req("/audit" + (module ? `?module=${encodeURIComponent(module)}` : "")); $("#audit-analysis-table").innerHTML = table(["Data","MÃ³dulo","AÃ§Ã£o","Entidade","Detalhes"], lastAuditRows.map(item => `<tr><td>${new Date(item.created_at).toLocaleString("pt-BR")}</td><td>${esc(item.module)}</td><td>${esc(item.action)}</td><td>${esc(item.entity_id)}</td><td>${esc(item.details)}</td></tr>`)); }
function downloadCsv(name, headers, rows) { const csv = [headers,...rows].map(row => row.map(value => `"${String(value ?? "").replaceAll('"','""')}"`).join(";")).join("\n"); const link=document.createElement("a"); link.href=URL.createObjectURL(new Blob(["\ufeff"+csv],{type:"text/csv"})); link.download=name; link.click(); setTimeout(()=>URL.revokeObjectURL(link.href),1000); }
function exportMonthlyCsv(){downloadCsv("analise_mensal_danfer.csv",["OP","Data","Status","Previsto","Realizado","Desvio","Percentual"],lastMonthlyRows.map(item=>[item.order,item.date,item.status,item.estimated,item.actual,item.variance,item.variance_percent]));}
function exportAuditCsv(){downloadCsv("auditoria_danfer.csv",["Data","MÃ³dulo","AÃ§Ã£o","Entidade","Detalhes"],lastAuditRows.map(item=>[item.created_at,item.module,item.action,item.entity_id,item.details]));}

async function renderUserAccess() {
  let card = $("#user-access-card");
  if (!card) {
    card = document.createElement("article");
    card.id = "user-access-card";
    card.innerHTML = `<div class="toolbar"><div><h2>UsuÃ¡rios e permissÃµes</h2><small>Perfil, situaÃ§Ã£o e mÃ³dulos liberados por usuÃ¡rio.</small></div></div><div id="user-access-table"></div>`;
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
  }
  await renderUserAccess();
  ensureAdminSystemTools();
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
  try {
    await req("/commercial/clients", {method:"POST", body:JSON.stringify(data)});
    $("#client-dialog").close(); event.target.reset(); await crm();
  } catch (error) { event.target.querySelector(".dialog-error").textContent = error.message; }
};

$("#new-quote").addEventListener("click", async () => {
  pendingQuoteItems = [];
  editingQuoteItemIndex = null;
  renderPendingQuoteItems();
  const [clients, materials, templates, bendTimes] = await Promise.all([
    req("/commercial/clients"), req("/catalogs/quote-materials"),
    req("/catalogs/quote-routing-templates"), req("/commercial/quote-bend-times")
  ]);
  quoteMaterialCatalog = materials;
  routingTemplates = templates;
  bendTimeSettings = bendTimes;
  $("#quote-material-options").innerHTML = materials.map(item => `<option value="${esc(item.description)}">${esc(item.erp_code)} · ${item.thickness_mm} mm</option>`).join("");
  $("#quote-client").innerHTML = clients.map(client =>
    `<option value="${client.id}">${esc(client.name)}</option>`
  ).join("");
  $("#quote-routing-template").innerHTML = '<option value="">Selecionar roteiro…</option>' + templates.map(template => `<option value="${template.id}">${esc(template.name)}</option>`).join("");
  const validity = new Date(); validity.setDate(validity.getDate() + 10);
  $("#quote-form [name=valid_until]").value = validity.toISOString().slice(0,10);
});

$("#quote-form [name=item_material]").addEventListener("change", event => {
  const selected = quoteMaterialCatalog.find(item => item.description.toLocaleLowerCase("pt-BR") === event.target.value.toLocaleLowerCase("pt-BR"));
  if (!selected) return;
  $("#quote-form [name=item_thickness]").value = selected.thickness_mm;
});

function quoteItemFromForm(form) {
  const template = routingTemplates.find(item => item.id === form.routing_template_id);
  const processes = (template?.steps || []).map((step, index) => ({
    name:step.process,
    minutes:Number(form[`process_minutes_${index}`] || step.default_minutes),
    hourly_rate:0,
    external_cost:0
  }));
  return {
    code:form.item_code, description:form.item_description,
    quantity:Number(form.item_quantity), material:form.item_material,
    thickness_mm:form.item_thickness ? Number(form.item_thickness) : null,
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
  const [materials, operations] = await Promise.all([req("/catalogs/materials"), req("/catalogs/operations")]);
  $("#material-catalog").innerHTML = table(["ERP","Material","Esp.","Preço/kg","Status"], materials.map(item => `<tr><td><b>${esc(item.erp_code)}</b></td><td>${esc(item.description)}<br><small>${esc(item.specification)}</small></td><td>${item.thickness_mm} mm</td><td>${money(item.price_per_kg)}</td><td>${pill(item.active ? "ativo" : "inativo")}</td></tr>`));
  $("#operation-catalog").innerHTML = table(["Código","Operação","Custeio","Valor hora"], operations.map(item => `<tr><td><b>${item.erp_code}</b></td><td>${esc(item.name)}</td><td>${esc(item.pricing_mode)}</td><td>${money(item.hourly_rate)}</td></tr>`));
  renderDxfDrafts();
}

function renderPendingQuoteItems() {
  $("#pending-quote-items").innerHTML = pendingQuoteItems.map((item, index) => `<tr><td>${index + 1}</td><td><b>${esc(item.code)}</b><br><small>${esc(item.description)}</small></td><td>${esc(item.material || "—")}${item.thickness_mm ? `<br><small>${item.thickness_mm} mm</small>` : ""}</td><td>${item.quantity}</td><td>${item.margin_percent ?? 30}%</td><td>${item.nesting_mode === "forcar_ncav" ? `NcAv ${item.utilization_percent || "auto"}%` : esc(item.nesting_mode || "automático")}</td><td>${esc(item.routing_template_name || "Sem roteiro")}<br><small>${(item.processes || []).map(process => `${esc(process.name)} ${process.minutes} min`).join(" · ")}</small></td><td class="quote-row-actions"><button type="button" data-edit-item="${index}">Editar</button><button type="button" data-remove-item="${index}">Excluir</button></td></tr>`).join("");
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
}

function renderProcessTimes(templateId, values = [], item = {}) {
  const template = routingTemplates.find(value => value.id === templateId);
  const hasLaser = template?.steps.some(step => step.process.toLocaleLowerCase("pt-BR").includes("laser"));
  const laserFields = hasLaser ? `<label>Perímetro de corte (mm)<input name="item_cut_length" type="number" min="0" step=".1" value="${item.cut_length_mm || 0}"></label><label>Perfurações<input name="item_piercings" type="number" min="0" step="1" value="${item.piercings || 0}"></label><label>Tempo estimado preservado (min)<input name="laser_estimated_minutes" type="number" min="0" step=".001" value="${item.laser_estimated_minutes || 0}" readonly></label><label>Laser adicional (min)<input name="laser_additional_minutes" type="number" min="0" step=".1" value="${item.laser_additional_minutes || 0}"></label><label class="span-2">Motivo do laser adicional<input name="laser_additional_reason" value="${esc(item.laser_additional_reason || "")}" placeholder="Ex.: muitas furações pequenas ou contorno complexo"></label><small class="span-2 muted">O tempo adicional é somado ao tempo calculado, sem apagar a estimativa original.</small>` : "";
  const hasBend = template?.steps.some(step => step.process.toLocaleLowerCase("pt-BR").includes("dobra"));
  const quantity = Number(item.quantity || $("#quote-form [name=item_quantity]").value || 1);
  const bendSuggested = quantity<=1?bendTimeSettings.one:quantity<=2?bendTimeSettings.two:quantity<=3?bendTimeSettings.three:quantity<=5?bendTimeSettings.four_to_five:bendTimeSettings.six_plus;
  const bendEstimate = item.bend_estimated_minutes || bendSuggested;
  const bendFields = hasBend ? `<label>Tempo padrão de dobra por peça (min)<input name="bend_estimated_minutes" type="number" min="0" step=".1" value="${bendEstimate}" ${quantity<6?"readonly":""}></label><label>Dobra adicional por peça (min)<input name="bend_additional_minutes" type="number" min="0" step=".1" value="${item.bend_additional_minutes || 0}"></label><label class="span-2">Motivo da dobra adicional<input name="bend_additional_reason" value="${esc(item.bend_additional_reason || "")}" placeholder="Ex.: geometria complexa, múltiplas regulagens ou conferência especial"></label><small class="span-2 muted">Sugestão para ${quantity} peça(s): ${bendSuggested} min por peça. Em lotes de 6 ou mais, o tempo-base pode ser ajustado pelo orçamentista.</small>` : "";
  $("#quote-process-times").innerHTML = template ? `<div class="process-time-grid">${template.steps.map((step, index) => `<label>${step.operation_erp_code} · ${esc(step.process)} (min)<input name="process_minutes_${index}" type="number" min="0" step=".1" value="${values[index]?.minutes ?? (step.process.toLocaleLowerCase("pt-BR").includes("dobra")?bendEstimate:step.default_minutes)}"></label>`).join("")}${laserFields}${bendFields}</div>` : '<small class="muted">Selecione um roteiro para informar os tempos de processo.</small>';
}

function resetQuoteItemEditor() {
  editingQuoteItemIndex = null;
  $("#item-editor-title").textContent = "Adicionar item";
  $("#add-quote-item").textContent = "Adicionar item";
  $("#cancel-item-edit").classList.add("hidden");
  ["item_code","item_description","item_material","item_thickness","item_weight","item_width","item_length","item_notes","item_utilization"].forEach(name => $("#quote-form [name=" + name + "]").value = "");
  $("#quote-form [name=item_quantity]").value = 1;
  $("#quote-form [name=item_margin_percent]").value = 30;
  $("#quote-form [name=nesting_mode]").value = "automatico";
  $("#quote-form [name=routing_template_id]").value = "";
  $(".ncav-field").classList.add("hidden");
  renderProcessTimes("");
}

function editQuoteItem(index) {
  const item = pendingQuoteItems[index];
  editingQuoteItemIndex = index;
  const form = $("#quote-form");
  const values = {item_code:item.code,item_description:item.description,item_quantity:item.quantity,item_material:item.material,item_thickness:item.thickness_mm,item_weight:item.net_weight_kg,item_width:item.width_mm,item_length:item.length_mm,item_margin_percent:item.margin_percent,item_utilization:item.utilization_percent,item_notes:item.notes,nesting_mode:item.nesting_mode,routing_template_id:item.routing_template_id};
  Object.entries(values).forEach(([name, value]) => { if (form.elements[name]) form.elements[name].value = value ?? ""; });
  $("#item-editor-title").textContent = `Editar item ${index + 1}`;
  $("#add-quote-item").textContent = "Atualizar item";
  $("#cancel-item-edit").classList.remove("hidden");
  $(".ncav-field").classList.toggle("hidden", item.nesting_mode !== "forcar_ncav");
  renderProcessTimes(item.routing_template_id, item.processes, item);
}

$("#quote-routing-template").onchange = event => renderProcessTimes(event.target.value);
$("#quote-nesting-mode").onchange = event => $(".ncav-field").classList.toggle("hidden", event.target.value !== "forcar_ncav");
$("#quote-form [name=expected_delivery]").onchange = renderPendingQuoteItems;
$("#cancel-item-edit").onclick = resetQuoteItemEditor;

$("#add-quote-item").onclick = () => {
  const form = Object.fromEntries(new FormData($("#quote-form")));
  if (!form.item_code || !form.item_description || !Number(form.item_quantity)) {
    $("#quote-form .dialog-error").textContent = "Preencha código, descrição e quantidade do item.";
    return;
  }
  const item = quoteItemFromForm(form);
  if (editingQuoteItemIndex === null) pendingQuoteItems.push(item);
  else pendingQuoteItems[editingQuoteItemIndex] = item;
  renderPendingQuoteItems();
  resetQuoteItemEditor();
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
  const payload = {
    type:form.type, billing_unit:form.billing_unit, client_id:form.client_id, requester:form.requester,
    prepared_by:form.prepared_by,
    valid_until:form.valid_until, expected_delivery:form.expected_delivery || null,
    payment_terms:form.payment_terms, freight_type:form.freight_type,
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
