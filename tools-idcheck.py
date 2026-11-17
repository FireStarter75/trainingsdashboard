"""Controleert dat elk DOM-id dat het JS opzoekt ook echt in de HTML staat.

Dekt app.js (gebruikt $) en coach.js (gebruikt cq). Ids die het JS zelf aanmaakt
(el.id = '...') zijn geen fout: die horen juist niet in de HTML te staan.
"""
import io, re, sys

FILES = ('/w/static/app.js', '/w/static/coach.js')
js = ''
for f in FILES:
    try:
        js += io.open(f, encoding='utf-8').read() + '\n'
    except OSError as e:
        print('  KON NIET LEZEN: %s (%s)' % (f, e))
        sys.exit(1)

html = io.open('/w/templates/index.html', encoding='utf-8').read()
login = io.open('/w/templates/login.html', encoding='utf-8').read()

html_ids = set(re.findall(r'id="([^"]+)"', html)) | set(re.findall(r'id="([^"]+)"', login))
made_in_js = set(re.findall(r"\.id\s*=\s*'([A-Za-z0-9_-]+)'", js))

used = set()
for pat in (r"\$\('#([A-Za-z0-9_-]+)'\)", r"cq\('#([A-Za-z0-9_-]+)'\)",
            r"mkChart\('([A-Za-z0-9_-]+)'", r"noData\('([A-Za-z0-9_-]+)'"):
    used |= set(re.findall(pat, js))

missing = sorted(u for u in used if u not in html_ids and u not in made_in_js)
print("  ids gebruikt in JS : %d" % len(used))
print("  ids in HTML        : %d" % len(html_ids))
print("  ids door JS gemaakt: %d" % len(made_in_js))
if missing:
    print("  ONTBREEKT IN HTML  : %s" % ", ".join(missing))
else:
    print("  alle gebruikte ids bestaan in de HTML")

print("")
for m in re.findall(r'src="(https://[^"]+)"', html):
    print("  extern script     : %s" % m)
for m in re.findall(r'href="(https://[^"]+)"', html):
    print("  extern stylesheet : %s" % m)
sys.exit(1 if missing else 0)
