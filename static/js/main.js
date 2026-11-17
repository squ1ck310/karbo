// Фронтенд: модалка товару та кошик. Усі дані беруться з Flask API.
const $ = (sel) => document.querySelector(sel);

let product = null;
let selectedSize = null;
let step = "cart"; // cart → form → done

const CSRF = document.querySelector('meta[name="csrf-token"]').content;
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

async function api(url, body) {
  const res = await fetch(url, body ? {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF },
    body: JSON.stringify(body),
  } : undefined);
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok) {
    const err = new Error(data.error || "Помилка сервера, спробуйте ще раз");
    err.fields = data.fields;
    throw err;
  }
  return data;
}

// ===== Модалка товару =====
document.querySelectorAll(".card").forEach((card) =>
  card.addEventListener("click", () => openModal(card.dataset.id))
);

async function openModal(id) {
  product = await api(`/api/products/${id}`);
  selectedSize = null;
  renderGallery(0);
  $("#modalTitle").textContent = product.name;
  $("#modalPrice").textContent = product.price_text;
  $("#modalDesc").textContent = product.desc;
  $("#modalSizes").innerHTML = product.sizes
    .map((s) => `<button class="size" data-size="${esc(s)}" aria-pressed="false">${esc(s)}</button>`)
    .join("");
  $("#productModal").hidden = false;
  document.body.style.overflow = "hidden";
  $("#productModal .modal-close").focus();
}
function renderGallery(active) {
  const imgBox = $("#modalImg");
  const thumbs = $("#modalThumbs");
  if (!product.images.length) {
    imgBox.classList.remove("has-photo");
    imgBox.innerHTML = '<span class="ph-k" aria-hidden="true">K</span>';
    thumbs.innerHTML = "";
    return;
  }
  imgBox.classList.add("has-photo");
  imgBox.innerHTML = `<img src="${esc(product.images[active])}" referrerpolicy="no-referrer" alt="${esc(product.name)}, фото ${active + 1}">`;
  thumbs.innerHTML = product.images.length > 1
    ? product.images.map((src, i) => `
        <button class="thumb-btn" data-i="${i}" aria-label="Фото ${i + 1}" aria-pressed="${i === active}">
          <img src="${esc(src)}" referrerpolicy="no-referrer" alt="">
        </button>`).join("")
    : "";
}
$("#modalThumbs").addEventListener("click", (e) => {
  const btn = e.target.closest(".thumb-btn");
  if (btn) renderGallery(Number(btn.dataset.i));
});

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
let needsAddress = false;
function renderCart(cart) {
  needsAddress = !!cart.needs_address;
  $("[data-addr]").hidden = !needsAddress;
  $("[data-np]").hidden = needsAddress;
  $("#cartCount").textContent = cart.count;
  $("#cartTotal").textContent = cart.total;
  $("#checkoutBtn").disabled = cart.count === 0;
  $("#cartList").innerHTML = cart.items.length
    ? cart.items.map((i, idx) => `
      <li class="cart-item">
        <div class="cart-thumb ${i.has_photo ? "has-photo" : ""}">${i.has_photo ? i.media : '<span class="ph-k" aria-hidden="true">K</span>'}</div>
        <div>
          <div class="cart-item-name">${esc(i.name)}</div>
          <div class="cart-item-meta">Розмір ${esc(i.size)} · ${esc(i.price)}</div>
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
  setStep("cart");
  $("#cartDrawer").hidden = false;
  document.body.style.overflow = "hidden";
}
function closeCart() { $("#cartDrawer").hidden = true; document.body.style.overflow = ""; }
$("#cartOpen").addEventListener("click", openCart);
$("#cartDrawer").addEventListener("click", (e) => { if (e.target.closest("[data-close-cart]")) closeCart(); });

// ===== Оформлення замовлення =====
function setStep(next) {
  step = next;
  $("#cartList").hidden = step !== "cart";
  $("#checkoutForm").hidden = step !== "form";
  $("#checkoutDone").hidden = step !== "done";
  $("#drawerFoot").hidden = step === "done";
  $(".drawer-head h3").textContent = step === "cart" ? "Кошик" : "Оформлення";
  $("#checkoutBtn").textContent = step === "form" ? "Підтвердити замовлення" : "Оформити замовлення";
  if (step === "form") $("#checkoutForm input").focus();
}
$("#checkoutBack").addEventListener("click", () => setStep("cart"));
$("#checkoutBtn").addEventListener("click", () => (step === "cart" ? setStep("form") : submitOrder()));
$("#checkoutForm").addEventListener("submit", (e) => { e.preventDefault(); submitOrder(); });

function showFieldErrors(fields = {}) {
  document.querySelectorAll(".field-error").forEach((el) => el.remove());
  document.querySelectorAll("#checkoutForm .invalid").forEach((el) => el.classList.remove("invalid"));
  Object.entries(fields).forEach(([name, msg]) => {
    const input = $(`#checkoutForm [name="${name}"]`);
    if (!input) return;
    input.classList.add("invalid");
    input.insertAdjacentHTML("afterend", `<span class="field-error">${esc(msg)}</span>`);
  });
  const first = $("#checkoutForm .invalid");
  if (first) first.focus();
}

async function submitOrder() {
  const btn = $("#checkoutBtn");
  btn.disabled = true;
  btn.textContent = "Відправляємо…";
  try {
    const data = Object.fromEntries(new FormData($("#checkoutForm")));
    const res = await api("/api/checkout", data);
    if (res.redirect) {            // оплата через Stripe: йдемо на сторінку оплати
      btn.textContent = "Переходимо до оплати…";
      btn.dataset.redirecting = "1";   // не даємо натиснути вдруге й створити друге замовлення
      window.location.href = res.redirect;
      return;
    }
    showFieldErrors();
    $("#checkoutForm").reset();
    $("#checkoutDone").innerHTML = `<h4>Дякуємо!</h4><p>${esc(res.message)}</p>`;
    renderCart(await api("/api/cart"));
    setStep("done");
  } catch (err) {
    btn.disabled = false;
    setStep("form");
    showFieldErrors(err.fields);
    showToast(err.message);
  } finally {
    if (!btn.dataset.redirecting) btn.disabled = false;
  }
}

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

// Покупець закрив сторінку оплати Stripe — кошик лишився, просто кажемо про це
if (new URLSearchParams(location.search).get("payment") === "cancelled") {
  showToast("Оплату скасовано. Товари лишились у кошику");
  history.replaceState(null, "", location.pathname + location.hash);
}
