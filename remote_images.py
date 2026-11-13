"""Фото за посиланням: перетворення посилань Imgur на прямі й перевірка, що там справді картинка."""

import io
import ipaddress
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 8
USER_AGENT = "Mozilla/5.0 (compatible; LizkaShop/1.0; +image-check)"


class RemoteImageError(ValueError):
    pass


IMGUR_ID = r"[A-Za-z0-9]{5,10}"


def normalize_url(raw: str) -> str:
    """Приводить посилання до прямого посилання на картинку.
    imgur.com/abc123  →  https://i.imgur.com/abc123.jpg"""
    url = raw.strip()
    if not url:
        raise RemoteImageError("Порожнє посилання")
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")

    if host in ("imgur.com", "www.imgur.com", "m.imgur.com"):
        if path.startswith(("/a/", "/gallery/", "/t/", "/user/")):
            raise RemoteImageError(
                "Це посилання на альбом Imgur, а не на одне фото. Відкрий потрібне фото, "
                "клацни по ньому правою кнопкою → «Копіювати адресу зображення»"
            )
        m = re.fullmatch(rf"/({IMGUR_ID})(\.\w+)?", path)
        if not m:
            raise RemoteImageError("Не вдалося розпізнати посилання Imgur")
        return f"https://i.imgur.com/{m.group(1)}{m.group(2) or '.jpg'}"

    if host == "i.imgur.com":
        m = re.fullmatch(rf"/({IMGUR_ID})(\.\w+)?", path)
        if not m:
            raise RemoteImageError("Не вдалося розпізнати посилання Imgur")
        return f"https://i.imgur.com/{m.group(1)}{m.group(2) or '.jpg'}"

    if host in ("prnt.sc", "prntscr.com"):
        raise RemoteImageError("Посилання prnt.sc ведуть на сторінку з рекламою, а не на картинку. Краще завантаж файл")

    if parsed.scheme.lower() != "https":
        raise RemoteImageError("Потрібне посилання, що починається з https://")
    if len(url) > 500:
        raise RemoteImageError("Посилання задовге")
    return url


def _check_host_is_public(url: str):
    """Захист: сервер не має ходити за посиланнями на внутрішні адреси (localhost, приватні мережі)."""
    host = urlparse(url).hostname
    if not host:
        raise RemoteImageError("Некоректне посилання")
    try:
        infos = socket.getaddrinfo(host, 443)
    except socket.gaierror:
        raise RemoteImageError(f"Сайт {host} не знайдено")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise RemoteImageError("Посилання веде на внутрішню адресу")


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise RemoteImageError("Посилання перенаправляє на небезпечну адресу")
        _check_host_is_public(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirect)


def inspect_remote_image(url: str):
    """Завантажує картинку й повертає (width, height).
    Кидає RemoteImageError, якщо за посиланням точно не картинка.
    Повертає (None, None), якщо перевірити не вдалося з мережевих причин (сайт тимчасово відмовив)."""
    _check_host_is_public(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if not ctype.startswith("image/"):
                raise RemoteImageError("За посиланням не картинка, а сторінка. Потрібне пряме посилання на фото")
            raw = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            raise RemoteImageError("За посиланням нічого немає (404). Можливо, фото видалене")
        return None, None          # 403/429/5xx — сайт не пустив сервер, але в браузері може працювати
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, None

    if len(raw) > MAX_BYTES:
        raise RemoteImageError("Фото за посиланням більше 10 МБ")
    try:
        img = Image.open(io.BytesIO(raw))
        return img.size
    except (UnidentifiedImageError, OSError):
        raise RemoteImageError("За посиланням не вдалося відкрити картинку")
