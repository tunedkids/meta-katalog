#!/usr/bin/env python3
"""
Tuned Kids - katalog Meta z wlasnymi kafelkami (Air Max Plus, meskie rozmiary).
Claude, 6.11.2026.

Co robi (codziennie w GitHub Actions):
1. Pobiera publiczny katalog sklepu (tunedkids.pl/collections/<kolekcja>/products.json).
2. Wybiera meskie warianty (rozmiar EU >= 40, tytul bez (W)/(GS)/(PS)/(TD)).
3. Dla kazdego produktu ma wyciety but (cuts/<id>.png); nowe produkty wycina modelem ISNet (rembg).
4. Renderuje kafelek 1080x1080 na kazda kombinacje (produkt, cena, cena przed obnizka):
   tlo z bladym logo, but z odbiciem, nazwa, cena, przekreslona cena, naklejka z % rabatu.
5. Zapisuje feed.csv dla Meta (id = ID wariantu Shopify, jak w katalogu Shopify i pikselu).
Kafelki, ktore juz istnieja, nie sa renderowane ponownie. Nieuzywane kafelki sa usuwane.

Zmienne: COLLECTION (domyslnie air-max-plus), TITLE_HAS (Air Max Plus), MIN_SIZE (40),
BASE_URL (adres raw repo, wstawiany w image_link), LIMIT (test), FORCE (1 = renderuj wszystko).
"""
import csv, hashlib, html, io, json, os, re, sys, time, urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.dirname(os.path.abspath(__file__))
A_DIR = os.path.join(ROOT, 'assets')
CUTS = os.path.join(ROOT, 'cuts')
TILES = os.path.join(ROOT, 't')
SHOP = 'https://tunedkids.pl'
DESIGN = 'v2'  # zmiana wymusza nowe nazwy plikow (Meta pobierze nowe obrazy)

env = lambda k, d='': os.environ.get(k, d) or d
COLLECTION = env('COLLECTION', 'air-max-plus')
TITLE_HAS = env('TITLE_HAS', 'Air Max Plus')
MIN_SIZE = float(env('MIN_SIZE', '40'))
BASE_URL = env('BASE_URL', 'https://raw.githubusercontent.com/tunedkids/meta-katalog/main').rstrip('/')
LIMIT = int(env('LIMIT', '0') or 0)
FORCE = env('FORCE', '0') == '1'
EXCL = re.compile(r"\((W|GS|PS|TD)\)|women", re.I)

S = 1080; SW = 920; FL = 680
RED = (229, 50, 45)


def A(z): return ImageFont.truetype(os.path.join(A_DIR, 'Anton.ttf'), z)


def M(z, w=700):
    f = ImageFont.truetype(os.path.join(A_DIR, 'Mont.ttf'), z)
    try: f.set_variation_by_axes([w])
    except Exception: pass
    return f


def get(url, tries=4):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (TunedKids meta-katalog)'}), timeout=60).read()
        except Exception as ex:
            if i == tries - 1: raise
            time.sleep(3 * (i + 1))


def products(col=None):
    col = col or COLLECTION
    out, page = [], 1
    while True:
        d = json.loads(get(f'{SHOP}/collections/{col}/products.json?limit=250&page={page}'))['products']
        if not d: break
        out += d; page += 1
    return out


SHOE = re.compile(r'(?i)air max|air force|shox|yeezy|slide|dunk|jordan|samba|gazelle|campus|new balance|asics|gel-|ugg|converse|vans|timberland|\bnb\b')
def is_shoe(p):
    return bool(SHOE.search((p.get('product_type') or '') + ' ' + p['title'])) and not re.search(r'(?i)skarpet|socks', p['title'])



def size_eu(v):
    m = re.search(r'(\d+(?:[.,]\d+)?)', v.get('option1') or v.get('title') or '')
    return float(m.group(1).replace(',', '.')) if m else None


# ---------- wycinanie ----------
_sess = None
def cutout(p):
    fn = os.path.join(CUTS, f"{p['id']}.png")
    if os.path.exists(fn): return Image.open(fn).convert('RGBA')
    global _sess
    from rembg import remove, new_session
    from scipy import ndimage
    if _sess is None: _sess = new_session('isnet-general-use')
    src = p['images'][0]['src']; src += ('&' if '?' in src else '?') + 'width=1400'
    o = Image.open(io.BytesIO(get(src))).convert('RGB')
    c = remove(o, session=_sess)
    a = np.array(c.split()[3]); fl = ndimage.binary_fill_holes(a > 25)
    na = np.where(ndimage.binary_erosion(fl, iterations=4), 255, a).astype('uint8')
    o.putalpha(Image.fromarray(na))
    o = o.crop(o.getbbox()); o.thumbnail((1100, 1100), Image.LANCZOS)
    os.makedirs(CUTS, exist_ok=True); o.save(fn, optimize=True)
    print('  wyciety:', p['title'])
    return o


