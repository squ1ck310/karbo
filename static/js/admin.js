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

// ===== Попередній перегляд вибраних фото =====
const photoInput = document.getElementById("photoInput");
if (photoInput) {
  const preview = document.getElementById("photoPreview");
  const zone = photoInput.closest(".upload");
  const text = zone.querySelector("strong");

  photoInput.addEventListener("change", () => {
    preview.querySelectorAll("img").forEach((img) => URL.revokeObjectURL(img.src));
    preview.innerHTML = "";
    [...photoInput.files].forEach((file) => {
      const li = document.createElement("li");
      li.className = "photo";
      const img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      img.alt = file.name;
      li.appendChild(img);
      preview.appendChild(li);
    });
    const n = photoInput.files.length;
    text.textContent = n ? `Обрано фото: ${n}` : "Обрати фото";
  });

  ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, () => zone.classList.add("dragover")));
  ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, () => zone.classList.remove("dragover")));
}

// Видалення фото — з підтвердженням
document.addEventListener("click", (e) => {
  if (e.target.closest(".photo-del") && !confirm("Видалити це фото?")) e.preventDefault();
});
