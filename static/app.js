/* ShelfClear frontend — vanilla JS, talks to the JSON API in app.py */
const $ = (s) => document.querySelector(s);
const money = (n) => "$" + Number(n).toFixed(2);

let currentDealId = null;
let currentApproveUrl = null;
let approveOpened = false;
let mode = "simulator";

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelectorAll("nav button").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name)
  );
  const el = document.getElementById("view-" + name);
  if (el) el.classList.add("active");
  if (name === "dashboard") loadDashboard();
  if (name === "inventory") loadItems();
  if (name === "storefront") loadStorefront();
  if (name === "deals") loadDeals();
}

document.querySelectorAll("nav button").forEach((b) =>
  b.addEventListener("click", () => showView(b.dataset.view))
);
$("#back-to-deals").addEventListener("click", () => showView("deals"));

async function loadMode() {
  const m = await api("/api/mode");
  mode = m.mode;
  const banner = $("#mode-banner");
  banner.textContent = m.mode === "sandbox"
    ? "● LIVE SANDBOX — real PayPal sandbox API calls"
    : "● SIMULATOR MODE — demo mode, no PayPal calls yet";
  banner.classList.toggle("sandbox", m.mode === "sandbox");
  $("#footer-mode").textContent = m.mode;
}

async function loadDashboard() {
  const d = await api("/api/dashboard");
  $("#stat-stuck").textContent = money(d.cash_stuck_usd);
  $("#stat-recovered").textContent = money(d.cash_recovered_usd);
  $("#stat-listed").textContent = d.items_listed;
  $("#stat-sold").textContent = d.items_sold;
  $("#stat-deals").textContent = d.active_deals;
  const total = d.cash_stuck_usd + d.cash_recovered_usd;
  const pct = total > 0 ? Math.round((d.cash_recovered_usd / total) * 100) : 0;
  $("#recovery-pct").textContent = pct + "% recovered";
  $("#recovery-bar").style.width = pct + "%";
  const deals = await api("/api/deals");
  $("#recent-deals").innerHTML = deals.length
    ? deals.slice(0, 5).map(dealRow).join("")
    : "<p>No deals yet. Open the Storefront and start negotiating.</p>";
  document.querySelectorAll("#recent-deals [data-deal]").forEach((el) =>
    el.addEventListener("click", () => openDeal(Number(el.dataset.deal)))
  );
}

function dealRow(d) {
  return `<div class="deal-row">
    <div class="meta"><strong>${d.item_name}</strong> — ${d.buyer_name}<br>
    Ask ${money(d.ask_price)}${d.agreed_price ? " · Agreed " + money(d.agreed_price) : ""}
    ${d.payment ? " · PayPal " + d.payment.status + " (" + d.payment.mode + ")" : ""}</div>
    <span><span class="status-pill status-${d.status}">${d.status.replace("_", " ")}</span>
    <button data-deal="${d.id}">Open</button></span>
  </div>`;
}

async function loadItems() {
  const items = await api("/api/items");
  $("#items-body").innerHTML = items.map((it) => `<tr>
    <td><strong>${it.name}</strong><br>${it.category} · ${it.qty} units · ${it.days_unsold} days unsold</td>
    <td>${money(it.original_price)}</td>
    <td><strong>${money(it.ai_price)}</strong> <span class="off">${it.ai_discount_pct}% off</span></td>
    <td>${it.dead_score}/100</td>
    <td>${it.ai_reason || ""}</td>
    <td><span class="badge ${it.status}">${it.status}</span></td>
    <td>${it.status === "listed" ? `<button class="secondary" data-reprice="${it.id}">Re-price</button>` : ""}</td>
  </tr>`).join("");
  document.querySelectorAll("[data-reprice]").forEach((el) =>
    el.addEventListener("click", async () => {
      await api(`/api/items/${el.dataset.reprice}/reprice`, { method: "POST" });
      loadItems();
    })
  );
}

async function loadStorefront() {
  const items = await api("/api/storefront");
  $("#store-grid").innerHTML = items.length ? items.map((it) => `<div class="deal-card">
    <h3>${it.name}</h3>
    <p>${it.category} · ${it.qty} in stock · stuck ${it.days_unsold} days</p>
    <p><span class="price-old">${money(it.original_price)}</span>
       <span class="price-new">${money(it.ai_price)}</span>
       <span class="off">${it.ai_discount_pct}% off</span></p>
    <p>${it.ai_reason || ""}</p>
    <button data-negotiate="${it.id}">Negotiate with the agent</button>
  </div>`).join("") : "<p>Nothing listed right now.</p>";
  document.querySelectorAll("[data-negotiate]").forEach((el) =>
    el.addEventListener("click", () => startDeal(Number(el.dataset.negotiate)))
  );
}

async function loadDeals() {
  const deals = await api("/api/deals");
  $("#deals-list").innerHTML = deals.length
    ? deals.map(dealRow).join("")
    : "<p>No deals yet. Open the Storefront and start negotiating.</p>";
  document.querySelectorAll("#deals-list [data-deal]").forEach((el) =>
    el.addEventListener("click", () => openDeal(Number(el.dataset.deal)))
  );
}

async function startDeal(itemId) {
  const buyer = "Guest Buyer";
  const { deal_id } = await api("/api/deals", {
    method: "POST",
    body: JSON.stringify({ item_id: itemId, buyer_name: buyer }),
  });
  openDeal(deal_id);
}

