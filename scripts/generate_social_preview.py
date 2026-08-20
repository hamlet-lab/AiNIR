from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 1280, 640
out = Path("assets/ainir-social-preview.png")
out.parent.mkdir(parents=True, exist_ok=True)
img = Image.new("RGB", (W, H), (15, 19, 25))
d = ImageDraw.Draw(img)

font = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
fb = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
fr = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
Ftitle = ImageFont.truetype(fb, 74)
Ftag = ImageFont.truetype(fr, 30)
Fsmall = ImageFont.truetype(fr, 22)
Fmono = ImageFont.truetype(font, 24)
FmonoS = ImageFont.truetype(font, 20)

WHITE = (242, 245, 248)
MUTED = (176, 188, 202)
BLUE = (118, 196, 255)
GREEN = (111, 255, 150)
RED = (255, 104, 112)
PANEL = (24, 31, 41)
BORDER = (54, 68, 84)
YELLOW = (255, 213, 105)
LINE = (110, 126, 144)

for x in range(0, W, 64):
    d.line((x, 0, x, H), fill=(20, 25, 32), width=1)
for y in range(0, H, 64):
    d.line((0, y, W, y), fill=(20, 25, 32), width=1)

x0, y0 = 70, 62
d.text((x0, y0), "AiNIR", font=Ftitle, fill=WHITE)
d.text((x0, y0 + 92), "Model output is a claim, not a fact.", font=Ftag, fill=BLUE)
d.text((x0, y0 + 142), "Semantic preflight for AI-generated actions before execution.", font=Fsmall, fill=MUTED)

ai = (70, 250, 275, 320)
gate = (335, 250, 610, 320)
passb = (700, 225, 825, 285)
host = (920, 225, 1205, 285)
refb = (700, 300, 845, 360)
stop = (930, 300, 1205, 360)

for label, box, col in [
    ("AI proposes", ai, BLUE),
    ("AiNIR Trust Gate", gate, WHITE),
    ("PASS", passb, GREEN),
    ("Host may execute", host, MUTED),
    ("REFUSE", refb, RED),
    ("Stop + explain", stop, RED),
]:
    d.rounded_rectangle(box, radius=16, fill=PANEL, outline=BORDER, width=2)
    bbox = d.textbbox((0, 0), label, font=Fsmall)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((box[0] + box[2] - tw) / 2, (box[1] + box[3] - th) / 2 - 2), label, font=Fsmall, fill=col)


def arrow(x1, y1, x2, y2):
    import math
    d.line((x1, y1, x2, y2), fill=LINE, width=3)
    ang = math.atan2(y2 - y1, x2 - x1)
    size = 10
    pts = [
        (x2, y2),
        (x2 - size * math.cos(ang - 0.6), y2 - size * math.sin(ang - 0.6)),
        (x2 - size * math.cos(ang + 0.6), y2 - size * math.sin(ang + 0.6)),
    ]
    d.polygon(pts, fill=LINE)


arrow(ai[2] + 15, 285, gate[0] - 15, 285)
junction_x = 650
arrow(gate[2] + 15, 285, junction_x, 285)
d.line((junction_x, 285, junction_x, 255), fill=LINE, width=3)
d.line((junction_x, 285, junction_x, 330), fill=LINE, width=3)
arrow(junction_x, 255, passb[0] - 15, 255)
arrow(passb[2] + 15, 255, host[0] - 15, 255)
arrow(junction_x, 330, refb[0] - 15, 330)
arrow(refb[2] + 15, 330, stop[0] - 15, 330)

left = (70, 405, 605, 575)
right = (675, 405, 1210, 575)
for box, title, dot in [(left, "REFUSED path", RED), (right, "PASSED path", GREEN)]:
    d.rounded_rectangle(box, radius=18, fill=PANEL, outline=BORDER, width=2)
    d.rounded_rectangle((box[0], box[1], box[2], box[1] + 42), radius=18, fill=(34, 42, 54))
    d.rectangle((box[0], box[1] + 18, box[2], box[1] + 42), fill=(34, 42, 54))
    d.ellipse((box[2] - 32, box[1] + 13, box[2] - 18, box[1] + 27), fill=dot)
    d.text((box[0] + 18, box[1] + 10), title, font=Fsmall, fill=WHITE)

d.text((90, 463), "AccountDeletion", font=Fmono, fill=WHITE)
d.text((90, 500), "hard_delete_user", font=FmonoS, fill=YELLOW)
d.text((90, 536), "REFUSED  •  10 critical findings", font=FmonoS, fill=RED)

d.text((695, 463), "CreateUserOutbox", font=Fmono, fill=WHITE)
d.text((695, 500), "transaction-bound safe path", font=FmonoS, fill=MUTED)
d.text((695, 536), "PASSED  •  TrustReceipt available", font=FmonoS, fill=GREEN)

d.text((70, 603), "AI proposes. AiNIR checks whether the proposal has earned the right to proceed.", font=Fsmall, fill=(202, 212, 224))

img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
img.save(out, optimize=True)
print(out)
