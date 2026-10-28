#!/usr/bin/env python3
"""
QR Code Generator
=================
Create customized QR codes for plain text, website URLs, Wi-Fi credentials
and vCard contacts, and save them as PNG or JPEG using Pillow.

Customization
-------------
* Colors: foreground and background (names like "navy" or hex like "#0a3d62")
* Border thickness (quiet zone, in modules)
* Error correction level: L (~7%), M (~15%), Q (~25%), H (~30%)
* Module size (pixels per square)

Install
-------
    pip install qrcode pillow

Usage
-----
    python qr_generator.py                       # interactive mode
    python qr_generator.py text "Hello" -o hello.png
    python qr_generator.py url example.com --fill "#0a3d62" --back white
    python qr_generator.py wifi --ssid HomeNet --password secret123 --security WPA
    python qr_generator.py vcard --name "Rahul S" --phone 9876543210 \\
        --email me@example.com --org "ABC Ltd" --title "Intern"
    python qr_generator.py url example.com --ec H --border 6 --format jpg
"""

import argparse
import os
import sys

try:
    import qrcode
    from qrcode.constants import (ERROR_CORRECT_H, ERROR_CORRECT_L,
                                  ERROR_CORRECT_M, ERROR_CORRECT_Q)
    from PIL import ImageColor
except ImportError:
    sys.exit("Missing packages. Install them with:  pip install qrcode pillow")

EC_LEVELS = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
             "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}
FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG"}


# ------------------------------------------------------------ payload builders
def build_text(text: str) -> str:
    if not text.strip():
        raise ValueError("text cannot be empty")
    return text


def build_url(url: str) -> str:
    url = url.strip()
    if not url or " " in url:
        raise ValueError("enter a valid website address, for example example.com")
    if "://" not in url:
        url = "https://" + url
    return url


def _wifi_escape(value: str) -> str:
    """Escape characters that have a special meaning in the WIFI: format."""
    for ch in ('\\', ';', ',', ':', '"'):
        value = value.replace(ch, "\\" + ch)
    return value


def build_wifi(ssid: str, password: str = "", security: str = "WPA",
               hidden: bool = False) -> str:
    security = security.upper()
    if security not in ("WPA", "WEP", "NOPASS"):
        raise ValueError("security must be WPA, WEP or nopass")
    if not ssid:
        raise ValueError("network name (SSID) is required")
    if security != "NOPASS" and not password:
        raise ValueError("password is required unless security is nopass")
    parts = f"WIFI:T:{'nopass' if security == 'NOPASS' else security};S:{_wifi_escape(ssid)};"
    if security != "NOPASS":
        parts += f"P:{_wifi_escape(password)};"
    if hidden:
        parts += "H:true;"
    return parts + ";"


def _vc_escape(value: str) -> str:
    return (value.replace("\\", "\\\\").replace("\n", "\\n")
                 .replace(",", "\\,").replace(";", "\\;"))


def build_vcard(name: str, phone: str = "", email: str = "", org: str = "",
                title: str = "", url: str = "", address: str = "") -> str:
    if not name.strip():
        raise ValueError("contact name is required")
    if not (phone or email):
        raise ValueError("give at least a phone number or an email")
    parts = name.strip().split()
    last, first = (parts[-1], " ".join(parts[:-1])) if len(parts) > 1 else (parts[0], "")
    lines = ["BEGIN:VCARD", "VERSION:3.0",
             f"N:{_vc_escape(last)};{_vc_escape(first)};;;",
             f"FN:{_vc_escape(name.strip())}"]
    if org:
        lines.append(f"ORG:{_vc_escape(org)}")
    if title:
        lines.append(f"TITLE:{_vc_escape(title)}")
    if phone:
        lines.append(f"TEL;TYPE=CELL:{phone.strip()}")
    if email:
        lines.append(f"EMAIL:{email.strip()}")
    if url:
        lines.append(f"URL:{url.strip()}")
    if address:
        lines.append(f"ADR:;;{_vc_escape(address)};;;;")
    lines.append("END:VCARD")
    return "\n".join(lines)


# ------------------------------------------------------------------ rendering
def parse_color(value: str):
    try:
        return ImageColor.getrgb(value.strip())
    except ValueError:
        raise ValueError(f'"{value}" is not a valid color. Use a name (navy) or hex (#0a3d62)')


def _luminance(rgb) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a, b) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def make_qr(data: str, fill="black", back="white", border: int = 4,
            ec: str = "M", box_size: int = 10):
    """Return a Pillow image of the QR code, plus a list of warnings."""
    ec = ec.upper()
    if ec not in EC_LEVELS:
        raise ValueError("error correction must be L, M, Q or H")
    if not 0 <= border <= 20:
        raise ValueError("border must be between 0 and 20 modules")
    if not 1 <= box_size <= 50:
        raise ValueError("box size must be between 1 and 50 pixels")
    fill_rgb, back_rgb = parse_color(fill), parse_color(back)

    warnings = []
    if contrast_ratio(fill_rgb, back_rgb) < 3:
        warnings.append("Low contrast between the two colors: the code may not scan.")
    if _luminance(fill_rgb) > _luminance(back_rgb):
        warnings.append("Light-on-dark (inverted) codes are not read by some scanners.")
    if border < 4:
        warnings.append("A border under 4 modules is below the QR standard and may not scan.")

    qr = qrcode.QRCode(version=None, error_correction=EC_LEVELS[ec],
                       box_size=box_size, border=border)
    qr.add_data(data)
    try:
        qr.make(fit=True)
    except Exception:
        raise ValueError("data is too long for a QR code. Shorten it or lower the error correction level")
    img = qr.make_image(fill_color=fill_rgb, back_color=back_rgb).get_image()
    return img.convert("RGB"), warnings