# ---------- naklejka ----------
_blank = None
def sticker(txt):
    global _blank
    if _blank is None: _blank = Image.open(os.path.join(A_DIR, 'sticker_blank.png')).convert('RGBA')
    st = _blank.copy(); W, H = st.size
    rx0, ry0, rx1, ry1 = 103, 85, 592, 286
    z = 260; d = ImageDraw.Draw(st)
    while True:
        f = M(z, 900); bb = d.textbbox((0, 0), txt, font=f)
        if bb[2] - bb[0] <= rx1 - rx0 and bb[3] - bb[1] <= ry1 - ry0: break
        z -= 4
    tm = Image.new('L', (W, H), 0)
    ImageDraw.Draw(tm).text(((rx0 + rx1) / 2 - (bb[0] + bb[2]) / 2, (ry0 + ry1) / 2 - (bb[1] + bb[3]) / 2), txt, font=f, fill=255)
    L = np.array(st.convert('L')).astype(float)
    hp = L - np.array(Image.fromarray(L.astype('uint8')).filter(ImageFilter.GaussianBlur(5))).astype(float)
    paper = np.clip(np.array([236, 232, 228])[None, None, :] + hp[..., None] * 1.3 + np.random.RandomState(1).normal(0, 6, (H, W, 1)), 0, 255).astype('uint8')
    out = st.copy(); out.paste(Image.fromarray(paper).convert('RGBA'), (0, 0), tm.filter(ImageFilter.GaussianBlur(0.5)))
    out.putalpha(st.split()[3])
    return out.crop(out.getbbox())


# ---------- kafelek ----------
_bg = None
def fmt(x): return ('%.2f' % x).replace('.', ',')


def fit(d, txt, font_fn, size, maxw, minsize):
    while size > minsize and d.textlength(txt, font=font_fn(size)) > maxw: size -= 2
    return font_fn(size)


