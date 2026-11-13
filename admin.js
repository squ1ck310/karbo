// Підтвердження видалення товару
const dialog = document.getElementById("deleteDialog");
const form = document.getElementById("deleteForm");

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-delete-url]");
  if (!btn) return;
  form.action = btn.dataset.deleteUrl;
  document.getElementById("deleteName").textContent = btn.dataset.deleteName;
  dialog.showModal();
  document.getElementById("deleteCancel").focus(); // за замовчуванням фокус на «Скасувати»
});

document.getElementById("deleteCancel").addEventListener("click", () => dialog.close());
// Клік по затемненню поза вікном закриває його
dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
