import tkinter as tk
from config import (
    COR_BG, COR_BORDA, COR_BORDA_LEVE, COR_CARD, COR_CARD_HOVER,
    COR_GOLD, COR_GOLD_CLARO, COR_PRIMARIA, COR_SUBTEXTO, COR_TEXTO,
    FONT_BODY, FONT_DISPLAY,
)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


# ============================================================================
# Helpers visuais (inspirados na estetica Soraluna)
# ============================================================================

def eyebrow(parent, text: str, *, bg: str | None = None) -> tk.Frame:
    """Linha-acento + texto pequeno em caixa alta dourada.

    Uso: cabeca de cada secao. Renderiza:
        ─── TITULO DA SECAO
    """
    bg = bg or _bg_of(parent)
    f = tk.Frame(parent, bg=bg)
    tk.Frame(f, bg=COR_GOLD, width=26, height=1).pack(side="left", padx=(0, 10), pady=4)
    tk.Label(
        f, text=text.upper(),
        font=(FONT_BODY, 9, "bold"),
        fg=COR_GOLD, bg=bg,
        anchor="w",
    ).pack(side="left")
    return f


def hero_title(parent, principal: str, italico: str = "", *,
               size: int = 32, bg: str | None = None) -> tk.Frame:
    """Titulo grande em serif (Georgia) com palavra opcional em italico dourado."""
    bg = bg or _bg_of(parent)
    f = tk.Frame(parent, bg=bg)
    tk.Label(
        f, text=principal,
        font=(FONT_DISPLAY, size),
        fg=COR_TEXTO, bg=bg,
    ).pack(side="left")
    if italico:
        tk.Label(
            f, text=" " + italico,
            font=(FONT_DISPLAY, size, "italic"),
            fg=COR_GOLD_CLARO, bg=bg,
        ).pack(side="left")
    return f


def subtitle(parent, text: str, *, bg: str | None = None) -> tk.Label:
    """Texto secundario sob o hero — em sans, cor subtexto."""
    bg = bg or _bg_of(parent)
    return tk.Label(
        parent, text=text,
        font=(FONT_BODY, 10),
        fg=COR_SUBTEXTO, bg=bg,
        anchor="w", justify="left",
    )


def pill(parent, text: str, *, fg: str = None, bg_pill: str = None) -> tk.Label:
    """Badge arredondado para status (Pronto, Processando, Erro)."""
    return tk.Label(
        parent, text=f"  {text}  ",
        font=(FONT_BODY, 9, "bold"),
        fg=fg or COR_GOLD_CLARO,
        bg=bg_pill or COR_BG,
        padx=4, pady=2,
    )


def divider(parent, *, color: str = None, padding: tuple = (12, 12),
            bg: str | None = None) -> tk.Frame:
    """Linha horizontal sutil — separa secoes."""
    bg = bg or _bg_of(parent)
    wrap = tk.Frame(parent, bg=bg)
    tk.Frame(wrap, bg=color or COR_BORDA_LEVE, height=1).pack(
        fill="x", pady=padding,
    )
    return wrap


def card_frame(parent, *, bg: str | None = None) -> tk.Frame:
    """Container com fundo elevado + borda sutil — padrao 'card' Soraluna."""
    return tk.Frame(
        parent,
        bg=bg or COR_CARD,
        highlightbackground=COR_BORDA,
        highlightthickness=1,
    )


def municipios_chips(parent, municipios: list[str], *,
                     prefix: str = "Municípios atendidos") -> tk.Frame:
    """Mostra os municípios da aba como CHIPS bem visíveis.

    Layout:
        MUNICÍPIOS ATENDIDOS   [ Goiânia ]  [ Aparecida ]  [ Anápolis ]
    """
    wrap = tk.Frame(parent, bg=_bg_of(parent))
    tk.Label(
        wrap, text=prefix.upper(),
        font=(FONT_BODY, 8, "bold"),
        fg=COR_GOLD, bg=_bg_of(parent),
    ).pack(side="left", padx=(0, 12))
    for nome in municipios:
        chip = tk.Frame(
            wrap,
            bg=COR_CARD,
            highlightbackground=COR_GOLD,
            highlightthickness=1,
        )
        chip.pack(side="left", padx=(0, 6), pady=2)
        tk.Label(
            chip, text=f"  {nome}  ",
            font=(FONT_BODY, 9, "bold"),
            fg=COR_GOLD_CLARO, bg=COR_CARD,
            padx=6, pady=3,
        ).pack()
    return wrap