def tile(cut, name, price, old):
    global _bg
    if _bg is None: _bg = Image.open(os.path.join(A_DIR, 'tlo.jpg')).convert('RGB').resize((S, S), Image.LANCZOS)
    bg = _bg.copy()
    sh = cut.crop(cut.split()[3].point(lambda v: 255 if v > 60 else 0).getbbox())
    sc = min(SW / sh.width, 470 / sh.height)
    sh = sh.resize((int(sh.width * sc), int(sh.height * sc)), Image.LANCZOS)
    sx = (S - sh.width) // 2; floor = FL; sy = floor - sh.height
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).ellipse((sx + 70, floor - 22, sx + sh.width - 70, floor + 26), fill=220)
    bg = Image.composite(Image.new('RGB', (S, S), (0, 0, 0)), bg, m.filter(ImageFilter.GaussianBlur(18)))
    r = ImageOps.flip(sh); ra = np.array(r.split()[3]).astype(float); h = ra.shape[0]
    fade = np.clip(1 - np.arange(h) / (h * 0.30), 0, 1)[:, None] * 0.25
    r.putalpha(Image.fromarray((ra * fade).astype('uint8'))); r = r.filter(ImageFilter.GaussianBlur(1.5))
    bg.paste(r, (sx, floor + 2), r); bg.paste(sh, (sx, sy), sh)
    d = ImageDraw.Draw(bg, 'RGBA')
    disc = old and old > price + 0.009
    d.text((56, S - 300), 'NIKE AIR MAX PLUS', font=M(30, 700), fill=(170, 170, 170))
    nf = fit(d, name, A, 92, (600 if disc else 968), 40)
    d.text((56, S - 262 + (92 - nf.size) // 2), name, font=nf, fill=(255, 255, 255))
    pf = A(84); p = f'{fmt(price)} ZŁ'; pw = d.textlength(p, font=pf)
    d.text((56, S - 140), p, font=pf, fill=(255, 255, 255))
    if disc:
        of = A(58); o = f'{fmt(old)} ZŁ'; ow = d.textlength(o, font=of)
        d.text((56 + pw + 30, S - 114), o, font=of, fill=(150, 150, 150))
        d.line((56 + pw + 26, S - 72, 56 + pw + 34 + ow, S - 72), fill=RED, width=6)
        pct = int(round((1 - price / old) * 100))
        if pct >= 5:
            stk = sticker(f'-{pct}%'); w = 340
            stk = stk.resize((w, int(stk.height * w / stk.width)), Image.LANCZOS).rotate(6, expand=True, resample=Image.BICUBIC)
            shd = Image.new('RGBA', stk.size, (0, 0, 0, 0))
            shd.putalpha(stk.split()[3].point(lambda v: int(v * 0.6)).filter(ImageFilter.GaussianBlur(10)))
            px = S - stk.width - 30; py = S - stk.height - 40
            bg.paste(shd, (px + 6, py + 10), shd); bg.paste(stk, (px, py), stk)
    return bg


def tile2(cut, price, old, shoe=True):
    global _bg
    if _bg is None: _bg = Image.open(os.path.join(A_DIR, 'tlo.jpg')).convert('RGB').resize((S, S), Image.LANCZOS)
    bg = _bg.copy()
    sh = cut.crop(cut.split()[3].point(lambda v: 255 if v > 60 else 0).getbbox())
    if shoe: maxw, maxh, floor = 900, 480, 700
    else: maxw, maxh, floor = 760, 640, 800
    sc = min(maxw / sh.width, maxh / sh.height)
    sh = sh.resize((int(sh.width * sc), int(sh.height * sc)), Image.LANCZOS)
    sx = (S - sh.width) // 2; sy = floor - sh.height
    m = Image.new('L', (S, S), 0)
    ImageDraw.Draw(m).ellipse((sx + 60, floor - 20, sx + sh.width - 60, floor + 24), fill=210 if shoe else 150)
    bg = Image.composite(Image.new('RGB', (S, S), (0, 0, 0)), bg, m.filter(ImageFilter.GaussianBlur(20)))
    if shoe:
        r = ImageOps.flip(sh); ra = np.array(r.split()[3]).astype(float); h = ra.shape[0]
        fade = np.clip(1 - np.arange(h) / (h * 0.30), 0, 1)[:, None] * 0.25
        r.putalpha(Image.fromarray((ra * fade).astype('uint8'))); r = r.filter(ImageFilter.GaussianBlur(1.5))
        bg.paste(r, (sx, floor + 2), r)
    bg.paste(sh, (sx, sy), sh)
    d = ImageDraw.Draw(bg)
    disc = old and old > price + 0.009
    pf = A(120); p = f'{fmt(price)} ZŁ'; pw = d.textlength(p, font=pf); y = S - 190
    d.text(((S - pw) / 2, y), p, font=pf, fill=(255, 255, 255))
    if disc:
        of = A(60); o = f'{fmt(old)} ZŁ'; ow = d.textlength(o, font=of)
        d.text(((S - ow) / 2, y - 80), o, font=of, fill=(150, 150, 150))
        d.line(((S - ow) / 2 - 6, y - 36, (S + ow) / 2 + 6, y - 36), fill=RED, width=7)
        pct = int(round((1 - price / old) * 100))
        if pct >= 5:
            stk = sticker(f'-{pct}%'); w = 300
            stk = stk.resize((w, int(stk.height * w / stk.width)), Image.LANCZOS).rotate(8, expand=True, resample=Image.BICUBIC)
            bg.paste(stk, (S - stk.width - 40, 40), stk)
    return bg


def short_name(title):
    n = re.sub(r'(?i)^nike\s+air\s+max\s+plus\s*', '', title).strip()
    n = re.sub(r'\s*\(TN\)\s*', ' ', n).strip() or 'TN'
    return n.upper()


def plain(htm, n=600):
    t = re.sub(r'<[^>]+>', ' ', htm or ''); t = html.unescape(re.sub(r'\s+', ' ', t)).strip()
    return t[:n]


def main():
    os.makedirs(TILES, exist_ok=True)
    P = [p for p in products() if TITLE_HAS.lower() in p['title'].lower() and not EXCL.search(p['title'])]
    if LIMIT: P = P[:LIMIT]
    print('produkty:', len(P))
    rows, used, made = [], set(), 0
    for p in P:
        try:
            cut = cutout(p)
        except Exception as ex:
            print('  BLAD wycinania', p['title'], ex); continue
        name = short_name(p['title'])
        vs = []
        for v in p['variants']:
            s = size_eu(v)
            if s is None or s < MIN_SIZE: continue
            if not v.get('available'): continue  # niedostepne (cena zastepcza 2000) pomijamy
            vs.append((s, v))
        if not vs: continue
        # jeden kafelek na model: najtansza dostepna cena (Kuba 6.11)
        _, vmin = min(vs, key=lambda x: (float(x[1]['price']), -float(x[1].get('compare_at_price') or 0)))
        tprice = float(vmin['price']); told = float(vmin.get('compare_at_price') or 0)
        key = f"{p['id']}_{vmin['price']}_{vmin.get('compare_at_price') or '0'}"
        h = hashlib.md5((key + DESIGN + name).encode()).hexdigest()[:8]
        fn = f"{p['id']}-{h}.jpg"; used.add(fn)
        path = os.path.join(TILES, fn)
        if FORCE or not os.path.exists(path):
            tile2(cut, tprice, told, True).save(path, quality=88, optimize=True, progressive=True); made += 1
        for s, v in vs:
            price = float(v['price']); old = float(v.get('compare_at_price') or 0)
            disc = old > price + 0.009
            rows.append({
                'id': v['id'], 'item_group_id': p['id'],
                'title': p['title'][:150],
                'description': plain(p.get('body_html')) or p['title'],
                'availability': 'in stock',
                'condition': 'new',
                'price': '%.2f PLN' % (old if disc else price),
                'sale_price': ('%.2f PLN' % price) if disc else '',
                'link': f"{SHOP}/products/{p['handle']}?variant={v['id']}",
                'image_link': f'{BASE_URL}/t/{fn}',
                'brand': p.get('vendor') or 'Nike',
                'size': ('%g' % s),
                'gender': 'male', 'age_group': 'adult',
                'google_product_category': 'Apparel & Accessories > Shoes',
                'product_type': p.get('product_type') or 'Air Max Plus',
                'custom_label_0': ('-%d%%' % round((1 - price / old) * 100)) if disc else '',
            })
    removed = 0
    for f in os.listdir(TILES):
        if f.endswith('.jpg') and f not in used: os.remove(os.path.join(TILES, f)); removed += 1
    with open(os.path.join(ROOT, 'feed.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('warianty w feedzie: %d | dostepne: %d | nowe kafelki: %d | usuniete: %d | kafelki razem: %d' % (
        len(rows), sum(r['availability'] == 'in stock' for r in rows), made, removed, len(used)))


# ---------- Bestsellery (osobny feed, kafelki v2: same ceny) – Kuba 12.11 ----------
BEST_COL = env('BEST_COL', 'bestsellery')
BEST_DIR = os.path.join(ROOT, 'tb')
DESIGN2 = 'b2'


def main_best():
    os.makedirs(BEST_DIR, exist_ok=True)
    P = [p for p in products(BEST_COL) if not EXCL.search(p['title'])]
    print('bestsellery produkty:', len(P))
    rows, used, made = [], set(), 0
    for p in P:
        try:
            cut = cutout(p)
        except Exception as ex:
            print('  BLAD wycinania', p['title'], ex); continue
        shoe = is_shoe(p)
        vs = []
        for v in p['variants']:
            s = size_eu(v) if shoe else 0
            if shoe and (s is None or s < MIN_SIZE): continue
            if not v.get('available'): continue
            vs.append((s, v))
        if not vs: continue
        _, vmin = min(vs, key=lambda x: (float(x[1]['price']), -float(x[1].get('compare_at_price') or 0)))
        tprice = float(vmin['price']); told = float(vmin.get('compare_at_price') or 0)
        key = f"{p['id']}_{vmin['price']}_{vmin.get('compare_at_price') or '0'}"
        h = hashlib.md5((key + DESIGN2).encode()).hexdigest()[:8]
        fn = f"{p['id']}-{h}.jpg"; used.add(fn)
        path = os.path.join(BEST_DIR, fn)
        if FORCE or not os.path.exists(path):
            tile2(cut, tprice, told, shoe).save(path, quality=88, optimize=True, progressive=True); made += 1
        for s, v in vs:
            price = float(v['price']); old = float(v.get('compare_at_price') or 0)
            disc = old > price + 0.009
            rows.append({
                'id': v['id'], 'item_group_id': p['id'],
                'title': p['title'][:150],
                'description': plain(p.get('body_html')) or p['title'],
                'availability': 'in stock', 'condition': 'new',
                'price': '%.2f PLN' % (old if disc else price),
                'sale_price': ('%.2f PLN' % price) if disc else '',
                'link': f"{SHOP}/products/{p['handle']}?variant={v['id']}",
                'image_link': f'{BASE_URL}/tb/{fn}',
                'brand': p.get('vendor') or 'Nike',
                'size': ('%g' % s) if shoe else (v.get('option1') or v.get('title') or ''),
                'gender': 'male' if shoe else 'unisex', 'age_group': 'adult',
                'google_product_category': 'Apparel & Accessories > Shoes' if shoe else 'Apparel & Accessories > Clothing',
                'product_type': p.get('product_type') or '',
                'custom_label_0': ('-%d%%' % round((1 - price / old) * 100)) if disc else '',
                'custom_label_1': 'bestsellery',
            })
    for f in os.listdir(BEST_DIR):
        if f.endswith('.jpg') and f not in used: os.remove(os.path.join(BEST_DIR, f))
    with open(os.path.join(ROOT, 'feed_best.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print('bestsellery: warianty %d | nowe kafelki %d | kafelki %d' % (len(rows), made, len(used)))


if __name__ == '__main__':
    main()
    main_best()
