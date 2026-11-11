import asyncio
import copy
import html
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from logging.handlers import RotatingFileHandler

from telethon import Button, TelegramClient, events
from telethon.tl.types import MessageEntityTextUrl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ENV = os.path.join(BASE_DIR, ".env")
ARQUIVO_JSON = os.path.join(BASE_DIR, "banco_de_dados.json")
PASTA_LOGS = os.path.join(BASE_DIR, "logs")
ARQUIVO_LOG = os.path.join(PASTA_LOGS, "bot.log")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

DADOS_PADRAO = {
    "canais": [
        "@promonationchat", "@NerdCupons", "@TJGOFERTASs", "@Radar_BugS_e_Ofertas",
        "@promocoeseachadinhos", "@viciadopromocao", "@nerdofertas", "@chinasuperofertas",
        "@promocoes", "@cupons", "@aliexpressb", "@ofertabrasil", "@ofertasbr",
        "@canaltech", "@meliuz", "@canalbr", "@Pedro_Indica", "@PedroIndicaChat", "@JuliaSaliba",
    ],
    "palavras": [
        r"\bbug\b", r"\bbugs\b", r"\bbugou\b", r"\bbugado\b",
        r"erro de pre[çc]o", r"pre[çc]o errado", r"erro de digita[çc][ãa]o",
        r"\bestagi[áa]rio\b", r"\bcorram+\b", r"\bcorre+\b",
        r"\bimperd[íi]vel\b", r"\bsurreal\b", r"de gra[çc]a", r"\bdado\b",
        r"100% off", r"90% off", r"desconto absurdo", r"\bpre[çc]o vil\b",
    ],
    "negativas": [
        r"\besgotado\b", r"\bacabou\b", r"\bencerrou\b",
        r"\bfinalizado\b", r"\bsem estoque\b", r"\bfoi se\b",
    ],
    "alvos_preco": {},
    "alvos_compostos": [],
    "desconto_minimo": 65.0,
}

STOPWORDS_CUPOM = {
    "NO", "NA", "NOS", "NAS", "DO", "DA", "DOS", "DAS", "DE", "EM", "UM", "UMA",
    "COM", "POR", "PARA", "PRA", "QUE", "SEU", "SUA", "AQUI", "LINK", "SITE", "APP",
    "LOJA", "HOJE", "AGORA", "ABAIXO", "ACIMA", "FOTO", "IMAGEM", "ATIVAR", "ATIVE",
    "RESGATAR", "RESGATE", "APLICAR", "APLICADO", "AUTOMATICAMENTE", "AUTOMATICO",
    "SELECIONAR", "SELECIONE", "DISPONIVEL", "PAGINA", "ANUNCIO", "CLIQUE", "PEGUE",
    "USE", "OFF", "REAIS", "DESCONTO", "CUPOM", "CODIGO", "VALOR", "FRETE", "GRATIS",
    "PRIME", "PIX", "CARTAO", "CARRINHO", "PAGAMENTO", "PRODUTO", "OFERTA", "PROMO",
    "PROMOCAO",
}

ENCURTADORES_E_LOJAS = (
    "amzn.to", "a.co", "amazon.",
    "meli.la", "mercadolivre.",
    "s.shopee.", "shp.ee", "shopee.",
    "divulgador.magalu.", "parceiro.magalu.", "magazineluiza.", "magalu.",
    "kabum.", "tidd.ly", "awin1.",
    "s.click.aliexpress.", "a.aliexpress.", "aliexpress.",
    "bit.ly", "tinyurl.com", "cutt.ly", "is.gd", "bityli.com", "ofertou.com",
)

PARAMS_TRACKING = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "fbclid", "gclid", "dclid", "msclkid", "ref", "ref_", "tag", "linkcode",
    "camp", "creative", "creativeasin", "psc", "th", "matt_tool", "matt_word",
    "matt_source", "matt_campaign_id", "matt_ad_group_id", "matt_match_type",
    "matt_network", "matt_device", "matt_creative", "matt_keyword", "matt_ad_id",
    "matt_ad_position", "matt_placement", "pdp_filters", "searchvariation",
    "position", "search_layout", "type", "tracking_id", "is_from_login",
    "sp_atk", "xptdk", "spm", "aff_fcid", "aff_fsk", "aff_platform", "sk",
    "partner_id", "seller_id",
}

PARAMS_REDIRECT = ("url", "u", "redir", "redirect", "target", "ued", "destination")

REGEX_CUPOM = re.compile(
    r"(?i)\b(cupom|c[oó]digo|c[oó]d\.?|voucher)"
    r"(?:\s+(?:de\s+desconto|promocional|exclusivo|vip))?"
    r"(?:[\s:=\-👇👉⬇️➡️🎟️🏷️*`\"'\r\n]+)"
    r"([A-Za-z0-9][A-Za-z0-9_-]{2,24})"
)

REGEX_ASIN_AMAZON = re.compile(
    r"(?:/dp/|/gp/product/|/gp/aw/d/|/aw/d/|/ASIN/|/product/)([A-Z0-9]{10})(?:[/?#]|$)",
    re.IGNORECASE,
)


def configurar_logger(caminho_log=ARQUIVO_LOG):
    """Configura logs no console e em arquivo rotativo."""
    logger_obj = logging.getLogger("bot_bugs")
    if logger_obj.handlers:
        return logger_obj

    logger_obj.setLevel(logging.INFO)
    os.makedirs(os.path.dirname(caminho_log), exist_ok=True)
    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        caminho_log, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formato)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formato)

    logger_obj.addHandler(file_handler)
    logger_obj.addHandler(stream_handler)
    return logger_obj


logger = configurar_logger()