async function openDeal(dealId) {
  currentDealId = dealId;
  currentApproveUrl = null;
  approveOpened = false;
  const data = await api(`/api/deals/${dealId}`);
  const d = data.deal;
  $("#deal-title").textContent = `${d.item_name} — deal with ${d.buyer_name}`;
  $("#deal-status").innerHTML = `Status: <span class="status-pill status-${d.status}">${d.status.replace("_", " ")}</span>
    · Ask: ${money(d.ask_price)}${d.agreed_price ? " · Agreed: " + money(d.agreed_price) : ""}`;
  renderChat(data.messages);
  const negotiating = d.status === "negotiating";
  $("#offer-box").classList.toggle("hidden", !negotiating);
  const payBox = $("#pay-box");
  payBox.classList.toggle("hidden", d.status !== "accepted" && d.status !== "paid");
  if (d.status === "accepted" || d.status === "paid") {
    $("#pay-info").textContent = d.status === "paid"
      ? `Paid ${money(d.agreed_price)}.`
      : `Agreed price ${money(d.agreed_price)}. Pay with PayPal to finish the sale.`;
    const p = data.payment;
    currentApproveUrl = p && p.approve_url ? p.approve_url : null;
    $("#pay-create-btn").classList.toggle("hidden", !!p);
    $("#pay-approve-btn").classList.toggle("hidden", !p || p.status !== "created");
    $("#pay-approve-btn").textContent = "Approve in PayPal";
    $("#pay-capture-btn").classList.toggle("hidden", !p || p.status !== "approved");
    if (p && p.status === "captured") {
      $("#pay-status").textContent = `Captured: ${money(p.amount)} (${p.mode} mode, ${p.capture_id}).`;
    } else {
      $("#pay-status").textContent = p
        ? `PayPal order ${p.paypal_order_id} — ${p.status} (${p.mode} mode).`
        : "";
    }
    if (d.status === "paid") {
      $("#pay-create-btn").classList.add("hidden");
      $("#pay-approve-btn").classList.add("hidden");
      $("#pay-capture-btn").classList.add("hidden");
    }
  }
  showView("deal");
}

function renderChat(messages) {
  $("#chat").innerHTML = messages.map((m) => {
    const who = m.sender === "buyer" ? "You (buyer)" : m.sender === "agent" ? "ShelfClear agent" : "System";
    return `<div class="msg ${m.sender}"><span class="who">${who}</span>${m.text}</div>`;
  }).join("");
  $("#chat").scrollTop = $("#chat").scrollHeight;
}

$("#offer-btn").addEventListener("click", async () => {
  const amount = parseFloat($("#offer-input").value);
  if (!amount || amount <= 0) return;
  $("#offer-input").value = "";
  const res = await api(`/api/deals/${currentDealId}/offer`, {
    method: "POST",
    body: JSON.stringify({ offer: amount }),
  });
  const data = await api(`/api/deals/${currentDealId}`);
  renderChat(data.messages);
  openDeal(currentDealId);
});

$("#pay-create-btn").addEventListener("click", async () => {
  const res = await api(`/api/deals/${currentDealId}/pay`, { method: "POST" });
  currentApproveUrl = res.approve_url;
  $("#pay-status").textContent = `Order ${res.order_id} created (${res.mode} mode).`;
  openDeal(currentDealId);
});

$("#pay-approve-btn").addEventListener("click", async () => {
  // Real sandbox: first click opens the PayPal approval page; the next
  // click verifies the approval with PayPal. Simulator: approve directly.
  if (mode === "sandbox" && currentApproveUrl && !approveOpened) {
    window.open(currentApproveUrl, "_blank");
    approveOpened = true;
    $("#pay-status").textContent = "Approve the payment in the PayPal sandbox tab, then come back and click “I approved — check status”.";
    $("#pay-approve-btn").textContent = "I approved — check status";
    return;
  }
  const res = await api(`/api/deals/${currentDealId}/approve`, { method: "POST" });
  $("#pay-status").textContent = `Approved (${res.mode} mode). Now capture the payment.`;
  openDeal(currentDealId);
});

$("#pay-capture-btn").addEventListener("click", async () => {
  const res = await api(`/api/deals/${currentDealId}/capture`, { method: "POST" });
  $("#pay-status").textContent = `Captured ${money(res.amount)} (${res.mode} mode). Cash recovered!`;
  loadDashboard();
  openDeal(currentDealId);
});

$("#add-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    name: fd.get("name"),
    category: fd.get("category"),
    original_price: parseFloat(fd.get("original_price")),
    cost_price: parseFloat(fd.get("cost_price")),
    floor_price: parseFloat(fd.get("floor_price")),
    qty: parseInt(fd.get("qty"), 10),
    days_unsold: parseInt(fd.get("days_unsold"), 10),
  };
  try {
    await api("/api/items", { method: "POST", body: JSON.stringify(body) });
    $("#form-error").textContent = "";
    e.target.reset();
    loadItems();
  } catch (err) {
    $("#form-error").textContent = err.message;
  }
});

// Deep link: ?deal=12 opens that deal; PayPal return lands on /return.
const params = new URLSearchParams(location.search);
if (params.get("deal")) {
  openDeal(Number(params.get("deal")));
}

loadMode().then(() => showView(params.get("view") || "dashboard"));
