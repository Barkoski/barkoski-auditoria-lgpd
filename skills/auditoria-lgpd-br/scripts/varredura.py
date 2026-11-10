#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Varredura deterministica de pistas LGPD em um projeto (somente leitura).

Uso:
    python -I varredura.py <raiz_do_projeto> [--saida arquivo.md|.json]
                           [--formato md|json] [--max-bytes N]

Garantias:
  - Python 3.9+, somente biblioteca padrao. Sem rede, nada do projeto e executado.
  - Unico subprocesso: `git` SOMENTE LEITURA (rev-parse, ls-files, check-ignore;
    lista de argumentos, shell=False, timeout curto, core.fsmonitor desligado),
    usado so para saber se arquivos .env* estao versionados ou ignorados. Sem git
    instalado ou fora de repositorio, isso e pulado (e informado no achado).
  - Somente leitura. Recusa gravar a saida dentro da raiz auditada.
  - Nao segue symlinks/junctions. Ignora node_modules, .git, vendor, .venv etc.
    (mas reporta que existem).
  - Valores de segredos e dados pessoais saem sempre mascarados
    (no maximo 2 primeiros caracteres + comprimento).
  - Nomes de arquivos em pastas de documentos nao sao reportados (so contagens).

O resultado e PISTA, nao prova. Zero achados nao prova ausencia de problema.
Exit code: 0 quando a varredura rodou; 2 para erro de uso (ex.: saida dentro da raiz).
"""
import argparse
import base64
import hashlib
import bisect
import fnmatch
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict

SEV_ORDER = {"alta": 0, "média": 1, "baixa": 2, "info": 3}
CATEGORIAS = [
    "segredos", "rastreadores_terceiros", "coleta_dados_pessoais",
    "sessao_cookies", "logs", "artefatos_deploy", "empacotamento",
    "pastas_documentos", "protecao_web", "ia_externa",
]

IGNORE_DIRS = {
    "node_modules", ".git", "vendor", ".venv", "venv", "__pycache__",
    "dist", ".next", "build", ".svn", ".hg",
    ".claude", ".agents", ".idea", ".vscode",
    "out", ".turbo", ".cache", "coverage", ".svelte-kit", ".nuxt", "target",
}
IGNORE_PREFIXES = (".next", ".cache")  # .next-auditoria, .cache_experimento etc.
IGNORE_REL_SUFFIXES = (".vercel/output",)
SERVED_DIRS = {"public", "public_html", "www", "htdocs", "dist", "build", "out", "static"}
TEST_WORDS = {"test", "tests", "spec", "specs", "e2e", "mock", "mocks", "fixture", "fixtures",
              "testar", "teste", "testes", "exemplo", "exemplos", "ficticio", "sonda", "sondas",
              "ouro", "seed", "demo", "sample", "samples", "fake", "dummy"}


def is_test_path(rel):
    """Caminho ou nome de arquivo com cara de teste/exemplo (inclui nomes em português)."""
    toks = re.split(r"[^a-z0-9]+", fold(rel))
    return any(t in TEST_WORDS for t in toks)
COMPILED_RE = re.compile(r"(\.min\.(js|css)$|(^|/)_next/|(^|/)static/chunks/|(^|/)chunks/[^/]*\.js$)", re.I)
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "composer.lock",
             "poetry.lock", "Pipfile.lock", "bun.lockb", "Gemfile.lock"}
DOC_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".heic",
            ".docx", ".doc", ".odt", ".webp"}
MARKUP_EXTS = {".html", ".htm", ".php", ".phtml", ".js", ".jsx", ".ts", ".tsx",
               ".mjs", ".cjs", ".vue", ".svelte", ".twig", ".ejs", ".hbs",
               ".njk", ".liquid", ".erb", ".astro", ".css", ".scss", ".less",
               ".json", ".xml", ".yml", ".yaml", ".py", ".rb", ".java", ".go", ".cs"}
CODE_EXTS = {".php", ".phtml", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py",
             ".rb", ".java", ".go", ".cs", ".vue", ".svelte", ".inc", ".astro"}
DATA_EXTS = {".sql", ".csv", ".tsv", ".json", ".txt", ".log", ".xml", ".ndjson", ".jsonl"}
ARTIFACT_EXTS_HIGH = (".sql", ".sql.gz", ".bak", ".dump", ".db", ".sqlite", ".sqlite3",
                      ".old", ".orig", ".swp")
ARTIFACT_EXTS_MED = (".zip", ".tar", ".tar.gz", ".tgz", ".gz", ".7z", ".rar")
SENSITIVE_NAMES = {
    "install.php": "script de instalação", "setup.php": "script de instalação",
    "phpinfo.php": "phpinfo", "info.php": "phpinfo", "adminer.php": "adminer",
    "wp-config.php": "config WordPress", ".htpasswd": "senhas htpasswd",
    "id_rsa": "chave privada", "credentials.json": "credenciais",
    ".DS_Store": "metadado de sistema", "error_log": "log de erros",
}
SENSITIVE_EXT = (".pem", ".key", ".p12", ".pfx", ".log")
SUSPICIOUS_DIR = re.compile(
    r"^(tmp|temp|uploads?|docs?|documentos?|pdfs?|ocr.*|scans?|digitaliza.*|anexos?|"
    r"arquivos?|files|storage|private|clientes?|processos?)$", re.I)
ASSET_SEGS = {"assets", "asset", "static", "img", "imgs", "images", "image", "icons",
              "icon", "fonts", "css", "js", "favicon", "screenshots"}


# ----------------------------------------------------------------- utilidades
def fold(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def mask(v):
    n = len(v)
    if n <= 4:
        return "… (%d car.)" % n
    return "%s… (%d car.)" % (v[:2], n)


def posix(p):
    return p.replace("\\", "/")


def within(root_real, p):
    try:
        a = os.path.normcase(root_real)
        b = os.path.normcase(os.path.realpath(p))
        return os.path.commonpath([a, b]) == a
    except ValueError:
        return False


def lp(p):
    """Prefixo de caminho longo no Windows (evita falha acima de 260 caracteres)."""
    prefix = "\\\\?\\"
    if os.name == "nt" and len(p) > 200 and not p.startswith(prefix):
        return prefix + os.path.abspath(p)
    return p


def is_link_like(p):
    if os.path.islink(p):
        return True
    isj = getattr(os.path, "isjunction", None)
    return bool(isj and isj(p))


PH_WORDS = {
    "changeme", "change_me", "change-me", "xxx", "xxxx", "xxxxx", "sua_senha",
    "sua-senha", "suasenha", "sua_chave", "your_password", "yourpassword",
    "your_key", "your-api-key", "password", "senha", "secret", "null", "none",
    "false", "true", "undefined", "todo", "example", "exemplo", "placeholder",
    "dummy", "redacted", "secret_key_here", "your_secret", "insert_here", "seu_token",
}


def is_placeholder(v):
    s = v.strip()
    low = s.lower()
    if len(s) < 3 or low in PH_WORDS:
        return True
    if re.fullmatch(r"[x*•\-_.#]+", low):
        return True
    if low.startswith(("${", "$(", "{{", "<", "%", "$", "@", "[")):
        return True
    if re.search(r"getenv\(|process\.env|os\.environ|\benv\(|config\(", low):
        return True
    if re.search(r"(your|seu|sua|my|minha)[_\- ]?(senha|password|key|chave|token|secret|api)", low):
        return True
    if "changeme" in low or "placeholder" in low or "xxxx" in low or "..." in s:
        return True
    return False


def plausible_secret(v):
    """Valor literal plausivel de segredo: nao placeholder, nao nome/identificador."""
    if is_placeholder(v) or len(v) < 6:
        return False
    if re.fullmatch(r"[A-Z][A-Z0-9_]*=?", v):          # NOME_EM_CAIXA_ALTA
        return False
    if re.search(r"[(){}<>\\]|=>", v) or len(set(v)) < 4:
        return False
    if re.match(r"https?://[^@]*$", v, re.I):
        return False
    if re.search(r"(process\.env|import\.meta\.env|os\.environ|getenv)", v):
        return False
    return True


LITERAL_RE = re.compile(r"['\"]([^'\"\s]{8,200})['\"]")
LOCALHOST_RE = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0|\[?::1)", re.I)
TOKENISH_RE =re.compile(r"[A-Za-z0-9_\-+/=]{16,}")


def mask_tokens(text):
    """Mascara QUALQUER sequencia longa com cara de token (hex, base64, JWT)."""
    def f(m):
        t = m.group(0)
        if re.fullmatch(r"[0-9a-fA-F]{16,}", t) or (re.search(r"\d", t) and re.search(r"[A-Za-z]", t)):
            return mask(t)
        return t
    return TOKENISH_RE.sub(f, text)


# ---------------------------------------------------------------- segredos
SECRET_TOKENS = {"pass", "password", "passwd", "pwd", "passphrase", "secret", "token",
                 "senha", "salt", "apikey", "credentials", "credential", "privatekey"}
SECRET_PAIRS = {("api", "key"), ("private", "key"), ("access", "key"), ("auth", "key"),
                ("service", "role"), ("client", "secret"), ("secret", "key"),
                ("signing", "key"), ("encryption", "key"), ("master", "key"),
                ("app", "key"), ("jwt", "secret")}
STRONG_TOKENS = {"secret", "private", "pass", "password", "passwd", "pwd", "senha",
                 "salt", "passphrase", "role"}
NOISE_TOKENS = {"expiry", "expires", "expire", "ttl", "max", "min", "length", "time",
                "timeout", "type", "name", "field", "header", "count", "url", "path",
                "file", "label", "placeholder", "required", "hint", "text", "message",
                "msg", "error", "input", "id", "hash", "reset", "forgot", "confirm",
                "show", "hide", "toggle", "visible", "strength", "policy", "regex", "rules"}
PUBLIC_PREFIX = re.compile(r"^(NEXT_PUBLIC_|VITE_|REACT_APP_|EXPO_PUBLIC_|NUXT_PUBLIC_|PUBLIC_|GATSBY_)")


def key_tokens(key):
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [t for t in re.split(r"[^A-Za-z0-9]+", k.lower()) if t]


def is_secret_key(key, const_ctx=False):
    t = key_tokens(key)
    if not t or any(x in NOISE_TOKENS for x in t):
        return False
    if any(x in SECRET_TOKENS for x in t):
        return True
    if any(p in SECRET_PAIRS for p in zip(t, t[1:])):
        return True
    if const_ctx and key.isupper() and t[-1] == "key":
        return True
    return False


def jwt_role(v):
    parts = v.split(".")
    if len(parts) != 3 or not v.startswith("eyJ"):
        return None
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(pad.encode()).decode("utf-8", "replace"))
        return str(data.get("role", "")) or "jwt"
    except Exception:
        return "jwt"


TOKEN_RES = [
    ("chave_sk", re.compile(r"(?<![A-Za-z0-9_\-])sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}")),
    ("chave_stripe", re.compile(r"(?<![A-Za-z0-9_])[sr]k_live_[A-Za-z0-9]{16,}")),
    ("aws_access_key", re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])")),
    ("github_token", re.compile(r"(?<![A-Za-z0-9_])(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("google_api_key", re.compile(r"(?<![A-Za-z0-9_\-])AIza[0-9A-Za-z_\-]{35}")),
    ("chave_privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----")),
    ("hash_de_senha", re.compile(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}")),
    ("jwt", re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
]
CONN_RE = re.compile(r"(?P<scheme>postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqps?|mssql)://"
                     r"(?P<u>[^:/@\s'\"]+):(?P<v>[^@\s/'\"]+)@")
DEFINE_RE = re.compile(r"(?:define|putenv|ini_set|env|setenv)\(\s*(?P<q1>['\"])(?P<k>[\w.\-]+)(?P=q1)\s*,\s*"
                       r"(?P<q>['\"])(?P<v>[^'\"\r\n]*)(?P=q)", re.I)
GENERIC_RE = re.compile(r"(?P<k>[A-Za-z_][\w.\-]*)['\"\]]*[ \t]*(?:=>|:=|=|:)[ \t]*"
                        r"(?P<q>['\"])(?P<v>[^'\"\r\n]*)(?P=q)")
ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?(?P<k>[A-Za-z_][\w.\-]*)\s*[=:]\s*(?P<q>['\"]?)"
                         r"(?P<v>[^'\"#\r\n]*?)(?P=q)\s*(?:#.*)?$")


def secret_spans(line, env_like, ctx):
    """Devolve lista de dicts com start,end (do valor), kind, key, value, sev, hint."""
    out = []

    def free(s, e):
        return all(e <= o["start"] or s >= o["end"] for o in out)

    def push(s, e, kind, key, value, sev, hint):
        if free(s, e):
            out.append(dict(start=s, end=e, kind=kind, key=key, value=value, sev=sev, hint=hint))

    for kind, rx in TOKEN_RES:
        for m in rx.finditer(line):
            v = m.group(0)
            sev, hint = "alta", "Credencial literal no arquivo: revogar/rotacionar e mover para variável de ambiente."
            if kind == "jwt":
                role = jwt_role(v)
                if role == "anon":
                    sev, hint = "info", "Chave pública por desenho (anon); confira regras/RLS."
                elif role == "service_role":
                    hint = "Chave service_role do Supabase dá acesso total: nunca no código nem no navegador."
                else:
                    sev, hint = "média", "JWT literal: confira se é chave pública ou segredo."
            elif kind == "google_api_key":
                if ctx.get("firebase"):
                    sev, hint = "info", "Chave web do Firebase/Google: pública por desenho; confira regras e restrição por domínio."
                else:
                    sev, hint = "média", "Chave de API Google: se for de servidor, é segredo; se de navegador, restrinja por domínio."
            elif kind == "hash_de_senha":
                sev, hint = "média", "Hash de senha em arquivo versionável/publicável: indica dump de dados de usuários."
            elif kind == "chave_privada":
                hint = "Chave privada no arquivo: remover e rotacionar."
            push(m.start(), m.end(), kind, kind, v, sev, hint)
    for m in CONN_RE.finditer(line):
        v = m.group("v")
        if not is_placeholder(v):
            local = LOCALHOST_RE.match(line[m.end():])
            push(m.start("v"), m.end("v"), "string_conexao", m.group("scheme"), v, "baixa" if local else "alta",
                 "String de conexão com senha embutida" + (" (host local: provável valor de desenvolvimento/teste)" if local else "") + ": mover para variável de ambiente e trocar a senha.")
    for m in DEFINE_RE.finditer(line):
        k, v = m.group("k"), m.group("v")
        if is_secret_key(k, True) and plausible_secret(v):
            push(m.start("v"), m.end("v"), "atribuicao", k, v, "alta",
                 "Segredo literal no código/config: mover para fora da pasta publicada ou variável de ambiente.")
    cands = []
    for m in GENERIC_RE.finditer(line):
        b = line[m.start("k") - 1] if m.start("k") > 0 else ""
        if b and b in "'\"`" and line[m.end("k"):m.end("k") + 1] in ("=", ":"):
            continue                        # "NOME=" dentro de string: nao e atribuicao
        cands.append((m.group("k"), m.group("v"), m.start("v"), m.end("v")))
    if env_like:
        m = ENV_LINE_RE.match(line)
        if m:
            cands.append((m.group("k"), m.group("v"), m.start("v"), m.end("v")))
    for k, v, s, e in cands:
        if not v or " " in v.strip() or not plausible_secret(v):
            continue
        if re.fullmatch(r"[A-Za-zÀ-ú]{1,12}", v) and (v.islower() or v.istitle()):
            continue                        # palavra comum (rotulo, estado), nao segredo
        pubname = bool(PUBLIC_PREFIX.match(k)) or any(t in ("anon", "publishable") for t in key_tokens(k))
        t = key_tokens(k)
        key_like = is_secret_key(k, env_like) or any(x in ("key", "apikey", "dsn") for x in t)
        role = jwt_role(v)
        if pubname and (key_like or role):
            strong = any(x in STRONG_TOKENS for x in t) or role == "service_role"
            if strong:
                push(s, e, "atribuicao", k, v, "alta",
                     "Chave que parece privilegiada exposta com prefixo público (vai para o navegador).")
            else:
                push(s, e, "chave_publica", k, v, "info",
                     "Pública por desenho; confira regras/RLS (Supabase), regras do Firebase e restrições de domínio.")
        elif is_secret_key(k, env_like):
            if k == "apiKey" and ctx.get("firebase"):
                push(s, e, "chave_publica", k, v, "info",
                     "Chave web do Firebase: pública por desenho; confira regras de segurança.")
            elif role == "anon":
                push(s, e, "chave_publica", k, v, "info", "Pública por desenho (anon); confira regras/RLS.")
            else:
                push(s, e, "atribuicao", k, v, "alta",
                     "Segredo literal no código/config: mover para fora da pasta publicada ou variável de ambiente.")
    return out


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,}")
CPF_RE = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")
CPF_DE_EXEMPLO = {"12345678909", "11144477735", "11122233396"}   # exemplos clássicos de documentação
CNPJ_RE = re.compile(r"(?<![\d.])\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?!\d)")
CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
_DDD = r"[1-9][1-9]"
_NUM = r"(?:9\d{4}|[2-5]\d{3})"
# Telefone brasileiro plausível: +55 opcional, DDD 11-99, celular 9xxxx ou fixo 2-5xxx, com parênteses/+55/separador.
FONE_RE = re.compile(
    r"(?<![\w.\-/])(?:"
    r"\+55[ -]?(?:\(" + _DDD + r"\)|" + _DDD + r")[ -]?" + _NUM + r"[ -]?\d{4}"
    r"|\(" + _DDD + r"\)[ -]?" + _NUM + r"[ -]?\d{4}"
    r"|" + _DDD + r"[ -]" + _NUM + r"-\d{4}"
    r")(?!\w|[.\-]\w)")


def cpf_valido(s):
    d = [int(c) for c in s if c.isdigit()]
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        r = sum(d[i] * (n + 1 - i) for i in range(n)) * 10 % 11 % 10
        if r != d[n]:
            return False
    return True


def cnpj_valido(s):
    d = [int(c) for c in s if c.isdigit()]
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        r = sum(d[i] * pesos[i] for i in range(n)) % 11
        if d[n] != (0 if r < 2 else 11 - r):
            return False
    return True


def scrub(line, env_like=False, ctx=None):
    """Mascara segredos e dados pessoais numa linha."""
    ctx = ctx or {}
    reps = []
    for sp in secret_spans(line, env_like, ctx):
        reps.append((sp["start"], sp["end"]))
    for rx in (CPF_RE, EMAIL_RE, FONE_RE):
        for m in rx.finditer(line):
            reps.append((m.start(), m.end()))
    for m in CONN_RE.finditer(line):
        reps.append((m.start("v"), m.end("v")))
    reps.sort()
    merged = []
    for s, e in reps:
        if merged and s < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    res, last = [], 0
    for s, e in merged:
        res.append(line[last:s])
        res.append(mask(line[s:e]))
        last = e
    res.append(line[last:])
    return "".join(res)


# -------------------------------------------------------------- rastreadores
TRACKERS = [
    ("Google Analytics", "alta", r"google-analytics\.com|googletagmanager\.com/gtag|\bgtag\s*\(|analytics\.js|\bga\(\s*['\"]create",
     "Analytics costuma exigir aviso e consentimento antes de carregar."),
    ("Google Tag Manager", "média", r"googletagmanager\.com/(?:gtm|ns)|\bGTM-[A-Z0-9]{5,}",
     "GTM pode carregar outros rastreadores; confira o que há no contêiner e o consentimento."),
    ("Meta Pixel", "alta", r"connect\.facebook\.net|\bfbq\s*\(|facebook\.com/tr\b",
     "Pixel de publicidade: confira consentimento e compartilhamento com a Meta."),
    ("Hotjar", "alta", r"hotjar\.com|\bhj\s*\(\s*['\"]", "Gravação de sessão/mapa de calor: risco de captar dados digitados."),
    ("Microsoft Clarity", "alta", r"clarity\.ms|c\.clarity", "Gravação de sessão: risco de captar dados digitados."),
    ("TikTok Pixel", "alta", r"analytics\.tiktok\.com|\bttq\.(?:load|track|page)", "Pixel de publicidade."),
    ("LinkedIn Insight", "alta", r"snap\.licdn\.com|_linkedin_partner_id|px\.ads\.linkedin\.com", "Pixel de publicidade."),
    ("X/Twitter Pixel", "alta", r"static\.ads-twitter\.com|\btwq\s*\(", "Pixel de publicidade."),
    ("Google Fonts", "média", r"fonts\.googleapis\.com|fonts\.gstatic\.com",
     "Carregar fontes do Google envia o IP do visitante a terceiro; considere hospedar localmente."),
    ("reCAPTCHA", "média", r"google\.com/recaptcha|gstatic\.com/recaptcha|g-recaptcha|grecaptcha",
     "Serviço do Google que coleta dados do visitante; confira aviso e base legal."),
    ("YouTube embed", "baixa", r"youtube(?:-nocookie)?\.com/embed|<iframe[^>]*youtu",
     "Incorporação de vídeo envia dados ao YouTube; considere youtube-nocookie ou carregar sob clique."),
    ("Google Maps", "baixa", r"google\.com/maps/embed|maps\.googleapis\.com|maps\.google\.com",
     "Mapa incorporado envia dados ao Google."),
    ("CDN de script", "baixa", r"cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|unpkg\.com|ajax\.googleapis\.com|code\.jquery\.com|bootstrapcdn\.com|kit\.fontawesome\.com",
     "Script de CDN externo: o IP do visitante vai ao terceiro; considere hospedar localmente."),
    ("Sentry", "média", r"sentry\.io|@sentry/|Sentry\.init|sentry-cdn", "Monitoramento de erros pode capturar dados pessoais nos eventos."),
    ("LogRocket", "alta", r"logrocket|LogRocket\.init", "Session replay: risco de captar dados digitados."),
    ("FullStory", "alta", r"fullstory\.com|edge\.fullstory", "Session replay: risco de captar dados digitados."),
    ("Session replay (outros)", "alta", r"\brrweb\b|smartlook|mouseflow", "Session replay: risco de captar dados digitados."),
    ("PostHog", "média", r"posthog", "Analytics de produto; confira consentimento, região e retenção."),
    ("Mixpanel", "média", r"mixpanel", "Analytics de produto; confira consentimento e transferência internacional."),
    ("Segment", "média", r"cdn\.segment\.com|segment\.com/analytics|analytics\.load\s*\(", "Encaminha dados a vários destinos; confira."),
    ("Vercel Analytics", "baixa", r"@vercel/analytics|va\.vercel-scripts\.com", "Analytics; confira aviso."),
    ("Chat/CRM externo", "média", r"hs-scripts\.com|embed\.tawk\.to|client\.crisp\.chat|widget\.intercom\.io|jivosite",
     "Widget de terceiro que coleta dados do visitante."),
]
TRACKERS_RE = [(n, s, re.compile(p, re.I), d) for n, s, p, d in TRACKERS]

IA_PROVIDERS = [
    ("OpenAI", r"api\.openai\.com|from\s+openai\s+import|import\s+openai\b|require\(\s*['\"]openai['\"]|from\s+['\"]openai['\"]|['\"]openai['\"]\s*:|^openai(?:[=<>~ ]|$)"),
    ("Anthropic", r"api\.anthropic\.com|@anthropic-ai/sdk|import\s+anthropic\b|from\s+anthropic\s+import|['\"]anthropic['\"]\s*:|^anthropic(?:[=<>~ ]|$)"),
    ("Google Gemini", r"generativelanguage\.googleapis\.com|google[._-]generativeai|@google/generative-ai"),
    ("Groq", r"api\.groq\.com|groq-sdk|from\s+groq\s+import|import\s+groq\b"),
    ("OpenRouter", r"openrouter\.ai"),
    ("Replicate", r"api\.replicate\.com|import\s+replicate\b|['\"]replicate['\"]\s*:"),
    ("Hugging Face", r"api-inference\.huggingface\.co|huggingface\.co/api|huggingface_hub|@huggingface/inference"),
    ("Mistral/Cohere", r"api\.mistral\.ai|api\.cohere\.(?:ai|com)"),
]
IA_RE = [(n, re.compile(p, re.I | re.M)) for n, p in IA_PROVIDERS]

# -------------------------------------------------------------- coleta de dados
B = r"(?<![a-z])"
E = r"(?![a-z])"
PII_FIELDS = [
    ("saude", "alta", re.compile(B + r"(saude|doenca|cid|diagnostico|health|medic\w*|laudo|deficiencia|sintoma\w*)" + E)),
    ("cpf", "média", re.compile(B + r"cpf" + E)),
    ("cnpj", "baixa", re.compile(B + r"cnpj" + E)),
    ("rg", "média", re.compile(B + r"rg" + E)),
    ("nascimento", "média", re.compile(r"nasc\w*|birth\w*|" + B + r"dob" + E + r"|aniversario")),
    ("senha", "baixa", re.compile(r"senha|passw\w*|" + B + r"password" + E)),
    ("email", "baixa", re.compile(r"e.?mail")),
    ("telefone", "baixa", re.compile(B + r"(tel|telefone|fone|phone|celular|whats\w*|mobile)" + E)),
    ("nome", "baixa", re.compile(B + r"(nome|name|fullname|sobrenome|first_?name|last_?name)" + E)),
    ("endereco", "baixa", re.compile(B + r"(endereco|address|logradouro|bairro|rua|street)" + E)),
    ("cep", "baixa", re.compile(B + r"(cep|zip|zipcode|postal\w*)" + E)),
]
TAG_RE = re.compile(r"<(?:input|textarea|select)\b[^>]*>", re.I | re.S)
FORM_RE = re.compile(r"<form\b[^>]*>", re.I | re.S)
ATTR_RE = re.compile(r"\b(name|id|type|autocomplete|placeholder)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
COL_RE = re.compile(r"^\s*[`\"\[]?([A-Za-z_]\w*)[`\"\]]?\s+(?:varchar|char|text|tinytext|mediumtext|longtext|int|integer|bigint|smallint|tinyint|date|datetime|timestamp|boolean|bool|json|jsonb|string|float|decimal|numeric|serial|uuid|bytea|blob|enum|citext)\b", re.I | re.M)

# ------------------------------------------------------------- sessao / logs
LOG_CALL_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:console\.(?:log|error|warn|info|debug)|error_log|var_dump|print_r|var_export|"
    r"logger\.\w+|log\.(?:info|error|debug|warn|warning)|logging\.\w+|Log::\w+|"
    r"\$this->logger->\w+|\$logger->\w+|print|puts|System\.out\.println|fmt\.Printf?|fmt\.Println)\s*\(")
LOG_BODY_RE = re.compile(r"req\.body\b(?!\s*[.\[])|request\.body\b(?!\s*[.\[])|\$_(?:POST|REQUEST|GET|COOKIE)\b(?!\s*\[)|"
                         r"\$request->all\(\)|php://input")
LOG_PII_RE = re.compile(r"(?<![A-Za-z])(cpf|cnpj|rg|email|e_mail|senha|password|passwd|telefone|phone|celular|nascimento|endereco|nome_?completo|nome_?cliente|nome_?usuario|cartao|card_number)(?![A-Za-z])", re.I)
SESSION_RE = re.compile(r"\bsession_start\s*\(")
SETCOOKIE_RE = re.compile(r"\bsetcookie\s*\(|\bsetrawcookie\s*\(|header\s*\(\s*['\"]Set-Cookie", re.I)
DOCCOOKIE_RE = re.compile(r"\bdocument\.cookie\s*=")
STORAGE_RE = re.compile(r"\b(localStorage|sessionStorage)\.setItem\s*\(\s*([^,)]*)")
SECHDRS = ("strict-transport-security", "content-security-policy", "x-content-type-options",
           "x-frame-options", "referrer-policy", "permissions-policy")

PACK_WORDS = re.compile(r"zip|compress-archive|\btar\b|rsync|scp\b|robocopy|ftp|7z|createentryfromfile|\bdeploy|publish", re.I)


# ------------------------------------------------------------------ ignore
def ignore_match(patterns, rel, is_dir=False):
    """Heuristica estilo .gitignore. patterns: lista de linhas."""
    rel = rel.strip("/")
    segs = rel.split("/")
    ignored = False
    for raw in patterns:
        p = raw.strip()
        if not p or p.startswith("#"):
            continue
        neg = p.startswith("!")
        if neg:
            p = p[1:]
        dir_only = p.endswith("/")
        p = p.rstrip("/")
        anchored = p.startswith("/") or "/" in p
        p = p.lstrip("/")
        hit = False
        if anchored:
            cands = ["/".join(segs[:i + 1]) for i in range(len(segs))]
            hit = any(fnmatch.fnmatchcase(c, p) or fnmatch.fnmatchcase(c, p.replace("**/", "")) for c in cands)
        else:
            for i, sgm in enumerate(segs):
                last = i == len(segs) - 1
                if dir_only and last and not is_dir:
                    continue
                if fnmatch.fnmatchcase(sgm, p):
                    hit = True
                    break
        if hit:
            ignored = not neg
    return ignored


# ---------------------------------------------------------------- htaccess
class Htaccess:
    def __init__(self):
        self.files_rx = []   # regex sobre nome do arquivo
        self.path_rx = []    # regex sobre caminho
        self.deny_all = False
        self.bad_rx = 0
        self.text = ""

    def parse(self, text):
        self.text = text
        depth, stack = 0, []
        for raw in text.splitlines():
            ln = raw.strip()
            if not ln or ln.startswith("#"):
                continue
            m = re.match(r"<(FilesMatch|Files|DirectoryMatch|Directory|LocationMatch|Location)\s+(.*?)>$", ln, re.I)
            if m:
                kind, arg = m.group(1).lower(), m.group(2).strip()
                tilde = arg.startswith("~")
                arg = arg.lstrip("~").strip().strip("\"'")
                stack.append({"kind": kind, "arg": arg, "tilde": tilde, "deny": False})
                continue
            if ln.startswith("</"):
                if stack:
                    blk = stack.pop()
                    if blk["deny"]:
                        self._add_block(blk)
                continue
            deny = bool(re.match(r"(Require\s+all\s+denied|Deny\s+from\s+all|Require\s+not\s+all\s+granted)\b", ln, re.I))
            if deny:
                if stack:
                    stack[-1]["deny"] = True
                else:
                    self.deny_all = True
            m = re.match(r"RedirectMatch\s+(?:(\d{3}|gone|forbidden|permanent)\s+)?(\S+)", ln, re.I)
            if m and (m.group(1) or "").lower() in ("403", "404", "410", "gone", "forbidden"):
                self.path_rx.append(m.group(2).strip("\"'"))
            m = re.match(r"Redirect\s+(403|404|410|gone|forbidden)\s+(\S+)", ln, re.I)
            if m:
                self.path_rx.append("^" + re.escape(m.group(2).strip("\"'")))
            m = re.match(r"RewriteRule\s+(\S+)\s+(\S+)(?:\s+\[([^\]]*)\])?", ln, re.I)
            if m and m.group(3):
                fl = m.group(3).upper().split(",")
                if any(f in ("F", "G") or re.match(r"R=(403|404|410)", f) for f in fl):
                    self.path_rx.append(m.group(1).strip("\"'"))

    def _add_block(self, blk):
        k, arg = blk["kind"], blk["arg"]
        if k == "filesmatch" or (k == "files" and blk["tilde"]):
            self.files_rx.append(arg)
        elif k == "files":
            self.files_rx.append("^" + re.escape(arg).replace(r"\*", ".*") + "$")
        elif k in ("directorymatch", "locationmatch"):
            self.path_rx.append(arg)

    def covers(self, rel):
        base = rel.rsplit("/", 1)[-1]
        if self.deny_all:
            return True
        for rx in self.files_rx:
            try:
                if re.search(rx, base):
                    return True
            except re.error:
                self.bad_rx += 1
        for rx in self.path_rx:
            try:
                if re.search(rx, rel) or re.search(rx, "/" + rel):
                    return True
            except re.error:
                self.bad_rx += 1
        return False


# ================================================================== scanner
class Scanner:
    def __init__(self, root, max_bytes):
        self.root = os.path.abspath(root)
        self.root_real = os.path.realpath(self.root)
        self.max_bytes = max_bytes
        self.findings = []
        self._seen = set()
        self.files = []          # dict(rel, abs, size, ext)
        self.ignored_dirs = []
        self.links = []
        self.limites = defaultdict(list)
        self.counts = Counter()
        self.flags = {"cookie_secure": False, "httponly": False, "samesite": False,
                      "sec_headers": set()}
        self.session_starts = []
        self.env_files = []
        self.env_hashes = {}
        self.hash_hits = set()
        self.git_state = None
        self.sens = []           # dict(path, kind, dir)
        self.doc_folders = []    # dict(path, counts, rec, suspicious)
        self.hidden_prefixes = []
        self.texts = {}

    # ---- registro
    def add(self, regra, cat, sev, arq, linha, trecho, dica, dedupe=None):
        key = dedupe or (regra, cat, arq, linha, trecho)
        if key in self._seen:
            return
        self._seen.add(key)
        trecho = re.sub(r"\s+", " ", trecho).strip()
        if cat in ("segredos", "rastreadores_terceiros", "coleta_dados_pessoais",
                   "sessao_cookies", "logs", "ia_externa"):
            trecho = mask_tokens(trecho)       # rede de seguranca: nada de token longo no trecho
            if len(trecho) > 130:
                trecho = trecho[:130] + "…"
        self.findings.append({"regra": regra, "categoria": cat, "severidade_sugerida": sev,
                              "arquivo": arq, "linha": linha, "trecho_mascarado": trecho, "dica": dica})

    # ---- caminhada
    def walk(self):
        for dp, dn, fn in os.walk(self.root, followlinks=False):
            reld = posix(os.path.relpath(dp, self.root))
            reld = "" if reld == "." else reld
            keep = []
            for d in sorted(dn):
                full = os.path.join(dp, d)
                rel = (reld + "/" if reld else "") + d
                if is_link_like(full) or not within(self.root_real, full):
                    self.links.append(rel)
                elif d in IGNORE_DIRS or d.startswith(IGNORE_PREFIXES) or rel.endswith(IGNORE_REL_SUFFIXES):
                    self.ignored_dirs.append(rel)
                else:
                    keep.append(d)
            dn[:] = keep
            for f in sorted(fn):
                full = os.path.join(dp, f)
                rel = (reld + "/" if reld else "") + f
                if not within(self.root_real, full):
                    self.links.append(rel)
                    continue
                try:
                    size = os.path.getsize(lp(full))
                except OSError:
                    self.limites["ilegiveis"].append(rel)
                    continue
                low = f.lower()
                ext = ".sql.gz" if low.endswith(".sql.gz") else (".tar.gz" if low.endswith(".tar.gz") else os.path.splitext(low)[1])
                self.files.append({"rel": rel, "abs": full, "size": size, "ext": ext, "name": f})

    # ---- pastas de documentos (antes de ler conteudo)
    def find_doc_folders(self):
        direct, rec = defaultdict(Counter), defaultdict(Counter)
        dirs_all = set()
        for f in self.files:
            parts = f["rel"].split("/")[:-1]
            if f["ext"] in DOC_EXTS:
                direct["/".join(parts)][f["ext"]] += 1
            for i in range(1, len(parts) + 1):
                d = "/".join(parts[:i])
                dirs_all.add(d)
                if f["ext"] in DOC_EXTS:
                    rec[d][f["ext"]] += 1
        reported = []
        for d in sorted(dirs_all, key=lambda x: (x.count("/"), x)):
            segs = d.split("/")
            if any(d == r or d.startswith(r + "/") for r in reported):
                continue
            susp = bool(SUSPICIOUS_DIR.match(segs[-1]))
            anysusp = any(SUSPICIOUS_DIR.match(s) for s in segs)
            if any(s.lower() in ASSET_SEGS for s in segs) and not anysusp:
                continue
            nrec = sum(rec[d].values())
            ndir = sum(direct[d].values())
            if (susp and nrec >= 5) or ndir >= 5:
                reported.append(d)
                total_files = sum(1 for f in self.files if f["rel"].startswith(d + "/"))
                self.doc_folders.append({"path": d, "counts": dict(rec[d]), "susp": susp or anysusp,
                                         "total": total_files})
        self.hidden_prefixes = [r + "/" for r in reported]

    def hidden(self, rel):
        return any(rel.startswith(p) for p in self.hidden_prefixes)

    # ---- leitura
    def read_text(self, f):
        if f["name"] in LOCKFILES or f["ext"] == ".map":
            self.limites["lockfile_ou_map"].append(f["rel"])
            return None
        if COMPILED_RE.search(f["rel"]):
            self.limites["compilados"].append(f["rel"])
            return None
        if f["size"] > self.max_bytes:
            self.limites["acima_max_bytes"].append(f["rel"])
            return None
        try:
            with open(lp(f["abs"]), "rb") as fh:
                data = fh.read(self.max_bytes + 1)
        except OSError:
            self.limites["ilegiveis"].append(f["rel"])
            return None
        if b"\0" in data[:8192]:
            self.limites["binarios"].append(f["rel"])
            return None
        return data.decode("utf-8", errors="replace")

    # ---- varredura de conteudo
    def scan_contents(self):
        def env_real(f):
            n = f["name"].lower()
            return (n == ".env" or bool(re.match(r"[.]env[.\-_]", n))) and not re.search(r"example|sample|template|dist", n)
        # .env* reais primeiro: seus valores (hash em memória) são comparados com os demais arquivos
        for f in sorted(self.files, key=lambda f: 0 if env_real(f) else 1):
            if self.hidden(f["rel"]):
                self.limites["em_pastas_documentos"].append(f["rel"])
                continue
            text = self.read_text(f)
            if text is None:
                continue
            self.texts[f["rel"]] = text
            self.scan_text(f, text)

    def scan_text(self, f, text):
        rel, ext, name = f["rel"], f["ext"], f["name"]
        lname = name.lower()
        starts = [0]
        for m in re.finditer("\n", text):
            starts.append(m.end())
        lines = text.split("\n")

        def lineno(pos):
            return bisect.bisect_right(starts, pos)

        env_like = lname.startswith(".env") or ext in (".env", ".ini", ".cfg", ".conf", ".properties", ".toml", ".yml", ".yaml")
        example = bool(re.search(r"(example|sample|template|dist)", lname))
        ctx = {"firebase": bool(re.search(r"authDomain|firebaseapp\.com|initializeApp", text))}
        is_markup = ext in MARKUP_EXTS or lname.endswith(".blade.php")
        is_code = ext in CODE_EXTS

        # flags globais
        low_text = text.lower()
        if "cookie_secure" in low_text or "session_set_cookie_params" in low_text:
            self.flags["cookie_secure"] = True
        if "httponly" in low_text:
            self.flags["httponly"] = True
        if "samesite" in low_text:
            self.flags["samesite"] = True
        for h in SECHDRS:
            if h in low_text:
                self.flags["sec_headers"].add(h)

        # 1. segredos (por linha)
        is_env_real = (lname == ".env" or bool(re.match(r"\.env[.\-_]", lname))) and not example
        env_names, env_pub = [], 0
        for i, line in enumerate(lines, 1):
            if len(line) > 20000 or not line.strip():
                continue
            minified = len(line) > 3000
            for sp in secret_spans(line, env_like and not minified, ctx):
                if minified and sp["kind"] == "atribuicao":
                    continue
                sev, hint = sp["sev"], sp["hint"]
                regra = "segredo_literal"
                h = None
                if sev != "info" and sp["kind"] not in ("hash_de_senha", "chave_privada") and len(sp["value"]) >= 8:
                    h = hashlib.sha256(sp["value"].encode("utf-8", "replace")).hexdigest()   # só em memória
                if is_env_real and h and sev in ("alta", "média"):
                    self.env_hashes.setdefault(h, (rel, sp["key"]))
                copia = self.env_hashes.get(h) if (h and not is_env_real) else None
                if copia:
                    sev, regra = "alta", "segredo_copiado_de_env"
                    hint = "Valor idêntico ao de %s (chave %s): segredo real copiado para outro arquivo.%s" % (
                        copia[0], copia[1], " Arquivo versionado no git." if self.versionado(rel) else "")
                    self.hash_hits.add((rel, i, h))
                elif sev == "alta" and not is_env_real and (is_test_path(rel) or any(t in TEST_WORDS for t in key_tokens(sp["key"]))):
                    sev, hint = "baixa", "Credencial de teste? Confirme que não é real."
                elif sev == "alta" and ext in (".md", ".txt", ".rst"):
                    sev, hint = "média", "Em documentação: provável exemplo; confirme que não é credencial real."
                if example and sev == "alta" and not copia:
                    sev = "média"
                    hint = "Arquivo de exemplo com valor que parece real: troque por placeholder."
                if is_env_real:
                    if sev in ("alta", "média") and sp["kind"] != "hash_de_senha":
                        if sp["key"] not in env_names:
                            env_names.append(sp["key"])
                    elif sev == "info":
                        env_pub += 1
                    continue
                trecho = self.window(scrub(line, env_like, ctx), line, sp["start"], env_like, ctx)
                self.add("chave_publica_cliente" if sev == "info" else regra,
                         "segredos", sev, rel, i, trecho, hint, dedupe=("seg", rel, i, sp["start"]))
                if sev in ("alta", "média") and not example and sp["kind"] != "hash_de_senha":
                    self.sens.append({"path": rel, "kind": "segredo", "dir": False})
        if self.env_hashes and not is_env_real:
            self.scan_literais_env(rel, lines)
        if is_env_real:
            self.env_files.append((rel, env_names, env_pub))
        # 2. rastreadores
        if is_markup and ext not in (".yml", ".yaml") or lname == "package.json":
            for nome, sev, rx, dica in TRACKERS_RE:
                ms = list(rx.finditer(text))
                if ms:
                    ln = lineno(ms[0].start())
                    trecho = self.window(scrub(lines[ln - 1]), lines[ln - 1], ms[0].start() - starts[ln - 1], False, {})
                    self.add("rastreador", "rastreadores_terceiros", sev, rel, ln, trecho,
                             "%s (%d ocorrência(s) no arquivo)." % (dica, len(ms)), dedupe=("rast", rel, nome))
        # 3. coleta
        if is_markup:
            self.scan_forms(rel, text, lines, starts, lineno)
        if ext == ".sql" or ext == ".prisma" or re.search(r"create\s+table|create_table", text[:200000], re.I):
            self.scan_schema(rel, text, lineno)
        self.scan_pii_data(rel, ext, name, text, lineno, lines)
        # 4. sessao / cookies
        if is_code or ext in (".html", ".htm"):
            self.scan_sessions(rel, text, lines, lineno)
        # 5. logs
        if is_code:
            self.scan_logs(rel, lines)
        # 6. IA
        if is_markup or lname in ("requirements.txt", "pyproject.toml") or env_like:
            for prov, rx in IA_RE:
                m = rx.search(text)
                if m:
                    ln = lineno(m.start())
                    trecho = self.window(scrub(lines[ln - 1]), lines[ln - 1], m.start() - starts[ln - 1], False, {})
                    self.add("ia_externa", "ia_externa", "info", rel, ln, trecho,
                             "Provedor %s: dados podem ir a provedor de IA; confira finalidade, retenção e transferência internacional." % prov,
                             dedupe=("ia", rel, prov))
        # 7. artefatos de .htaccess etc. tratados depois

    def window(self, scrubbed, raw, pos, env_like, ctx):
        pre = mask_tokens(scrub(raw[:max(pos, 0)], env_like, ctx))
        scrubbed = mask_tokens(scrubbed)
        p = len(pre)
        s = scrubbed.strip()
        lead = len(scrubbed) - len(scrubbed.lstrip())
        p = max(p - lead, 0)
        if len(s) <= 110:
            return s
        a = max(0, p - 35)
        out = s[a:a + 110]
        return ("…" if a else "") + out + "…"

    def versionado(self, rel):
        t = self.git_tracked()
        return bool(t) and rel in t

    def scan_literais_env(self, rel, lines):
        """Qualquer literal entre aspas cujo SHA-256 (em memória) bata com um valor de .env* real."""
        for i, line in enumerate(lines, 1):
            if len(line) > 3000:
                continue
            for m in LITERAL_RE.finditer(line):
                v = m.group(1)
                if not any(c.isdigit() for c in v):
                    continue
                h = hashlib.sha256(v.encode("utf-8", "replace")).hexdigest()
                if h in self.env_hashes and (rel, i, h) not in self.hash_hits:
                    self.hash_hits.add((rel, i, h))
                    nome, chave = self.env_hashes[h]
                    trecho = self.window(scrub(line), line, m.start(1), False, {})
                    self.add("segredo_copiado_de_env", "segredos", "alta", rel, i, trecho,
                             "Valor idêntico ao de %s (chave %s): segredo real copiado para outro arquivo.%s" % (
                                 nome, chave, " Arquivo versionado no git." if self.versionado(rel) else ""),
                             dedupe=("segenv", rel, i, h))
                    self.sens.append({"path": rel, "kind": "segredo", "dir": False})

    def scan_forms(self, rel, text, lines, starts, lineno):
        forms = list(FORM_RE.finditer(text))
        if forms:
            ln = lineno(forms[0].start())
            self.add("formulario", "coleta_dados_pessoais", "info", rel, ln,
                     mask_tokens(re.sub(r"\s+", " ", forms[0].group(0)))[:120],
                     "Formulário (%d no arquivo): confira aviso de privacidade, finalidade e base legal no ponto de coleta." % len(forms),
                     dedupe=("form", rel))
        found = {}
        for m in TAG_RE.finditer(text):
            tag = m.group(0)
            attrs = {}
            for am in ATTR_RE.finditer(tag):
                attrs[am.group(1).lower()] = am.group(2) or am.group(3) or am.group(4) or ""
            typ = fold(attrs.get("type", ""))
            blob = fold(" ".join(attrs.get(k, "") for k in ("name", "id", "autocomplete")))   # nunca placeholder/value/texto
            if typ == "file":
                found.setdefault("upload", (lineno(m.start()), "média", tag, 0))
            hits = set()
            for field, sev, rx in PII_FIELDS:
                if rx.search(blob):
                    hits.add(field)
            if typ == "email":
                hits.add("email")
            if typ == "tel":
                hits.add("telefone")
            if typ == "password":
                hits.add("senha")
            for field in hits:
                sev = next(s for f, s, _ in PII_FIELDS if f == field)
                prev = found.get(field)
                found[field] = (prev[0] if prev else lineno(m.start()), sev, prev[2] if prev else tag, (prev[3] if prev else 0) + 1)
        for field, (ln, sev, tag, n) in found.items():
            if field == "upload":
                dica = "Upload de arquivo: confira tipos aceitos, onde ficam salvos, acesso e retenção."
            else:
                dica = "Campo que coleta %s: confira finalidade, base legal e minimização." % field
            self.add("campo_formulario", "coleta_dados_pessoais", sev, rel, ln,
                     mask_tokens(re.sub(r"\s+", " ", tag))[:130], dica, dedupe=("campo", rel, field))

    def scan_schema(self, rel, text, lineno):
        found = {}
        for m in COL_RE.finditer(text):
            col = fold(m.group(1))
            for field, sev, rx in PII_FIELDS:
                if field in ("senha",) and not re.search(r"senha|passw", col):
                    continue
                if rx.search(col):
                    s2 = "média" if sev in ("alta", "média") else "baixa"
                    found.setdefault(field, [lineno(m.start()), s2, m.group(1), 0])
                    found[field][3] += 1
        for field, (ln, sev, col, n) in found.items():
            self.add("coluna_schema", "coleta_dados_pessoais", sev, rel, ln,
                     "coluna %s (%d coluna(s) do tipo %s)" % (col, n, field),
                     "Schema armazena %s: confira necessidade, retenção, acesso e criptografia." % field,
                     dedupe=("col", rel, field))

    def scan_pii_data(self, rel, ext, name, text, lineno, lines):
        teste = is_test_path(rel)
        for rx, check, regra, rotulo in ((CPF_RE, cpf_valido, "cpf_no_arquivo", "CPF"),
                                         (CNPJ_RE, cnpj_valido, "cnpj_no_arquivo", "CNPJ")):
            valid = [m for m in rx.finditer(text) if check(m.group(0))]   # DV inválido ou repetido não é achado
            if valid:
                m = valid[0]
                so_conhecidos = all(re.sub(r"\D", "", m.group(0)) in CPF_DE_EXEMPLO for m in valid)
                exemplo = teste or ext in (".md", ".rst") or so_conhecidos
                # CNPJ identifica pessoa jurídica (não pessoa natural): sempre baixa
                sev = "baixa" if (exemplo or rotulo == "CNPJ") else "média"
                dica = "%d %s(s) com dígitos verificadores válidos (podem ser reais)%s." % (
                    len(valid), rotulo, "; arquivo de teste/exemplo/documentação: confirme que não é real" if exemplo else "")
                self.add(regra, "coleta_dados_pessoais", sev, rel, lineno(m.start()),
                         rotulo + " " + mask(m.group(0)), dica, dedupe=(regra, rel))
        if ext in DATA_EXTS and name not in ("package.json", "composer.json", "tsconfig.json", "skills-lock.json"):
            em = [m for m in EMAIL_RE.finditer(text)]
            if em:
                self.add("email_no_arquivo", "coleta_dados_pessoais", "baixa", rel, lineno(em[0].start()),
                         "e-mail " + mask(em[0].group(0)),
                         "%d e-mail(s) em arquivo de dados: confira se são dados reais de pessoas e se o arquivo deveria estar aqui." % len(em),
                         dedupe=("email", rel))
            cnj = [(c.start(), c.end()) for c in CNJ_RE.finditer(text)]
            fo = [m for m in FONE_RE.finditer(text)
                  if not any(s < m.end() and m.start() < e for s, e in cnj)]
            if fo:
                self.add("telefone_no_arquivo", "coleta_dados_pessoais", "baixa", rel, lineno(fo[0].start()),
                         "telefone " + mask(fo[0].group(0)),
                         "%d telefone(s) em arquivo de dados: confira se são dados reais." % len(fo),
                         dedupe=("fone", rel))

    def scan_sessions(self, rel, text, lines, lineno):
        for m in SESSION_RE.finditer(text):
            self.session_starts.append((rel, lineno(m.start()), lines[lineno(m.start()) - 1]))
        for m in SETCOOKIE_RE.finditer(text):
            seg = text[m.start():m.start() + 500].split(";")[0].lower()
            ln = lineno(m.start())
            missing = [k for k in ("secure", "httponly", "samesite") if k not in seg]
            if missing:
                self.add("cookie_sem_flags", "sessao_cookies", "baixa", rel, ln, mask_tokens(scrub(lines[ln - 1].strip()))[:130],
                         "Cookie sem %s (análise heurística; confira se os flags são definidos em outro ponto)." % ", ".join(missing),
                         dedupe=("setcookie", rel, ln))
        m = DOCCOOKIE_RE.search(text)
        if m:
            ln = lineno(m.start())
            self.add("document_cookie", "sessao_cookies", "baixa", rel, ln, mask_tokens(scrub(lines[ln - 1].strip()))[:130],
                     "Cookie escrito por JavaScript não pode ser HttpOnly; confira o que guarda e o consentimento.",
                     dedupe=("doccookie", rel))
        for m in STORAGE_RE.finditer(text):
            ln = lineno(m.start())
            key = m.group(2).lower()
            sev = "média" if re.search(r"token|jwt|senha|password|cpf|user|email", key) else "baixa"
            self.add("web_storage", "sessao_cookies", sev, rel, ln, mask_tokens(scrub(lines[ln - 1].strip()))[:130],
                     "Dados guardados no navegador (%s) ficam legíveis por qualquer script da página; evite tokens/dados pessoais." % m.group(1),
                     dedupe=("storage", rel, m.group(1), key))

    def scan_logs(self, rel, lines):
        for i, line in enumerate(lines, 1):
            if len(line) > 3000:
                continue
            m = LOG_CALL_RE.search(line)
            if not m:
                continue
            rest = line[m.end():]
            body = LOG_BODY_RE.search(rest)
            r2 = re.sub(r"\[\s*['\"](\w+)['\"]\s*\]", r".\1", rest)
            r2 = re.sub(r"\"[^\"{}$]*\"|'[^'{}$]*'", '""', r2)
            pii = LOG_PII_RE.search(r2)
            if body or pii:
                sev = "média" if body else "baixa"
                what = "corpo inteiro da requisição" if body else "variável com nome de dado pessoal (%s)" % pii.group(1).lower()
                self.add("log_dado_pessoal", "logs", sev, rel, i, mask_tokens(scrub(line.strip()))[:130],
                         "Log registra %s: logs costumam ficar sem controle de acesso/retenção." % what,
                         dedupe=("log", rel, i))

    # ================== pos-processamento
    # ---- git (somente leitura)
    def git(self, *args):
        try:
            env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
            r = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", self.root] + list(args),
                               capture_output=True, timeout=8, shell=False, env=env)
            return r.returncode, r.stdout
        except (OSError, subprocess.SubprocessError):
            return None, b""

    def git_tracked(self):
        """Conjunto de arquivos versionados, ou None se nao ha git/repositorio."""
        if self.git_state is None:
            rc, out = self.git("rev-parse", "--is-inside-work-tree")
            if rc == 0 and out.strip() == b"true":
                rc, out = self.git("ls-files", "-z")
                self.git_state = set(x.decode("utf-8", "replace") for x in out.split(b"\0") if x) if rc == 0 else False
            else:
                self.git_state = False
        return self.git_state if self.git_state is not False else None

    def env_status(self, rel):
        tracked = self.git_tracked()
        if tracked is None:
            return "sem_git"
        if rel in tracked:
            return "versionado"
        rc, _ = self.git("check-ignore", "-q", "--", rel)
        if rc == 0:
            return "ignorado"
        return "nao_ignorado" if rc == 1 else "sem_git"

    def post_env(self):
        for rel, names, npub in self.env_files:
            st = self.env_status(rel)
            k = len(names)
            lista = ", ".join(names[:8]) + ("…" if k > 8 else "")
            txt = "arquivo de ambiente com %d valor(es) secreto(s)" % k + (" (nomes: %s)" % lista if k else "")
            if npub:
                txt += "; +%d chave(s) pública(s) por desenho" % npub
            if st in ("versionado", "nao_ignorado"):
                sev = "alta" if k else "média"
                dica = ("O arquivo está versionado no git." if st == "versionado" else "O arquivo NÃO está no .gitignore.") +                        " Remova do repositório, rotacione os segredos e mantenha fora de deploy e backup."
            elif st == "ignorado":
                sev = "info"
                dica = "Ignorado pelo git e só local: mantenha fora de deploy e backup."
            else:
                sev = "média" if k else "info"
                dica = "Não consegui verificar o git (sem git ou fora de repositório): confirme que o arquivo fica fora de repositório, deploy e backup."
            self.add("arquivo_ambiente", "segredos", sev, rel, 0, txt, dica, dedupe=("env", rel))
            if sev in ("alta", "média"):
                self.sens.append({"path": rel, "kind": "segredo", "dir": False})

    def classify_sql(self, f):
        low, rel = f["name"].lower(), f["rel"]
        text = self.texts.get(rel)
        dump = f["size"] > 1048576 or bool(re.search(r"dump|backup|bkp", low))
        if text is not None and not dump:
            if re.search(r"^COPY\s+\S+.*FROM\s+stdin", text, re.I | re.M):
                dump = True
            elif len(re.findall(r"^\s*INSERT\s+INTO", text, re.I | re.M)) >= 50:
                dump = True
        if dump:
            return ("alta", "Arquivo de dados/backup na árvore do projeto: pode conter dados pessoais e ser baixado se estiver em pasta pública.", "artefato")
        return ("info", "SQL de schema/migration (não parece dump de dados): confira se não embute dados pessoais e se a pasta não é pública.", "schema")

    def post(self):
        self.post_env()
        self.post_sessions()
        self.post_artifacts()
        self.post_docs()
        self.post_protecao()
        self.post_empacotamento()

    def post_sessions(self):
        if not self.session_starts:
            return
        if not self.flags["cookie_secure"]:
            seen = set()
            for rel, ln, line in self.session_starts:
                if rel in seen:
                    continue
                seen.add(rel)
                self.add("session_start_sem_cookie_secure", "sessao_cookies", "média", rel, ln, line.strip()[:150],
                         "session_start sem cookie_secure/session_set_cookie_params em todo o projeto: o cookie de sessão pode trafegar fora de HTTPS. Verifique também no php.ini do servidor.",
                         dedupe=("sess", rel))
        miss = [k for k in ("httponly", "samesite") if not self.flags[k]]
        if miss:
            rel, ln, line = self.session_starts[0]
            self.add("sessao_sem_flags", "sessao_cookies", "baixa", rel, ln, line.strip()[:150],
                     "Não encontrei configuração de %s para o cookie de sessão (heurístico; pode estar no php.ini)." % " e ".join(miss),
                     dedupe=("sessflags",))

    def post_artifacts(self):
        gi_lines = None
        for f in self.files:
            if f["rel"] == ".gitignore":
                gi_lines = (self.texts.get(".gitignore") or "").splitlines()
        for d in self.ignored_dirs:
            if d.rsplit("/", 1)[-1] == ".git":
                servida = bool(set(s.lower() for s in d.split("/")[:-1]) & SERVED_DIRS)
                self.add("git_presente", "artefatos_deploy", "alta" if servida else "info", d, 0, ".git/",
                         ("Pasta .git dentro de pasta servida/de deploy: expõe código-fonte e histórico (inclusive segredos antigos). Remova." if servida
                          else "Pasta .git na raiz do projeto é normal; só vira problema se for publicada junto do site ou entrar no pacote de deploy."),
                         dedupe=("git", d))
        for f in self.files:
            rel, name, low = f["rel"], f["name"], f["name"].lower()
            if self.hidden(rel):
                continue
            hit = None
            if low.endswith(".sql"):
                hit = self.classify_sql(f)
            elif low.endswith(ARTIFACT_EXTS_HIGH):
                hit = ("alta", "Arquivo de dados/backup na árvore do projeto: pode conter dados pessoais e ser baixado se estiver em pasta pública.", "artefato")
            elif low.endswith(ARTIFACT_EXTS_MED):
                hit = ("média", "Pacote/arquivo compactado na árvore: confira o conteúdo e se está em pasta pública ou entra no próximo pacote de deploy.", "artefato")
            if name in SENSITIVE_NAMES or low in SENSITIVE_NAMES:
                hit = ("alta" if low in ("phpinfo.php", "info.php", "adminer.php", ".htpasswd", "id_rsa") else "média",
                       "Arquivo de instalação/diagnóstico (%s): remova do servidor de produção ou proteja o acesso." % SENSITIVE_NAMES.get(name, SENSITIVE_NAMES.get(low)),
                       "setup")
            elif low.endswith(SENSITIVE_EXT) and not low.endswith(".log"):
                hit = ("alta", "Chave/certificado na árvore do projeto: não deve ficar no repositório nem em pasta pública.", "artefato")
            elif low.endswith(".log"):
                hit = ("média", "Arquivo de log na árvore: pode conter dados pessoais.", "artefato")
            elif low == ".env" or (low.startswith(".env.") and not re.search(r"example|sample|template|dist", low)):
                hit = ("alta", "Arquivo de variáveis de ambiente real na árvore: garanta que esteja fora do repositório e do pacote de deploy.", "segredo")
            if hit:
                sev, dica, kind = hit
                if not (kind == "segredo" and rel in self.texts):   # .env lidos viram achado agregado
                    self.add("artefato_sensivel" if sev != "info" else "sql_schema_ou_migration",
                             "artefatos_deploy", sev, rel, 0, f["ext"] or "(arquivo)", dica, dedupe=("art", rel))
                self.sens.append({"path": rel, "kind": kind, "dir": False})
        # .gitignore
        secret_files = sorted({s["path"] for s in self.sens if s["kind"] in ("segredo", "artefato", "setup")})
        high_secret = any(f["severidade_sugerida"] == "alta" and f["categoria"] == "segredos" for f in self.findings)
        if gi_lines is None:
            if high_secret:
                self.add("sem_gitignore", "artefatos_deploy", "média", ".gitignore", 0, "(ausente)",
                         "Há segredos no projeto e não existe .gitignore: se usar git, crie um e exclua arquivos de configuração com senha, .env, dumps e pastas de documentos.",
                         dedupe=("nogi",))
        else:
            unc = [p for p in secret_files if not ignore_match(gi_lines, p)]
            if unc:
                self.add("gitignore_nao_cobre", "artefatos_deploy", "média", ".gitignore", 0,
                         ", ".join(unc[:10]) + (" (+%d)" % (len(unc) - 10) if len(unc) > 10 else ""),
                         "Itens sensíveis que o .gitignore (heurístico) não parece cobrir.", dedupe=("gicov",))

    def post_docs(self):
        ht = self.htaccess_for_root()
        for d in self.doc_folders:
            ext_txt = ", ".join("%s: %d" % (k, v) for k, v in sorted(d["counts"].items()))
            probe = d["path"] + "/x" + (sorted(d["counts"])[0] if d["counts"] else ".pdf")
            blocked = self.is_covered(probe, ht)
            if blocked:
                sev = "info"
                status = "há regra de bloqueio detectada para a pasta"
            else:
                sev = "alta" if d["susp"] else "baixa"
                status = "NÃO encontrei .htaccess/regra de bloqueio para a pasta"
            outros = d["total"] - sum(d["counts"].values())
            segs = set(s.lower() for s in d["path"].split("/"))
            so_imagens = not (set(d["counts"]) & {".pdf", ".docx", ".doc", ".odt", ".tif", ".tiff"})
            publica = bool(segs & {"public", "static", "assets", "asset", "img", "imgs", "images"}) and so_imagens
            if publica:
                self.add("pasta_de_documentos", "pastas_documentos", "baixa", d["path"] + "/", 0,
                         "%s (outros arquivos não listados: %d)" % (ext_txt, outros),
                         "Conteúdo público por desenho; confirme que não há documento de cliente. Nomes de arquivos omitidos de propósito.",
                         dedupe=("docs", d["path"]))
                continue
            docs_n = sum(d["counts"].values())
            minoria = sev == "alta" and outros > 4 * docs_n
            if minoria:
                # Documentos são minoria numa pasta majoritariamente de texto/código:
                # padrão típico de documentação do projeto, não de acervo de clientes.
                sev = "média"
                status += "; documentos são minoria na pasta (provável documentação do projeto; confira se algum é de cliente)"
            self.add("pasta_de_documentos", "pastas_documentos", sev, d["path"] + "/", 0,
                     "%s (outros arquivos não listados: %d)" % (ext_txt, outros),
                     "Pasta com documentos/imagens digitalizadas: %s. Confira base legal, retenção e se o acesso público é impossível. Nomes de arquivos omitidos de propósito." % status,
                     dedupe=("docs", d["path"]))
            self.sens.append({"path": d["path"], "kind": "pasta_docs", "dir": True, "probe": probe})

    def htaccess_for_root(self):
        ht = Htaccess()
        if ".htaccess" in self.texts:
            ht.parse(self.texts[".htaccess"])
        return ht

    def is_covered(self, rel, root_ht):
        if root_ht.covers(rel):
            return True
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            sub = "/".join(parts[:i]) + "/.htaccess"
            if sub in self.texts:
                h = Htaccess()
                h.parse(self.texts[sub])
                if h.deny_all:
                    return True
        return False

    def post_protecao(self):
        has_php = any(f["ext"] in (".php", ".phtml") for f in self.files)
        has_ht = ".htaccess" in self.texts
        if not (has_php or has_ht):
            return
        ht = self.htaccess_for_root()
        items, seen = [], set()
        for s in self.sens:
            if s["kind"] in ("pasta_docs",):
                probe = s.get("probe", s["path"] + "/x.pdf")
                if not self.is_covered(probe, ht) and s["path"] not in seen:
                    seen.add(s["path"])
                    items.append(("pasta", s["path"] + "/"))
            else:
                if not self.is_covered(s["path"], ht):
                    d = s["path"].rsplit("/", 1)[0] if "/" in s["path"] else ""
                    items.append(("arquivo", s["path"], d))
        files_by_dir = defaultdict(list)
        listed = []
        for it in items:
            if it[0] == "arquivo":
                if it[2]:
                    files_by_dir[it[2]].append(it[1])
                elif it[1] not in listed:
                    listed.append(it[1])
        for d, fs in sorted(files_by_dir.items()):
            listed.append("%s/ (%d arquivo(s))" % (d, len(set(fs))))
        for it in items:
            if it[0] == "pasta":
                listed.append(it[1])
        listed = list(dict.fromkeys(listed))
        if not has_ht:
            if listed:
                self.add("sem_htaccess", "protecao_web", "média", ".htaccess", 0, "(ausente na raiz)",
                         "Sem .htaccess na raiz, nada (neste projeto) bloqueia acesso direto a: %s. Se o servidor for nginx ou similar, a regra equivalente fica na configuração do servidor, que eu não vejo." % ", ".join(listed[:12]),
                         dedupe=("noht",))
        elif listed:
            sev = "alta" if any(s["kind"] == "segredo" and not self.is_covered(s["path"], ht) for s in self.sens) or any(it[0] == "pasta" for it in items) else "média"
            self.add("htaccess_nao_cobre", "protecao_web", sev, ".htaccess", 1,
                     ", ".join(listed[:12]) + (" (+%d)" % (len(listed) - 12) if len(listed) > 12 else ""),
                     "Itens sensíveis encontrados que o .htaccess da raiz NÃO parece bloquear (heurístico: FilesMatch/RedirectMatch/RewriteRule [F]/Require all denied). Teste a URL direta de cada um e/ou mova-os para fora da pasta pública.",
                     dedupe=("htcov",))
        if ht.bad_rx:
            self.limites["regex_htaccess"].append("%d regra(s) .htaccess com regex não interpretável" % ht.bad_rx)
        # redirect HTTPS / headers / Indexes
        txt = ht.text
        if has_ht or has_php:
            https = bool(re.search(r"%\{HTTPS\}\s+off|X-Forwarded-Proto|%\{SERVER_PORT\}\s+80|RewriteCond.*https", txt, re.I)) or \
                bool(re.search(r"\$_SERVER\[['\"]HTTPS['\"]\]", " ".join(self.texts.get(f["rel"], "") for f in self.files if f["ext"] == ".php")))
            if not https:
                self.add("sem_redirect_https", "protecao_web", "info", ".htaccess", 0, "(não encontrado)",
                         "Não encontrei redirecionamento para HTTPS no código/.htaccess (a hospedagem pode fazê-lo no painel). Confira.",
                         dedupe=("https",))
            missing = [h for h in SECHDRS if h not in self.flags["sec_headers"]]
            if missing:
                self.add("sem_headers_seguranca", "protecao_web", "info", ".htaccess", 0, ", ".join(missing),
                         "Cabeçalhos de segurança não encontrados no projeto (podem ser definidos pela hospedagem). Confira com curl -I ou no navegador.",
                         dedupe=("hdrs",))
            if has_ht and not re.search(r"Options\s+[^\n]*-Indexes", txt, re.I):
                self.add("listagem_diretorio", "protecao_web", "baixa", ".htaccess", 0, "(Options -Indexes ausente)",
                         "Sem 'Options -Indexes', pastas sem index podem listar arquivos no navegador.", dedupe=("idx",))

    # ---- empacotamento
    def post_empacotamento(self):
        sens_paths = [s for s in self.sens]
        ignored_pack_names = (".gitignore", ".vercelignore", ".dockerignore", ".npmignore")
        scripts = []
        for f in self.files:
            low = f["name"].lower()
            if self.hidden(f["rel"]) or f["rel"] not in self.texts:
                continue
            if low.endswith((".ps1", ".sh", ".bat", ".cmd")) or low == "makefile" or \
                    re.match(r"(deploy|build|package|release)[\w.\-]*$", low) and f["ext"] not in (".zip", ".png", ".jpg"):
                scripts.append(f)
        for f in scripts:
            self.analyze_script(f, sens_paths)
        if "package.json" in self.texts:
            self.analyze_package_json(sens_paths)
        if "vercel.json" in self.texts or ".vercelignore" in self.texts:
            self.analyze_ignore_file(".vercelignore", sens_paths, "Vercel")
        for ig, label in ((".dockerignore", "Docker"), (".npmignore", "npm")):
            if ig in self.texts:
                self.analyze_ignore_file(ig, sens_paths, label)
        if "Dockerfile" in self.texts and ".dockerignore" not in self.texts and sens_paths:
            self.add("docker_sem_ignore", "empacotamento", "média", "Dockerfile", 0, "(sem .dockerignore)",
                     "Dockerfile sem .dockerignore: COPY . pode levar segredos, dumps e documentos para dentro da imagem.",
                     dedupe=("dock",))

    def tem_git_raiz(self):
        return any(d == ".git" for d in self.ignored_dirs)

    def sens_groups(self, sens, covered_fn):
        a, b = [], []
        seen = set()
        for s in sens:
            p = s["path"]
            if p in seen or s["kind"] == "schema":      # schema/migration (info) não entra na lista de empacotamento
                continue
            seen.add(p)
            if covered_fn(p, s):
                continue
            label = p + ("/" if s["dir"] else "")
            top = p.split("/")[0]
            if "/" in p and not s["dir"]:
                label += " (topo: %s)" % top
            (a if s["kind"] in ("segredo", "pasta_docs", "setup") else b).append(label)
        return a, b

    def emit_uncovered(self, rel, linha, a, b, fonte, modo):
        def fmt(xs):
            return ", ".join(xs[:12]) + (" (+%d)" % (len(xs) - 12) if len(xs) > 12 else "")
        if a:
            self.add("empacotamento_nao_exclui", "empacotamento", "alta", rel, linha, fmt(a),
                     "%s itens com segredos, documentos ou scripts de instalação que o script NÃO exclui do pacote." % modo,
                     dedupe=("pack", rel, "a"))
        if b:
            self.add("empacotamento_nao_exclui_artefatos", "empacotamento", "média", rel, linha, fmt(b),
                     "%s dumps, backups e arquivos compactados que o script NÃO exclui (um deploy .zip antigo pode entrar dentro do novo)." % modo,
                     dedupe=("pack", rel, "b"))

    def analyze_script(self, f, sens):
        rel, text = f["rel"], self.texts[f["rel"]]
        if not PACK_WORDS.search(text):
            return
        m = re.search(r"\$(\w*(?:exclu|ignor|skip)\w*)\s*=\s*@\((.*?)\)", text, re.I | re.S)
        if f["ext"] == ".ps1" and m:
            items = [x.strip() for x in re.findall(r"['\"]([^'\"]+)['\"]", m.group(2))]
            low_items = {x.lower().replace("\\", "/") for x in items}
            first_seg = bool(re.search(r"\.Split\([^)]*\)\s*\[0\]|reltop", text, re.I))
            ln = text[:m.start()].count("\n") + 1
            if first_seg:
                modo = "O filtro compara só o primeiro segmento do caminho com a lista $%s;" % m.group(1)

                def cov(p, s):
                    return p.split("/")[0].lower() in low_items
                bad = [x for x in items if "/" in x.replace("\\", "/") or "*" in x]
                if bad:
                    self.add("empacotamento_entrada_inutil", "empacotamento", "média", rel, ln, ", ".join(bad),
                             "Entradas com barra ou curinga nunca casam quando só o primeiro segmento é comparado.",
                             dedupe=("packbad", rel))
            else:
                modo = "Verificação heurística da lista $%s (não consegui confirmar como o script a aplica);" % m.group(1)

                def cov(p, s):
                    segs = p.lower().split("/")
                    return p.lower() in low_items or any(x in low_items for x in segs)
                self.add("empacotamento_revisar", "empacotamento", "info", rel, ln, "$%s com %d item(ns)" % (m.group(1), len(items)),
                         "info: revisar manualmente o que o script empacota.", dedupe=("packrev", rel))
            a, b = self.sens_groups(sens, cov)
            if first_seg and ".git" not in low_items and self.tem_git_raiz() and re.search(r"-Force", text, re.I):
                a.append(".git/ (histórico do repositório)")
            self.emit_uncovered(rel, ln, a, b, rel, modo)
            return
        pats = []
        for mm in re.finditer(r"(?:--exclude(?:-from)?[=\s]+|\s-x\s+|\s-e\s+)((?:['\"][^'\"]+['\"]|[^\s'\"-][^\s]*)(?:\s+(?:['\"][^'\"]+['\"]|[^\s'\"-][^\s]*))*)", text):
            pats += [x.strip("'\"") for x in re.findall(r"['\"][^'\"]+['\"]|\S+", mm.group(1))]
        if pats:
            def cov(p, s):
                return ignore_match([x for x in pats], p, s["dir"]) or any(
                    fnmatch.fnmatch(p, x) or fnmatch.fnmatch(p.split("/")[-1], x) or fnmatch.fnmatch(p.split("/")[0], x.rstrip("/*")) for x in pats)
            a, b = self.sens_groups(sens, cov)
            if self.tem_git_raiz() and not any(x.strip("/*") == ".git" or fnmatch.fnmatch(".git", x) for x in pats)                     and re.search(r"zip|tar|rsync|7z", text, re.I):
                a.append(".git/ (histórico do repositório)")
            self.emit_uncovered(rel, 1, a, b, rel, "Verificação heurística das exclusões do script (%d padrão(ões));" % len(pats))
            if not (a or b):
                return
        self.add("empacotamento_revisar", "empacotamento", "info", rel, 1, "(script de empacotamento/deploy)",
                 "info: revisar manualmente o que o script empacota.", dedupe=("packrev", rel))

    def analyze_package_json(self, sens):
        try:
            data = json.loads(self.texts["package.json"])
        except Exception:
            return
        scripts = data.get("scripts") or {}
        hot = {k: v for k, v in scripts.items() if re.search(r"deploy|pack|zip|publish|release", k + " " + str(v), re.I)}
        if hot:
            extra = " O campo \"files\" do package.json define a lista do pacote npm." if "files" in data else ""
            self.add("empacotamento_revisar", "empacotamento", "info", "package.json", 1,
                     "scripts: " + ", ".join(sorted(hot)),
                     "info: revisar manualmente o que o script empacota." + extra, dedupe=("packrev", "package.json"))

    def analyze_ignore_file(self, igname, sens, label):
        lines = (self.texts.get(igname) or "").splitlines() if igname in self.texts else None
        if lines is None:
            if sens:
                self.add("empacotamento_revisar", "empacotamento", "info", "vercel.json" if "vercel.json" in self.texts else igname, 1,
                         "(sem %s)" % igname,
                         "info: revisar manualmente o que o %s envia; sem %s, confira o .gitignore e os arquivos sensíveis encontrados." % (label, igname),
                         dedupe=("packrev", label))
            return
        a, b = self.sens_groups(sens, lambda p, s: ignore_match(lines, p, s["dir"]))
        self.emit_uncovered(igname, 1, a, b, igname, "Verificação heurística de %s;" % igname)

    # ================== saida
    def result(self):
        order = sorted(self.findings, key=lambda x: (SEV_ORDER[x["severidade_sugerida"]], CATEGORIAS.index(x["categoria"]),
                                                    x["arquivo"], x["linha"]))
        resumo = {}
        for c in CATEGORIAS:
            cs = [x for x in order if x["categoria"] == c]
            resumo[c] = {"total": len(cs), **{s: sum(1 for x in cs if x["severidade_sugerida"] == s) for s in SEV_ORDER}}
        lim = {
            "arquivos_inventariados": len(self.files),
            "pastas_ignoradas_existentes": sorted(self.ignored_dirs),
            "links_nao_seguidos": sorted(self.links),
            "binarios_pulados": len(self.limites["binarios"]),
            "acima_max_bytes": sorted(self.limites["acima_max_bytes"]),
            "lockfiles_e_maps_pulados": len(self.limites["lockfile_ou_map"]),
            "compilados_pulados": len(self.limites["compilados"]),
            "arquivos_em_pastas_de_documentos_nao_lidos": len(self.limites["em_pastas_documentos"]),
            "ilegiveis": len(self.limites["ilegiveis"]),
            "max_bytes": self.max_bytes,
            "observacao": "Resultado é pista, não prova. Zero achados não prova ausência de problema.",
        }
        if self.limites["regex_htaccess"]:
            lim["avisos"] = self.limites["regex_htaccess"]
        return {"versao": 1, "raiz": os.path.basename(self.root) or self.root, "achados": order,
                "resumo_por_categoria": resumo, "limites": lim}


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ").replace("`", "'")


CAT_PRI = {"empacotamento": 0, "segredos": 1, "protecao_web": 2, "pastas_documentos": 3,
           "artefatos_deploy": 4, "coleta_dados_pessoais": 5, "sessao_cookies": 6,
           "rastreadores_terceiros": 7, "logs": 8, "ia_externa": 9}


def agrupar(achados):
    """Agrupa achados repetidos (mesma severidade, categoria, regra e pasta) para leitura."""
    grupos = {}
    for a in achados:
        arq = a["arquivo"]
        d = arq.rsplit("/", 1)[0] if "/" in arq else ""
        grupos.setdefault((a["severidade_sugerida"], a["categoria"], a["regra"], d), []).append(a)
    rows = []
    for (sev, cat, regra, d), xs in grupos.items():
        a = dict(xs[0])
        a["n"] = len(xs)
        if len(xs) > 1:
            a["arquivo"] = (d + "/" if d else "(raiz)") + " (%d ocorrências)" % len(xs)
            a["linha"] = 0
            ex = [x["arquivo"].rsplit("/", 1)[-1] + (":%d" % x["linha"] if x["linha"] else "") for x in xs[:3]]
            a["trecho_mascarado"] = "ex.: " + "; ".join(ex) + (" …" if len(xs) > 3 else "")
        rows.append(a)
    rows.sort(key=lambda a: (SEV_ORDER[a["severidade_sugerida"]], CAT_PRI.get(a["categoria"], 99), -a["n"], a["arquivo"]))
    return rows


def to_md(res):
    L = ["# Varredura LGPD (pistas automáticas)", "",
         "> Resultado é **pista, não prova**. Zero achados não prova ausência de problema. "
         "Valores de segredos e dados pessoais aparecem mascarados. Revise com o advogado/responsável.", "",
         "Projeto: `%s`" % res["raiz"], "", "## Resumo por categoria", "",
         "| Categoria | Total | alta | média | baixa | info |", "|---|---|---|---|---|---|"]
    for c, v in res["resumo_por_categoria"].items():
        L.append("| %s | %d | %d | %d | %d | %d |" % (c, v["total"], v["alta"], v["média"], v["baixa"], v["info"]))
    lim = res["limites"]
    L += ["", "## Limites (o que não foi lido)", ""]
    L.append("- Arquivos inventariados: %d; binários pulados: %d; lockfiles/.map pulados: %d; compilados/minificados pulados: %d; ilegíveis: %d."
             % (lim["arquivos_inventariados"], lim["binarios_pulados"], lim["lockfiles_e_maps_pulados"], lim.get("compilados_pulados", 0), lim["ilegiveis"]))
    L.append("- Pastas ignoradas que existem: %s." % (", ".join(lim["pastas_ignoradas_existentes"]) or "nenhuma"))
    L.append("- Links/junctions não seguidos: %s." % (", ".join(lim["links_nao_seguidos"]) or "nenhum"))
    L.append("- Arquivos acima de %d bytes pulados: %s." % (lim["max_bytes"], ", ".join(lim["acima_max_bytes"]) or "nenhum"))
    L.append("- Arquivos dentro de pastas de documentos (conteúdo e nomes não lidos): %d." % lim["arquivos_em_pastas_de_documentos_nao_lidos"])
    for a in lim.get("avisos", []):
        L.append("- Aviso: %s." % a)
    L.append("")
    rows = agrupar(res["achados"])
    L += ["## Top 10 para olhar primeiro", "",
          "| # | Severidade | Categoria | Onde | O que | Dica |", "|---|---|---|---|---|---|"]
    for n, a in enumerate(rows[:10], 1):
        loc = a["arquivo"] + (":%d" % a["linha"] if a["linha"] else "")
        L.append("| %d | %s | %s | %s | %s | %s |" % (n, a["severidade_sugerida"], cell(a["categoria"]), cell(loc),
                                                    cell(a["trecho_mascarado"]), cell(a["dica"])))
    if not rows:
        L.append("| - | - | - | Nenhum achado (isso não prova ausência de problemas) | - | - |")
    L += ["", "(Achados repetidos na mesma pasta aparecem agrupados; o JSON traz a lista completa.)", ""]
    cur = None
    for a in rows:
        if a["severidade_sugerida"] != cur:
            cur = a["severidade_sugerida"]
            L += ["", "## Achados: severidade %s" % cur, "",
                  "| Categoria | Regra | Arquivo:linha | Trecho (mascarado) | Dica |", "|---|---|---|---|---|"]
        loc = a["arquivo"] + (":%d" % a["linha"] if a["linha"] else "")
        L.append("| %s | %s | %s | %s | %s |" % (cell(a["categoria"]), cell(a["regra"]), cell(loc),
                                                 cell(a["trecho_mascarado"]), cell(a["dica"])))
    L.append("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Varredura determinística de pistas LGPD (somente leitura).")
    ap.add_argument("raiz")
    ap.add_argument("--saida")
    ap.add_argument("--formato", choices=["md", "json"])
    ap.add_argument("--max-bytes", type=int, default=1048576)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if not os.path.isdir(a.raiz):
        print("Erro: raiz não é uma pasta: %s" % a.raiz, file=sys.stderr)
        return 2
    root_real = os.path.realpath(a.raiz)
    if a.saida:
        out_real = os.path.realpath(a.saida)
        if within(root_real, out_real) or os.path.normcase(out_real) == os.path.normcase(root_real):
            print("Erro: a saída não pode ficar dentro da pasta auditada (%s). Escolha um caminho fora dela, por exemplo a pasta temporária." % a.raiz,
                  file=sys.stderr)
            return 2
    fmt = a.formato or ("json" if a.saida and a.saida.lower().endswith(".json") else "md")
    sc = Scanner(a.raiz, a.max_bytes)
    sc.walk()
    sc.find_doc_folders()
    sc.scan_contents()
    sc.post()
    res = sc.result()
    out = json.dumps(res, ensure_ascii=False, indent=2) if fmt == "json" else to_md(res)
    if a.saida:
        os.makedirs(os.path.dirname(out_real) or ".", exist_ok=True)
        with open(out_real, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
        print("Varredura concluída: %d achado(s). Relatório: %s" % (len(res["achados"]), a.saida))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