def carregar_env(caminho_env=ARQUIVO_ENV):
    """Carrega variáveis de um arquivo .env para os.environ sem sobrescrever existentes."""
    if not os.path.exists(caminho_env):
        return False
    with open(caminho_env, "r", encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            chave = chave.strip()
            valor = valor.strip().strip('"').strip("'")
            if chave:
                os.environ.setdefault(chave, valor)
    return True


def carregar_configuracoes(caminho_env=ARQUIVO_ENV):
    """Lê e valida as credenciais e parâmetros do ambiente."""
    carregar_env(caminho_env)
    obrigatorias = ("API_ID", "API_HASH", "BOT_TOKEN", "MEU_CHAT_ID")
    faltantes = [k for k in obrigatorias if not os.environ.get(k)]
    if faltantes:
        raise RuntimeError(
            f"Variáveis obrigatórias ausentes no .env: {', '.join(faltantes)}"
        )

    return {
        "API_ID": int(os.environ["API_ID"]),
        "API_HASH": os.environ["API_HASH"],
        "BOT_TOKEN": os.environ["BOT_TOKEN"],
        "MEU_CHAT_ID": int(os.environ["MEU_CHAT_ID"]),
        "URL_MACRODROID": os.environ.get("URL_MACRODROID", "").strip(),
        "TEMPO_DE_ESPERA": int(os.environ.get("TEMPO_DE_ESPERA", "15")),
        "TEMPO_DUPLICATA": int(os.environ.get("TEMPO_DUPLICATA", "900")),
        "DESCONTO_MINIMO_AUTO": float(os.environ.get("DESCONTO_MINIMO_AUTO", "65")),
    }


def carregar_dados(caminho_json=ARQUIVO_JSON, desconto_padrao=None):
    """Carrega e migra o banco JSON preservando dados existentes."""
    if desconto_padrao is None:
        desconto_padrao = float(os.environ.get("DESCONTO_MINIMO_AUTO", DADOS_PADRAO["desconto_minimo"]))

    if os.path.exists(caminho_json):
        with open(caminho_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
        alterado = False
        for chave, valor_padrao in DADOS_PADRAO.items():
            if chave not in dados:
                dados[chave] = desconto_padrao if chave == "desconto_minimo" else copy.deepcopy(valor_padrao)
                alterado = True
        if alterado:
            salvar_dados(dados, caminho_json)
        return dados

    dados = copy.deepcopy(DADOS_PADRAO)
    dados["desconto_minimo"] = desconto_padrao
    return dados


def salvar_dados(dados, caminho_json=ARQUIVO_JSON):
    """Salva o banco JSON de forma atômica para evitar corrupção."""
    pasta = os.path.dirname(os.path.abspath(caminho_json))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    caminho_tmp = f"{caminho_json}.tmp"
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)
    os.replace(caminho_tmp, caminho_json)


def regex_valida(padrao):
    """Valida se uma expressão regular compila sem erro."""
    try:
        re.compile(padrao, re.IGNORECASE)
        return True, None
    except re.error as err:
        return False, str(err)


def match_padrao(padrao, texto):
    """Busca por regex (ou literal se a regex for inválida) ignorando maiúsculas."""
    try:
        return re.search(padrao, texto, re.IGNORECASE) is not None
    except re.error:
        return padrao.lower() in texto.lower()


def parse_numero_br(numero_sujo):
    """Converte string monetária BR/US (ex: '1.299,90' ou '199.90') para float."""
    limpo = numero_sujo.strip(" .,\t\n\r")
    if not limpo or not any(ch.isdigit() for ch in limpo):
        return None

    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif "." in limpo:
        partes = limpo.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
            limpo = limpo.replace(".", "")

    try:
        valor = float(limpo)
        return valor if valor > 0 else None
    except ValueError:
        return None


def _eh_contexto_ignorado(contexto_antes, contexto_depois):
    """Identifica se o valor monetário é parcela, cupom, frete ou cashback."""
    if re.search(r"(?:\b\d+\s*x\s*(?:de\s*)?|\bparcela\w*\s*(?:de\s*)?)$", contexto_antes, re.IGNORECASE):
        return True
    if re.search(
        r"(?:cupom|desconto|economize|economiza|ganhe|cashback|frete|acima\s+de|m[ií]nimo(?:\s+de)?|off\s+em)\s*(?:de\s*)?$",
        contexto_antes,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"^\s*(?:off\b|de\s+desconto|de\s+cashback|em\s+cupom|de\s+economia)",
        contexto_depois,
        re.IGNORECASE,
    ):
        return True
    return False


def _eh_preco_antigo(contexto_antes):
    """Verifica se o preço está marcado como valor anterior ('de R$', '~~R$', etc.)."""
    return bool(
        re.search(r"(?:\b(?:de|antes|era|custava)\s*:?\s*~{0,2}|~~\s*|[❌🔴]\s*)$", contexto_antes, re.IGNORECASE)
    )


def extrair_preco(texto):
    """Extrai o menor preço atual válido, ignorando parcelas, descontos e 'de R$' quando há preço atual."""
    atuais = []
    todos_validos = []

    for match in re.finditer(r"r\$\s*([\d\.,]+)", texto, re.IGNORECASE):
        valor = parse_numero_br(match.group(1))
        if valor is None:
            continue
        inicio, fim = match.span()
        antes = texto[max(0, inicio - 30):inicio]
        depois = texto[fim:min(len(texto), fim + 25)]

        if _eh_contexto_ignorado(antes, depois):
            continue

        todos_validos.append(valor)
        if not _eh_preco_antigo(antes):
            atuais.append(valor)

    if atuais:
        return min(atuais)
    if todos_validos:
        return min(todos_validos)
    return None


def detectar_desconto_real(texto, desconto_minimo):
    """Detecta queda real em padrões 'De R$ X por R$ Y' e retorna (pct, de, por) se >= mínimo."""
    if not desconto_minimo or desconto_minimo <= 0:
        return None

    padroes = [
        r"(?i)\b(?:de|antes|era|custava)\s*:?\s*~{0,2}r\$\s*([\d\.,]+)~{0,2}[\s\S]{0,80}?\b(?:por|agora|sai(?:\s+a|\s+por)?|apenas|s[óo]|hoje)\s*:?\s*r\$\s*([\d\.,]+)",
        r"(?i)~~\s*r\$\s*([\d\.,]+)\s*~~[\s\S]{0,80}?r\$\s*([\d\.,]+)",
        r"(?i)[❌🔴]\s*r\$\s*([\d\.,]+)[\s\S]{0,80}?[✅🟢🔥]\s*r\$\s*([\d\.,]+)",
    ]

    melhor = None
    for padrao in padroes:
        for match in re.finditer(padrao, texto):
            preco_de = parse_numero_br(match.group(1))
            preco_por = parse_numero_br(match.group(2))
            if not preco_de or not preco_por or preco_por >= preco_de:
                continue

            pos_por = match.start(2)
            fim_por = match.end(2)
            antes_por = texto[max(0, pos_por - 25):pos_por]
            depois_por = texto[fim_por:min(len(texto), fim_por + 25)]
            if _eh_contexto_ignorado(antes_por, depois_por):
                continue

            pct = ((preco_de - preco_por) / preco_de) * 100.0
            if pct >= desconto_minimo and (melhor is None or pct > melhor[0]):
                melhor = (pct, preco_de, preco_por)

    return melhor


def extrair_cupons(texto):
    """Extrai códigos de cupom mesmo em quebras de linha ou após 'código:'."""
    cupons = []
    vistos = set()

    for match in REGEX_CUPOM.finditer(texto):
        codigo = match.group(2).strip("`*_\"'.,;:!?-")
        if len(codigo) < 3:
            continue
        chave = codigo.upper()
        if chave in STOPWORDS_CUPOM or chave in vistos:
            continue
        vistos.add(chave)
        cupons.append(codigo)

    return cupons


def formatar_texto_alerta_html(texto_bruto, cupons):
    """Escapa HTML do post e destaca os cupons encontrados em <code> para cópia com 1 toque."""
    texto_seguro = html.escape(texto_bruto)
    for cupom in sorted(cupons, key=len, reverse=True):
        cupom_escapado = html.escape(cupom)
        texto_seguro = re.sub(
            rf"(?<![A-Za-z0-9_-])({re.escape(cupom_escapado)})(?![A-Za-z0-9_-])",
            r"<code>\1</code>",
            texto_seguro,
            flags=re.IGNORECASE,
        )
    return texto_seguro


def limpar_parametros_url(url):
    """Remove parâmetros de rastreamento/afiliado mantendo parâmetros funcionais."""
    try:
        parsed = urllib.parse.urlparse(url)
        query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        limpos = [(k, v) for k, v in query_items if k.lower() not in PARAMS_TRACKING]
        nova_query = urllib.parse.urlencode(limpos)
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", nova_query, ""))
    except Exception:
        return url


def limpar_link(url):
    """Retorna host + path normalizados para chave de deduplicação."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.rstrip("/")
        return f"{host}{path}"
    except Exception:
        return url


def _desembrulhar_query_redirect(url):
    """Extrai URL de destino quando vem em query params como ?url= ou ?redir=."""
    atual = url
    for _ in range(3):
        parsed = urllib.parse.urlparse(atual)
        params = urllib.parse.parse_qs(parsed.query)
        proxima = None
        for chave in PARAMS_REDIRECT:
            if chave in params and params[chave]:
                candidata = params[chave][0].strip()
                if candidata.startswith(("http://", "https://")):
                    proxima = candidata
                    break
        if not proxima or proxima == atual:
            break
        atual = proxima
    return atual


def _extrair_url_de_html(conteudo_html, url_atual):
    """Busca redirecionamento meta refresh ou link de produto ML em página intermediária."""
    meta = re.search(
        r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\'][^"\']*url=([^"\'>\s]+)',
        conteudo_html,
        re.IGNORECASE,
    )
    if meta:
        destino = html.unescape(meta.group(1)).strip()
        return urllib.parse.urljoin(url_atual, destino)

    if "mercadolivre.com" in url_atual.lower():
        ml_link = re.search(
            r'https://(?:produto|www)\.mercadolivre\.com\.br/[^\s"\'<>]*MLB-?\d{6,14}[^\s"\'<>]*',
            conteudo_html,
            re.IGNORECASE,
        )
        if ml_link:
            return html.unescape(ml_link.group(0))

    return None


def _url_bloqueio_ou_login(url):
    """Evita substituir um link funcional por página de login/captcha após redirect."""
    lower = url.lower()
    return any(
        termo in lower
        for termo in ("login.", "passport.", "/login", "captcha", "verify", "universal-link", "about:blank")
    )


def expandir_link(url, timeout=4):
    """Expande encurtadores (Amazon, ML, Shopee, Magalu, Kabum, AliExpress) seguindo redirects."""
    url_inicial = _desembrulhar_query_redirect(url)
    host = urllib.parse.urlparse(url_inicial).netloc.lower()

    precisa_expandir = any(dom in host for dom in ENCURTADORES_E_LOJAS) or len(url_inicial) < 45
    if not precisa_expandir:
        return url_inicial

    url_final = url_inicial
    url_atual = url_inicial
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"}

    for metodo in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url_atual, headers=headers, method=metodo)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                candidata = _desembrulhar_query_redirect(resp.geturl())
                if not _url_bloqueio_ou_login(candidata):
                    url_final = candidata
                    url_atual = candidata

                if metodo == "GET":
                    body = resp.read(65536).decode("utf-8", errors="ignore")
                    extraida = _extrair_url_de_html(body, url_final)
                    if extraida and not _url_bloqueio_ou_login(extraida):
                        url_final = _desembrulhar_query_redirect(extraida)
                if metodo == "HEAD" and identificar_produto(url_final)["produto_id"]:
                    break
                if metodo == "HEAD" and url_final == url_inicial:
                    continue
                break
        except urllib.error.HTTPError as err:
            try:
                url_erro = _desembrulhar_query_redirect(err.geturl())
                if url_erro and not _url_bloqueio_ou_login(url_erro):
                    url_final = url_erro
                    url_atual = url_erro
            except Exception:
                pass
            finally:
                codigo = err.code
                err.close()
            if identificar_produto(url_final)["produto_id"]:
                break
            if metodo == "HEAD" and codigo in (400, 403, 405, 501):
                continue
            break
        except Exception:
            if metodo == "HEAD":
                continue
            break

    return url_final


def _extrair_asin_amazon(url):
    """Extrai o código ASIN (10 caracteres) de uma URL da Amazon."""
    match = REGEX_ASIN_AMAZON.search(url)
    return match.group(1).upper() if match else None


def obter_carrinho_amazon(url_real):
    """Extrai o ASIN de um link Amazon e retorna a URL de adição direta ao carrinho."""
    asin = _extrair_asin_amazon(url_real)
    if asin:
        return f"https://www.amazon.com.br/gp/aws/cart/add.html?ASIN.1={asin}&Quantity.1=1"
    return None


def identificar_produto(url):
    """Identifica loja, ID único para deduplicação, link limpo e carrinho Amazon."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    link_limpo = limpar_parametros_url(url)
    resultado = {"loja": None, "produto_id": None, "link_limpo": link_limpo, "carrinho_amazon": None}

    if "amazon." in host:
        resultado["loja"] = "Amazon"
        asin = _extrair_asin_amazon(url)
        if asin:
            resultado["produto_id"] = f"amazon:{asin}"
            resultado["link_limpo"] = f"https://www.amazon.com.br/dp/{asin}"
            resultado["carrinho_amazon"] = obter_carrinho_amazon(resultado["link_limpo"])
        return resultado

    if "mercadolivre." in host:
        resultado["loja"] = "Mercado Livre"
        match = re.search(r"\b(MLB)-?(\d{6,14})\b", path, re.IGNORECASE) or re.search(
            r"\b(MLB)-?(\d{6,14})\b", url, re.IGNORECASE
        )
        if match:
            resultado["produto_id"] = f"ml:MLB{match.group(2)}"
        return resultado

    if "shopee." in host:
        resultado["loja"] = "Shopee"
        match = re.search(r"(?:-i\.(\d+)\.(\d+)|/product/(\d+)/(\d+))", url, re.IGNORECASE)
        if match:
            shop_id = match.group(1) or match.group(3)
            item_id = match.group(2) or match.group(4)
            resultado["produto_id"] = f"shopee:{shop_id}.{item_id}"
            resultado["link_limpo"] = f"https://shopee.com.br/product/{shop_id}/{item_id}"
        return resultado

    if "kabum." in host:
        resultado["loja"] = "Kabum"
        match = re.search(r"/produto/(\d+)", path, re.IGNORECASE)
        if match:
            resultado["produto_id"] = f"kabum:{match.group(1)}"
        return resultado

    if "magazineluiza." in host or "magalu." in host:
        resultado["loja"] = "Magalu"
        match = re.search(r"/p/([a-zA-Z0-9]+)", path, re.IGNORECASE)
        if match:
            resultado["produto_id"] = f"magalu:{match.group(1).lower()}"
        return resultado

    if "aliexpress." in host:
        resultado["loja"] = "AliExpress"
        match = re.search(r"/item/(\d+)\.html", path, re.IGNORECASE)
        if match:
            item_id = match.group(1)
            resultado["produto_id"] = f"aliexpress:{item_id}"
            resultado["link_limpo"] = f"https://pt.aliexpress.com/item/{item_id}.html"
        return resultado

    return resultado


def extrair_links_mensagem(raw_text, entities=None):
    """Extrai links de entidades TextUrl e do texto bruto preservando a ordem sem duplicar."""
    links = []
    vistos = set()

    def adicionar(url):
        if not url:
            return
        url_limpa = url.strip().rstrip(".,;)")
        if url_limpa.startswith(("http://", "https://")) and url_limpa not in vistos:
            vistos.add(url_limpa)
            links.append(url_limpa)

    if entities:
        for entity in entities:
            if isinstance(entity, MessageEntityTextUrl):
                adicionar(entity.url)

    for url in re.findall(r'https?://[^\s<>"\'\)\]]+', raw_text or ""):
        adicionar(url)

    return links


def escolher_link_oferta(links):
    """Prioriza links de lojas em vez de convites de Telegram/WhatsApp."""
    dominios_sociais = ("t.me/", "telegram.me/", "wa.me/", "chat.whatsapp.com/")
    for link in links:
        lower = link.lower()
        if not any(soc in lower for soc in dominios_sociais):
            return link
    return links[0] if links else None


def url_valida_botao(url):
    """Garante que a URL é válida para uso em Button.url no Telegram."""
    if not url or " " in url:
        return False
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def avaliar_gatilhos(texto_bruto, banco):
    """Avalia bloqueios negativos, palavras-chave, alvos compostos, tetos simples e desconto real."""
    for neg in banco.get("negativas", []):
        if match_padrao(neg, texto_bruto):
            return False, f"Bloqueio negativo ({neg})"

    for palavra in banco.get("palavras", []):
        if match_padrao(palavra, texto_bruto):
            return True, f"Palavra-Chave ({palavra})"

    preco_encontrado = extrair_preco(texto_bruto)

    for alvo in banco.get("alvos_compostos", []):
        nome = alvo.get("nome", "combo")
        incluir = alvo.get("incluir", [])
        excluir = alvo.get("excluir", [])
        teto = alvo.get("teto")

        if not incluir or not all(match_padrao(termo, texto_bruto) for termo in incluir):
            continue
        if any(match_padrao(termo, texto_bruto) for termo in excluir):
            continue
        if teto is not None and teto > 0:
            if preco_encontrado is None or preco_encontrado > float(teto):
                continue
            return True, f"Combo ({nome} por R$ {preco_encontrado:.2f})"
        return True, f"Combo ({nome})"

    if preco_encontrado is not None:
        for produto, preco_teto in banco.get("alvos_preco", {}).items():
            if match_padrao(produto, texto_bruto) and preco_encontrado <= float(preco_teto):
                return True, f"Teto Atingido ({produto} por R$ {preco_encontrado:.2f})"

    desconto_min = float(banco.get("desconto_minimo", 0) or 0)
    desconto = detectar_desconto_real(texto_bruto, desconto_min)
    if desconto is not None:
        pct, preco_de, preco_por = desconto
        return True, f"Queda Real de {pct:.0f}% (De R$ {preco_de:.2f} por R$ {preco_por:.2f})"

    return False, "Sem gatilho correspondente"


def parsear_comando_composto(argumento):
    """
    Faz parsing de:
      nome | incluir1 + incluir2 | excluir1 + excluir2 | valor
    ou (sem exclusões):
      nome | incluir1 + incluir2 | valor
    """
    partes = [p.strip() for p in argumento.split("|")]
    if len(partes) not in (3, 4):
        raise ValueError("Formato inválido")

    nome = partes[0].lower()
    incluir = [x.strip() for x in re.split(r"[+,]", partes[1]) if x.strip()]
    if not nome or not incluir:
        raise ValueError("Nome ou termos obrigatórios vazios")

    if len(partes) == 4:
        excluir = [x.strip() for x in re.split(r"[+,]", partes[2]) if x.strip()]
        teto_str = partes[3]
    else:
        excluir = []
        teto_str = partes[2]

    teto = parse_numero_br(re.sub(r"(?i)r\$", "", teto_str).strip())
    if teto is None:
        raise ValueError("Valor numérico inválido")

    for termo in incluir + excluir:
        valida, erro = regex_valida(termo)
        if not valida:
            raise ValueError(f"Regex inválida em '{termo}': {erro}")

    return {"nome": nome, "incluir": incluir, "excluir": excluir, "teto": teto}


def montar_chave_duplicata(info_produto, link_referencia, motivo, texto_bruto):
    """Define a chave única de deduplicação priorizando o ID real do produto."""
    if info_produto and info_produto.get("produto_id"):
        return info_produto["produto_id"]
    if link_referencia:
        return limpar_link(link_referencia)
    if "Teto Atingido" in motivo or "Combo" in motivo:
        return motivo
    return (texto_bruto or "")[:60].strip().lower()


def montar_mensagem_e_botoes(
    nome_grupo,
    motivo_disparo,
    texto_bruto,
    cupons,
    info_produto,
    link_oferta,
    link_origem,
    links_extras=None,
    texto_recuperado=None,
):
    """Monta a mensagem HTML (com cupom no topo) e botões grandes Button.url."""
    linhas = ["🚨 <b>ALERTA DE PROMOÇÃO!</b> 🚨"]

    if cupons:
        cupons_html = " ".join(f"<code>{html.escape(c)}</code>" for c in cupons)
        linhas.append(f"🎟️ <b>Cupom(ns):</b> {cupons_html}")

    linhas.append(f"📢 <b>Grupo:</b> {html.escape(nome_grupo)}")
    if info_produto and info_produto.get("loja"):
        linhas.append(f"🏪 <b>Loja:</b> {html.escape(info_produto['loja'])}")
    linhas.append(f"🎯 <i>Motivo: {html.escape(motivo_disparo)}</i>")
    linhas.append("")
    linhas.append(formatar_texto_alerta_html(texto_bruto, cupons))

    if texto_recuperado:
        linhas.append("")
        linhas.append("🕰️ <b>[RECUPERADO DA MENSAGEM ANTERIOR]:</b>")
        linhas.append(formatar_texto_alerta_html(texto_recuperado, cupons))

    links_visiveis = []
    for lk in [link_oferta] + list(links_extras or []):
        if lk and lk not in links_visiveis:
            links_visiveis.append(lk)

    if links_visiveis:
        linhas.append("")
        linhas.append("🔗 <b>Link(s):</b>")
        for lk in links_visiveis[:5]:
            linhas.append(html.escape(lk))

    mensagem = "\n".join(linhas)
    if len(mensagem) > 4000:
        mensagem = mensagem[:3990] + "\n..."

    botoes = []
    if url_valida_botao(link_oferta):
        botoes.append([Button.url("🔥 Abrir Oferta", link_oferta)])
    if info_produto and url_valida_botao(info_produto.get("carrinho_amazon")):
        botoes.append([Button.url("🛒 Carrinho Amazon", info_produto["carrinho_amazon"])])
    if url_valida_botao(link_origem):
        botoes.append([Button.url("📢 Ver Post Original", link_origem)])

    return mensagem, (botoes or None)


def disparar_macrodroid(url_macrodroid, link_oferta, timeout=5):
    """Envia POST síncrono ao MacroDroid (chamado via asyncio.to_thread)."""
    req = urllib.request.Request(
        url_macrodroid,
        data=link_oferta.encode("utf-8"),
        headers={"User-Agent": USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


async def enviar_em_partes(event, texto, parse_mode="html"):
    """Envia mensagens longas dividindo por linhas para respeitar o limite do Telegram."""
    if len(texto) <= 4000:
        await event.reply(texto, parse_mode=parse_mode)
        return

    bloco = ""
    for linha in texto.splitlines(keepends=True):
        if len(bloco) + len(linha) > 3900:
            await event.reply(bloco, parse_mode=parse_mode)
            bloco = ""
        bloco += linha
    if bloco:
        await event.reply(bloco, parse_mode=parse_mode)


def _gerenciar_lista_regex(banco, chave, adicionar, argumento, nome_singular):
    """Adiciona ou remove expressões em 'palavras' ou 'negativas' com validação de regex."""
    if adicionar:
        valida, erro = regex_valida(argumento)
        if not valida:
            return f"⚠️ Expressão inválida: <code>{html.escape(erro)}</code>"
        if argumento in banco[chave]:
            return f"ℹ️ {nome_singular} já existe na lista."
        banco[chave].append(argumento)
        salvar_dados(banco)
        return f"✅ <code>{html.escape(argumento)}</code> adicionada!"

    if argumento not in banco[chave]:
        return f"⚠️ {nome_singular} não encontrada."
    banco[chave].remove(argumento)
    salvar_dados(banco)
    return f"🗑️ <code>{html.escape(argumento)}</code> removida!"


def _formatar_lista_painel(banco, estado):
    """Monta a resposta do comando /lista."""
    txt_canais = "\n".join(html.escape(c) for c in banco["canais"]) or "Nenhum"
    txt_palavras = "\n".join(html.escape(p) for p in banco["palavras"]) or "Nenhuma"
    txt_negativas = "\n".join(html.escape(n) for n in banco["negativas"]) or "Nenhuma"

    if banco.get("alvos_preco"):
        txt_tetos = "\n".join(
            f"🎯 <b>{html.escape(k)}</b>: até R$ {v:.2f}"
            for k, v in banco["alvos_preco"].items()
        )
    else:
        txt_tetos = "Nenhum limite simples configurado."

    if banco.get("alvos_compostos"):
        linhas_comp = []
        for c in banco["alvos_compostos"]:
            inc = " + ".join(c["incluir"])
            exc = f" | sem: {', '.join(c['excluir'])}" if c.get("excluir") else ""
            teto_txt = f"≤ R$ {float(c['teto']):.2f}" if c.get("teto") else "sem teto"
            linhas_comp.append(
                f"🧩 <b>{html.escape(c['nome'])}</b>: [{html.escape(inc)}{html.escape(exc)}] ({teto_txt})"
            )
        txt_compostos = "\n".join(linhas_comp)
    else:
        txt_compostos = "Nenhum alvo composto configurado."

    desc = float(banco.get("desconto_minimo", 0) or 0)
    txt_desc = f"{desc:.0f}%" if desc > 0 else "Desativado"
    status_txt = "⏸️ Pausado" if estado["pausado"] else "✅ Ativo"

    return (
        f"⚙️ <b>Status:</b> {status_txt} | <b>Desconto Auto:</b> {txt_desc}\n\n"
        f"📡 <b>Canais e Grupos ({len(banco['canais'])}):</b>\n{txt_canais}\n\n"
        f"🔑 <b>Palavras-Chave ({len(banco['palavras'])}):</b>\n{txt_palavras}\n\n"
        f"📉 <b>Tetos Simples ({len(banco['alvos_preco'])}):</b>\n{txt_tetos}\n\n"
        f"🧩 <b>Tetos Compostos ({len(banco['alvos_compostos'])}):</b>\n{txt_compostos}\n\n"
        f"⛔ <b>Bloqueios ({len(banco['negativas'])}):</b>\n{txt_negativas}"
    )


async def processar_comando_painel(event, banco, cfg, estado):
    """Processa comandos administrativos enviados no chat do bot."""
    cmd_full = (event.raw_text or "").strip()
    if not cmd_full.startswith("/"):
        return

    partes = cmd_full.split(" ", 1)
    comando = partes[0].lower()
    argumento = partes[1].strip() if len(partes) > 1 else ""
    logger.info("Comando recebido no painel: %s", cmd_full)

    if comando == "/ajuda":
        msg = (
            "🤖 <b>Comandos Disponíveis</b>\n\n"
            "• <code>/lista</code> — Exibe canais, palavras, bloqueios, tetos e desconto\n"
            "• <code>/addcanal @canal</code> | <code>/delcanal @canal</code>\n"
            "• <code>/addpalavra termo</code> | <code>/delpalavra termo</code>\n"
            "• <code>/addbloqueio termo</code> | <code>/delbloqueio termo</code>\n"
            "• <code>/addteto item, valor</code> | <code>/delteto item</code>\n"
            "• <code>/addcomposto nome | ter1 + ter2 | ex1, ex2 | valor</code>\n"
            "• <code>/delcomposto nome</code>\n"
            "• <code>/setdesconto 65</code> (0 desativa detecção automática de %)\n"
            "• <code>/status</code> | <code>/pausar</code> | <code>/retomar</code>\n"
            "• <code>/getid</code> (envie no grupo alvo com sua conta)"
        )
        await event.reply(msg, parse_mode="html")
    elif comando == "/lista":
        await enviar_em_partes(event, _formatar_lista_painel(banco, estado), parse_mode="html")
    elif comando == "/status":
        uptime_min = int((time.time() - estado["inicio"]) // 60)
        status_txt = "⏸️ Pausado" if estado["pausado"] else "✅ Ativo"
        await event.reply(
            f"📊 <b>Status do Caçador</b>\n"
            f"• Estado: {status_txt}\n"
            f"• Tempo ativo: {uptime_min} min\n"
            f"• Alertas enviados: {estado['alertas_enviados']}\n"
            f"• Canais monitorados: {len(banco['canais'])}\n"
            f"• Desconto mínimo auto: {banco.get('desconto_minimo', 0)}%\n"
            f"• MacroDroid: {'Configurado' if cfg['URL_MACRODROID'] else 'Desativado'}",
            parse_mode="html",
        )
    elif comando == "/pausar":
        estado["pausado"] = True
        await event.reply("⏸️ Monitoramento pausado. Envie <code>/retomar</code> para voltar.", parse_mode="html")
    elif comando == "/retomar":
        estado["pausado"] = False
        await event.reply("▶️ Monitoramento retomado!", parse_mode="html")
    elif comando == "/addcanal" and argumento:
        novo = argumento.lower()
        if not novo.startswith("@") and not novo.lstrip("-").isdigit():
            novo = f"@{novo}"
        if novo not in [c.lower() for c in banco["canais"]]:
            banco["canais"].append(novo)
            salvar_dados(banco)
            await event.reply(f"✅ Alvo <code>{html.escape(novo)}</code> adicionado!", parse_mode="html")
        else:
            await event.reply(f"ℹ️ <code>{html.escape(novo)}</code> já está na lista.", parse_mode="html")
    elif comando == "/delcanal" and argumento:
        remover = argumento.lower()
        if not remover.startswith("@") and not remover.lstrip("-").isdigit():
            remover = f"@{remover}"
        encontrado = next((c for c in banco["canais"] if c.lower() == remover), None)
        if encontrado:
            banco["canais"].remove(encontrado)
            salvar_dados(banco)
            await event.reply(f"🗑️ <code>{html.escape(encontrado)}</code> removido!", parse_mode="html")
        else:
            await event.reply(f"⚠️ <code>{html.escape(remover)}</code> não encontrado.", parse_mode="html")
    elif comando in ("/addpalavra", "/delpalavra") and argumento:
        resp = _gerenciar_lista_regex(banco, "palavras", comando == "/addpalavra", argumento, "Palavra")
        await event.reply(resp, parse_mode="html")
    elif comando in ("/addbloqueio", "/delbloqueio") and argumento:
        resp = _gerenciar_lista_regex(banco, "negativas", comando == "/addbloqueio", argumento, "Bloqueio")
        await event.reply(resp, parse_mode="html")
    elif comando == "/addteto" and argumento:
        try:
            produto, preco_str = [x.strip() for x in argumento.rsplit(",", 1)]
            preco = parse_numero_br(re.sub(r"(?i)r\$", "", preco_str).strip())
            valida, erro = regex_valida(produto)
            if not valida:
                await event.reply(f"⚠️ Padrão inválido: <code>{html.escape(erro)}</code>", parse_mode="html")
                return
            if preco is None:
                raise ValueError("Preço inválido")
            banco["alvos_preco"][produto.lower()] = preco
            salvar_dados(banco)
            await event.reply(
                f"🎯 <b>Teto adicionado!</b> Disparo para <b>{html.escape(produto)}</b> até <b>R$ {preco:.2f}</b>",
                parse_mode="html",
            )
        except Exception:
            await event.reply(
                "⚠️ <b>Formato incorreto!</b>\nUse: <code>/addteto nome da peça, valor</code>",
                parse_mode="html",
            )
    elif comando == "/delteto" and argumento:
        alvo = argumento.lower().strip()
        if alvo in banco["alvos_preco"]:
            del banco["alvos_preco"][alvo]
            salvar_dados(banco)
            await event.reply(f"🗑️ Teto para <code>{html.escape(alvo)}</code> removido!", parse_mode="html")
        else:
            await event.reply("⚠️ Teto não encontrado.")
    elif comando == "/addcomposto" and argumento:
        try:
            composto = parsear_comando_composto(argumento)
            banco["alvos_compostos"] = [
                c for c in banco["alvos_compostos"] if c.get("nome") != composto["nome"]
            ]
            banco["alvos_compostos"].append(composto)
            salvar_dados(banco)
            exc_txt = ", ".join(composto["excluir"]) if composto["excluir"] else "nenhuma"
            await event.reply(
                f"🧩 <b>Alvo composto salvo!</b>\n"
                f"• Nome: <b>{html.escape(composto['nome'])}</b>\n"
                f"• Exige: <code>{html.escape(' + '.join(composto['incluir']))}</code>\n"
                f"• Exclui: <code>{html.escape(exc_txt)}</code>\n"
                f"• Teto: <b>R$ {composto['teto']:.2f}</b>",
                parse_mode="html",
            )
        except Exception as err:
            await event.reply(
                f"⚠️ <b>Formato incorreto</b> ({html.escape(str(err))}).\n"
                "Use: <code>/addcomposto ram16 | 16gb + ddr4 | notebook, sodimm | 220</code>\n"
                "Ou sem exclusões: <code>/addcomposto ram16 | 16gb + ddr4 | 220</code>",
                parse_mode="html",
            )
    elif comando == "/delcomposto" and argumento:
        alvo = argumento.lower().strip()
        antes = len(banco["alvos_compostos"])
        banco["alvos_compostos"] = [c for c in banco["alvos_compostos"] if c.get("nome") != alvo]
        if len(banco["alvos_compostos"]) < antes:
            salvar_dados(banco)
            await event.reply(f"🗑️ Alvo composto <code>{html.escape(alvo)}</code> removido!", parse_mode="html")
        else:
            await event.reply("⚠️ Alvo composto não encontrado.")
    elif comando == "/setdesconto" and argumento:
        try:
            valor = float(argumento.replace("%", "").replace(",", ".").strip())
            if valor < 0 or valor >= 100:
                raise ValueError("Percentual fora de 0..99")
            banco["desconto_minimo"] = valor
            salvar_dados(banco)
            if valor == 0:
                await event.reply("🔕 Detector automático de queda de preço desativado.")
            else:
                await event.reply(
                    f"📉 Detector automático configurado para quedas ≥ <b>{valor:.0f}%</b>.",
                    parse_mode="html",
                )
        except Exception:
            await event.reply("⚠️ Use <code>/setdesconto 65</code> (ou <code>0</code> para desativar).", parse_mode="html")


async def _resolver_link_e_produto(links_atuais, chat_id, agora, memoria_canais):
    """Obtém o link da oferta (com fallback na memória de 5 min), expande e identifica produto."""
    texto_recuperado = None
    links_combinados = list(links_atuais)
    link_oferta_bruto = escolher_link_oferta(links_combinados)

    if not link_oferta_bruto and chat_id in memoria_canais:
        memoria = memoria_canais[chat_id]
        if (agora - memoria["tempo"]) <= 300:
            texto_recuperado = memoria["raw_text"]
            for lk in memoria["links"]:
                if lk not in links_combinados:
                    links_combinados.append(lk)
            link_oferta_bruto = escolher_link_oferta(links_combinados)

    link_expandido = None
    if link_oferta_bruto:
        link_expandido = await asyncio.to_thread(expandir_link, link_oferta_bruto)

    info_produto = identificar_produto(link_expandido or link_oferta_bruto or "")
    link_para_abrir = info_produto["link_limpo"] if link_expandido else link_oferta_bruto
    return link_para_abrir, link_oferta_bruto, info_produto, links_combinados, texto_recuperado


async def main():
    cfg = carregar_configuracoes()
    banco = carregar_dados(desconto_padrao=cfg["DESCONTO_MINIMO_AUTO"])

    memoria_canais = {}
    historico_alertas = {}
    estado = {
        "ultimo_disparo": 0.0,
        "pausado": False,
        "alertas_enviados": 0,
        "inicio": time.time(),
    }

    sessao_user = os.path.join(BASE_DIR, "sessao_bot")
    sessao_bot = os.path.join(BASE_DIR, "sessao_carteiro")
    user_client = TelegramClient(sessao_user, cfg["API_ID"], cfg["API_HASH"], connection_retries=None)
    bot_client = TelegramClient(sessao_bot, cfg["API_ID"], cfg["API_HASH"], connection_retries=None)

    @bot_client.on(events.NewMessage(chats=cfg["MEU_CHAT_ID"]))
    async def painel(event):
        await processar_comando_painel(event, banco, cfg, estado)

    @user_client.on(events.NewMessage())
    async def ninja_id(event):
        if event.out and (event.raw_text or "").strip().lower() == "/getid":
            chat = await event.get_chat()
            nome = getattr(chat, "title", "Grupo/Canal")
            try:
                await event.delete()
            except Exception:
                pass
            msg = (
                f"🕵️‍♂️ <b>RAIO-X DE CHAT</b>\n\n"
                f"<b>Nome:</b> {html.escape(nome)}\n"
                f"<b>ID:</b> <code>{event.chat_id}</code>\n\n"
                f"Para monitorar, envie no bot:\n<code>/addcanal {event.chat_id}</code>"
            )
            await bot_client.send_message(cfg["MEU_CHAT_ID"], msg, parse_mode="html")

    @user_client.on(events.NewMessage())
    @user_client.on(events.MessageEdited())
    async def cacador(event):
        if estado["pausado"] or event.is_private or event.out:
            return

        texto_bruto = event.raw_text or ""
        if not texto_bruto.strip():
            return

        chat = await event.get_chat()
        chat_id = str(event.chat_id)
        username = getattr(chat, "username", None)
        canal_username = f"@{username}".lower() if username else ""
        lista_canais = [str(c).lower() for c in banco["canais"]]

        if canal_username not in lista_canais and chat_id not in lista_canais:
            return

        agora = time.time()
        links_atuais = extrair_links_mensagem(texto_bruto, event.entities)
        if links_atuais:
            memoria_canais[chat_id] = {
                "raw_text": texto_bruto,
                "links": links_atuais,
                "tempo": agora,
            }

        disparar, motivo = avaliar_gatilhos(texto_bruto, banco)
        nome_grupo = getattr(chat, "title", canal_username or chat_id)
        if not disparar:
            logger.info("Ignorado [%s]: %s | trecho=%r", nome_grupo, motivo, texto_bruto[:80])
            return

        link_para_abrir, link_bruto, info_produto, links_combinados, texto_recuperado = (
            await _resolver_link_e_produto(links_atuais, chat_id, agora, memoria_canais)
        )

        expiradas = [k for k, ts in historico_alertas.items() if (agora - ts) > cfg["TEMPO_DUPLICATA"]]
        for k in expiradas:
            del historico_alertas[k]

        chave_unica = montar_chave_duplicata(
            info_produto, link_para_abrir or link_bruto, motivo, texto_bruto
        )
        if chave_unica in historico_alertas:
            logger.info("Duplicata ignorada [%s]: chave=%s (%s)", nome_grupo, chave_unica, motivo)
            return
        historico_alertas[chave_unica] = agora

        if username:
            link_origem = f"https://t.me/{username}/{event.id}"
        else:
            chat_id_limpo = str(event.chat_id).removeprefix("-100")
            link_origem = f"https://t.me/c/{chat_id_limpo}/{event.id}"

        cupons = extrair_cupons(f"{texto_bruto}\n{texto_recuperado or ''}")
        mensagem, botoes = montar_mensagem_e_botoes(
            nome_grupo=nome_grupo,
            motivo_disparo=motivo,
            texto_bruto=texto_bruto,
            cupons=cupons,
            info_produto=info_produto,
            link_oferta=link_para_abrir,
            link_origem=link_origem,
            links_extras=links_combinados,
            texto_recuperado=texto_recuperado,
        )

        logger.info(
            "DISPARO [%s] motivo=%s chave=%s loja=%s link=%s cupons=%s",
            nome_grupo,
            motivo,
            chave_unica,
            info_produto.get("loja"),
            link_para_abrir,
            cupons,
        )

        try:
            await bot_client.send_message(
                cfg["MEU_CHAT_ID"],
                mensagem,
                parse_mode="html",
                link_preview=False,
                buttons=botoes,
            )
            estado["alertas_enviados"] += 1
        except Exception as err:
            logger.error("Erro ao enviar alerta HTML (%s); tentando texto simples.", err)
            await bot_client.send_message(
                cfg["MEU_CHAT_ID"],
                f"ALERTA [{nome_grupo}] ({motivo})\n\n{texto_bruto}\n\n{link_para_abrir or link_origem}",
                link_preview=False,
            )
            estado["alertas_enviados"] += 1

        if cfg["URL_MACRODROID"] and link_para_abrir and (agora - estado["ultimo_disparo"]) >= cfg["TEMPO_DE_ESPERA"]:
            try:
                status_http = await asyncio.to_thread(disparar_macrodroid, cfg["URL_MACRODROID"], link_para_abrir)
                estado["ultimo_disparo"] = agora
                logger.info("MacroDroid acionado (HTTP %s) com %s", status_http, link_para_abrir)
            except Exception as err:
                logger.warning("Falha ao acionar MacroDroid: %s", err)

    logger.info("✅ Sistema Definitivo v2 rodando! Monitorando %d canais.", len(banco["canais"]))
    await user_client.start()
    await bot_client.start(bot_token=cfg["BOT_TOKEN"])
    try:
        await asyncio.gather(
            user_client.run_until_disconnected(),
            bot_client.run_until_disconnected(),
        )
    finally:
        await user_client.disconnect()
        await bot_client.disconnect()
        logger.info("Clientes desconectados com segurança.")


if __name__ == "__main__":
    asyncio.run(main())
