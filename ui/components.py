import tkinter as tk
from config import COR_BORDA, COR_CARD, COR_PRIMARIA, COR_TEXTO

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# Fontes do sistema para o percentual
_FONT_PATHS = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


class CircularProgress(tk.Label):
    """Indicador de progresso circular com anti-aliasing e glow laranja.

    Usa tk.Label (não Canvas) para evitar conflito de fundo com ttkbootstrap.
    """

    _TRACK = (215, 210, 205)     # anel de fundo cinza claro
    _ARC   = (229, 138, 78)     # laranja primário (#E58A4E)
    _EDGE  = (252, 195, 148)    # laranja claro (borda brilhante)
    _TXT   = (60, 60, 60)       # texto escuro

    def __init__(self, parent, size: int = 140, bg: str = "#F5F5F5", **kwargs):
        super().__init__(parent, bg=bg, borderwidth=0, padx=0, pady=0, **kwargs)
        self._size = size
        self._bg_hex = bg
        self._value = 0
        self._maximum = 100
        self._photo_ref = None
        self._pil_font = self._carregar_fonte(max(int(size * 0.16 * 3), 12))
        self._redraw()

    @staticmethod
    def _hex_to_rgb(h: str):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    @staticmethod
    def _carregar_fonte(size_px: int):
        if not _PIL_OK:
            return None
        for path in _FONT_PATHS:
            try:
                return ImageFont.truetype(path, size_px)
            except Exception:
                pass
        return None

    def _redraw(self):
        pct = self._value / max(self._maximum, 1)
        s = self._size
        if _PIL_OK:
            self._render_pil(s, pct)
        else:
            self.configure(
                text=f"{int(pct * 100)}%",
                font=("Segoe UI", max(int(s * 0.16), 12), "bold"),
                fg="white",
            )

    def _render_pil(self, s: int, pct: float):
        SCALE = 3
        S = s * SCALE
        pad = 18 * SCALE
        extent = min(pct * 360.0, 359.5)

        bg_rgb = self._hex_to_rgb(self._bg_hex)
        base = Image.new("RGBA", (S, S), (*bg_rgb, 255))

        d = ImageDraw.Draw(base)

        # Anel de fundo (track)
        d.arc([pad, pad, S - pad, S - pad],
              start=0, end=360,
              fill=(*self._TRACK, 255), width=SCALE * 10)

        if extent > 0.5:
            # Arco principal
            d.arc([pad, pad, S - pad, S - pad],
                  start=-90, end=-90 + extent,
                  fill=(*self._ARC, 255), width=SCALE * 10)
            # Borda brilhante
            ep = pad + SCALE * 2
            d.arc([ep, ep, S - ep, S - ep],
                  start=-90, end=-90 + extent,
                  fill=(*self._EDGE, 255), width=SCALE * 3)

        # Texto do percentual desenhado no PIL (evita criar_text sobre Canvas)
        txt = f"{int(pct * 100)}%"
        d2 = ImageDraw.Draw(base)
        font = self._pil_font
        try:
            bbox = d2.textbbox((0, 0), txt, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (S - tw) // 2 - bbox[0]
            ty = (S - th) // 2 - bbox[1]
            d2.text((tx, ty), txt, fill=(*self._TXT, 255), font=font)
        except Exception:
            d2.text((S // 2, S // 2), txt, fill=(*self._TXT, 255), anchor="mm")

        img = base.convert("RGB").resize((s, s), Image.LANCZOS)
        photo = _PILImageTk.PhotoImage(img)
        self._photo_ref = photo
        self.configure(image=photo, text="")

    # ── interface dict-style (progress["value"] = x) ──────────────────────────

    def __setitem__(self, key: str, value):
        if key == "value":
            self._value = max(0, int(value))
            self._redraw()
        elif key == "maximum":
            self._maximum = max(1, int(value))
            self._redraw()
        else:
            self.configure(**{key: value})

    def __getitem__(self, key: str):
        if key == "value":
            return self._value
        if key == "maximum":
            return self._maximum
        return super().__getitem__(key)


def _escurecer(hex_color: str) -> str:
    """Escurece uma cor hex em ~15%."""
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    r = max(0, int(r * 0.85))
    g = max(0, int(g * 0.85))
    b = max(0, int(b * 0.85))
    return f"#{r:02x}{g:02x}{b:02x}"


def criar_botao(parent, texto, comando, bg, fg="#FFFFFF", width=28, font_size=11):
    """Cria botão com efeito hover."""
    cor_hover = _escurecer(bg)
    btn = tk.Button(
        parent,
        text=texto,
        font=("Segoe UI", font_size, "bold"),
        bg=bg,
        fg=fg,
        relief="flat",
        width=width,
        cursor="hand2",
        command=comando,
        activebackground=cor_hover,
        activeforeground=fg,
        pady=8,
        bd=0,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=cor_hover))
    btn.bind("<Leave>", lambda e: btn.configure(bg=bg))
    return btn


def criar_entry(parent, **kwargs):
    """Entry com borda arredondada simulada via Frame."""
    frame = tk.Frame(parent, bg=COR_BORDA, padx=1, pady=1)
    entry = tk.Entry(
        frame,
        font=("Segoe UI", 12),
        justify="center",
        relief="flat",
        bg=COR_CARD,
        fg=COR_TEXTO,
        insertbackground=COR_TEXTO,
        **kwargs
    )
    entry.pack(fill="x", padx=2, pady=2)
    entry.bind("<FocusIn>", lambda e: frame.configure(bg=COR_PRIMARIA))
    entry.bind("<FocusOut>", lambda e: frame.configure(bg=COR_BORDA))
    return frame, entry
