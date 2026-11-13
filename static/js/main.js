// Фронтенд: модалка товару та кошик. Усі дані беруться з Flask API.
const $ = (sel) => document.querySelector(sel);

let product = null;
let selectedSize = null;

async function api(url, body) {
  const res = await fetch(url, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  } : undefined);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Помилка сервера");
  return data;
}

// ===== Модалка товару =====
document.querySelectorAll(".card").forEach((card) =>
  card.addEventListener("click", () => openModal(card.dataset.id))
);

async function openModal(id) {
  product = await api(`/api/products/${id}`);
  selectedSize = null;
  $("#modalImg").style.background = product.bg;
  $("#modalImg").innerHTML = product.svg;
  $("#modalTitle").textContent = product.name;
  $("#modalPrice").textContent = product.price_text;
  $("#modalDesc").textContent = product.desc;
  $("#modalSizes").innerHTML = product.sizes
    .map((s) => `<button class="size" data-size="${s}" aria-pressed="false">${s}</button>`)
    .join("");
  $("#productModal").hidden = false;
  document.body.style.overflow = "hidden";
  $("#productModal .modal-close").focus();
}
function closeModal() {
  $("#productModal").hidden = true;
  document.body.style.overflow = "";
}
$("#modalSizes").addEventListener("click", (e) => {
  const btn = e.target.closest(".size");
  if (!btn) return;
  selectedSize = btn.dataset.size;
  document.querySelectorAll(".size").forEach((b) => b.setAttribute("aria-pressed", b === btn));
});
$("#modalAdd").addEventListener("click", async () => {
  if (!selectedSize) return showToast("Оберіть розмір");
  try {
    renderCart(await api("/api/cart/add", { id: product.id, size: selectedSize }));
    bumpCount();
    closeModal();
    showToast(`${product.name} (${selectedSize}) додано в кошик`);
  } catch (err) { showToast(err.message); }
});
$("#productModal").addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeModal(); });

// ===== Кошик =====
function renderCart(cart) {
  $("#cartCount").textContent = cart.count;
  $("#cartTotal").textContent = cart.total;
  $("#checkoutBtn").disabled = cart.count === 0;
  $("#cartList").innerHTML = cart.items.length
    ? cart.items.map((i, idx) => `
      <li class="cart-item">
        <div class="cart-thumb" style="background:${i.bg}">${i.svg}</div>
        <div>
          <div class="cart-item-name">${i.name}</div>
          <div class="cart-item-meta">Розмір ${i.size} · ${i.price}</div>
          <div class="qty">
            <button data-act="dec" data-idx="${idx}" aria-label="Менше">−</button>
            <span>${i.qty}</span>
            <button data-act="inc" data-idx="${idx}" aria-label="Більше">+</button>
          </div>
        </div>
        <button class="remove" data-act="del" data-idx="${idx}">Видалити</button>
      </li>`).join("")
    : `<li class="cart-empty">Кошик порожній. Оберіть щось у каталозі.</li>`;
}
function bumpCount() {
  const b = $("#cartCount");
  b.classList.remove("bump"); void b.offsetWidth; b.classList.add("bump");
}
$("#cartList").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  try {
    renderCart(await api("/api/cart/update", { index: Number(btn.dataset.idx), action: btn.dataset.act }));
  } catch (err) { showToast(err.message); }
});
async function openCart() {
  renderCart(await api("/api/cart"));
  $("#cartDrawer").hidden = false;
  document.body.style.overflow = "hidden";
}
function closeCart() { $("#cartDrawer").hidden = true; document.body.style.overflow = ""; }
$("#cartOpen").addEventListener("click", openCart);
$("#cartDrawer").addEventListener("click", (e) => { if (e.target.closest("[data-close-cart]")) closeCart(); });
$("#checkoutBtn").addEventListener("click", async () => {
  const res = await api("/api/checkout", {});
  showToast(res.message);
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("#productModal").hidden) closeModal();
  if (!$("#cartDrawer").hidden) closeCart();
});

// ===== Тост =====
let toastTimer;
function showToast(text) {
  const t = $("#toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}
