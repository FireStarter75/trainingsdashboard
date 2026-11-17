"""Zoekt namen die in app.js of coach.js worden aangeroepen maar nergens gedefinieerd zijn.

node --check vindt dit niet: een ontbrekende functie is geen syntaxfout maar een
ReferenceError die pas bij gebruik opduikt. Precies waardoor een verwijderde
hulpfunctie ongemerkt in productie kwam.

Commentaar, strings en regex-literals moeten eerst weg, anders tellen woorden
daaruit mee. Dat gebeurt met een kleine tokenizer in plaats van met reguliere
expressies: die laatste gingen de mist in op een string die over twee regels is
geknipt (app.js 662) en op een regex die backticks bevat (coach.js 46). Een los
aanhalingsteken verschoof dan alle paren erna, waardoor hele blokken code als
string werden gezien en elke functie daarin "niet gedefinieerd" leek.
"""
import io, re, sys

FILES = ('/w/static/app.js', '/w/static/coach.js')
FLAGS = 'gimsuyd'
# Na deze tekens is een / het begin van een regex-literal; anders is het delen.
REGEX_AFTER = set('=(,:[!&|?+{;~^%*<>-\n')


def strip_literals(src):
    out, i, n, prev = [], 0, len(src), '\n'
    while i < n:
        ch, two = src[i], src[i:i + 2]
        if two == '//':
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        if two == '/*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            out.append(' ')
            continue
        if ch in '"\'':
            i += 1
            while i < n and src[i] != ch:
                i += 2 if src[i] == '\\' else 1
            i, prev = i + 1, '"'
            out.append(' "" ')
            continue
        if ch == '`':
            # Template literal: de tekst gooien we weg, maar wat in ${...} staat
            # is gewone code en moet juist meegenomen worden.
            i += 1
            out.append(' "" ')
            while i < n and src[i] != '`':
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i:i + 2] == '${':
                    depth, i = 1, i + 2
                    start = i
                    while i < n and depth:
                        if src[i] == '{':
                            depth += 1
                        elif src[i] == '}':
                            depth -= 1
                        i += 1
                    out.append(' ' + src[start:max(start, i - 1)] + ' ')
                    continue
                i += 1
            i, prev = i + 1, '"'
            continue
        if ch == '/' and prev in REGEX_AFTER:
            i += 1
            while i < n and src[i] != '/':
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == '[':                       # [^/] mag een slash bevatten
                    i += 1
                    while i < n and src[i] != ']':
                        i += 2 if src[i] == '\\' else 1
                i += 1
            i += 1
            while i < n and src[i] in FLAGS:
                i += 1
            out.append(' 0 ')
            prev = '0'
            continue
        out.append(ch)
        if not ch.isspace():
            prev = ch
        i += 1
    return ''.join(out)


src = ''
for f in FILES:
    try:
        src += io.open(f, encoding='utf-8').read() + '\n'
    except OSError as e:
        print('  KON NIET LEZEN: %s (%s)' % (f, e))
        sys.exit(1)

clean = strip_literals(src)

declared = set()
for pat in (r'\bfunction\s+([A-Za-z_$][\w$]*)',
            r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)',
            r'\b(?:const|let|var)\s*\{([^}]*)\}',
            r'\bcatch\s*\(\s*([A-Za-z_$][\w$]*)',
            r'\bfunction\s*[A-Za-z_$\w]*\s*\(([^)]*)\)',
            r'\(([^)]*)\)\s*=>',
            r'\b([A-Za-z_$][\w$]*)\s*=>',
            r'\(\s*\[([^\]]*)\]\s*\)\s*=>',      # ([a, b]) => ...
            r'(?m)^\s*([A-Za-z_$][\w$]*)\s*:',     # sleutels in objectliteralen
            r'\{\s*([A-Za-z_$][\w$]*)\s*:'):
    for m in re.findall(pat, clean):
        for part in re.split(r'[,\s=]+', m):
            part = part.strip().lstrip('.')
            if re.fullmatch(r'[A-Za-z_$][\w$]*', part or ''):
                declared.add(part)

GLOBALS = {
    'window','document','console','Math','JSON','Date','Number','String','Boolean',
    'Array','Object','Promise','Set','Map','parseInt','parseFloat','isNaN','fetch',
    'localStorage','sessionStorage','setTimeout','setInterval','clearTimeout','alert',
    'confirm','location','navigator','Error','RegExp','encodeURIComponent','L','Chart',
    'requestAnimationFrame','structuredClone','AbortController','URLSearchParams',
    'matchMedia','queueMicrotask',
    'if','for','while','switch','catch','return','typeof','function','class','new',
    'await','of','in','do','else','try','throw','delete','void','super','this',
}

used = set(re.findall(r'(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(', clean))
missing = sorted(u for u in used if u not in declared and u not in GLOBALS)

bare = set(re.findall(r'(?<![.\w$"\'])([A-Z][A-Z0-9_]{2,})(?![\w$])(?!\s*:)', clean))
missing_consts = sorted(b for b in bare if b not in declared and b not in GLOBALS)

ok = True
if missing:
    ok = False
    print('  AANGEROEPEN MAAR NIET GEDEFINIEERD:')
    for m in missing:
        print('    %s' % m)
if missing_consts:
    ok = False
    print('  CONSTANTE GEBRUIKT MAAR NIET GEDEFINIEERD:')
    for m in missing_consts:
        print('    %s' % m)
if ok:
    print('  alle aangeroepen functies en constanten zijn gedefinieerd (%d namen)' % len(declared))
sys.exit(0 if ok else 1)