def hero_compacto(parent, eyebrow_text: str, titulo: str,
                  italico: str, subtit: str) -> tk.Frame:
    """Hero compacto em UMA linha — eyebrow gold + título serif + subtítulo.

    Visual:
        ─── ABA · TITULO    Geração X.    sub · sub · sub
    Ocupa ~60px de altura em vez dos ~280px dos 3 cards do hero_card.
    """
    card = tk.Frame(
        parent, bg=COR_CARD,
        highlightbackground=COR_BORDA_LEVE, highlightthickness=1,
    )
    inner = tk.Frame(card, bg=COR_CARD)
    inner.pack(fill="x", padx=18, pady=10)

    # Linha 1: eyebrow + título lado a lado
    linha1 = tk.Frame(inner, bg=COR_CARD)
    linha1.pack(fill="x")
    tk.Frame(linha1, bg=COR_GOLD, width=20, height=1).pack(
        side="left", padx=(0, 8), pady=10,
    )
    tk.Label(
        linha1, text=eyebrow_text.upper(),
        font=(FONT_BODY, 8, "bold"),
        fg=COR_GOLD, bg=COR_CARD,
    ).pack(side="left", padx=(0, 14))
    tk.Label(
        linha1, text=titulo,
        font=(FONT_DISPLAY, 18),
        fg=COR_TEXTO, bg=COR_CARD,
    ).pack(side="left")
    if italico:
        tk.Label(
            linha1, text=" " + italico,
            font=(FONT_DISPLAY, 18, "italic"),
            fg=COR_GOLD_CLARO, bg=COR_CARD,
        ).pack(side="left")

    # Linha 2: subtítulo (pequeno)
    tk.Label(
        inner, text=subtit,
        font=(FONT_BODY, 9),
        fg=COR_SUBTEXTO, bg=COR_CARD,
        anchor="w", justify="left",
    ).pack(anchor="w", pady=(2, 0))

    return card


def hero_card(parent, kind: str, eyebrow_text: str = "",
              titulo: str = "", italico: str = "", subtit: str = "",
              *, size: int = 30) -> tk.Frame:
    """Hero composto por 3 mini-cards empilhados, todos alinhados (mesma
    largura via fill='x'), cada um com fundo elevado e borda sutil.

    kind:
        "eyebrow" -> renderiza eyebrow_text (linha gold + uppercase)
        "title"   -> renderiza titulo + italico em serif
        "subtitle"-> renderiza subtit em sans

    Wraps individuais ficam consistentes em padding e borda.
    """
    card = tk.Frame(
        parent,
        bg=COR_CARD,
        highlightbackground=COR_BORDA_LEVE,
        highlightthickness=1,
    )
    inner = tk.Frame(card, bg=COR_CARD)
    inner.pack(fill="x", padx=18, pady=10)

    if kind == "eyebrow":
        tk.Frame(inner, bg=COR_GOLD, width=26, height=1).pack(
            side="left", padx=(0, 10), pady=4,
        )
        tk.Label(
            inner, text=eyebrow_text.upper(),
            font=(FONT_BODY, 9, "bold"),
            fg=COR_GOLD, bg=COR_CARD,
            anchor="w",
        ).pack(side="left")
    elif kind == "title":
        tk.Label(
            inner, text=titulo,
            font=(FONT_DISPLAY, size),
            fg=COR_TEXTO, bg=COR_CARD,
        ).pack(side="left")
        if italico:
            tk.Label(
                inner, text=" " + italico,
                font=(FONT_DISPLAY, size, "italic"),
                fg=COR_GOLD_CLARO, bg=COR_CARD,
            ).pack(side="left")
    elif kind == "subtitle":
        tk.Label(
            inner, text=subtit,
            font=(FONT_BODY, 10),
            fg=COR_SUBTEXTO, bg=COR_CARD,
            anchor="w", justify="left",
        ).pack(side="left")

    return card


def _bg_of(widget) -> str:
    """Lê o bg de um widget tkinter — gracefully cai pra COR_BG."""
    try:
        return widget.cget("bg") or COR_BG
    except tk.TclError:
        return COR_BG

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
