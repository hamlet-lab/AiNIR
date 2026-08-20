from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
mono18 = ImageFont.truetype(FONT, 18)
mono20 = ImageFont.truetype(FONT, 20)
mono22 = ImageFont.truetype(FONT, 22)
mono28 = ImageFont.truetype(FONT, 28)
ui18 = ImageFont.truetype(FONT, 18)
ui20 = ImageFont.truetype(FONT, 20)

WHITE = (235, 235, 235)
GREEN = (146, 255, 146)
RED = (255, 108, 108)
YELLOW = (255, 214, 102)
BLUE = (140, 205, 255)
MUTED = (180, 190, 200)
BG = (16, 16, 16)
WIN_PANEL = (10, 10, 10)
WIN_TITLE = (34, 34, 34)
BORDER = (50, 58, 70)


def text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    image = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(image)
    return draw.textbbox((0, 0), text, font=font)[2]


def wrap(text: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if text_width(candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current or not lines:
        lines.append(current)
    return lines


def command_lines(prompt: str, command: str, max_width: int) -> list[str]:
    tokens = command.split(" ")
    lines: list[str] = []
    current = ""
    continuation = "... "
    for token in tokens:
        candidate = token if not current else current + " " + token
        prefix = prompt if not lines else continuation
        if text_width(prefix + candidate, mono20) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(prefix + current)
                current = token
            else:
                rest = token
                while rest:
                    prefix = prompt if not lines else continuation
                    part = ""
                    for char in rest:
                        if text_width(prefix + part + char, mono20) <= max_width:
                            part += char
                        else:
                            break
                    lines.append(prefix + part)
                    rest = rest[len(part) :]
    prefix = prompt if not lines else continuation
    if current or not lines:
        lines.append(prefix + current)
    return lines


def command_prompt_base() -> Image.Image:
    width, height = 980, 560
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    margin = 18
    draw.rounded_rectangle(
        (margin, margin, width - margin, height - margin),
        radius=18,
        fill=WIN_PANEL,
        outline=BORDER,
        width=2,
    )
    draw.rounded_rectangle(
        (margin, margin, width - margin, margin + 44),
        radius=18,
        fill=WIN_TITLE,
    )
    draw.rectangle((margin, margin + 18, width - margin, margin + 44), fill=WIN_TITLE)
    x = width - margin - 88
    for label in ["—", "□", "×"]:
        draw.text((x, margin + 8), label, font=ui18, fill=(220, 220, 220))
        x += 28
    title = "Command Prompt"
    title_width = draw.textbbox((0, 0), title, font=ui20)[2]
    draw.text(((width - title_width) / 2, margin + 11), title, font=ui20, fill=WHITE)
    return image


def render_short(
    base: Image.Image,
    input_lines: list[str],
    content: list[tuple[str, tuple[int, int, int]]],
    typed_counts: list[int] | None = None,
    caret: tuple[int, int] | None = None,
) -> Image.Image:
    image = base.copy()
    draw = ImageDraw.Draw(image)
    x, y = 46, 92
    draw.text((x, y), "AiNIR Trust Gate demo", font=mono22, fill=BLUE)
    y += 34
    for index, line in enumerate(input_lines):
        visible = line
        if typed_counts is not None:
            count = typed_counts[index]
            visible = line[:count]
            if caret and index == caret[0] and count <= len(line):
                visible += "█"
        draw.text((x, y), visible, font=mono20, fill=GREEN)
        y += 28
    y += 10
    for line, color in content:
        if not line:
            y += 10
            continue
        for piece in wrap(line, 860, mono20):
            draw.text((x, y), piece, font=mono20, fill=color)
            y += 28
    return image


def save_gif(frames: list[Image.Image], durations: list[int], path: Path) -> None:
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


def generate_short_demo() -> None:
    base = command_prompt_base()
    prompt = "PS C:\\ainir> "
    command = (
        "python -m ainir trust evaluate "
        "examples/account_deletion_hard_delete_blocked/draft.yaml --json"
    )
    inputs = command_lines(prompt, command, 885)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for line_index, line in enumerate(inputs):
        for char_index in range(1, len(line) + 1):
            counts = [
                len(item) if index < line_index else char_index if index == line_index else 0
                for index, item in enumerate(inputs)
            ]
            frames.append(render_short(base, inputs, [], counts, (line_index, char_index)))
            durations.append(42)

    output = [
        ("{", WHITE),
        ('  "status": "REFUSED",', RED),
        ('  "workflow": "AccountDeletion",', WHITE),
        ('  "critical_findings": 10,', YELLOW),
        ('  "highlights": [', WHITE),
        ('    "destructive hard delete effect",', WHITE),
        ('    "capability not sufficiently authorized",', WHITE),
        ('    "evidence requirements unmet"', WHITE),
        ("  ]", WHITE),
        ("}", WHITE),
        ("", WHITE),
        ("Next: create_user_outbox_safe", MUTED),
        ("→ PASSED  •  TrustReceipt available", GREEN),
    ]
    shown: list[tuple[str, tuple[int, int, int]]] = []
    for line, color in output:
        if not line:
            shown.append((line, color))
            frames.append(render_short(base, inputs, shown))
            durations.append(160)
            continue
        segment = max(4, min(14, len(line) // 2))
        frames.append(render_short(base, inputs, shown + [(line[:segment], color)]))
        durations.append(120)
        shown.append((line, color))
        frames.append(render_short(base, inputs, shown))
        durations.append(320 if "PASSED" in line else 210)
    for _ in range(6):
        frames.append(render_short(base, inputs, shown))
        durations.append(340)

    save_gif(frames, durations, OUT / "ainir-readme-short-demo.gif")


def comparison_frame(left_steps: int, right_steps: int, final: bool = False) -> Image.Image:
    width, height = 1100, 680
    image = Image.new("RGB", (width, height), (16, 20, 24))
    draw = ImageDraw.Draw(image)
    draw.text((34, 24), "AiNIR: REFUSED vs PASSED", font=mono28, fill=WHITE)
    draw.text(
        (34, 60),
        "Same trust gate, two different outcomes based on evidence and semantic boundaries",
        font=mono20,
        fill=MUTED,
    )
    left = (34, 104, 530, 640)
    right = (570, 104, 1066, 640)
    for box, title, dot in [(left, "REFUSED path", RED), (right, "PASSED path", GREEN)]:
        draw.rounded_rectangle(box, radius=18, fill=(22, 28, 36), outline=(58, 68, 80), width=2)
        draw.rounded_rectangle((box[0], box[1], box[2], box[1] + 42), radius=18, fill=(32, 38, 48))
        draw.rectangle((box[0], box[1] + 18, box[2], box[1] + 42), fill=(32, 38, 48))
        draw.text((box[0] + 18, box[1] + 11), title, font=ui18, fill=WHITE)
        draw.ellipse((box[2] - 28, box[1] + 12, box[2] - 14, box[1] + 26), fill=dot)

    left_lines = [
        ("PS C:\\ainir> evaluate AccountDeletion", GREEN),
        ("workflow: AccountDeletion", WHITE),
        ("op: db.hard_delete_user", WHITE),
        ("checks: evidence ✕, capability ✕, transaction ✕", YELLOW),
        ("result: REFUSED (10 critical)", RED),
    ]
    right_lines = [
        ("PS C:\\ainir> evaluate CreateUserOutbox", GREEN),
        ("workflow: CreateUserOutbox", WHITE),
        ("pattern: transaction-bound outbox", WHITE),
        ("checks: evidence ✓, capability ✓, transaction ✓", GREEN),
        ("result: PASSED • TrustReceipt available", GREEN),
    ]

    def draw_panel(lines, box, steps):
        x, y = box[0] + 18, box[1] + 58
        max_width = box[2] - box[0] - 36
        for text, color in lines[:steps]:
            for piece in wrap(text, max_width, mono20):
                draw.text((x, y), piece, font=mono20, fill=color)
                y += 32
            y += 4

    draw_panel(left_lines, left, left_steps)
    draw_panel(right_lines, right, right_steps)

    if final:
        banner = (250, 590, 850, 646)
        draw.rounded_rectangle(banner, radius=14, fill=(40, 46, 58))
        message = "AI proposes. AiNIR decides whether the proposal may move forward."
        y = banner[1] + 10
        for piece in wrap(message, banner[2] - banner[0] - 28, mono18)[:2]:
            draw.text((banner[0] + 16, y), piece, font=mono18, fill=BLUE)
            y += 20
    return image


def generate_comparison() -> None:
    frames: list[Image.Image] = []
    durations: list[int] = []
    for left, right in [(1, 1), (2, 2), (3, 3), (4, 4), (5, 5)]:
        frames.append(comparison_frame(left, right))
        durations.append(500)
    for _ in range(6):
        frames.append(comparison_frame(5, 5, True))
        durations.append(420)
    save_gif(frames, durations, OUT / "ainir-refused-vs-passed.gif")


if __name__ == "__main__":
    generate_short_demo()
    generate_comparison()
    print(OUT / "ainir-readme-short-demo.gif")
    print(OUT / "ainir-refused-vs-passed.gif")
