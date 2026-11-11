import copy
import datetime
import hashlib
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_ENV = os.path.join(BASE_DIR, ".env")
ARQUIVO_JSON = os.path.join(BASE_DIR, "banco_de_dados.json")
ARQUIVO_ESTADO = os.path.join(BASE_DIR, "estado_bot.json")
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
    "desconto_critico": 75.0,
    "prioridades": {
        "teto": "alta",
        "combo": "alta",
        "palavras_altas": [
            r"\bbug\b", r"\bbugs\b", r"\bbugou\b", r"\bbugado\b",
            r"erro de pre[çc]o", r"pre[çc]o errado", r"erro de digita[çc][ãa]o",
            r"de gra[çc]a", r"100% off", r"90% off",
        ],
    },
    "nao_perturbe": {"ativo": True, "inicio": 0, "fim": 7},
    "filtros_extras": {"bloquear_usados": False, "bloquear_importacao": False},
    "resumo_hora": 21,
}

PADROES_USADOS = (
    r"\busad[oa]s?\b",
    r"\brecondicionad[oa]s?\b",
    r"\bseminov[oa]s?\b",
    r"\bopen\s*box\b",
    r"\bvitrine\b",
    r"\boutlet\b",
)

PADROES_IMPORTACAO = (
    r"compra\s+internacional",
    r"remessa\s+conforme",
    r"envio\s+internacional",
    r"enviado\s+d[aeo]\s+china",
    r"produto\s+internacional",
    r"impostos?\s+de\s+importa[çc][ãa]o",
    r"taxa\s+de\s+importa[çc][ãa]o",
)

PADROES_BUG_CRITICO = (
    r"bug",
    r"erro de pre",
    r"pre[çc]o errado",
    r"erro de digita",
    r"100% off",
    r"90% off",
    r"de gra[çc]a",
)

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
    r"(?i)(?:"
    r"\b(?:cupom|c[oó]digo|c[oó]d\.?|voucher)(?:\s+(?:de\s+desconto|promocional|exclusivo|vip))?(?:[\s:=\-👇👉⬇️➡️🎟️🏷️*`\"'\r\n]+)"
    r"|"
    r"\boff\s*[:=\-👇👉⬇️➡️🎟️🏷️][\s*`\"'\r\n]*"
    r")"
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
        "TEMPO_SILENCIO_HORAS": float(os.environ.get("TEMPO_SILENCIO_HORAS", "3")),
        "DESCONTO_MINIMO_AUTO": float(os.environ.get("DESCONTO_MINIMO_AUTO", "65")),
        "DESCONTO_CRITICO_MACRODROID": float(os.environ.get("DESCONTO_CRITICO_MACRODROID", "75")),
    }


def _salvar_json_atomico(dados, caminho_json):
    """Salva qualquer arquivo JSON de forma atômica via arquivo temporário."""
    pasta = os.path.dirname(os.path.abspath(caminho_json))
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    caminho_tmp = f"{caminho_json}.tmp"
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)
    os.replace(caminho_tmp, caminho_json)


def salvar_dados(dados, caminho_json=ARQUIVO_JSON):
    """Salva o banco principal JSON de forma atômica."""
    _salvar_json_atomico(dados, caminho_json)


def migrar_estrutura_dados(dados, desconto_padrao=65.0, desconto_critico=75.0):
    """Garante todas as chaves esperadas em dados antigos sem perder informações."""
    alterado = False
    for chave, valor_padrao in DADOS_PADRAO.items():
        if chave not in dados:
            if chave == "desconto_minimo":
                dados[chave] = desconto_padrao
            elif chave == "desconto_critico":
                dados[chave] = desconto_critico
            elif chave == "prioridades":
                palavras_existentes = dados.get("palavras", [])
                dados[chave] = {
                    "teto": "alta",
                    "combo": "alta",
                    "palavras_altas": [p for p in palavras_existentes if _eh_palavra_critica_bug(p)],
                }
            else:
                dados[chave] = copy.deepcopy(valor_padrao)
            alterado = True
        elif isinstance(valor_padrao, dict) and isinstance(dados[chave], dict) and chave in ("nao_perturbe", "filtros_extras", "prioridades"):
            for sub_k, sub_v in valor_padrao.items():
                if sub_k not in dados[chave]:
                    dados[chave][sub_k] = copy.deepcopy(sub_v)
                    alterado = True
    return dados, alterado