def save_image(img, path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext not in FORMATS:
        raise ValueError("output file must end in .png, .jpg or .jpeg")
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    if FORMATS[ext] == "JPEG":
        img.save(path, "JPEG", quality=95)      # JPEG has no alpha: image is already RGB
    else:
        img.save(path, "PNG")
    return os.path.abspath(path)


def generate(data, out, **style):
    img, warnings = make_qr(data, **style)
    saved = save_image(img, out)
    for w in warnings:
        print(f"Warning: {w}")
    print(f"Saved {saved}  ({img.width}x{img.height} px)")
    return saved


# ------------------------------------------------------------------------ CLI
def ask(prompt, default=None):
    suffix = f" [{default}]" if default not in (None, "") else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or (default or "")


def interactive():
    print("QR CODE GENERATOR\n")
    kinds = {"1": "text", "2": "url", "3": "wifi", "4": "vcard"}
    while True:
        print("What should the QR code contain?\n  1) Text\n  2) Website URL\n  3) Wi-Fi login\n  4) Contact card (vCard)")
        kind = kinds.get(ask("Choose 1-4", "1"))
        if kind:
            break
        print("Please choose 1, 2, 3 or 4.\n")

    while True:
        try:
            if kind == "text":
                data = build_text(ask("Text"))
            elif kind == "url":
                data = build_url(ask("Website address"))
            elif kind == "wifi":
                sec = ask("Security (WPA/WEP/nopass)", "WPA")
                data = build_wifi(ask("Network name (SSID)"),
                                  "" if sec.lower() == "nopass" else ask("Password"),
                                  sec, ask("Hidden network? (y/n)", "n").lower() == "y")
            else:
                data = build_vcard(ask("Full name"), ask("Phone"), ask("Email"),
                                   ask("Organization"), ask("Job title"), ask("Website"), ask("Address"))
            break
        except ValueError as err:
            print(f"  Problem: {err}. Try again.\n")

    print("\nStyle (press Enter to keep the default)")
    while True:
        try:
            style = dict(fill=ask("Foreground color", "black"), back=ask("Background color", "white"),
                         border=int(ask("Border thickness in modules (0-20)", "4")),
                         ec=ask("Error correction L/M/Q/H", "M"),
                         box_size=int(ask("Pixels per module", "10")))
            out = ask("Output file (.png or .jpg)", f"qr_{kind}.png")
            generate(data, out, **style)
            break
        except ValueError as err:
            print(f"  Problem: {err}. Try again.\n")


def add_style_args(p):
    p.add_argument("-o", "--output", help="output file (.png/.jpg). Default: qr_<type>.<format>")
    p.add_argument("--format", choices=["png", "jpg", "jpeg"], default="png",
                   help="used when --output has no extension (default png)")
    p.add_argument("--fill", default="black", help="foreground color (default black)")
    p.add_argument("--back", default="white", help="background color (default white)")
    p.add_argument("--border", type=int, default=4, help="border thickness in modules (default 4)")
    p.add_argument("--ec", default="M", choices=list("LMQHlmqh"), help="error correction level (default M)")
    p.add_argument("--box-size", type=int, default=10, help="pixels per module (default 10)")


def main(argv=None):
    if not (argv if argv is not None else sys.argv[1:]):
        try:
            interactive()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
        return 0

    ap = argparse.ArgumentParser(description="Customizable QR code generator (PNG/JPEG via Pillow)")
    sub = ap.add_subparsers(dest="kind", required=True)

    p = sub.add_parser("text", help="plain text"); p.add_argument("text"); add_style_args(p)
    p = sub.add_parser("url", help="website URL"); p.add_argument("url"); add_style_args(p)
    p = sub.add_parser("wifi", help="Wi-Fi credentials")
    p.add_argument("--ssid", required=True); p.add_argument("--password", default="")
    p.add_argument("--security", default="WPA", help="WPA, WEP or nopass")
    p.add_argument("--hidden", action="store_true"); add_style_args(p)
    p = sub.add_parser("vcard", help="contact card")
    p.add_argument("--name", required=True); p.add_argument("--phone", default="")
    p.add_argument("--email", default=""); p.add_argument("--org", default="")
    p.add_argument("--title", default=""); p.add_argument("--url", default="")
    p.add_argument("--address", default=""); add_style_args(p)
    a = ap.parse_args(argv)

    try:
        if a.kind == "text":
            data = build_text(a.text)
        elif a.kind == "url":
            data = build_url(a.url)
        elif a.kind == "wifi":
            data = build_wifi(a.ssid, a.password, a.security, a.hidden)
        else:
            data = build_vcard(a.name, a.phone, a.email, a.org, a.title, a.url, a.address)
        out = a.output or f"qr_{a.kind}.{a.format}"
        generate(data, out, fill=a.fill, back=a.back, border=a.border,
                 ec=a.ec, box_size=a.box_size)
    except ValueError as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())