def carregar_dados(caminho_json=ARQUIVO_JSON, desconto_padrao=None, desconto_critico=None):
    """Carrega e migra o banco JSON preservando dados existentes."""
    if desconto_padrao is None:
        desconto_padrao = float(os.environ.get("DESCONTO_MINIMO_AUTO", DADOS_PADRAO["desconto_minimo"]))
    if desconto_critico is None:
        desconto_critico = float(os.environ.get("DESCONTO_CRITICO_MACRODROID", DADOS_PADRAO["desconto_critico"]))

    if os.path.exists(caminho_json):
        with open(caminho_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
        dados, alterado = migrar_estrutura_dados(dados, desconto_padrao, desconto_critico)
        if alterado:
            salvar_dados(dados, caminho_json)
        return dados

    dados = copy.deepcopy(DADOS_PADRAO)
    dados["desconto_minimo"] = desconto_padrao
    dados["desconto_critico"] = desconto_critico
    return dados


def _estado_padrao():
    return {
        "dedup": {},
        "ultimos": [],
        "ultimo_resumo_data": "",
        "stats_dia": {
            "data": datetime.date.today().isoformat(),
            "mensagens_lidas": 0,
            "alertas_enviados": 0,
            "duplicatas_barradas": 0,
            "bloqueios_negativos": 0,
            "bloqueios_dnd": 0,
        },
    }


def carregar_estado_persistente(caminho_estado=ARQUIVO_ESTADO):
    """Carrega histórico de deduplicação, últimos alertas e estatísticas diárias."""
    base = _estado_padrao()
    if not os.path.exists(caminho_estado):
        return base

    try:
        with open(caminho_estado, "r", encoding="utf-8") as f:
            lido = json.load(f)
    except Exception:
        return base

    agora = time.time()
    dedup_raw = lido.get("dedup", {})
    base["dedup"] = {k: float(v) for k, v in dedup_raw.items() if float(v) > agora}
    base["ultimos"] = list(lido.get("ultimos", []))[-20:]
    base["ultimo_resumo_data"] = lido.get("ultimo_resumo_data", "")

    hoje = datetime.date.today().isoformat()
    stats_lido = lido.get("stats_dia", {})
    if stats_lido.get("data") == hoje:
        for k in base["stats_dia"]:
            if k in stats_lido and k != "data":
                base["stats_dia"][k] = int(stats_lido[k])
    return base


def salvar_estado_persistente(estado_persistente, caminho_estado=ARQUIVO_ESTADO):
    """Remove entradas expiradas de dedup e salva o estado persistente atomicamente."""
    agora = time.time()
    estado_persistente["dedup"] = {
        k: v for k, v in estado_persistente.get("dedup", {}).items() if v > agora
    }
    estado_persistente["ultimos"] = estado_persistente.get("ultimos", [])[-20:]
    _salvar_json_atomico(estado_persistente, caminho_estado)


def esta_no_historico(estado_persistente, chave, agora=None):
    """Verifica se uma chave ainda está dentro da janela de bloqueio/silenciamento."""
    agora = time.time() if agora is None else agora
    expira = estado_persistente.get("dedup", {}).get(chave)
    if expira is None:
        return False
    if expira <= agora:
        del estado_persistente["dedup"][chave]
        return False
    return True


def registrar_historico(estado_persistente, chave, ttl_segundos, caminho_estado=ARQUIVO_ESTADO, agora=None):
    """Registra chave no histórico persistente com expiração configurada."""
    agora = time.time() if agora is None else agora
    estado_persistente.setdefault("dedup", {})[chave] = agora + ttl_segundos
    salvar_estado_persistente(estado_persistente, caminho_estado)


def registrar_alerta_enviado(estado_persistente, item_alerta, caminho_estado=ARQUIVO_ESTADO):
    """Adiciona item aos últimos alertas e salva o estado."""
    estado_persistente.setdefault("ultimos", []).append(item_alerta)
    salvar_estado_persistente(estado_persistente, caminho_estado)


def garantir_stats_do_dia(estado_persistente, data_hoje=None):
    """Zera contadores se mudou o dia."""
    hoje = data_hoje or datetime.date.today().isoformat()
    stats = estado_persistente.setdefault("stats_dia", {})
    if stats.get("data") != hoje:
        estado_persistente["stats_dia"] = {
            "data": hoje,
            "mensagens_lidas": 0,
            "alertas_enviados": 0,
            "duplicatas_barradas": 0,
            "bloqueios_negativos": 0,
            "bloqueios_dnd": 0,
        }
    return estado_persistente["stats_dia"]


def hash_curto_chave(chave):
    """Gera identificador curto (12 chars) para callback_data <= 64 bytes."""
    return hashlib.sha1(chave.encode("utf-8")).hexdigest()[:12]


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


def normalizar_faixa_preco(valor):
    """Converte float legado ou dict {'min', 'max'} para tupla (minimo, maximo)."""
    if isinstance(valor, dict):
        return float(valor.get("min", 0) or 0), float(valor.get("max", 0) or 0)
    return 0.0, float(valor)


def parsear_faixa_preco(texto_valor):
    """
    Aceita:
      - '1300' -> (0.0, 1300.0)
      - '400-1300' ou '400 a 1300' ou '400, 1300' -> (400.0, 1300.0)
    """
    limpo = re.sub(r"(?i)r\$", "", texto_valor).strip()
    partes = re.split(r"\s*(?:-|–|\ba\b)\s*", limpo)
    if len(partes) == 1 and "," in limpo:
        # Só separa por vírgula se parecerem dois números distintos (ex: "400, 1300")
        cand = [p.strip() for p in limpo.split(",")]
        if len(cand) == 2 and parse_numero_br(cand[0]) is not None and parse_numero_br(cand[1]) is not None:
            if len(cand[1]) != 2:  # Evita quebrar decimal tipo "1200,50"
                partes = cand

    if len(partes) == 1:
        maximo = parse_numero_br(partes[0])
        if maximo is None:
            raise ValueError("Valor máximo inválido")
        return 0.0, maximo

    if len(partes) == 2:
        minimo = parse_numero_br(partes[0])
        maximo = parse_numero_br(partes[1])
        if minimo is None or maximo is None or minimo > maximo:
            raise ValueError("Faixa mínima/máxima inválida")
        return minimo, maximo

    raise ValueError("Formato de faixa inválido")


def formatar_faixa_preco(minimo, maximo):
    """Formata faixa monetária para exibição legível."""
    if minimo and minimo > 0:
        return f"R$ {minimo:.2f} a R$ {maximo:.2f}"
    return f"até R$ {maximo:.2f}"


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


def _eh_palavra_critica_bug(padrao):
    """Distingue palavras explícitas de bug/erro de palavras genéricas de urgência."""
    lower = padrao.lower()
    return any(termo in lower for termo in PADROES_BUG_CRITICO)


def palavra_eh_alta(banco, palavra):
    """Verifica se uma palavra-chave tem prioridade alta configurada."""
    if "prioridades" in banco:
        return palavra in banco.get("prioridades", {}).get("palavras_altas", [])
    return _eh_palavra_critica_bug(palavra)


def alternar_prioridade_palavra(banco, palavra, nivel=None):
    """Alterna ou define a prioridade ('alta'/'normal') de uma palavra-chave."""
    prio = banco.setdefault(
        "prioridades",
        {"teto": "alta", "combo": "alta", "palavras_altas": []},
    )
    altas = prio.setdefault("palavras_altas", [])
    atualmente_alta = palavra in altas
    tornar_alta = (not atualmente_alta) if nivel is None else (nivel == "alta")

    if tornar_alta and palavra not in altas:
        altas.append(palavra)
    elif not tornar_alta and palavra in altas:
        altas.remove(palavra)
    return "alta" if tornar_alta else "normal"


def eh_horario_dnd(dnd_cfg, agora_dt=None):
    """Retorna True se o momento atual estiver dentro da faixa Não Perturbe."""
    if not dnd_cfg or not dnd_cfg.get("ativo"):
        return False
    agora_dt = agora_dt or datetime.datetime.now()
    hora = agora_dt.hour
    inicio = int(dnd_cfg.get("inicio", 0))
    fim = int(dnd_cfg.get("fim", 7))
    if inicio == fim:
        return False
    if inicio < fim:
        return inicio <= hora < fim
    return hora >= inicio or hora < fim


def _resultado_gatilho(
    disparar,
    motivo,
    prioridade=None,
    preco=None,
    bloqueado_por=None,
    tipo_gatilho=None,
    alvo_gatilho=None,
):
    return {
        "disparar": disparar,
        "motivo": motivo,
        "prioridade": prioridade,
        "preco": preco,
        "bloqueado_por": bloqueado_por,
        "tipo_gatilho": tipo_gatilho,
        "alvo_gatilho": alvo_gatilho,
    }


def avaliar_gatilhos(texto_bruto, banco):
    """
    Avalia bloqueios, filtros extras e gatilhos respeitando prioridades configuradas.
    Retorna dict: {disparar, motivo, prioridade, preco, bloqueado_por, tipo_gatilho, alvo_gatilho}
    """
    for neg in banco.get("negativas", []):
        if match_padrao(neg, texto_bruto):
            return _resultado_gatilho(False, f"Bloqueio negativo ({neg})", bloqueado_por="negativa")

    filtros = banco.get("filtros_extras", {})
    if filtros.get("bloquear_usados"):
        for pad in PADROES_USADOS:
            if match_padrao(pad, texto_bruto):
                return _resultado_gatilho(False, f"Filtro usado/recondicionado ({pad})", bloqueado_por="filtro_usado")

    if filtros.get("bloquear_importacao"):
        for pad in PADROES_IMPORTACAO:
            if match_padrao(pad, texto_bruto):
                return _resultado_gatilho(False, f"Filtro compra internacional ({pad})", bloqueado_por="filtro_importacao")

    preco_encontrado = extrair_preco(texto_bruto)
    prio_cfg = banco.get("prioridades", {})
    prio_combo = prio_cfg.get("combo", "alta")
    prio_teto = prio_cfg.get("teto", "alta")
    candidato_normal = None

    # 1. Alvos compostos
    for alvo in banco.get("alvos_compostos", []):
        nome = alvo.get("nome", "combo")
        incluir = alvo.get("incluir", [])
        excluir = alvo.get("excluir", [])
        teto_min = float(alvo.get("teto_min", 0) or 0)
        teto_max = alvo.get("teto")

        if not incluir or not all(match_padrao(termo, texto_bruto) for termo in incluir):
            continue
        if any(match_padrao(termo, texto_bruto) for termo in excluir):
            continue
        if teto_max is not None and float(teto_max) > 0:
            if preco_encontrado is None or preco_encontrado < teto_min or preco_encontrado > float(teto_max):
                continue
            motivo = f"Combo ({nome} por R$ {preco_encontrado:.2f})"
        else:
            motivo = f"Combo ({nome})"
        res = _resultado_gatilho(
            True, motivo, prio_combo, preco_encontrado, tipo_gatilho="combo", alvo_gatilho=nome
        )
        if prio_combo == "alta":
            return res
        candidato_normal = candidato_normal or res
        break

    # 2. Alvos simples com faixa min..max
    if preco_encontrado is not None:
        for produto, valor_teto in banco.get("alvos_preco", {}).items():
            min_p, max_p = normalizar_faixa_preco(valor_teto)
            if match_padrao(produto, texto_bruto) and min_p <= preco_encontrado <= max_p:
                res = _resultado_gatilho(
                    True,
                    f"Teto Atingido ({produto} por R$ {preco_encontrado:.2f})",
                    prio_teto,
                    preco_encontrado,
                    tipo_gatilho="teto",
                    alvo_gatilho=produto,
                )
                if prio_teto == "alta":
                    return res
                candidato_normal = candidato_normal or res
                break

    # 3. Detector de queda real (ALTA se >= critico e critico < 100)
    desconto_min = float(banco.get("desconto_minimo", 0) or 0)
    desconto_critico = float(banco.get("desconto_critico", 75.0) or 75.0)
    desconto = detectar_desconto_real(texto_bruto, desconto_min)
    if desconto is not None and desconto_critico < 100 and desconto[0] >= desconto_critico:
        pct, preco_de, preco_por = desconto
        return _resultado_gatilho(
            True,
            f"Queda Real de {pct:.0f}% (De R$ {preco_de:.2f} por R$ {preco_por:.2f})",
            "alta",
            preco_por,
            tipo_gatilho="queda",
        )

    # 4. Palavras-chave (avalia altas primeiro, depois normais)
    palavras = banco.get("palavras", [])
    for palavra in palavras:
        if palavra_eh_alta(banco, palavra) and match_padrao(palavra, texto_bruto):
            return _resultado_gatilho(
                True,
                f"Palavra-Chave ({palavra})",
                "alta",
                preco_encontrado,
                tipo_gatilho="palavra",
                alvo_gatilho=palavra,
            )

    for palavra in palavras:
        if not palavra_eh_alta(banco, palavra) and match_padrao(palavra, texto_bruto):
            candidato_normal = candidato_normal or _resultado_gatilho(
                True,
                f"Palavra-Chave ({palavra})",
                "normal",
                preco_encontrado,
                tipo_gatilho="palavra",
                alvo_gatilho=palavra,
            )
            break

    if desconto is not None:
        pct, preco_de, preco_por = desconto
        candidato_normal = candidato_normal or _resultado_gatilho(
            True,
            f"Queda Real de {pct:.0f}% (De R$ {preco_de:.2f} por R$ {preco_por:.2f})",
            "normal",
            preco_por,
            tipo_gatilho="queda",
        )

    if candidato_normal:
        return candidato_normal

    return _resultado_gatilho(False, "Sem gatilho correspondente", preco=preco_encontrado)


def parsear_comando_composto(argumento):
    """
    Faz parsing de:
      nome | incluir1 + incluir2 | excluir1 + excluir2 | min-max (ou valor)
    ou (sem exclusões):
      nome | incluir1 + incluir2 | min-max (ou valor)
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

    teto_min, teto_max = parsear_faixa_preco(teto_str)

    for termo in incluir + excluir:
        valida, erro = regex_valida(termo)
        if not valida:
            raise ValueError(f"Regex inválida em '{termo}': {erro}")

    return {
        "nome": nome,
        "incluir": incluir,
        "excluir": excluir,
        "teto_min": teto_min,
        "teto": teto_max,
    }


def extrair_cupons(texto):
    """Extrai códigos de cupom mesmo em quebras de linha ou após 'código:'."""
    cupons = []
    vistos = set()

    for match in REGEX_CUPOM.finditer(texto):
        codigo = match.group(1).strip("`*_\"'.,;:!?-")
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


def _extrair_termo_busca(texto_bruto, url_oferta=None):
    """Extrai termo curto de produto para busca de comparação de preço."""
    if url_oferta:
        path = urllib.parse.urlparse(url_oferta).path
        slug = max((seg for seg in path.split("/") if len(seg) > 8 and not seg.isdigit()), default="")
        if slug:
            slug_limpo = re.sub(r"\bMLB-?\d+\b|_JM|\.html", " ", slug, flags=re.IGNORECASE)
            palavras = [p for p in re.split(r"[-_]+", slug_limpo) if len(p) > 1]
            if len(palavras) >= 2:
                return " ".join(palavras[:6])

    sem_urls = re.sub(r"https?://\S+", " ", texto_bruto or "")
    sem_precos = re.sub(r"(?i)r\$\s*[\d\.,]+", " ", sem_urls)
    for linha in sem_precos.splitlines():
        limpa = re.sub(r"[^\w\s-]", " ", linha, flags=re.UNICODE).strip()
        palavras = [
            p for p in limpa.split()
            if len(p) > 1 and p.lower() not in {"bug", "bugs", "corre", "corram", "imperdivel", "oferta", "cupom"}
        ]
        if len(palavras) >= 2:
            return " ".join(palavras[:6])
    return None


def gerar_url_comparacao(info_produto, texto_bruto, url_oferta=None):
    """Gera link para Keepa (Amazon BR) ou busca no Buscapé para comparação rápida."""
    produto_id = (info_produto or {}).get("produto_id") or ""
    if produto_id.startswith("amazon:"):
        asin = produto_id.split(":", 1)[1]
        return f"https://keepa.com/#!product/12-{asin}"

    termo = _extrair_termo_busca(texto_bruto, url_oferta)
    if termo:
        return f"https://www.buscape.com.br/search?q={urllib.parse.quote_plus(termo)}"
    return None


def alerta_eh_vago(texto_bruto):
    """Retorna True se o post original praticamente não descreve o produto ou preço."""
    sem_urls = re.sub(r"https?://\S+", " ", texto_bruto or "")
    tem_preco = extrair_preco(sem_urls) is not None
    palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]{2,}", sem_urls)
    if tem_preco and len(palavras) >= 4:
        return False
    return len(palavras) <= 4 or len(" ".join(palavras)) < 25


def buscar_metadados_pagina(url, timeout=4):
    """Extrai título e preço de meta tags HTML para enriquecer alertas vagos."""
    if not url or _url_bloqueio_ou_login(url):
        return {"titulo": None, "preco": None}

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"}
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            conteudo = resp.read(65536).decode("utf-8", errors="ignore")
    except Exception:
        return {"titulo": None, "preco": None}

    titulo = None
    for pat in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r"<title[^>]*>([^<]+)</title>",
    ):
        m = re.search(pat, conteudo, re.IGNORECASE)
        if m:
            candidato = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
            candidato = re.sub(
                r"\s*[\|\-–:]\s*(?:Amazon\.com\.br|Mercado Livre|Shopee|KaBuM!?|Magalu|Magazine Luiza|AliExpress).*$",
                "",
                candidato,
                flags=re.IGNORECASE,
            ).strip()
            bloqueados = ("just a moment", "access denied", "attention required", "robot", "captcha", "amazon.com.br", "mercado livre")
            if len(candidato) >= 5 and candidato.lower() not in bloqueados:
                titulo = candidato[:140]
                break

    preco = None
    m_preco = re.search(
        r'<meta[^>]+(?:product:price:amount|og:price:amount)["\'][^>]+content=["\']([\d\.,]+)["\']',
        conteudo,
        re.IGNORECASE,
    )
    if m_preco:
        preco = parse_numero_br(m_preco.group(1))

    return {"titulo": titulo, "preco": preco}


def extrair_links_mensagem(raw_text, entities=None, text_url_cls=None):
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
            is_text_url = isinstance(entity, text_url_cls) if text_url_cls else hasattr(entity, "url")
            if is_text_url and getattr(entity, "url", None):
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


def montar_chave_duplicata(info_produto, link_referencia, motivo, texto_bruto):
    """Define a chave única de deduplicação priorizando o ID real do produto."""
    if info_produto and info_produto.get("produto_id"):
        return info_produto["produto_id"]
    if link_referencia:
        return limpar_link(link_referencia)
    if "Teto Atingido" in motivo or "Combo" in motivo:
        return motivo
    return (texto_bruto or "")[:60].strip().lower()


def _formatar_rotulo_parar(alvo):
    """Limpa âncoras regex simples para exibir um rótulo legível no botão."""
    limpo = re.sub(r"\\b", "", alvo).strip()
    if len(limpo) > 22:
        limpo = f"{limpo[:21]}…"
    return f'🔕 Parar de monitorar "{limpo}"'


def montar_mensagem_e_botoes_spec(
    nome_grupo,
    motivo_disparo,
    prioridade,
    texto_bruto,
    cupons,
    info_produto,
    link_oferta,
    link_origem,
    links_extras=None,
    texto_recuperado=None,
    titulo_detectado=None,
    preco_detectado=None,
    url_comparacao=None,
    chave_silenciar=None,
    tipo_gatilho=None,
    alvo_gatilho=None,
):
    """Monta HTML completo, legenda <= 1000 chars (para fotos) e especificação dos botões."""
    cabecalho = [
        "🚨 <b>BUG / ALTA PRIORIDADE!</b> 🚨"
        if prioridade == "alta"
        else "🔔 <b>ALERTA DE OFERTA (Silencioso)</b>"
    ]
    if cupons:
        cupons_html = " ".join(f"<code>{html.escape(c)}</code>" for c in cupons)
        cabecalho.append(f"🎟️ <b>Cupom(ns):</b> {cupons_html}")
    cabecalho.append(f"📢 <b>Grupo:</b> {html.escape(nome_grupo)}")
    if info_produto and info_produto.get("loja"):
        cabecalho.append(f"🏪 <b>Loja:</b> {html.escape(info_produto['loja'])}")
    cabecalho.append(f"🎯 <i>Motivo: {html.escape(motivo_disparo)}</i>")
    if titulo_detectado:
        preco_txt = f" — <b>R$ {preco_detectado:.2f}</b>" if preco_detectado else ""
        cabecalho.append(f"🏷️ <b>Produto:</b> {html.escape(titulo_detectado)}{preco_txt}")

    corpo = [formatar_texto_alerta_html(texto_bruto, cupons)]
    if texto_recuperado:
        corpo.append("")
        corpo.append("🕰️ <b>[RECUPERADO DA MENSAGEM ANTERIOR]:</b>")
        corpo.append(formatar_texto_alerta_html(texto_recuperado, cupons))

    links_visiveis = []
    for lk in [link_oferta] + list(links_extras or []):
        if lk and lk not in links_visiveis:
            links_visiveis.append(lk)
    bloco_links = []
    if links_visiveis:
        bloco_links.append("")
        bloco_links.append("🔗 <b>Link(s):</b>")
        for lk in links_visiveis[:4]:
            bloco_links.append(html.escape(lk))

    mensagem_completa = "\n".join(cabecalho + [""] + corpo + bloco_links)
    if len(mensagem_completa) > 4000:
        mensagem_completa = mensagem_completa[:3990] + "\n..."

    if len(mensagem_completa) <= 1000:
        legenda_foto = mensagem_completa
    else:
        base_cab = "\n".join(cabecalho)
        espaco_corpo = max(80, 960 - len(base_cab))
        corpo_txt = "\n".join(corpo)
        if len(corpo_txt) > espaco_corpo:
            corpo_txt = corpo_txt[:espaco_corpo - 3] + "..."
        legenda_foto = f"{base_cab}\n\n{corpo_txt}"[:1000]

    botoes_spec = []
    if url_valida_botao(link_oferta):
        botoes_spec.append([("url", "🔥 Abrir Oferta", link_oferta)])
    if info_produto and url_valida_botao(info_produto.get("carrinho_amazon")):
        botoes_spec.append([("url", "🛒 Carrinho Amazon", info_produto["carrinho_amazon"])])

    linha_apoio = []
    if url_valida_botao(url_comparacao):
        linha_apoio.append(("url", "📊 Comparar Preço", url_comparacao))
    if url_valida_botao(link_origem):
        linha_apoio.append(("url", "📢 Post Original", link_origem))
    if linha_apoio:
        botoes_spec.append(linha_apoio)

    if chave_silenciar:
        botoes_spec.append([("inline", "🤫 Silenciar 3h", f"sil:{chave_silenciar}")])
    if tipo_gatilho in ("palavra", "teto", "combo") and alvo_gatilho:
        codigo_tipo = tipo_gatilho[0]
        botoes_spec.append(
            [("inline", _formatar_rotulo_parar(alvo_gatilho), f"stop:{codigo_tipo}:{hash_curto_chave(alvo_gatilho)}")]
        )

    return mensagem_completa, legenda_foto, botoes_spec


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


def ler_ultimas_linhas_log(qtd=30, caminho_log=ARQUIVO_LOG):
    """Lê as últimas N linhas do arquivo de log."""
    if not os.path.exists(caminho_log):
        return []
    with open(caminho_log, "r", encoding="utf-8", errors="ignore") as f:
        linhas = f.readlines()
    return [linha.rstrip("\r\n") for linha in linhas[-qtd:]]


def formatar_resumo_diario(stats, data_str=None):
    """Monta texto HTML do resumo diário."""
    data_exib = data_str or stats.get("data", datetime.date.today().isoformat())
    return (
        f"📊 <b>Resumo Diário ({html.escape(data_exib)})</b>\n\n"
        f"• Mensagens analisadas: <b>{stats.get('mensagens_lidas', 0)}</b>\n"
        f"• Alertas enviados: <b>{stats.get('alertas_enviados', 0)}</b>\n"
        f"• Duplicatas barradas: <b>{stats.get('duplicatas_barradas', 0)}</b>\n"
        f"• Bloqueios negativos/filtros: <b>{stats.get('bloqueios_negativos', 0)}</b>\n"
        f"• Silenciados na madrugada (DND): <b>{stats.get('bloqueios_dnd', 0)}</b>"
    )


def remover_itens_lista(lista, argumento, case_insensitive=False, normalizar_fn=None, separar_espacos=False):
    """Remove itens por índice (1-based, ex: '1, 3') ou por texto/lote."""
    removidos = []
    nao_encontrados = []
    arg = argumento.strip()

    if re.fullmatch(r"[\d\s,;]+", arg):
        tokens = [int(t) for t in re.split(r"[\s,;]+", arg) if t.isdigit()]
        indices_unicos = sorted(set(tokens), reverse=True)
        for idx in indices_unicos:
            if 1 <= idx <= len(lista):
                removidos.append(lista.pop(idx - 1))
            else:
                nao_encontrados.append(f"#{idx}")
        removidos.reverse()
        return removidos, nao_encontrados

    padrao_sep = r"[\s;\n]+" if separar_espacos else r"[;\n]+"
    alvos = [x.strip() for x in re.split(padrao_sep, arg) if x.strip()]
    for item in alvos:
        alvo = normalizar_fn(item) if normalizar_fn else item
        if case_insensitive:
            achado = next((x for x in lista if x.lower() == alvo.lower()), None)
        else:
            achado = alvo if alvo in lista else None
        if achado is not None:
            lista.remove(achado)
            removidos.append(achado)
        else:
            nao_encontrados.append(alvo)
    return removidos, nao_encontrados


def remover_chaves_dict(dicionario, argumento):
    """Remove entradas de um dicionário por índice (1-based) ou por chave."""
    removidos = []
    nao_encontrados = []
    arg = argumento.strip()
    chaves = list(dicionario.keys())

    if re.fullmatch(r"[\d\s,;]+", arg):
        tokens = sorted({int(t) for t in re.split(r"[\s,;]+", arg) if t.isdigit()}, reverse=True)
        for idx in tokens:
            if 1 <= idx <= len(chaves):
                k = chaves[idx - 1]
                del dicionario[k]
                removidos.append(k)
            else:
                nao_encontrados.append(f"#{idx}")
        removidos.reverse()
        return removidos, nao_encontrados

    for item in [x.strip().lower() for x in re.split(r"[;\n]+", arg) if x.strip()]:
        if item in dicionario:
            del dicionario[item]
            removidos.append(item)
        else:
            nao_encontrados.append(item)
    return removidos, nao_encontrados


def remover_compostos(alvos_compostos, argumento):
    """Remove alvos compostos por índice (1-based) ou por nome."""
    removidos = []
    nao_encontrados = []
    arg = argumento.strip()

    if re.fullmatch(r"[\d\s,;]+", arg):
        tokens = sorted({int(t) for t in re.split(r"[\s,;]+", arg) if t.isdigit()}, reverse=True)
        for idx in tokens:
            if 1 <= idx <= len(alvos_compostos):
                removidos.append(alvos_compostos.pop(idx - 1)["nome"])
            else:
                nao_encontrados.append(f"#{idx}")
        removidos.reverse()
        return removidos, nao_encontrados

    for item in [x.strip().lower() for x in re.split(r"[;\n]+", arg) if x.strip()]:
        achado = next((c for c in alvos_compostos if c.get("nome") == item), None)
        if achado:
            alvos_compostos.remove(achado)
            removidos.append(achado["nome"])
        else:
            nao_encontrados.append(item)
    return removidos, nao_encontrados


def formatar_lista_numerada(itens, titulo, comando_del):
    """Formata lista numerada para facilitar remoção rápida por índice."""
    if not itens:
        return f"📭 <b>{html.escape(titulo)}</b>: nenhum item cadastrado."
    linhas = [f"<b>{html.escape(titulo)}:</b>"]
    for i, item in enumerate(itens, 1):
        linhas.append(f"{i}. <code>{html.escape(str(item))}</code>")
    linhas.append(f"\n💡 Para remover por número: <code>{html.escape(comando_del)} 1</code>")
    return "\n".join(linhas)


def montar_painel_menu_spec(banco, estado_runtime, estado_persistente):
    """Monta painel interativo principal (/menu)."""
    stats = garantir_stats_do_dia(estado_persistente)
    pausado = estado_runtime.get("pausado", False)
    dnd = banco.get("nao_perturbe", {})
    filtros = banco.get("filtros_extras", {})
    desc_min = float(banco.get("desconto_minimo", 0) or 0)
    desc_crit = float(banco.get("desconto_critico", 75) or 75)

    dnd_lbl = f"🌙 DND: {dnd.get('inicio', 0):02d}-{dnd.get('fim', 7):02d}h" if dnd.get("ativo") else "☀️ DND: OFF"
    usados_lbl = f"🧹 Usados: {'ON' if filtros.get('bloquear_usados') else 'OFF'}"
    import_lbl = f"✈️ Import: {'ON' if filtros.get('bloquear_importacao') else 'OFF'}"
    pausa_lbl = "▶️ Retomar" if pausado else "⏸️ Pausar"
    prio = banco.get("prioridades", {})
    crit_txt = "OFF" if desc_crit >= 100 or desc_min <= 0 else f"≥{desc_crit:.0f}%"
    min_txt = "OFF" if desc_min <= 0 else f"≥{desc_min:.0f}%"

    texto = (
        f"🎛️ <b>Painel de Controle</b>\n\n"
        f"• Estado: <b>{'⏸️ Pausado' if pausado else '✅ Ativo'}</b> | Canais: <b>{len(banco.get('canais', []))}</b>\n"
        f"• Hoje: <b>{stats['mensagens_lidas']}</b> lidas | <b>{stats['alertas_enviados']}</b> alertas | <b>{stats['duplicatas_barradas']}</b> dup.\n"
        f"• Prioridade Alta: Teto=<b>{prio.get('teto', 'alta').upper()}</b> | Combo=<b>{prio.get('combo', 'alta').upper()}</b> | Queda Alta=<b>{crit_txt}</b> (Normal {min_txt})\n\n"
        f"<i>Toque nos botões abaixo para configurar sem digitar:</i>"
    )

    botoes_spec = [
        [("inline", "📋 Listas", "menu:lista"), ("inline", "📊 Status", "menu:status"), ("inline", "🧪 Teste", "menu:teste")],
        [("inline", pausa_lbl, "menu:pausa"), ("inline", dnd_lbl, "menu:dnd")],
        [("inline", usados_lbl, "menu:usados"), ("inline", import_lbl, "menu:import")],
        [("inline", "⚡ Prioridades e Faixas", "prio:main"), ("inline", "💾 Backup", "menu:backup")],
        [("inline", "🕘 Últimos", "menu:ultimos"), ("inline", "📄 Logs", "menu:logs"), ("inline", "❓ Atalhos", "menu:ajuda")],
    ]
    return texto, botoes_spec


def montar_painel_prioridades_spec(banco):
    """Monta o painel interativo de edição de prioridades e faixas."""
    prio = banco.setdefault(
        "prioridades",
        {"teto": "alta", "combo": "alta", "palavras_altas": []},
    )
    teto_alta = prio.get("teto", "alta") == "alta"
    combo_alta = prio.get("combo", "alta") == "alta"
    desc_min = float(banco.get("desconto_minimo", 65) or 0)
    desc_crit = float(banco.get("desconto_critico", 75) or 75)
    palavras = banco.get("palavras", [])
    altas_qtd = sum(1 for p in palavras if palavra_eh_alta(banco, p))
    normais_qtd = len(palavras) - altas_qtd

    min_txt = "OFF" if desc_min <= 0 else f"{desc_min:.0f}%"
    crit_txt = "OFF (só silenc.)" if desc_crit >= 100 or desc_min <= 0 else f"≥ {desc_crit:.0f}%"
    faixa_norm_txt = (
        "Desativada"
        if desc_min <= 0
        else (f"{desc_min:.0f}%–{desc_crit - 1:.0f}%" if desc_crit < 100 and desc_crit > desc_min else f"≥ {desc_min:.0f}%")
    )

    texto = (
        f"⚡ <b>Configurar Prioridades (Telegram vs MacroDroid)</b>\n\n"
        f"🔴 <b>ALTA</b> = Som normal no Telegram + abre no MacroDroid\n"
        f"🟡 <b>NORMAL</b> = Notificação silenciosa no Telegram (sem MacroDroid)\n\n"
        f"• 🎯 <b>Teto Atingido:</b> {'🔴 ALTA' if teto_alta else '🟡 NORMAL'}\n"
        f"• 🧩 <b>Combo:</b> {'🔴 ALTA' if combo_alta else '🟡 NORMAL'}\n"
        f"• 📉 <b>Queda Normal (Silenciosa):</b> <code>{faixa_norm_txt}</code>\n"
        f"• 🔥 <b>Queda Alta (MacroDroid):</b> <code>{crit_txt}</code>\n"
        f"• 🔑 <b>Palavras-Chave:</b> {altas_qtd} 🔴 altas | {normais_qtd} 🟡 normais\n\n"
        f"<i>Dica: também aceita comandos como</i> <code>/prio queda 60 80</code> <i>ou</i> <code>/prio teto normal</code>"
    )

    botoes_spec = [
        [
            ("inline", f"🎯 Teto: {'🔴 ALTA' if teto_alta else '🟡 NORMAL'}", "prio:teto"),
            ("inline", f"🧩 Combo: {'🔴 ALTA' if combo_alta else '🟡 NORMAL'}", "prio:combo"),
        ],
        [
            ("inline", "📉 Min -5%", "prio:dmin:-5"),
            ("inline", f"Normal: {min_txt}", "noop"),
            ("inline", "📉 Min +5%", "prio:dmin:5"),
        ],
        [
            ("inline", "🔥 Alta -5%", "prio:dcrit:-5"),
            ("inline", f"Alta: {crit_txt}", "noop"),
            ("inline", "🔥 Alta +5%", "prio:dcrit:5"),
        ],
        [
            ("inline", f"🔑 Palavras ({altas_qtd}🔴/{normais_qtd}🟡)", "prio:pal:0"),
            ("inline", "⬅️ Menu", "menu:home"),
        ],
    ]
    return texto, botoes_spec


def montar_painel_palavras_prio_spec(banco, pagina=0, por_pagina=8):
    """Monta submenu paginado com botões para alternar palavras entre ALTA e NORMAL."""
    palavras = banco.get("palavras", [])
    total = len(palavras)
    total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
    pagina = max(0, min(pagina, total_paginas - 1))
    inicio = pagina * por_pagina
    fatia = palavras[inicio:inicio + por_pagina]

    linhas_txt = [
        f"🔑 <b>Prioridade das Palavras-Chave (Pág. {pagina + 1}/{total_paginas})</b>\n"
        f"Toque em uma palavra para alternar entre 🔴 <b>ALTA</b> e 🟡 <b>NORMAL</b>:\n"
    ]
    botoes_spec = []
    linha_atual = []
    for offset, palavra in enumerate(fatia):
        idx = inicio + offset
        eh_alta = palavra_eh_alta(banco, palavra)
        icone = "🔴" if eh_alta else "🟡"
        linhas_txt.append(f"{idx + 1}. {icone} <code>{html.escape(palavra)}</code>")

        rotulo = palavra if len(palavra) <= 17 else f"{palavra[:16]}…"
        linha_atual.append(("inline", f"{icone} {rotulo}", f"prio:w:{idx}:{pagina}"))
        if len(linha_atual) == 2:
            botoes_spec.append(linha_atual)
            linha_atual = []
    if linha_atual:
        botoes_spec.append(linha_atual)

    if total_paginas > 1:
        nav = []
        if pagina > 0:
            nav.append(("inline", "◀️ Anterior", f"prio:pal:{pagina - 1}"))
        nav.append(("inline", f"{pagina + 1}/{total_paginas}", "noop"))
        if pagina + 1 < total_paginas:
            nav.append(("inline", "Próxima ▶️", f"prio:pal:{pagina + 1}"))
        botoes_spec.append(nav)

    botoes_spec.append([("inline", "⬅️ Voltar Prioridades", "prio:main"), ("inline", "🏠 Menu", "menu:home")])
    return "\n".join(linhas_txt), botoes_spec


TECLADO_FIXO_SPEC = [
    [("text", "➕ Adicionar"), ("text", "➖ Remover")],
    [("text", "📋 Minhas listas"), ("text", "🎛️ Painel")],
    [("text", "⚡ Prioridades"), ("text", "🕘 Histórico")],
]

TEXTOS_TECLADO_FIXO = {txt for linha in TECLADO_FIXO_SPEC for _, txt in linha}

WIZARD_CATEGORIAS = {
    "p": ("palavra", "🔑 Palavra-Chave"),
    "t": ("teto", "🎯 Teto de Preço"),
    "c": ("combo", "🧩 Combo"),
    "g": ("canal", "📡 Canal / Grupo"),
    "b": ("bloqueio", "⛔ Bloqueio"),
}

PROMPTS_ADICIONAR = {
    "palavra": (
        "🔑 <b>Digite a(s) palavra(s)-chave para adicionar:</b>\n\n"
        "• Exemplo simples: <code>liquidação</code>\n"
        "• Várias de uma vez (use <code>;</code>): <code>erro de preço; oferta relâmpago</code>"
    ),
    "teto": (
        "🎯 <b>Digite o item e o preço (ou faixa min-max):</b>\n\n"
        "• Com mínimo e máximo: <code>placa de vídeo, 400-1300</code>\n"
        "• Só máximo: <code>ssd 1tb, 350</code>"
    ),
    "combo": (
        "🧩 <b>Digite a regra composta:</b>\n\n"
        "• Com exclusões: <code>ram16 | 16gb + ddr4 | notebook, sodimm | 120-220</code>\n"
        "• Sem exclusões: <code>ssd1tb | ssd + 1tb | 200-380</code>"
    ),
    "canal": (
        "📡 <b>Digite o(s) @canal(is) ou ID(s) do grupo:</b>\n\n"
        "• Exemplo: <code>@ofertasbr</code> ou <code>@canal1 @canal2</code>"
    ),
    "bloqueio": (
        "⛔ <b>Digite o(s) termo(s) para bloquear:</b>\n\n"
        "• Exemplo: <code>obsid</code> ou vários: <code>usado; sem estoque</code>"
    ),
}


def montar_wizard_categoria_spec(modo):
    """Monta escolha de categoria para Adicionar ('add') ou Remover ('rem')."""
    if modo == "add":
        titulo = "➕ <b>O que você deseja adicionar?</b>"
        prefixo = "wiz:add"
    else:
        titulo = "➖ <b>Escolha de qual lista deseja remover:</b>"
        prefixo = "wiz:delcat"

    botoes_spec = [
        [("inline", "🔑 Palavra-Chave", f"{prefixo}:p"), ("inline", "🎯 Teto de Preço", f"{prefixo}:t")],
        [("inline", "🧩 Combo", f"{prefixo}:c"), ("inline", "📡 Canal / Grupo", f"{prefixo}:g")],
        [("inline", "⛔ Bloqueio", f"{prefixo}:b")],
        [("inline", "❌ Cancelar", "wiz:cancel")],
    ]
    return titulo, botoes_spec


def _itens_categoria(banco, cat_codigo):
    """Retorna lista de (valor_bruto, rotulo_exibicao) para a categoria informada."""
    if cat_codigo == "p":
        return [
            (p, f"{'🔴' if palavra_eh_alta(banco, p) else '🟡'} {p}")
            for p in banco.get("palavras", [])
        ]
    if cat_codigo == "t":
        return [
            (k, f"{k} ({formatar_faixa_preco(*normalizar_faixa_preco(v))})")
            for k, v in banco.get("alvos_preco", {}).items()
        ]
    if cat_codigo == "c":
        return [
            (c["nome"], f"{c['nome']} [{' + '.join(c['incluir'])}]")
            for c in banco.get("alvos_compostos", [])
        ]
    if cat_codigo == "g":
        return [(c, c) for c in banco.get("canais", [])]
    if cat_codigo == "b":
        return [(n, n) for n in banco.get("negativas", [])]
    return []


def montar_wizard_remover_itens_spec(banco, cat_codigo, pagina=0, por_pagina=7):
    """Monta botões grandes (1 por linha) para remover itens com 1 toque."""
    _, nome_cat = WIZARD_CATEGORIAS.get(cat_codigo, ("", "Item"))
    itens = _itens_categoria(banco, cat_codigo)
    if not itens:
        return (
            f"📭 <b>{html.escape(nome_cat)}</b>: nenhum item cadastrado.",
            [[("inline", "⬅️ Voltar", "wiz:rem"), ("inline", "❌ Cancelar", "wiz:cancel")]],
        )

    total_paginas = max(1, (len(itens) + por_pagina - 1) // por_pagina)
    pagina = max(0, min(pagina, total_paginas - 1))
    inicio = pagina * por_pagina
    fatia = itens[inicio:inicio + por_pagina]

    botoes_spec = []
    for offset, (_, rotulo) in enumerate(fatia):
        idx = inicio + offset
        texto_btn = rotulo if len(rotulo) <= 36 else f"{rotulo[:35]}…"
        botoes_spec.append([("inline", texto_btn, f"wiz:del:{cat_codigo}:{idx}:{pagina}")])

    if total_paginas > 1:
        nav = []
        if pagina > 0:
            nav.append(("inline", "◀️ Anterior", f"wiz:delcat:{cat_codigo}:{pagina - 1}"))
        nav.append(("inline", f"{pagina + 1}/{total_paginas}", "noop"))
        if pagina + 1 < total_paginas:
            nav.append(("inline", "Próxima ▶️", f"wiz:delcat:{cat_codigo}:{pagina + 1}"))
        botoes_spec.append(nav)

    botoes_spec.append([("inline", "⬅️ Voltar", "wiz:rem"), ("inline", "❌ Cancelar", "wiz:cancel")])
    titulo = f"🗑️ <b>Escolha qual item remover ({html.escape(nome_cat)}):</b>"
    return titulo, botoes_spec
