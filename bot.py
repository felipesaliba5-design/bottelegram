import asyncio
import datetime
import difflib
import html
import io
import json
import os
import re
import time

from telethon import Button, TelegramClient, events, functions, types
from telethon.tl.types import MessageEntityTextUrl

from core import (
    ARQUIVO_ESTADO,
    ARQUIVO_JSON,
    ARQUIVO_LOG,
    BASE_DIR,
    PROMPTS_ADICIONAR,
    TECLADO_FIXO_SPEC,
    TEXTOS_TECLADO_FIXO,
    WIZARD_CATEGORIAS,
    alerta_eh_vago,
    alternar_prioridade_palavra,
    avaliar_gatilhos,
    buscar_metadados_pagina,
    carregar_configuracoes,
    carregar_dados,
    carregar_estado_persistente,
    detectar_desconto_real,
    disparar_macrodroid,
    eh_horario_dnd,
    escolher_link_oferta,
    esta_no_historico,
    expandir_link,
    extrair_cupons,
    extrair_links_mensagem,
    extrair_parcelamento,
    extrair_preco,
    formatar_faixa_preco,
    formatar_lista_numerada,
    formatar_resumo_diario,
    garantir_stats_do_dia,
    gerar_snapshot_estado,
    gerar_url_comparacao,
    hash_curto_chave,
    host_confiavel,
    identificar_produto,
    ler_ultimas_linhas_log,
    logger,
    loja_em_snooze,
    migrar_estrutura_dados,
    montar_chave_duplicata,
    montar_mensagem_e_botoes_spec,
    montar_painel_dnd_spec,
    montar_painel_menu_spec,
    montar_painel_palavras_prio_spec,
    montar_painel_prioridades_spec,
    montar_wizard_categoria_spec,
    montar_wizard_remover_itens_spec,
    normalizar_faixa_preco,
    normalizar_loja_snooze,
    palavra_eh_alta,
    parsear_comando_composto,
    parsear_faixa_preco,
    regex_valida,
    registrar_alerta_enviado,
    registrar_historico,
    remover_chaves_dict,
    remover_compostos,
    remover_itens_lista,
    salvar_dados,
    salvar_estado_persistente,
)

ALIASES_COMANDO = {
    "/m": "/menu",
    "/h": "/ajuda",
    "/help": "/ajuda",
    "/l": "/lista",
    "/s": "/status",
    "/p": "/pausar",
    "/r": "/retomar",
    "/ac": "/addcanal",
    "/dc": "/delcanal",
    "/ap": "/addpalavra",
    "/dp": "/delpalavra",
    "/ab": "/addbloqueio",
    "/db": "/delbloqueio",
    "/at": "/addteto",
    "/dt": "/delteto",
    "/ax": "/addcomposto",
    "/dx": "/delcomposto",
    "/sd": "/setdesconto",
    "/prio": "/prioridade",
    "/t": "/teste",
    "/u": "/ultimos",
    "/b": "/backup",
    "/res": "/resumo",
    "/sim": "/simular",
    "/rank": "/ranking",
}

COMANDOS_BOT_MENU = [
    ("menu", "Painel interativo com botões"),
    ("teclado", "Mostrar teclado fixo na barra inferior"),
    ("add", "Assistente para adicionar por botões"),
    ("rem", "Assistente para remover por botões"),
    ("prioridade", "Editar prioridades e faixas (Alta/Normal)"),
    ("lista", "Listar canais, palavras e tetos numerados"),
    ("status", "Resumo do dia e estado do bot"),
    ("pausar", "Pausar ou retomar monitoramento"),
    ("addteto", "Teto simples: /addteto item, min-max"),
    ("addcomposto", "Combo: /addcomposto nome | inc | exc | min-max"),
    ("addpalavra", "Adicionar palavra(s): /ap t1; t2"),
    ("delpalavra", "Remover palavra por nº ou texto: /dp 1"),
    ("addcanal", "Adicionar canal(is): /ac @c1 @c2"),
    ("delcanal", "Remover canal por nº ou nome: /dc 1"),
    ("dnd", "Modo madrugada: /dnd 0-7 ou off"),
    ("filtro", "Filtros usados/importação"),
    ("snooze", "Pausar loja temporariamente: /snooze amazon 60"),
    ("simular", "Testar texto de oferta sem enviar em canal"),
    ("ranking", "Ranking de canais por alertas gerados"),
    ("buscar", "Buscar nos últimos alertas enviados"),
    ("ping", "Testar resposta e latência do bot"),
    ("teste", "Testar alerta com botões e MacroDroid"),
    ("backup", "Baixar backup JSON (envie .json para restaurar)"),
    ("ajuda", "Ver todos os comandos e atalhos"),
]

COMANDOS_CONHECIDOS = (
    {f"/{cmd}" for cmd, _ in COMANDOS_BOT_MENU}
    | set(ALIASES_COMANDO.values())
    | {"/start", "/cancelar", "/ultimos", "/logs", "/resumo", "/setdesconto"}
)

_TAREFAS_BG = set()


def _agendar_bg(corrotina):
    """create_task com referência forte para evitar coleta prematura pelo garbage collector."""
    tarefa = asyncio.create_task(corrotina)
    _TAREFAS_BG.add(tarefa)
    tarefa.add_done_callback(_TAREFAS_BG.discard)
    return tarefa


async def _acionar_macrodroid(url_macrodroid, link, estado_runtime, cooldown_anterior, disparo_reservado):
    """Dispara o MacroDroid fora do caminho crítico; restaura cooldown se falhar."""
    try:
        status_http = await asyncio.to_thread(disparar_macrodroid, url_macrodroid, link)
        logger.info("MacroDroid acionado (HTTP %s) com %s", status_http, link)
    except Exception as err:
        if estado_runtime.get("ultimo_disparo") == disparo_reservado:
            estado_runtime["ultimo_disparo"] = cooldown_anterior
        logger.warning("Falha ao acionar MacroDroid: %s", err)


def converter_botoes_telethon(botoes_spec):
    """Converte especificação de botões [(tipo, texto, valor?)] em objetos Button do Telethon."""
    if not botoes_spec:
        return None
    linhas = []
    for linha in botoes_spec:
        botoes_linha = []
        for item in linha:
            tipo, texto = item[0], item[1]
            if tipo == "url":
                botoes_linha.append(Button.url(texto, item[2]))
            elif tipo == "inline":
                botoes_linha.append(Button.inline(texto, item[2].encode("utf-8")))
            elif tipo == "text":
                botoes_linha.append(Button.text(texto, resize=True, single_use=False))
        if botoes_linha:
            linhas.append(botoes_linha)
    return linhas or None


async def enviar_em_partes_fn(send_fn, texto, parse_mode="html"):
    """Envia mensagens longas dividindo por linhas para respeitar o limite do Telegram."""
    if len(texto) <= 4000:
        await send_fn(texto, parse_mode=parse_mode)
        return

    bloco = ""
    for linha in texto.splitlines(keepends=True):
        if len(bloco) + len(linha) > 3900:
            await send_fn(bloco, parse_mode=parse_mode)
            bloco = ""
        bloco += linha
    if bloco:
        await send_fn(bloco, parse_mode=parse_mode)


def _formatar_texto_ajuda():
    return (
        "🤖 <b>Comandos e Atalhos Rápidos</b>\n\n"
        "<b>Painel Visual (1 toque):</b>\n"
        "• <code>/menu</code> (<code>/m</code>) — Painel principal com botões\n"
        "• <code>/prioridade</code> (<code>/prio</code>) — Editar o que dispara MacroDroid/som vs silencioso\n\n"
        "<b>Consultas e Controle:</b>\n"
        "• <code>/lista</code> (<code>/l</code>) — Listas numeradas (para remover pelo número)\n"
        "• <code>/status</code> (<code>/s</code>) — Estatísticas e estado\n"
        "• <code>/pausar [min]</code> (<code>/p</code> alterna) | <code>/retomar</code> (<code>/r</code>)\n"
        "• <code>/teste</code> (<code>/t</code>) | <code>/ping</code> | <code>/ultimos</code> (<code>/u</code>) | <code>/buscar termo</code> | <code>/logs [30]</code>\n"
        "• <code>/ranking</code> (<code>/rank</code>) — Ranking de canais que mais geram alertas\n"
        "• <code>/simular texto</code> (<code>/sim</code>) — Simula extração e regras numa oferta\n"
        "• <code>/snooze amazon 60</code> (ou <code>off</code>) — Silencia uma loja por X min\n"
        "• <code>/backup</code> (<code>/b</code>) — Baixar JSON (envie um <code>.json</code> para restaurar)\n\n"
        "<b>Edição Rápida (aceita lote com <code>;</code> e remoção por nº):</b>\n"
        "• <code>/ac @c1 @c2</code> | <code>/dc 1</code> (canais)\n"
        "• <code>/ap termo1; termo2</code> | <code>/dp 1, 3</code> (palavras)\n"
        "• <code>/ab termo</code> | <code>/db 1</code> (bloqueios)\n"
        "• <code>/at item, 400-1300</code> | <code>/dt 1</code> (tetos simples)\n"
        "• <code>/ax nome | ter1 + ter2 | ex1, ex2 | 120-220</code> | <code>/dx 1</code> (combos)\n"
        "• <code>/sd 65, 75</code> (ou <code>/prio queda 65 75</code>)\n"
        "• <code>/dnd 0-7</code> (ou <code>off</code>) | <code>/filtro usados on|off</code> | <code>/res 21</code>"
    )


def _verificar_auto_retomar(estado_runtime):
    """Retoma monitoramento automaticamente se o tempo de /pausar [min] expirou."""
    ate = estado_runtime.get("pausado_ate")
    if estado_runtime.get("pausado") and ate and time.time() >= ate:
        estado_runtime["pausado"] = False
        estado_runtime["pausado_ate"] = None


def _formatar_texto_status(banco, cfg, estado_runtime, estado_persistente):
    _verificar_auto_retomar(estado_runtime)
    uptime_min = int((time.time() - estado_runtime["inicio"]) // 60)
    stats = garantir_stats_do_dia(estado_persistente)
    dnd = banco.get("nao_perturbe", {})
    filtros = banco.get("filtros_extras", {})
    prio = banco.get("prioridades", {})
    dnd_txt = f"{dnd.get('inicio', 0):02d}h-{dnd.get('fim', 7):02d}h" if dnd.get("ativo") else "OFF"
    usados_txt = "ON" if filtros.get("bloquear_usados") else "OFF"
    import_txt = "ON" if filtros.get("bloquear_importacao") else "OFF"
    if estado_runtime.get("pausado"):
        ate = estado_runtime.get("pausado_ate")
        if ate:
            rest_min = max(1, int((ate - time.time()) // 60) + 1)
            estado_txt = f"⏸️ Pausado (volta em {rest_min} min)"
        else:
            estado_txt = "⏸️ Pausado"
    else:
        estado_txt = "✅ Ativo"
    macro_txt = "Ativo" if cfg["URL_MACRODROID"] else "Desativado"
    desc_crit = float(banco.get("desconto_critico", 75) or 75)
    crit_txt = "OFF" if desc_crit >= 100 else f"≥{desc_crit:.0f}%"
    return (
        f"📊 <b>Status do Caçador</b>\n"
        f"• Estado: {estado_txt} ({uptime_min} min online)\n"
        f"• Hoje: {stats['mensagens_lidas']} msgs lidas | {stats['alertas_enviados']} alertas | {stats['duplicatas_barradas']} duplicatas\n"
        f"• Prioridades Altas: Teto={prio.get('teto', 'alta').upper()} | Combo={prio.get('combo', 'alta').upper()} | Queda={crit_txt}\n"
        f"• DND madrugada: {dnd_txt}\n"
        f"• Filtros: Usados={usados_txt} | Import={import_txt}\n"
        f"• Canais: {len(banco['canais'])} | MacroDroid: {macro_txt}"
    )


def _formatar_lista_painel(banco, estado_runtime):
    """Monta /lista com itens numerados e ícones de prioridade."""
    txt_canais = "\n".join(f"{i}. <code>{html.escape(c)}</code>" for i, c in enumerate(banco["canais"], 1)) or "Nenhum"
    txt_palavras = "\n".join(
        f"{i}. {'🔴' if palavra_eh_alta(banco, p) else '🟡'} <code>{html.escape(p)}</code>"
        for i, p in enumerate(banco["palavras"], 1)
    ) or "Nenhuma"
    txt_negativas = "\n".join(f"{i}. <code>{html.escape(n)}</code>" for i, n in enumerate(banco["negativas"], 1)) or "Nenhuma"

    if banco.get("alvos_preco"):
        linhas_tetos = []
        for i, (k, val) in enumerate(banco["alvos_preco"].items(), 1):
            min_p, max_p = normalizar_faixa_preco(val)
            linhas_tetos.append(f"{i}. 🎯 <b>{html.escape(k)}</b>: {formatar_faixa_preco(min_p, max_p)}")
        txt_tetos = "\n".join(linhas_tetos)
    else:
        txt_tetos = "Nenhum limite simples configurado."

    if banco.get("alvos_compostos"):
        linhas_comp = []
        for i, c in enumerate(banco["alvos_compostos"], 1):
            inc = " + ".join(c["incluir"])
            exc = f" | sem: {', '.join(c['excluir'])}" if c.get("excluir") else ""
            faixa = formatar_faixa_preco(c.get("teto_min", 0), c["teto"]) if c.get("teto") else "sem teto"
            linhas_comp.append(
                f"{i}. 🧩 <b>{html.escape(c['nome'])}</b>: [{html.escape(inc)}{html.escape(exc)}] ({faixa})"
            )
        txt_compostos = "\n".join(linhas_comp)
    else:
        txt_compostos = "Nenhum alvo composto configurado."

    desc = float(banco.get("desconto_minimo", 0) or 0)
    desc_crit = float(banco.get("desconto_critico", 75) or 75)
    crit_txt = "OFF" if desc_crit >= 100 else f"≥ {desc_crit:.0f}%"
    txt_desc = f"Normal ≥ {desc:.0f}% | Alta {crit_txt}" if desc > 0 else "Desativado"

    prio = banco.get("prioridades", {})
    dnd = banco.get("nao_perturbe", {})
    txt_dnd = f"{dnd.get('inicio', 0):02d}h-{dnd.get('fim', 7):02d}h" if dnd.get("ativo") else "Desativado"

    filtros = banco.get("filtros_extras", {})
    txt_usados = "ON" if filtros.get("bloquear_usados") else "OFF"
    txt_import = "ON" if filtros.get("bloquear_importacao") else "OFF"

    resumo_h = banco.get("resumo_hora")
    txt_resumo = f"{int(resumo_h):02d}:00" if resumo_h is not None and int(resumo_h) >= 0 else "OFF"
    status_txt = "⏸️ Pausado" if estado_runtime["pausado"] else "✅ Ativo"

    return (
        f"⚙️ <b>Status:</b> {status_txt} | <b>DND:</b> {txt_dnd} | <b>Resumo:</b> {txt_resumo}\n"
        f"⚡ <b>Prioridades:</b> Teto={prio.get('teto', 'alta').upper()} | Combo={prio.get('combo', 'alta').upper()} | Queda: {txt_desc}\n"
        f"🧹 <b>Filtros:</b> Usados={txt_usados} | Importação={txt_import}\n\n"
        f"📡 <b>Canais ({len(banco['canais'])}):</b>\n{txt_canais}\n\n"
        f"🔑 <b>Palavras-Chave ({len(banco['palavras'])}) [🔴Alta / 🟡Normal]:</b>\n{txt_palavras}\n\n"
        f"📉 <b>Tetos Simples ({len(banco['alvos_preco'])}):</b>\n{txt_tetos}\n\n"
        f"🧩 <b>Tetos Compostos ({len(banco['alvos_compostos'])}):</b>\n{txt_compostos}\n\n"
        f"⛔ <b>Bloqueios ({len(banco['negativas'])}):</b>\n{txt_negativas}\n\n"
        f"💡 <i>Use /dc, /dp, /db, /dt ou /dx + número para remover rápido.</i>"
    )


def _normalizar_canal(item):
    novo = item.lower().strip()
    if novo and not novo.startswith("@") and not novo.lstrip("-").isdigit():
        novo = f"@{novo}"
    return novo


def _regex_generica_demais(padrao):
    """Rejeita padrões que casariam com praticamente toda mensagem (ex.: '.', '.*', '\\w', 'a')."""
    p = padrao.strip()
    if len(p) < 2:
        return True
    return (
        bool(re.search(p, "", re.IGNORECASE))
        or all(re.search(p, s, re.IGNORECASE) for s in ("a", "1"))
        or bool(re.fullmatch(p, " "))
    )


def _adicionar_regex_lote(banco, chave, argumento, caminho_json=ARQUIVO_JSON):
    """Adiciona uma ou várias expressões (separadas por ';' ou quebra de linha) com validação."""
    itens = [x.strip() for x in re.split(r"[;\n]+", argumento) if x.strip()]
    adicionados, ja_existiam, invalidos = [], [], []
    for item in itens:
        valida, erro = regex_valida(item)
        if not valida:
            invalidos.append(f"{item} ({erro})")
            continue
        if _regex_generica_demais(item):
            invalidos.append(f"{item} (genérica demais: casaria com quase toda mensagem)")
            continue
        if item in banco[chave]:
            ja_existiam.append(item)
            continue
        banco[chave].append(item)
        adicionados.append(item)

    if adicionados:
        salvar_dados(banco, caminho_json)

    partes = []
    if adicionados:
        partes.append(f"✅ Adicionado(s): {', '.join(f'<code>{html.escape(x)}</code>' for x in adicionados)}")
        if chave == "palavras":
            partes.append("<i>(Entraram como 🟡 NORMAL; use /prio para promover para 🔴 ALTA)</i>")
    if ja_existiam:
        partes.append(f"ℹ️ Já existia(m): {', '.join(f'<code>{html.escape(x)}</code>' for x in ja_existiam)}")
    if invalidos:
        partes.append(f"⚠️ Inválida(s): {', '.join(html.escape(x) for x in invalidos)}")
    if not partes:
        return False, "⚠️ Nenhum termo válido informado."
    return len(invalidos) == 0, "\n".join(partes)


def _executar_add_canal(banco, argumento, caminho_json=ARQUIVO_JSON):
    itens = [_normalizar_canal(x) for x in re.split(r"[\s,;]+", argumento) if x.strip()]
    if not itens:
        return False, "⚠️ Informe ao menos um canal (ex.: <code>@ofertasbr</code>)."
    adicionados, existentes = [], []
    existentes_lower = {c.lower() for c in banco["canais"]}
    for novo in itens:
        if novo not in existentes_lower:
            banco["canais"].append(novo)
            existentes_lower.add(novo)
            adicionados.append(novo)
        else:
            existentes.append(novo)
    if adicionados:
        salvar_dados(banco, caminho_json)
    msgs = []
    if adicionados:
        msgs.append(f"✅ Adicionado(s): {', '.join(f'<code>{html.escape(c)}</code>' for c in adicionados)}")
    if existentes:
        msgs.append(f"ℹ️ Já existia(m): {', '.join(f'<code>{html.escape(c)}</code>' for c in existentes)}")
    return True, "\n".join(msgs)


def _executar_add_teto(banco, argumento, caminho_json=ARQUIVO_JSON):
    try:
        produto, faixa_str = [x.strip() for x in argumento.split(",", 1)]
        valida, erro = regex_valida(produto)
        if not valida:
            return False, f"⚠️ Padrão inválido: <code>{html.escape(erro)}</code>"
        if _regex_generica_demais(produto):
            return False, "⚠️ Padrão genérico demais: casaria com praticamente toda mensagem."
        min_p, max_p = parsear_faixa_preco(faixa_str)
        existentes = [k for k in banco["alvos_preco"] if k.lower() == produto.lower() and k != produto]
        for k_ant in existentes:
            del banco["alvos_preco"][k_ant]
        banco["alvos_preco"][produto] = {"min": min_p, "max": max_p} if min_p > 0 else max_p
        salvar_dados(banco, caminho_json)
        return (
            True,
            f"🎯 <b>Teto adicionado!</b> Disparo para <b>{html.escape(produto)}</b> ({formatar_faixa_preco(min_p, max_p)})",
        )
    except Exception:
        return (
            False,
            "⚠️ <b>Formato incorreto!</b>\nUse: <code>placa de vídeo, 400-1300</code> ou <code>ssd, 300</code>",
        )


def _executar_add_combo(banco, argumento, caminho_json=ARQUIVO_JSON):
    try:
        composto = parsear_comando_composto(argumento)
        banco["alvos_compostos"] = [
            c for c in banco["alvos_compostos"] if c.get("nome") != composto["nome"]
        ]
        banco["alvos_compostos"].append(composto)
        salvar_dados(banco, caminho_json)
        exc_txt = ", ".join(composto["excluir"]) if composto["excluir"] else "nenhuma"
        return (
            True,
            f"🧩 <b>Alvo composto salvo!</b>\n"
            f"• Nome: <b>{html.escape(composto['nome'])}</b>\n"
            f"• Exige: <code>{html.escape(' + '.join(composto['incluir']))}</code>\n"
            f"• Exclui: <code>{html.escape(exc_txt)}</code>\n"
            f"• Faixa: <b>{formatar_faixa_preco(composto['teto_min'], composto['teto'])}</b>",
        )
    except Exception as err:
        return (
            False,
            f"⚠️ <b>Formato incorreto</b> ({html.escape(str(err))}).\n"
            "Use: <code>ram16 | 16gb + ddr4 | notebook, sodimm | 120-220</code>",
        )


async def _executar_teste_sistema(send_fn, cfg):
    """Envia alerta simulado com botões e testa o disparo do MacroDroid."""
    info_demo = identificar_produto("https://www.amazon.com.br/dp/B09V3KXJPB")
    url_comp = gerar_url_comparacao(info_demo, "SSD NVMe 1TB Teste", info_demo["link_limpo"])
    msg, _, spec = montar_mensagem_e_botoes_spec(
        nome_grupo="Teste do Sistema",
        motivo_disparo="Teste Manual (/teste)",
        prioridade="alta",
        texto_bruto="SSD NVMe 1TB Teste — Cupom: TESTE20\nDe R$ 600,00 por R$ 149,90",
        cupons=["TESTE20"],
        info_produto=info_demo,
        link_oferta=info_demo["link_limpo"],
        link_origem="https://t.me/Telegram",
        url_comparacao=url_comp,
        chave_silenciar=hash_curto_chave("teste:demo"),
    )
    await send_fn(msg, parse_mode="html", link_preview=False, buttons=converter_botoes_telethon(spec))

    if not cfg["URL_MACRODROID"]:
        await send_fn("ℹ️ MacroDroid está desativado (<code>URL_MACRODROID</code> vazio no <code>.env</code>).", parse_mode="html")
        return

    try:
        status_http = await asyncio.to_thread(disparar_macrodroid, cfg["URL_MACRODROID"], "https://www.amazon.com.br")
        await send_fn(f"✅ MacroDroid respondeu com sucesso (HTTP <code>{status_http}</code>).", parse_mode="html")
    except Exception as err:
        await send_fn(f"⚠️ Falha ao testar MacroDroid: <code>{html.escape(str(err))}</code>", parse_mode="html")


def _validar_estrutura_banco(novo):
    """Valida tipos, faixas e regex de um backup; levanta ValueError com a causa."""
    for chave in ("canais", "palavras", "negativas"):
        if not isinstance(novo.get(chave), list) or not all(isinstance(x, str) for x in novo[chave]):
            raise ValueError(f"'{chave}' ausente ou não é uma lista de textos")
    tipos = {
        "alvos_preco": dict,
        "alvos_compostos": list,
        "prioridades": dict,
        "nao_perturbe": dict,
        "filtros_extras": dict,
    }
    for chave, tipo in tipos.items():
        if chave in novo and not isinstance(novo[chave], tipo):
            raise ValueError(f"'{chave}' deve ser do tipo {tipo.__name__}")
    for padrao in novo["palavras"] + novo["negativas"] + list(novo.get("alvos_preco", {})):
        valida, erro = regex_valida(padrao)
        if not valida:
            raise ValueError(f"Regex inválida '{padrao}': {erro}")
    for faixa in novo.get("alvos_preco", {}).values():
        if isinstance(faixa, bool) or not isinstance(faixa, (int, float, dict)):
            raise ValueError("Faixa de preço inválida em 'alvos_preco'")
        normalizar_faixa_preco(faixa)
    for alvo in novo.get("alvos_compostos", []):
        if (
            not isinstance(alvo, dict)
            or not isinstance(alvo.get("nome"), str)
            or not alvo.get("nome").strip()
            or not isinstance(alvo.get("incluir"), list)
            or not alvo["incluir"]
            or not all(isinstance(x, str) and regex_valida(x)[0] for x in alvo["incluir"])
        ):
            raise ValueError("Item de 'alvos_compostos' sem nome/incluir válidos")
        if "excluir" in alvo and (
            not isinstance(alvo["excluir"], list)
            or not all(isinstance(x, str) and regex_valida(x)[0] for x in alvo["excluir"])
        ):
            raise ValueError(f"Combo '{alvo['nome']}' possui 'excluir' inválido")
    for chave in ("desconto_minimo", "desconto_critico"):
        if chave in novo:
            if isinstance(novo[chave], bool):
                raise ValueError(f"'{chave}' inválido")
            float(novo[chave])
    dnd = novo.get("nao_perturbe")
    if dnd is not None:
        for campo_h in ("inicio", "fim"):
            val_h = dnd.get(campo_h, 0)
            if isinstance(val_h, bool) or not isinstance(val_h, int) or not (0 <= val_h <= 23):
                raise ValueError(f"'nao_perturbe.{campo_h}' deve ser hora inteira entre 0 e 23")
        if "ativo" in dnd and not isinstance(dnd["ativo"], bool):
            raise ValueError("'nao_perturbe.ativo' deve ser booleano")
    flt = novo.get("filtros_extras")
    if flt is not None:
        for campo_b in ("bloquear_usados", "bloquear_importacao"):
            if campo_b in flt and not isinstance(flt[campo_b], bool):
                raise ValueError(f"'filtros_extras.{campo_b}' deve ser booleano")
    prio = novo.get("prioridades")
    if prio is not None:
        for cp in ("teto", "combo"):
            if cp in prio and prio[cp] not in ("alta", "normal"):
                raise ValueError(f"'prioridades.{cp}' inválido")
        if "palavras_altas" in prio and (
            not isinstance(prio["palavras_altas"], list) or not all(isinstance(x, str) for x in prio["palavras_altas"])
        ):
            raise ValueError("'prioridades.palavras_altas' deve ser lista de textos")
    if novo.get("resumo_hora") is not None:
        rh = novo["resumo_hora"]
        if isinstance(rh, bool) or not isinstance(rh, int) or not (0 <= rh <= 23):
            raise ValueError("'resumo_hora' deve ser inteiro entre 0 e 23 ou null")


async def processar_backup_recebido(event, banco, caminho_json=ARQUIVO_JSON):
    """Restaura um arquivo banco_de_dados.json enviado pelo usuário no chat do bot."""
    if not event.document:
        return False
    nome_arq = getattr(event.file, "name", "") or ""
    if not nome_arq.lower().endswith(".json"):
        return False

    try:
        dados_bytes = await event.download_media(file=bytes)
        novo_banco = json.loads(dados_bytes.decode("utf-8"))
        if not isinstance(novo_banco, dict):
            raise ValueError("JSON raiz deve ser um objeto")
        _validar_estrutura_banco(novo_banco)

        if os.path.exists(caminho_json):
            with open(caminho_json, "r", encoding="utf-8") as orig, open(f"{caminho_json}.bak", "w", encoding="utf-8") as bak:
                bak.write(orig.read())

        novo_banco, _ = migrar_estrutura_dados(novo_banco)
        salvar_dados(novo_banco, caminho_json)
        banco.clear()
        banco.update(novo_banco)

        await event.reply(
            f"✅ <b>Backup restaurado com sucesso!</b>\n"
            f"• Canais: {len(banco['canais'])}\n"
            f"• Palavras: {len(banco['palavras'])}\n"
            f"• Tetos simples: {len(banco['alvos_preco'])}\n"
            f"• Tetos compostos: {len(banco['alvos_compostos'])}",
            parse_mode="html",
        )
        logger.info("Backup restaurado via Telegram (%d canais).", len(banco["canais"]))
    except Exception as err:
        await event.reply(f"⚠️ Falha ao restaurar JSON: <code>{html.escape(str(err))}</code>", parse_mode="html")
    return True


def _aplicar_setdesconto(banco, min_val, crit_val=None, caminho_json=ARQUIVO_JSON):
    """Atualiza faixas de desconto mínimo e crítico validando limites."""
    if min_val < 0 or min_val >= 100:
        raise ValueError("Desconto mínimo deve ser entre 0 e 99")
    banco["desconto_minimo"] = float(min_val)
    if crit_val is not None:
        if crit_val < 0 or crit_val > 100:
            raise ValueError("Desconto crítico deve ser entre 0 e 100")
        banco["desconto_critico"] = 100.0 if crit_val == 0 else max(float(min_val), float(crit_val))
    elif float(banco.get("desconto_critico", 75) or 75) < float(min_val):
        banco["desconto_critico"] = float(min_val)
    salvar_dados(banco, caminho_json)


def _resolver_alvo_palavra(banco, token):
    """Localiza palavra por índice 1-based ou por texto exato."""
    palavras = banco.get("palavras", [])
    if token.isdigit():
        idx = int(token)
        if 1 <= idx <= len(palavras):
            return palavras[idx - 1]
        return None
    if token in palavras:
        return token
    return next((p for p in palavras if p.lower() == token.lower()), None)


async def _processar_prioridade_texto(event, banco, argumento, caminho_json=ARQUIVO_JSON):
    """Gerencia /prioridade (/prio) via texto ou abre o painel inline."""
    if not argumento:
        texto, spec = montar_painel_prioridades_spec(banco)
        await event.reply(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
        return

    tokens = argumento.split()
    sub = tokens[0].lower()
    prio = banco.setdefault("prioridades", {"teto": "alta", "combo": "alta", "palavras_altas": []})

    if sub in ("teto", "combo"):
        if len(tokens) == 1:
            atual = prio.get(sub, "alta")
            novo = "normal" if atual == "alta" else "alta"
        elif tokens[1].lower() in ("alta", "normal"):
            novo = tokens[1].lower()
        else:
            await event.reply(f"⚠️ Use <code>/prio {sub} alta</code> ou <code>/prio {sub} normal</code>.", parse_mode="html")
            return
        prio[sub] = novo
        salvar_dados(banco, caminho_json)
        icone = "🔴 ALTA (MacroDroid)" if novo == "alta" else "🟡 NORMAL (Silenciosa)"
        await event.reply(f"⚡ Prioridade de <b>{sub.capitalize()}</b> alterada para {icone}.", parse_mode="html")

    elif sub == "queda":
        try:
            if len(tokens) < 2:
                raise ValueError("Faltam valores")
            min_v = float(tokens[1].replace("%", "").replace(",", "."))
            crit_v = None
            if len(tokens) >= 3:
                crit_raw = tokens[2].lower()
                crit_v = 100.0 if crit_raw in ("off", "0", "desativar") else float(crit_raw.replace("%", "").replace(",", "."))
            _aplicar_setdesconto(banco, min_v, crit_v, caminho_json)
            crit_txt = "OFF (só silenc.)" if banco["desconto_critico"] >= 100 else f"≥ {banco['desconto_critico']:.0f}%"
            await event.reply(
                f"📉 Quedas atualizadas: Normal ≥ <b>{banco['desconto_minimo']:.0f}%</b> | Alta <b>{crit_txt}</b>.",
                parse_mode="html",
            )
        except Exception:
            await event.reply("⚠️ Use <code>/prio queda 65 75</code> (ou <code>/prio queda 65 off</code>).", parse_mode="html")

    elif sub in ("palavra", "p"):
        if len(tokens) < 2:
            texto, spec = montar_painel_palavras_prio_spec(banco, 0)
            await event.reply(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
            return
        nivel = None
        if len(tokens) >= 3 and tokens[-1].lower() in ("alta", "normal"):
            nivel = tokens[-1].lower()
            alvo_str = " ".join(tokens[1:-1])
        else:
            alvo_str = " ".join(tokens[1:])
        palavra = _resolver_alvo_palavra(banco, alvo_str)
        if not palavra:
            await event.reply("⚠️ Palavra não encontrada (use o número de <code>/lista</code> ou o texto exato).", parse_mode="html")
            return
        novo = alternar_prioridade_palavra(banco, palavra, nivel)
        salvar_dados(banco, caminho_json)
        icone = "🔴 ALTA" if novo == "alta" else "🟡 NORMAL"
        await event.reply(f"🔑 <code>{html.escape(palavra)}</code> agora é {icone}.", parse_mode="html")

    else:
        await event.reply(
            "⚠️ Subcomando inválido.\n"
            "• <code>/prio</code> (abre botões)\n"
            "• <code>/prio teto alta|normal</code>\n"
            "• <code>/prio combo alta|normal</code>\n"
            "• <code>/prio queda 65 75</code>\n"
            "• <code>/prio palavra 3 alta|normal</code>",
            parse_mode="html",
        )


async def _enviar_ultimos(send_fn, estado_persistente):
    ultimos = list(reversed(estado_persistente.get("ultimos", [])[-10:]))
    if not ultimos:
        await send_fn("📭 Nenhum alerta registrado ainda.")
        return
    linhas = ["🕘 <b>Últimos Alertas Enviados</b>\n"]
    for i, item in enumerate(ultimos, 1):
        linhas.append(
            f"{i}. <b>{html.escape(item.get('hora', '--:--'))}</b> "
            f"[{html.escape(item.get('loja') or 'Link')}] "
            f"<i>{html.escape(item.get('motivo', ''))}</i>\n"
            f"   {html.escape(item.get('link') or '')}"
        )
    await enviar_em_partes_fn(send_fn, "\n".join(linhas), parse_mode="html")


def _formatar_ranking_canais(estado_persistente, top=10, minimo_mudo=200):
    """Mostra quais canais geram alertas e quais só gastam processamento."""
    por_canal = estado_persistente.get("por_canal", {})
    if not por_canal:
        return "📭 Ainda sem dados por canal (aparecem após as próximas mensagens)."
    ordenados = sorted(por_canal.items(), key=lambda kv: (kv[1]["alertas"], kv[1]["lidas"]), reverse=True)
    linhas = ["🏆 <b>Ranking de Canais</b> (alertas / mensagens lidas)\n"]
    for i, (nome, d) in enumerate(ordenados[:top], 1):
        taxa = (d["alertas"] / d["lidas"] * 100) if d["lidas"] else 0.0
        linhas.append(f"{i}. <b>{html.escape(nome)}</b>: {d['alertas']} / {d['lidas']} ({taxa:.1f}%)")
    mudos = [n for n, d in por_canal.items() if d["lidas"] >= minimo_mudo and d["alertas"] == 0]
    if mudos:
        lista = ", ".join(html.escape(n) for n in mudos[:5])
        linhas.append(f"\n💤 Sem nenhum alerta em {minimo_mudo}+ mensagens: {lista} — candidatos a remover (/dc).")
    return "\n".join(linhas)


async def _enviar_logs(send_fn, qtd=30, caminho_log=ARQUIVO_LOG):
    linhas = ler_ultimas_linhas_log(qtd, caminho_log=caminho_log)
    if not linhas:
        await send_fn("📄 Arquivo de log ainda está vazio.")
        return
    conteudo = html.escape("\n".join(linhas))
    if len(conteudo) > 3900:
        conteudo = conteudo[-3900:]
    await send_fn(f"📄 <b>Últimas {len(linhas)} linhas do log:</b>\n<pre>{conteudo}</pre>", parse_mode="html")


async def _enviar_backup(send_fn, bot_client, chat_id, caminho_json=ARQUIVO_JSON):
    if bot_client and os.path.exists(caminho_json):
        await bot_client.send_file(
            chat_id,
            caminho_json,
            caption="💾 Backup atual do banco_de_dados.json (envie um .json aqui para restaurar).",
        )
    else:
        await send_fn("⚠️ Banco ainda não foi gravado em disco ou cliente indisponível.")


async def _responder_wizard_add(event, estado_runtime, banco, tipo_acao, texto, caminho_json=ARQUIVO_JSON):
    """Processa texto digitado pelo usuário durante o fluxo interativo ➕ Adicionar."""
    if tipo_acao == "add:palavra":
        ok, msg = _adicionar_regex_lote(banco, "palavras", texto, caminho_json)
    elif tipo_acao == "add:bloqueio":
        ok, msg = _adicionar_regex_lote(banco, "negativas", texto, caminho_json)
    elif tipo_acao == "add:canal":
        ok, msg = _executar_add_canal(banco, texto, caminho_json)
    elif tipo_acao == "add:teto":
        ok, msg = _executar_add_teto(banco, texto, caminho_json)
    elif tipo_acao == "add:combo":
        ok, msg = _executar_add_combo(banco, texto, caminho_json)
    else:
        estado_runtime["aguardando"] = None
        estado_runtime["aguardando_ate"] = None
        return

    if ok:
        estado_runtime["aguardando"] = None
        estado_runtime["aguardando_ate"] = None
        await event.reply(msg, parse_mode="html")
    else:
        await event.reply(
            f"{msg}\n\n<i>Tente novamente ou toque em ❌ Cancelar:</i>",
            parse_mode="html",
            buttons=converter_botoes_telethon([[("inline", "❌ Cancelar", "wiz:cancel")]]),
        )


async def processar_comando_painel(
    event,
    banco,
    cfg,
    estado_runtime,
    estado_persistente,
    bot_client=None,
    caminho_json=ARQUIVO_JSON,
    caminho_log=ARQUIVO_LOG,
):
    """Processa teclado fixo, fluxos interativos, comandos e atalhos no chat do bot."""
    cmd_full = (event.raw_text or "").strip()
    if not cmd_full:
        return

    # 1. Botões do teclado fixo inferior têm prioridade e nunca viram texto de cadastro
    if cmd_full in TEXTOS_TECLADO_FIXO:
        estado_runtime["aguardando"] = None
        if cmd_full == "➕ Adicionar":
            titulo, spec = montar_wizard_categoria_spec("add")
            await event.reply(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))
            return
        if cmd_full == "➖ Remover":
            titulo, spec = montar_wizard_categoria_spec("rem")
            await event.reply(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))
            return
        if cmd_full == "📋 Minhas listas":
            cmd_full = "/lista"
        elif cmd_full == "🎛️ Painel":
            cmd_full = "/menu"
        elif cmd_full == "⚡ Prioridades":
            cmd_full = "/prioridade"
        elif cmd_full == "🕘 Histórico":
            cmd_full = "/ultimos"

    _verificar_auto_retomar(estado_runtime)

    # 2. Mensagem de texto livre durante wizard ativo
    if not cmd_full.startswith("/"):
        acao_pendente = estado_runtime.get("aguardando")
        if acao_pendente:
            expira = estado_runtime.get("aguardando_ate")
            if expira is not None and time.time() > expira:
                estado_runtime["aguardando"] = None
                estado_runtime["aguardando_ate"] = None
                await event.reply("⌛ O assistente expirou (5 min sem resposta). Toque em ➕ Adicionar para recomeçar.")
                return
            await _responder_wizard_add(event, estado_runtime, banco, acao_pendente, cmd_full, caminho_json)
        else:
            await event.reply(
                "ℹ️ Nenhuma operação ativa. Use /menu para o painel, /simular [texto] para testar ou /ajuda para comandos."
            )
        return

    tinha_pendencia = bool(estado_runtime.get("aguardando"))
    estado_runtime["aguardando"] = None
    estado_runtime["aguardando_ate"] = None
    partes = cmd_full.split(" ", 1)
    cmd_original = partes[0].lower()
    comando = ALIASES_COMANDO.get(cmd_original, cmd_original)
    argumento = partes[1].strip() if len(partes) > 1 else ""
    logger.info("Comando recebido no painel: %s", cmd_full)

    if comando == "/start":
        await event.reply(
            "⌨️ <b>Teclado rápido ativado na barra inferior!</b>",
            parse_mode="html",
            buttons=converter_botoes_telethon(TECLADO_FIXO_SPEC),
        )
        texto, spec = montar_painel_menu_spec(banco, estado_runtime, estado_persistente)
        await event.reply(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))

    elif comando == "/teclado":
        await event.reply(
            "⌨️ <b>Teclado fixo ativado na barra inferior!</b>",
            parse_mode="html",
            buttons=converter_botoes_telethon(TECLADO_FIXO_SPEC),
        )

    elif comando == "/cancelar":
        await event.reply("❌ Operação cancelada." if tinha_pendencia else "ℹ️ Nenhuma operação pendente.")

    elif comando == "/add":
        titulo, spec = montar_wizard_categoria_spec("add")
        await event.reply(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))

    elif comando == "/rem":
        titulo, spec = montar_wizard_categoria_spec("rem")
        await event.reply(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))

    elif comando == "/menu":
        texto, spec = montar_painel_menu_spec(banco, estado_runtime, estado_persistente)
        await event.reply(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))

    elif comando == "/ajuda":
        await event.reply(_formatar_texto_ajuda(), parse_mode="html")

    elif comando == "/prioridade":
        await _processar_prioridade_texto(event, banco, argumento, caminho_json)

    elif comando == "/lista":
        await enviar_em_partes_fn(event.reply, _formatar_lista_painel(banco, estado_runtime), parse_mode="html")

    elif comando == "/status":
        await event.reply(_formatar_texto_status(banco, cfg, estado_runtime, estado_persistente), parse_mode="html")

    elif comando == "/teste":
        await _executar_teste_sistema(event.reply, cfg)

    elif comando == "/ping":
        inicio_ping = time.perf_counter()
        msg_ping = await event.reply("🏓 Pong!")
        latencia_ms = (time.perf_counter() - inicio_ping) * 1000.0
        try:
            await msg_ping.edit(f"🏓 <b>Pong!</b> Latência: <code>{latencia_ms:.0f} ms</code>", parse_mode="html")
        except Exception:
            pass

    elif comando == "/snooze":
        snooze_lojas = estado_runtime.setdefault("snooze_lojas", {})
        agora = time.time()
        for k in [k for k, v in snooze_lojas.items() if v <= agora]:
            del snooze_lojas[k]

        if not argumento:
            if not snooze_lojas:
                await event.reply(
                    "😴 Nenhuma loja em snooze.\nUse: <code>/snooze amazon 60</code> (ou <code>shopee 120</code>)",
                    parse_mode="html",
                )
            else:
                linhas = ["😴 <b>Lojas em Snooze:</b>"]
                for loja_k, exp in snooze_lojas.items():
                    rest_min = max(1, int((exp - agora) // 60) + 1)
                    linhas.append(f"• <b>{html.escape(loja_k.title())}</b>: {rest_min} min restantes")
                linhas.append("\nPara cancelar: <code>/snooze off</code> ou <code>/snooze loja off</code>")
                await event.reply("\n".join(linhas), parse_mode="html")
            return

        tokens = argumento.split()
        if tokens[0].lower() in ("off", "limpar", "cancelar"):
            snooze_lojas.clear()
            await event.reply("🔔 Todos os snoozes de lojas foram cancelados.")
            return

        if len(tokens) >= 2 and (tokens[-1].lower() in ("off", "0") or tokens[-1].isdigit() or re.fullmatch(r"-\d+", tokens[-1])):
            loja = normalizar_loja_snooze(" ".join(tokens[:-1]))
            sufixo = tokens[-1]
        else:
            loja = normalizar_loja_snooze(" ".join(tokens))
            sufixo = None

        if not loja:
            await event.reply("⚠️ Informe o nome da loja (ex.: <code>/snooze amazon 60</code>).", parse_mode="html")
            return

        if sufixo is not None and sufixo.lower() in ("off", "0"):
            if snooze_lojas.pop(loja, None) is not None:
                await event.reply(f"🔔 Snooze cancelado para <b>{html.escape(loja.title())}</b>.", parse_mode="html")
            else:
                await event.reply(f"ℹ️ <b>{html.escape(loja.title())}</b> não estava em snooze.", parse_mode="html")
            return

        minutos = 60
        if sufixo is not None:
            if not sufixo.isdigit() or not (1 <= int(sufixo) <= 1440):
                await event.reply("⚠️ Informe minutos entre 1 e 1440 (ex.: <code>/snooze amazon 60</code>).", parse_mode="html")
                return
            minutos = int(sufixo)

        snooze_lojas[loja] = agora + (minutos * 60)
        await event.reply(f"😴 <b>{html.escape(loja.title())}</b> silenciada por <b>{minutos} min</b>.", parse_mode="html")

    elif comando == "/simular":
        if not argumento:
            await event.reply(
                "🧪 <b>Simulador de Regras</b>\n"
                "Envie: <code>/simular [texto da oferta]</code> para testar preço, desconto, parcelamento, cupons e gatilhos.",
                parse_mode="html",
            )
            return
        preco_sim = extrair_preco(argumento)
        desc_sim = detectar_desconto_real(argumento, banco.get("desconto_minimo", 0))
        cupons_sim = extrair_cupons(argumento)
        parcel_sim = extrair_parcelamento(argumento)
        links_sim = extrair_links_mensagem(
            argumento, getattr(event, "entities", None), text_url_cls=MessageEntityTextUrl
        )
        link_sim = escolher_link_oferta(links_sim)
        info_sim = identificar_produto(link_sim) if link_sim else {"loja": None}
        avaliacao_sim = avaliar_gatilhos(argumento, banco)

        prioridade_sim = avaliacao_sim.get("prioridade")
        notas_envio = []
        if avaliacao_sim["disparar"]:
            if prioridade_sim != "alta" and eh_horario_dnd(banco.get("nao_perturbe")):
                notas_envio.append("segurado pelo DND agora")
            loja_snz = loja_em_snooze(info_sim, link_sim, estado_runtime.get("snooze_lojas", {}))
            if loja_snz:
                notas_envio.append(f"em snooze ({loja_snz})")

        status_sim = "✅ DISPARARIA" if avaliacao_sim["disparar"] else "🛑 IGNORADO / BLOQUEADO"
        if notas_envio:
            status_sim = f"⏸️ {status_sim} ({', '.join(notas_envio)})"

        prio_txt = (prioridade_sim or "nenhuma").upper()
        if prioridade_sim == "alta":
            prio_txt = "🔴 ALTA (som + MacroDroid)"
        elif prioridade_sim == "normal":
            prio_txt = "🟡 NORMAL (silencioso)"

        preco_txt = f"R$ {preco_sim:.2f}" if preco_sim is not None else "Não detectado"
        desc_txt = (
            f"{desc_sim[0]:.0f}% (R$ {desc_sim[1]:.2f} → R$ {desc_sim[2]:.2f})"
            if desc_sim
            else "Não detectado"
        )
        cupons_txt = ", ".join(f"<code>{html.escape(c)}</code>" for c in cupons_sim) if cupons_sim else "Nenhum"
        parcel_txt = html.escape(parcel_sim) if parcel_sim else "Não detectado"
        loja_txt = html.escape(info_sim.get("loja")) if info_sim.get("loja") else "Não identificada"

        await event.reply(
            f"🧪 <b>Resultado da Simulação</b>\n\n"
            f"• <b>Decisão:</b> {status_sim}\n"
            f"• <b>Motivo:</b> <code>{html.escape(avaliacao_sim['motivo'])}</code>\n"
            f"• <b>Prioridade:</b> <b>{prio_txt}</b>\n"
            f"• <b>Loja:</b> {loja_txt}\n"
            f"• <b>Preço extraído:</b> {preco_txt}\n"
            f"• <b>Desconto real:</b> {desc_txt}\n"
            f"• <b>Parcelamento:</b> {parcel_txt}\n"
            f"• <b>Cupons:</b> {cupons_txt}",
            parse_mode="html",
        )

    elif comando == "/ranking":
        await event.reply(_formatar_ranking_canais(estado_persistente), parse_mode="html")

    elif comando == "/ultimos":
        await _enviar_ultimos(event.reply, estado_persistente)

    elif comando == "/logs":
        qtd = max(5, min(100, int(argumento))) if argumento.isdigit() else 30
        await _enviar_logs(event.reply, qtd, caminho_log=caminho_log)

    elif comando == "/backup":
        await _enviar_backup(event.reply, bot_client, cfg["MEU_CHAT_ID"], caminho_json=caminho_json)

    elif comando == "/pausar":
        if cmd_original == "/p" and estado_runtime["pausado"] and not argumento:
            estado_runtime["pausado"] = False
            estado_runtime["pausado_ate"] = None
            await event.reply("▶️ Monitoramento retomado!")
        elif argumento:
            if not argumento.isdigit() or not (1 <= int(argumento) <= 1440):
                await event.reply(
                    "⚠️ Informe minutos entre 1 e 1440 (ex.: <code>/pausar 30</code>) ou envie só <code>/pausar</code>.",
                    parse_mode="html",
                )
                return
            minutos = int(argumento)
            estado_runtime["pausado"] = True
            estado_runtime["pausado_ate"] = time.time() + (minutos * 60)
            await event.reply(
                f"⏸️ Monitoramento pausado por <b>{minutos} min</b>. Envie <code>/r</code> para voltar antes.",
                parse_mode="html",
            )
        else:
            estado_runtime["pausado"] = True
            estado_runtime["pausado_ate"] = None
            await event.reply("⏸️ Monitoramento pausado. Envie <code>/p</code> ou <code>/r</code> para voltar.", parse_mode="html")

    elif comando == "/retomar":
        estado_runtime["pausado"] = False
        estado_runtime["pausado_ate"] = None
        await event.reply("▶️ Monitoramento retomado!", parse_mode="html")

    elif comando == "/addcanal":
        if not argumento:
            await event.reply("💡 Use: <code>/ac @canal</code> ou vários: <code>/ac @canal1 @canal2</code>", parse_mode="html")
            return
        _, msg = _executar_add_canal(banco, argumento, caminho_json)
        await event.reply(msg, parse_mode="html")

    elif comando == "/delcanal":
        if not argumento:
            await enviar_em_partes_fn(event.reply, formatar_lista_numerada(banco["canais"], "Canais", "/dc"), parse_mode="html")
            return
        removidos, nao_achados = remover_itens_lista(
            banco["canais"], argumento, case_insensitive=True, normalizar_fn=_normalizar_canal, separar_espacos=True
        )
        if removidos:
            salvar_dados(banco, caminho_json)
        msgs = []
        if removidos:
            msgs.append(f"🗑️ Removido(s): {', '.join(f'<code>{html.escape(x)}</code>' for x in removidos)}")
        if nao_achados:
            msgs.append(f"⚠️ Não encontrado(s): {', '.join(html.escape(x) for x in nao_achados)}")
        await event.reply("\n".join(msgs), parse_mode="html")

    elif comando == "/addpalavra":
        if not argumento:
            await event.reply("💡 Use: <code>/ap termo</code> ou vários: <code>/ap termo1; termo2</code>", parse_mode="html")
            return
        _, msg = _adicionar_regex_lote(banco, "palavras", argumento, caminho_json)
        await event.reply(msg, parse_mode="html")

    elif comando == "/delpalavra":
        if not argumento:
            await enviar_em_partes_fn(event.reply, formatar_lista_numerada(banco["palavras"], "Palavras-Chave", "/dp"), parse_mode="html")
            return
        removidos, nao_achados = remover_itens_lista(banco["palavras"], argumento)
        if removidos:
            altas = banco.get("prioridades", {}).get("palavras_altas", [])
            for r in removidos:
                if r in altas:
                    altas.remove(r)
            salvar_dados(banco, caminho_json)
        msgs = []
        if removidos:
            msgs.append(f"🗑️ Removida(s): {', '.join(f'<code>{html.escape(x)}</code>' for x in removidos)}")
        if nao_achados:
            msgs.append(f"⚠️ Não encontrada(s): {', '.join(html.escape(x) for x in nao_achados)}")
        await event.reply("\n".join(msgs), parse_mode="html")

    elif comando == "/addbloqueio":
        if not argumento:
            await event.reply("💡 Use: <code>/ab termo</code> ou vários: <code>/ab termo1; termo2</code>", parse_mode="html")
            return
        _, msg = _adicionar_regex_lote(banco, "negativas", argumento, caminho_json)
        await event.reply(msg, parse_mode="html")

    elif comando == "/delbloqueio":
        if not argumento:
            await enviar_em_partes_fn(event.reply, formatar_lista_numerada(banco["negativas"], "Bloqueios", "/db"), parse_mode="html")
            return
        removidos, nao_achados = remover_itens_lista(banco["negativas"], argumento)
        if removidos:
            salvar_dados(banco, caminho_json)
        msgs = []
        if removidos:
            msgs.append(f"🗑️ Removido(s): {', '.join(f'<code>{html.escape(x)}</code>' for x in removidos)}")
        if nao_achados:
            msgs.append(f"⚠️ Não encontrado(s): {', '.join(html.escape(x) for x in nao_achados)}")
        await event.reply("\n".join(msgs), parse_mode="html")

    elif comando == "/addteto":
        if not argumento:
            await event.reply("💡 Use: <code>/at placa de vídeo, 400-1300</code> ou <code>/at ssd, 300</code>", parse_mode="html")
            return
        _, msg = _executar_add_teto(banco, argumento, caminho_json)
        await event.reply(msg, parse_mode="html")

    elif comando == "/delteto":
        if not argumento:
            itens = [
                f"{k} ({formatar_faixa_preco(*normalizar_faixa_preco(v))})"
                for k, v in banco["alvos_preco"].items()
            ]
            await enviar_em_partes_fn(event.reply, formatar_lista_numerada(itens, "Tetos Simples", "/dt"), parse_mode="html")
            return
        removidos, nao_achados = remover_chaves_dict(banco["alvos_preco"], argumento)
        if removidos:
            salvar_dados(banco, caminho_json)
        msgs = []
        if removidos:
            msgs.append(f"🗑️ Teto(s) removido(s): {', '.join(f'<code>{html.escape(x)}</code>' for x in removidos)}")
        if nao_achados:
            msgs.append(f"⚠️ Não encontrado(s): {', '.join(html.escape(x) for x in nao_achados)}")
        await event.reply("\n".join(msgs), parse_mode="html")

    elif comando == "/addcomposto":
        if not argumento:
            await event.reply(
                "💡 Use: <code>/ax ram16 | 16gb + ddr4 | notebook, sodimm | 120-220</code>\n"
                "Ou sem exclusões: <code>/ax ssd1tb | ssd + 1tb | 200-380</code>",
                parse_mode="html",
            )
            return
        _, msg = _executar_add_combo(banco, argumento, caminho_json)
        await event.reply(msg, parse_mode="html")

    elif comando == "/delcomposto":
        if not argumento:
            itens = [
                f"{c['nome']} [{' + '.join(c['incluir'])}]"
                for c in banco["alvos_compostos"]
            ]
            await enviar_em_partes_fn(event.reply, formatar_lista_numerada(itens, "Tetos Compostos", "/dx"), parse_mode="html")
            return
        removidos, nao_achados = remover_compostos(banco["alvos_compostos"], argumento)
        if removidos:
            salvar_dados(banco, caminho_json)
        msgs = []
        if removidos:
            msgs.append(f"🗑️ Combo(s) removido(s): {', '.join(f'<code>{html.escape(x)}</code>' for x in removidos)}")
        if nao_achados:
            msgs.append(f"⚠️ Não encontrado(s): {', '.join(html.escape(x) for x in nao_achados)}")
        await event.reply("\n".join(msgs), parse_mode="html")

    elif comando == "/setdesconto":
        if not argumento:
            crit = float(banco.get("desconto_critico", 75) or 75)
            crit_txt = "OFF" if crit >= 100 else f"{crit:.0f}%"
            await event.reply(
                f"📉 Atual: Normal ≥ <b>{banco.get('desconto_minimo', 0):.0f}%</b> | Alta <b>{crit_txt}</b>\n"
                f"Use <code>/sd 65, 75</code> ou <code>/sd 65, off</code> (<code>0</code> desativa).",
                parse_mode="html",
            )
            return
        try:
            tokens = [x.strip() for x in re.split(r"[\s,]+", argumento) if x.strip()]
            min_v = float(tokens[0].replace("%", "").replace(",", "."))
            crit_v = None
            if len(tokens) >= 2:
                crit_v = 100.0 if tokens[1].lower() in ("off", "0") else float(tokens[1].replace("%", "").replace(",", "."))
            _aplicar_setdesconto(banco, min_v, crit_v, caminho_json)
            if banco["desconto_minimo"] == 0:
                await event.reply("🔕 Detector automático de queda de preço desativado.")
            else:
                crit_txt = "OFF (só silenc.)" if banco["desconto_critico"] >= 100 else f"≥ {banco['desconto_critico']:.0f}%"
                await event.reply(
                    f"📉 Queda automática: Normal ≥ <b>{banco['desconto_minimo']:.0f}%</b> | Alta <b>{crit_txt}</b>.",
                    parse_mode="html",
                )
        except Exception:
            await event.reply("⚠️ Use <code>/sd 65</code> ou <code>/sd 65, 75</code> (<code>0</code> desativa).", parse_mode="html")

    elif comando == "/dnd":
        dnd = banco.setdefault("nao_perturbe", {"ativo": True, "inicio": 0, "fim": 7})
        arg = argumento.lower()
        if not arg:
            texto, spec = montar_painel_dnd_spec(banco)
            await event.reply(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
        elif arg in ("off", "desativar", "0"):
            dnd["ativo"] = False
            salvar_dados(banco, caminho_json)
            await event.reply("☀️ Modo Não Perturbe desativado.")
        elif arg in ("on", "ativar"):
            dnd["ativo"] = True
            salvar_dados(banco, caminho_json)
            await event.reply(f"🌙 Modo Não Perturbe ativado: <b>{dnd['inicio']:02d}h às {dnd['fim']:02d}h</b>.", parse_mode="html")
        else:
            m = re.match(r"^(\d{1,2})(?:h|:00)?\s*(?:-|a|às|as|\s)\s*(\d{1,2})(?:h|:00)?$", arg)
            if not m:
                await event.reply("⚠️ Use <code>/dnd 0-7</code>, <code>/dnd 23-7</code> ou <code>/dnd off</code>.", parse_mode="html")
                return
            ini, fim = int(m.group(1)), int(m.group(2))
            if not (0 <= ini <= 23 and 0 <= fim <= 23):
                await event.reply("⚠️ Horas devem estar entre 0 e 23.")
                return
            dnd.update({"ativo": True, "inicio": ini, "fim": fim})
            salvar_dados(banco, caminho_json)
            await event.reply(f"🌙 Modo Não Perturbe ativado: <b>{ini:02d}h às {fim:02d}h</b>.", parse_mode="html")

    elif comando == "/filtro":
        filtros = banco.setdefault("filtros_extras", {"bloquear_usados": False, "bloquear_importacao": False})
        tokens = argumento.lower().split()
        if not tokens:
            await event.reply(
                f"🧹 <b>Filtros Extras</b>\n"
                f"• Usados/recondicionados: <b>{'ON' if filtros.get('bloquear_usados') else 'OFF'}</b>\n"
                f"• Compra internacional: <b>{'ON' if filtros.get('bloquear_importacao') else 'OFF'}</b>\n\n"
                f"Use: <code>/filtro usados on</code> ou <code>/filtro importacao off</code>",
                parse_mode="html",
            )
            return
        alvo = tokens[0]
        ligar = (tokens[1] in ("on", "1", "sim", "ativar")) if len(tokens) > 1 else None
        if alvo.startswith("usad"):
            novo = (not filtros.get("bloquear_usados")) if ligar is None else ligar
            filtros["bloquear_usados"] = novo
            salvar_dados(banco, caminho_json)
            await event.reply(f"🧹 Bloqueio de usados/recondicionados: <b>{'ON' if novo else 'OFF'}</b>", parse_mode="html")
        elif alvo.startswith("import"):
            novo = (not filtros.get("bloquear_importacao")) if ligar is None else ligar
            filtros["bloquear_importacao"] = novo
            salvar_dados(banco, caminho_json)
            await event.reply(f"🧹 Bloqueio de compra internacional: <b>{'ON' if novo else 'OFF'}</b>", parse_mode="html")
        else:
            await event.reply("⚠️ Use <code>/filtro usados on|off</code> ou <code>/filtro importacao on|off</code>.", parse_mode="html")

    elif comando == "/resumo":
        arg = argumento.lower()
        if not arg:
            h = banco.get("resumo_hora")
            txt = f"{int(h):02d}:00" if h is not None and int(h) >= 0 else "OFF"
            await event.reply(f"📊 Resumo diário automático: <b>{txt}</b>\nUse <code>/resumo 21</code> ou <code>/resumo off</code>.", parse_mode="html")
        elif arg in ("off", "desativar"):
            banco["resumo_hora"] = None
            salvar_dados(banco, caminho_json)
            await event.reply("🔕 Resumo diário automático desativado.")
        elif arg.isdigit() and 0 <= int(arg) <= 23:
            banco["resumo_hora"] = int(arg)
            salvar_dados(banco, caminho_json)
            await event.reply(f"📊 Resumo diário agendado para as <b>{int(arg):02d}:00</b>.", parse_mode="html")
        else:
            await event.reply("⚠️ Informe uma hora de 0 a 23 (ex.: <code>/resumo 21</code>) ou <code>off</code>.", parse_mode="html")

    elif comando == "/buscar":
        if not argumento:
            await event.reply("🔎 Use: <code>/buscar amazon</code> ou <code>/buscar ssd</code>", parse_mode="html")
            return
        termo = argumento.lower()
        achados = [
            i for i in reversed(estado_persistente.get("ultimos", []))
            if termo in " ".join(str(i.get(k) or "") for k in ("loja", "motivo", "grupo", "link")).lower()
        ]
        if not achados:
            await event.reply("📭 Nada encontrado nos últimos alertas.")
        else:
            linhas = [f"🔎 <b>{len(achados)} resultado(s) para</b> <code>{html.escape(termo)}</code>\n"]
            for i, it in enumerate(achados[:10], 1):
                linhas.append(
                    f"{i}. <b>{html.escape(it.get('hora', '--:--'))}</b> [{html.escape(it.get('loja') or 'Link')}] "
                    f"<i>{html.escape(it.get('motivo', ''))}</i>\n   {html.escape(it.get('link') or '')}"
                )
            await enviar_em_partes_fn(event.reply, "\n".join(linhas), parse_mode="html")

    else:
        sugestao = difflib.get_close_matches(comando, sorted(COMANDOS_CONHECIDOS), n=1, cutoff=0.6)
        dica = f" Você quis dizer <code>{sugestao[0]}</code>?" if sugestao else ""
        await event.reply(
            f"❓ Comando desconhecido: <code>{html.escape(cmd_original)}</code>.{dica}\nEnvie /ajuda para ver a lista.",
            parse_mode="html",
        )


async def _substituir_botao_alerta(event, novo_rotulo):
    """Troca o botão inline clicado no alerta por um rótulo informativo."""
    try:
        msg_orig = await event.get_message()
        novos_botoes = []
        for linha in msg_orig.buttons or []:
            nova_linha = []
            for btn in linha:
                if getattr(btn, "data", b"") == event.data:
                    nova_linha.append(Button.inline(novo_rotulo, b"noop"))
                else:
                    nova_linha.append(btn)
            novos_botoes.append(nova_linha)
        if novos_botoes:
            await event.edit(buttons=novos_botoes)
    except Exception:
        pass


def _parar_monitorar_por_hash(banco, codigo_tipo, hash_alvo, caminho_json=ARQUIVO_JSON):
    """Remove palavra, teto ou combo pelo código de tipo e hash curto do alvo."""
    if codigo_tipo == "p":
        alvo = next((p for p in banco.get("palavras", []) if hash_curto_chave(p) == hash_alvo), None)
        if not alvo:
            return None
        banco["palavras"].remove(alvo)
        altas = banco.get("prioridades", {}).get("palavras_altas", [])
        if alvo in altas:
            altas.remove(alvo)
        salvar_dados(banco, caminho_json)
        return alvo

    if codigo_tipo == "t":
        alvo = next((k for k in banco.get("alvos_preco", {}) if hash_curto_chave(k) == hash_alvo), None)
        if not alvo:
            return None
        del banco["alvos_preco"][alvo]
        salvar_dados(banco, caminho_json)
        return alvo

    if codigo_tipo == "c":
        alvo = next((c for c in banco.get("alvos_compostos", []) if hash_curto_chave(c["nome"]) == hash_alvo), None)
        if not alvo:
            return None
        banco["alvos_compostos"].remove(alvo)
        salvar_dados(banco, caminho_json)
        return alvo["nome"]

    return None


def _remover_item_wizard(banco, cat_codigo, idx, caminho_json=ARQUIVO_JSON):
    """Remove um item pelo índice dentro da categoria do assistente ➖ Remover."""
    removido = None
    if cat_codigo == "p":
        lista = banco.get("palavras", [])
        if 0 <= idx < len(lista):
            removido = lista.pop(idx)
            altas = banco.get("prioridades", {}).get("palavras_altas", [])
            if removido in altas:
                altas.remove(removido)
    elif cat_codigo == "t":
        chaves = list(banco.get("alvos_preco", {}).keys())
        if 0 <= idx < len(chaves):
            removido = chaves[idx]
            del banco["alvos_preco"][removido]
    elif cat_codigo == "c":
        lista = banco.get("alvos_compostos", [])
        if 0 <= idx < len(lista):
            removido = lista.pop(idx)["nome"]
    elif cat_codigo == "g":
        lista = banco.get("canais", [])
        if 0 <= idx < len(lista):
            removido = lista.pop(idx)
    elif cat_codigo == "b":
        lista = banco.get("negativas", [])
        if 0 <= idx < len(lista):
            removido = lista.pop(idx)

    if removido is not None:
        salvar_dados(banco, caminho_json)
    return removido


async def processar_callback_painel(
    event,
    banco,
    cfg,
    estado_runtime,
    estado_persistente,
    mapa_silenciar,
    bot_client=None,
    caminho_json=ARQUIVO_JSON,
    caminho_estado=ARQUIVO_ESTADO,
    caminho_log=ARQUIVO_LOG,
):
    """Processa todos os cliques em botões inline (silenciar, parar, wizard, menu e prioridades)."""
    if event.sender_id != cfg["MEU_CHAT_ID"]:
        await event.answer("Não autorizado.", alert=True)
        return

    data = (event.data or b"").decode("utf-8", errors="ignore")
    if data == "noop":
        await event.answer("Botão informativo.")
        return

    async def send_chat(texto, **kwargs):
        if bot_client is not None:
            return await bot_client.send_message(cfg["MEU_CHAT_ID"], texto, **kwargs)
        return await event.respond(texto, **kwargs)

    # 1. Silenciar produto por 3h direto do alerta
    if data.startswith("sil:"):
        hash_curto = data.split(":", 1)[1]
        ttl_silencio = int(cfg["TEMPO_SILENCIO_HORAS"] * 3600)
        chave_orig = mapa_silenciar.get(hash_curto)
        if chave_orig:
            registrar_historico(estado_persistente, chave_orig, ttl_silencio, caminho_estado)
        registrar_historico(estado_persistente, f"sil_hash:{hash_curto}", ttl_silencio, caminho_estado)

        await _substituir_botao_alerta(event, f"✅ Silenciado por {cfg['TEMPO_SILENCIO_HORAS']:g}h")
        await event.answer(f"🤫 Produto silenciado por {cfg['TEMPO_SILENCIO_HORAS']:g}h!")
        logger.info("Produto silenciado manualmente via botão (hash=%s, chave=%s).", hash_curto, chave_orig)
        return

    # 1b. Parar de monitorar o gatilho direto do alerta
    if data.startswith("stop:"):
        partes = data.split(":")
        if len(partes) == 3:
            removido = _parar_monitorar_por_hash(banco, partes[1], partes[2], caminho_json)
            if removido:
                await _substituir_botao_alerta(event, f"✅ Parou de monitorar: {removido[:20]}")
                await event.answer(f"🔕 Parou de monitorar: {removido}")
                logger.info("Gatilho removido pelo botão do alerta: %s (%s)", removido, partes[1])
            else:
                await _substituir_botao_alerta(event, "✅ Já removido")
                await event.answer("Esse gatilho já havia sido removido.")
        return

    # 1c. Fluxos interativos Adicionar / Remover (wiz:*)
    if data.startswith("wiz:"):
        partes = data.split(":")
        sub = partes[1]

        if sub == "cancel":
            estado_runtime["aguardando"] = None
            estado_runtime["aguardando_ate"] = None
            await event.edit("❌ Operação cancelada.", buttons=None)
            await event.answer("Cancelado")
            return

        if sub == "rem":
            estado_runtime["aguardando"] = None
            estado_runtime["aguardando_ate"] = None
            titulo, spec = montar_wizard_categoria_spec("rem")
            await event.edit(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))
            await event.answer()
            return

        if sub == "add" and len(partes) >= 3:
            cat = partes[2]
            if cat in WIZARD_CATEGORIAS:
                tipo_nome, _ = WIZARD_CATEGORIAS[cat]
                estado_runtime["aguardando"] = f"add:{tipo_nome}"
                estado_runtime["aguardando_ate"] = time.time() + 300
                await event.edit(
                    PROMPTS_ADICIONAR[tipo_nome],
                    parse_mode="html",
                    buttons=converter_botoes_telethon([[("inline", "❌ Cancelar", "wiz:cancel")]]),
                )
            await event.answer()
            return

        if sub == "delcat" and len(partes) >= 3:
            cat = partes[2]
            pagina = int(partes[3]) if len(partes) >= 4 else 0
            titulo, spec = montar_wizard_remover_itens_spec(banco, cat, pagina)
            await event.edit(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))
            await event.answer()
            return

        if sub == "del" and len(partes) >= 5:
            cat, idx, pagina = partes[2], int(partes[3]), int(partes[4])
            removido = _remover_item_wizard(banco, cat, idx, caminho_json)
            titulo, spec = montar_wizard_remover_itens_spec(banco, cat, pagina)
            try:
                await event.edit(titulo, parse_mode="html", buttons=converter_botoes_telethon(spec))
            except Exception:
                pass
            await event.answer(f"🗑️ Removido: {removido}" if removido else "Item não encontrado")
            return

    # 2. Ações do /menu
    if data.startswith("menu:"):
        acao = data.split(":", 1)[1]
        atualizar_menu = False
        toast = "Atualizado!"

        if acao == "home":
            atualizar_menu = True
        elif acao == "pausa":
            estado_runtime["pausado"] = not estado_runtime["pausado"]
            estado_runtime["pausado_ate"] = None
            atualizar_menu = True
            toast = "⏸️ Pausado!" if estado_runtime["pausado"] else "▶️ Retomado!"
        elif acao == "dnd":
            dnd = banco.setdefault("nao_perturbe", {"ativo": True, "inicio": 0, "fim": 7})
            dnd["ativo"] = not dnd.get("ativo", False)
            salvar_dados(banco, caminho_json)
            atualizar_menu = True
            toast = f"🌙 DND {'ativado' if dnd['ativo'] else 'desativado'}!"
        elif acao == "usados":
            flt = banco.setdefault("filtros_extras", {"bloquear_usados": False, "bloquear_importacao": False})
            flt["bloquear_usados"] = not flt.get("bloquear_usados", False)
            salvar_dados(banco, caminho_json)
            atualizar_menu = True
            toast = f"🧹 Filtro usados {'ON' if flt['bloquear_usados'] else 'OFF'}"
        elif acao == "import":
            flt = banco.setdefault("filtros_extras", {"bloquear_usados": False, "bloquear_importacao": False})
            flt["bloquear_importacao"] = not flt.get("bloquear_importacao", False)
            salvar_dados(banco, caminho_json)
            atualizar_menu = True
            toast = f"✈️ Filtro importação {'ON' if flt['bloquear_importacao'] else 'OFF'}"
        elif acao == "limpar_snooze":
            estado_runtime.setdefault("snooze_lojas", {}).clear()
            atualizar_menu = True
            toast = "🔔 Snoozes limpos!"
        elif acao == "lista":
            await event.answer()
            await enviar_em_partes_fn(send_chat, _formatar_lista_painel(banco, estado_runtime), parse_mode="html")
            return
        elif acao == "status":
            await event.answer()
            await send_chat(_formatar_texto_status(banco, cfg, estado_runtime, estado_persistente), parse_mode="html")
            return
        elif acao == "teste":
            await event.answer("Executando teste...")
            await _executar_teste_sistema(send_chat, cfg)
            return
        elif acao == "ultimos":
            await event.answer()
            await _enviar_ultimos(send_chat, estado_persistente)
            return
        elif acao == "logs":
            await event.answer()
            await _enviar_logs(send_chat, 30, caminho_log=caminho_log)
            return
        elif acao == "backup":
            await event.answer()
            await _enviar_backup(send_chat, bot_client, cfg["MEU_CHAT_ID"], caminho_json=caminho_json)
            return
        elif acao == "ajuda":
            await event.answer()
            await send_chat(_formatar_texto_ajuda(), parse_mode="html")
            return

        if atualizar_menu:
            texto, spec = montar_painel_menu_spec(banco, estado_runtime, estado_persistente)
            try:
                await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
            except Exception:
                pass
            await event.answer(toast)
        return

    # 2b. Ações visuais de Não Perturbe (/dnd)
    if data.startswith("dnd:"):
        partes = data.split(":")
        sub = partes[1]
        dnd = banco.setdefault("nao_perturbe", {"ativo": True, "inicio": 0, "fim": 7})
        toast = "Atualizado!"

        if sub == "main":
            texto, spec = montar_painel_dnd_spec(banco)
            try:
                await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
            except Exception:
                pass
            await event.answer()
            return

        if sub == "toggle":
            dnd["ativo"] = not dnd.get("ativo", False)
            toast = f"🌙 DND {'ativado' if dnd['ativo'] else 'desativado'}!"
        elif sub == "ini" and len(partes) >= 3:
            delta = int(partes[2])
            dnd["inicio"] = (int(dnd.get("inicio", 0)) + delta) % 24
            toast = f"Início: {dnd['inicio']:02d}h"
        elif sub == "fim" and len(partes) >= 3:
            delta = int(partes[2])
            dnd["fim"] = (int(dnd.get("fim", 7)) + delta) % 24
            toast = f"Fim: {dnd['fim']:02d}h"
        elif sub == "set" and len(partes) >= 4:
            ini, fim = int(partes[2]), int(partes[3])
            if 0 <= ini <= 23 and 0 <= fim <= 23:
                dnd.update({"ativo": True, "inicio": ini, "fim": fim})
                toast = f"🌙 {ini:02d}h–{fim:02d}h ativado!"

        salvar_dados(banco, caminho_json)
        texto, spec = montar_painel_dnd_spec(banco)
        try:
            await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
        except Exception:
            pass
        await event.answer(toast)
        return

    # 3. Ações de Prioridades e Faixas (/prioridade)
    if data.startswith("prio:"):
        partes = data.split(":")
        sub = partes[1]
        prio = banco.setdefault("prioridades", {"teto": "alta", "combo": "alta", "palavras_altas": []})
        toast = "Atualizado!"

        if sub == "main":
            texto, spec = montar_painel_prioridades_spec(banco)
            await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
            await event.answer()
            return

        if sub in ("teto", "combo"):
            novo = "normal" if prio.get(sub, "alta") == "alta" else "alta"
            prio[sub] = novo
            salvar_dados(banco, caminho_json)
            toast = f"{sub.capitalize()}: {novo.upper()}"
        elif sub == "dmin":
            delta = int(partes[2])
            atual = float(banco.get("desconto_minimo", 65) or 0)
            crit = float(banco.get("desconto_critico", 75) or 75)
            if delta > 0 and atual == 0:
                novo_min = min(50.0, crit)
            else:
                novo_min = max(0.0, min(95.0, atual + delta))
            novo_crit = max(novo_min, crit) if novo_min > 0 else crit
            _aplicar_setdesconto(banco, novo_min, novo_crit, caminho_json)
            toast = f"Normal: {novo_min:.0f}%" if novo_min > 0 else "Queda automática OFF"
        elif sub == "dcrit":
            delta = int(partes[2])
            atual_min = float(banco.get("desconto_minimo", 65) or 0)
            atual_crit = float(banco.get("desconto_critico", 75) or 75)
            novo_crit = max(atual_min, min(100.0, atual_crit + delta))
            _aplicar_setdesconto(banco, atual_min, novo_crit, caminho_json)
            toast = "Alta em quedas OFF" if novo_crit >= 100 else f"Alta: ≥ {novo_crit:.0f}%"
        elif sub == "pal":
            pagina = int(partes[2])
            texto, spec = montar_painel_palavras_prio_spec(banco, pagina)
            await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
            await event.answer()
            return
        elif sub == "w":
            idx = int(partes[2])
            pagina = int(partes[3])
            palavras = banco.get("palavras", [])
            if 0 <= idx < len(palavras):
                palavra = palavras[idx]
                novo = alternar_prioridade_palavra(banco, palavra)
                salvar_dados(banco, caminho_json)
                toast = f"{palavra}: {'🔴 ALTA' if novo == 'alta' else '🟡 NORMAL'}"
            texto, spec = montar_painel_palavras_prio_spec(banco, pagina)
            try:
                await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
            except Exception:
                pass
            await event.answer(toast)
            return

        texto, spec = montar_painel_prioridades_spec(banco)
        try:
            await event.edit(texto, parse_mode="html", buttons=converter_botoes_telethon(spec))
        except Exception:
            pass
        await event.answer(toast)


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


async def _enviar_alerta_telegram(
    bot_client,
    user_client,
    event_origem,
    chat_id_destino,
    mensagem,
    legenda_foto,
    botoes,
    silencioso,
):
    """Envia alerta com a foto original (se houver) ou mensagem HTML, com fallback seguro."""
    foto = getattr(event_origem, "photo", None)
    if foto:
        try:
            buf = io.BytesIO()
            await user_client.download_media(foto, file=buf)
            if buf.tell() > 0:
                buf.seek(0)
                buf.name = "oferta.jpg"
                sent = await bot_client.send_file(
                    chat_id_destino,
                    buf,
                    caption=legenda_foto,
                    parse_mode="html",
                    buttons=botoes,
                    silent=silencioso,
                )
                return sent, True
        except Exception as err:
            logger.warning("Falha ao enviar foto (%s); enviando como texto.", err)

    try:
        sent = await bot_client.send_message(
            chat_id_destino,
            mensagem,
            parse_mode="html",
            link_preview=False,
            buttons=botoes,
            silent=silencioso,
        )
        return sent, False
    except Exception as err:
        logger.error("Erro ao enviar alerta HTML (%s); tentando texto simples.", err)
        sent = await bot_client.send_message(
            chat_id_destino,
            re.sub(r"<[^>]+>", "", mensagem),
            link_preview=False,
            silent=silencioso,
        )
        return sent, False


async def _persistir_estado_async(estado_persistente, caminho_estado=ARQUIVO_ESTADO, lock=None):
    """Gera cópia isolada do estado no event loop e grava em disco via thread sem bloquear."""
    if lock is None:
        snapshot = gerar_snapshot_estado(estado_persistente)
        await asyncio.to_thread(salvar_estado_persistente, snapshot, caminho_estado)
        return
    async with lock:
        snapshot = gerar_snapshot_estado(estado_persistente)
        await asyncio.to_thread(salvar_estado_persistente, snapshot, caminho_estado)


async def _enriquecer_alerta_vago(sent_msg, foi_foto, contexto_msg):
    """Para posts vagos, busca o título real da página e edita o alerta logo após o envio."""
    url = contexto_msg.get("link_oferta")
    if not url:
        return
    try:
        meta = await asyncio.to_thread(buscar_metadados_pagina, url)
        titulo = meta.get("titulo")
        preco = meta.get("preco")
        mostrar_buscando = bool(contexto_msg.get("buscando_titulo"))
        if not titulo and not preco and not mostrar_buscando:
            return

        url_comp = contexto_msg.get("url_comparacao") or gerar_url_comparacao(
            contexto_msg["info_produto"],
            titulo or contexto_msg["texto_bruto"],
            url,
        )
        msg_nova, legenda_nova, botoes_spec = montar_mensagem_e_botoes_spec(
            nome_grupo=contexto_msg["nome_grupo"],
            motivo_disparo=contexto_msg["motivo_disparo"],
            prioridade=contexto_msg["prioridade"],
            texto_bruto=contexto_msg["texto_bruto"],
            cupons=contexto_msg["cupons"],
            info_produto=contexto_msg["info_produto"],
            link_oferta=url,
            link_origem=contexto_msg["link_origem"],
            links_extras=contexto_msg["links_extras"],
            texto_recuperado=contexto_msg["texto_recuperado"],
            titulo_detectado=titulo,
            preco_detectado=preco,
            url_comparacao=url_comp,
            chave_silenciar=contexto_msg["chave_curta"],
            tipo_gatilho=contexto_msg.get("tipo_gatilho"),
            alvo_gatilho=contexto_msg.get("alvo_gatilho"),
            buscando_titulo=False,
        )
        await sent_msg.edit(
            legenda_nova if foi_foto else msg_nova,
            parse_mode="html",
            buttons=converter_botoes_telethon(botoes_spec),
            link_preview=False,
        )
        if titulo or preco:
            logger.info("Alerta vago atualizado com título: %s", titulo)
        else:
            logger.debug("Aviso de carregamento removido de alerta vago sem metadados.")
    except Exception as err:
        logger.debug("Não foi possível editar alerta vago: %s", err)


async def _loop_resumo_diario(
    bot_client,
    cfg,
    banco,
    estado_persistente,
    save_lock=None,
    caminho_estado=ARQUIVO_ESTADO,
):
    """Envia o resumo diário automaticamente no horário configurado sem bloquear o event loop."""
    while True:
        try:
            await asyncio.sleep(30)
            resumo_hora = banco.get("resumo_hora")
            if resumo_hora is None or int(resumo_hora) < 0:
                continue

            agora_dt = datetime.datetime.now()
            hoje = agora_dt.date().isoformat()

            if agora_dt.hour == int(resumo_hora) and estado_persistente.get("ultimo_resumo_data") != hoje:
                stats_atual = estado_persistente.get("stats_dia", {})
                data_ant = stats_atual.get("data", "")
                if int(resumo_hora) == 0 and data_ant and data_ant != hoje:
                    data_fmt = datetime.date.fromisoformat(data_ant).strftime("%d/%m/%Y")
                    texto = formatar_resumo_diario(stats_atual, data_fmt)
                    garantir_stats_do_dia(estado_persistente, hoje)
                else:
                    stats = garantir_stats_do_dia(estado_persistente, hoje)
                    texto = formatar_resumo_diario(stats, agora_dt.strftime("%d/%m/%Y"))
                await bot_client.send_message(cfg["MEU_CHAT_ID"], texto, parse_mode="html", silent=True)
                estado_persistente["ultimo_resumo_data"] = hoje
                await _persistir_estado_async(estado_persistente, caminho_estado, save_lock)
                logger.info("Resumo diário enviado (%s).", hoje)
            else:
                garantir_stats_do_dia(estado_persistente, hoje)
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.warning("Erro no loop de resumo diário: %s", err)


async def _loop_backup_semanal(
    bot_client,
    cfg,
    estado_persistente,
    save_lock=None,
    caminho_json=ARQUIVO_JSON,
    caminho_estado=ARQUIVO_ESTADO,
    dias=7,
):
    """Envia o banco_de_dados.json ao chat automaticamente a cada N dias."""
    while True:
        try:
            await asyncio.sleep(3600)
            if time.time() - estado_persistente.get("ultimo_backup_ts", 0.0) >= dias * 86400 and os.path.exists(caminho_json):
                await bot_client.send_file(
                    cfg["MEU_CHAT_ID"],
                    caminho_json,
                    caption="💾 Backup semanal automático (envie este .json aqui para restaurar).",
                    silent=True,
                )
                estado_persistente["ultimo_backup_ts"] = time.time()
                await _persistir_estado_async(estado_persistente, caminho_estado, save_lock)
                logger.info("Backup semanal automático enviado.")
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.warning("Erro no backup semanal: %s", err)


async def _loop_sentinela(bot_client, cfg, banco, estado_runtime, limite_horas=3.0, intervalo=300):
    """Avisa se nenhuma mensagem dos canais monitorados chegou há muito tempo."""
    avisado = False
    while True:
        try:
            await asyncio.sleep(intervalo)
            agora = time.time()
            if estado_runtime.get("pausado") or eh_horario_dnd(banco.get("nao_perturbe")):
                estado_runtime["ultima_leitura"] = agora
                avisado = False
                continue
            parado_h = (agora - estado_runtime.get("ultima_leitura", agora)) / 3600.0
            if parado_h >= limite_horas and not avisado:
                await bot_client.send_message(
                    cfg["MEU_CHAT_ID"],
                    f"⚠️ <b>Sentinela:</b> nenhuma mensagem dos canais monitorados há <b>{parado_h:.1f} h</b>.\n"
                    "Verifique a internet, a sessão do Telegram ou se os canais continuam ativos (use /ping).",
                    parse_mode="html",
                )
                avisado = True
            elif parado_h < limite_horas:
                avisado = False
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.warning("Erro no loop da sentinela: %s", err)


async def _loop_digest_dnd(bot_client, cfg, banco, estado_runtime, intervalo=60):
    """Quando o DND termina, envia silenciosamente um resumo das ofertas normais seguradas."""
    while True:
        try:
            await asyncio.sleep(intervalo)
            adiados = estado_runtime.get("adiados")
            if not adiados or eh_horario_dnd(banco.get("nao_perturbe")):
                continue
            itens = list(adiados)
            linhas = [f"🌅 <b>Digest do Não Perturbe</b> — {len(itens)} oferta(s) segurada(s):\n"]
            for i, it in enumerate(itens[-15:], 1):
                link = f"\n   {html.escape(it['link'])}" if it.get("link") else ""
                linhas.append(
                    f"{i}. <b>{html.escape(it['hora'])}</b> [{html.escape(it['grupo'])}] "
                    f"<i>{html.escape(it['motivo'])}</i>\n   {html.escape(it['trecho'])}{link}"
                )
            if len(itens) > 15:
                linhas.append(f"\n<i>(+ {len(itens) - 15} oferta(s) mais antigas omitidas)</i>")

            async def enviar(texto, **kwargs):
                return await bot_client.send_message(
                    cfg["MEU_CHAT_ID"], texto, silent=True, link_preview=False, **kwargs
                )

            await enviar_em_partes_fn(enviar, "\n".join(linhas))
            del adiados[: len(itens)]
        except asyncio.CancelledError:
            break
        except Exception as err:
            logger.warning("Erro no digest do DND: %s", err)


async def registrar_comandos_telegram(bot_client):
    """Registra o menu '/' nativo do Telegram com descrições dos comandos."""
    comandos = [types.BotCommand(command=cmd, description=desc) for cmd, desc in COMANDOS_BOT_MENU]
    try:
        await bot_client(
            functions.bots.SetBotCommandsRequest(
                scope=types.BotCommandScopeDefault(),
                lang_code="",
                commands=comandos,
            )
        )
        logger.info("Menu de comandos '/' registrado no Telegram (%d comandos).", len(comandos))
    except Exception as err:
        logger.warning("Não foi possível registrar menu '/' no Telegram: %s", err)


async def processar_mensagem_cacador(
    event,
    user_client,
    bot_client,
    cfg,
    banco,
    estado_runtime,
    estado_persistente,
    memoria_canais,
    mapa_silenciar,
    caminho_estado=ARQUIVO_ESTADO,
):
    """Processa uma mensagem/edição recebida de canal monitorado."""
    _verificar_auto_retomar(estado_runtime)
    if estado_runtime.get("pausado") or getattr(event, "is_private", False) or getattr(event, "out", False):
        return

    texto_bruto = getattr(event, "raw_text", None) or ""
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
    stats = garantir_stats_do_dia(estado_persistente)
    stats["mensagens_lidas"] += 1
    estado_runtime["ultima_leitura"] = agora

    nome_grupo = getattr(chat, "title", canal_username or chat_id)
    reg_canal = estado_persistente.setdefault("por_canal", {}).setdefault(nome_grupo, {"lidas": 0, "alertas": 0})
    reg_canal["lidas"] += 1

    links_atuais = extrair_links_mensagem(
        texto_bruto, getattr(event, "entities", None), text_url_cls=MessageEntityTextUrl
    )
    if links_atuais:
        memoria_canais[chat_id] = {"raw_text": texto_bruto, "links": links_atuais, "tempo": agora}
        chaves_expiradas = [k for k, v in memoria_canais.items() if (agora - v["tempo"]) > 300]
        for k in chaves_expiradas:
            del memoria_canais[k]

    avaliacao = avaliar_gatilhos(texto_bruto, banco)
    if not avaliacao["disparar"]:
        if avaliacao["bloqueado_por"]:
            stats["bloqueios_negativos"] += 1
        logger.info("Ignorado [%s]: %s | trecho=%r", nome_grupo, avaliacao["motivo"], texto_bruto[:80])
        return

    prioridade = avaliacao["prioridade"]
    motivo = avaliacao["motivo"]

    if prioridade != "alta" and eh_horario_dnd(banco.get("nao_perturbe")):
        stats["bloqueios_dnd"] += 1
        logger.info("Silenciado pelo DND [%s]: %s", nome_grupo, motivo)
        adiados = estado_runtime.setdefault("adiados", [])
        trecho = " ".join(texto_bruto.split())[:120]
        if not any(a["trecho"][:60] == trecho[:60] for a in adiados):
            if len(adiados) >= 30:
                del adiados[0]
            adiados.append({
                "hora": datetime.datetime.now().strftime("%H:%M"),
                "grupo": nome_grupo,
                "motivo": motivo,
                "trecho": trecho,
                "link": escolher_link_oferta(links_atuais),
            })
        return

    link_para_abrir, link_bruto, info_produto, links_combinados, texto_recuperado = (
        await _resolver_link_e_produto(links_atuais, chat_id, agora, memoria_canais)
    )

    loja_pausada = loja_em_snooze(
        info_produto,
        link_para_abrir or link_bruto,
        estado_runtime.get("snooze_lojas", {}),
        agora,
    )
    if loja_pausada:
        logger.info("Snooze ativo [%s] para loja '%s': %s", nome_grupo, loja_pausada, motivo)
        return

    chave_unica = montar_chave_duplicata(info_produto, link_para_abrir or link_bruto, motivo, texto_bruto)
    chave_alta = f"{chave_unica}#alta"
    chave_curto = hash_curto_chave(chave_unica)
    chave_checagem = chave_alta if prioridade == "alta" else chave_unica
    if esta_no_historico(estado_persistente, chave_checagem, agora) or esta_no_historico(
        estado_persistente, f"sil_hash:{chave_curto}", agora
    ):
        stats["duplicatas_barradas"] += 1
        logger.info("Duplicata/silenciada ignorada [%s]: chave=%s (%s)", nome_grupo, chave_checagem, motivo)
        return

    registrar_historico(
        estado_persistente,
        chave_unica,
        cfg["TEMPO_DUPLICATA"],
        caminho_estado,
        agora,
        salvar=False,
    )
    if prioridade == "alta":
        registrar_historico(
            estado_persistente,
            chave_alta,
            cfg["TEMPO_DUPLICATA"],
            caminho_estado,
            agora,
            salvar=False,
        )
    if chave_curto in mapa_silenciar:
        del mapa_silenciar[chave_curto]
    elif len(mapa_silenciar) >= 1000:
        del mapa_silenciar[next(iter(mapa_silenciar))]
    mapa_silenciar[chave_curto] = chave_unica

    if username:
        link_origem = f"https://t.me/{username}/{event.id}"
    else:
        chat_id_limpo = str(event.chat_id).removeprefix("-100")
        link_origem = f"https://t.me/c/{chat_id_limpo}/{event.id}"

    cupons = extrair_cupons(f"{texto_bruto}\n{texto_recuperado or ''}")
    url_comparacao = gerar_url_comparacao(info_produto, texto_bruto, link_para_abrir)
    buscando_titulo = alerta_eh_vago(texto_bruto) and bool(link_para_abrir)
    mensagem, legenda_foto, botoes_spec = montar_mensagem_e_botoes_spec(
        nome_grupo=nome_grupo,
        motivo_disparo=motivo,
        prioridade=prioridade,
        texto_bruto=texto_bruto,
        cupons=cupons,
        info_produto=info_produto,
        link_oferta=link_para_abrir,
        link_origem=link_origem,
        links_extras=links_combinados,
        texto_recuperado=texto_recuperado,
        url_comparacao=url_comparacao,
        chave_silenciar=chave_curto,
        tipo_gatilho=avaliacao.get("tipo_gatilho"),
        alvo_gatilho=avaliacao.get("alvo_gatilho"),
        buscando_titulo=buscando_titulo,
    )
    botoes = converter_botoes_telethon(botoes_spec)
    silencioso = prioridade != "alta"

    logger.info(
        "DISPARO [%s] prio=%s motivo=%s chave=%s loja=%s link=%s cupons=%s",
        nome_grupo, prioridade, motivo, chave_unica, info_produto.get("loja"), link_para_abrir, cupons,
    )

    if prioridade == "alta" and cfg["URL_MACRODROID"] and link_para_abrir:
        if not host_confiavel(link_para_abrir):
            logger.warning("MacroDroid bloqueado: host não confiável (%s)", link_para_abrir)
        elif (agora - estado_runtime.get("ultimo_disparo", 0.0)) >= cfg["TEMPO_DE_ESPERA"]:
            cooldown_anterior = estado_runtime.get("ultimo_disparo", 0.0)
            estado_runtime["ultimo_disparo"] = agora
            _agendar_bg(
                _acionar_macrodroid(cfg["URL_MACRODROID"], link_para_abrir, estado_runtime, cooldown_anterior, agora)
            )
            await asyncio.sleep(0)

    try:
        sent_msg, foi_foto = await _enviar_alerta_telegram(
            bot_client, user_client, event, cfg["MEU_CHAT_ID"], mensagem, legenda_foto, botoes, silencioso
        )
    except Exception:
        dedup = estado_persistente.get("dedup", {})
        dedup.pop(chave_unica, None)
        dedup.pop(chave_alta, None)
        logger.exception("Falha ao entregar alerta [%s] (%s); chave de duplicata liberada.", nome_grupo, motivo)
        return

    stats["alertas_enviados"] += 1
    reg_canal["alertas"] += 1
    registrar_alerta_enviado(
        estado_persistente,
        {
            "hora": datetime.datetime.now().strftime("%H:%M"),
            "grupo": nome_grupo,
            "loja": info_produto.get("loja"),
            "motivo": motivo,
            "prioridade": prioridade,
            "link": link_para_abrir or link_origem,
        },
        caminho_estado,
        salvar=False,
    )
    await _persistir_estado_async(estado_persistente, caminho_estado, estado_runtime.get("save_lock"))

    if buscando_titulo and sent_msg is not None:
        _agendar_bg(
            _enriquecer_alerta_vago(
                sent_msg,
                foi_foto,
                {
                    "nome_grupo": nome_grupo,
                    "motivo_disparo": motivo,
                    "prioridade": prioridade,
                    "texto_bruto": texto_bruto,
                    "cupons": cupons,
                    "info_produto": info_produto,
                    "link_oferta": link_para_abrir,
                    "link_origem": link_origem,
                    "links_extras": links_combinados,
                    "texto_recuperado": texto_recuperado,
                    "url_comparacao": url_comparacao,
                    "chave_curta": chave_curto,
                    "tipo_gatilho": avaliacao.get("tipo_gatilho"),
                    "alvo_gatilho": avaliacao.get("alvo_gatilho"),
                    "buscando_titulo": buscando_titulo,
                },
            )
        )


async def main():
    cfg = carregar_configuracoes()
    banco = carregar_dados(desconto_padrao=cfg["DESCONTO_MINIMO_AUTO"], desconto_critico=cfg["DESCONTO_CRITICO_MACRODROID"])
    estado_persistente = carregar_estado_persistente(ARQUIVO_ESTADO)

    memoria_canais = {}
    mapa_silenciar = {}
    agora_inicio = time.time()
    estado_runtime = {
        "ultimo_disparo": 0.0,
        "pausado": False,
        "pausado_ate": None,
        "inicio": agora_inicio,
        "aguardando": None,
        "aguardando_ate": None,
        "snooze_lojas": {},
        "ultima_leitura": agora_inicio,
        "adiados": [],
        "save_lock": asyncio.Lock(),
    }

    sessao_user = os.path.join(BASE_DIR, "sessao_bot")
    sessao_bot = os.path.join(BASE_DIR, "sessao_carteiro")
    user_client = TelegramClient(sessao_user, cfg["API_ID"], cfg["API_HASH"], connection_retries=None)
    bot_client = TelegramClient(sessao_bot, cfg["API_ID"], cfg["API_HASH"], connection_retries=None)

    @bot_client.on(events.NewMessage(chats=cfg["MEU_CHAT_ID"]))
    async def painel(event):
        if event.document and not (event.raw_text or "").strip().startswith("/"):
            if await processar_backup_recebido(event, banco, ARQUIVO_JSON):
                return
        await processar_comando_painel(event, banco, cfg, estado_runtime, estado_persistente, bot_client=bot_client)

    @bot_client.on(events.CallbackQuery())
    async def acoes_inline(event):
        await processar_callback_painel(
            event, banco, cfg, estado_runtime, estado_persistente, mapa_silenciar, bot_client=bot_client
        )

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
                f"Para monitorar, envie no bot:\n<code>/ac {event.chat_id}</code>"
            )
            await bot_client.send_message(cfg["MEU_CHAT_ID"], msg, parse_mode="html")

    @user_client.on(events.NewMessage())
    @user_client.on(events.MessageEdited())
    async def cacador(event):
        await processar_mensagem_cacador(
            event, user_client, bot_client, cfg, banco, estado_runtime, estado_persistente, memoria_canais, mapa_silenciar
        )

    logger.info("✅ Sistema Definitivo v3.1 rodando! Monitorando %d canais.", len(banco["canais"]))
    await user_client.start()
    await bot_client.start(bot_token=cfg["BOT_TOKEN"])
    await registrar_comandos_telegram(bot_client)

    try:
        await bot_client.send_message(
            cfg["MEU_CHAT_ID"],
            f"🟢 <b>Caçador online!</b> Monitorando <b>{len(banco['canais'])}</b> canais.\nUse os botões abaixo ou /menu para configurar.",
            parse_mode="html",
            buttons=converter_botoes_telethon(TECLADO_FIXO_SPEC),
            silent=True,
        )
    except Exception as err:
        logger.warning("Não foi possível enviar aviso de inicialização: %s", err)

    tarefa_resumo = asyncio.create_task(
        _loop_resumo_diario(bot_client, cfg, banco, estado_persistente, estado_runtime["save_lock"])
    )
    tarefa_sentinela = asyncio.create_task(_loop_sentinela(bot_client, cfg, banco, estado_runtime))
    tarefa_digest = asyncio.create_task(_loop_digest_dnd(bot_client, cfg, banco, estado_runtime))
    tarefa_backup = asyncio.create_task(
        _loop_backup_semanal(bot_client, cfg, estado_persistente, estado_runtime["save_lock"])
    )
    try:
        await asyncio.gather(
            user_client.run_until_disconnected(),
            bot_client.run_until_disconnected(),
        )
    finally:
        tarefa_resumo.cancel()
        tarefa_sentinela.cancel()
        tarefa_digest.cancel()
        tarefa_backup.cancel()
        salvar_estado_persistente(estado_persistente, ARQUIVO_ESTADO)
        await user_client.disconnect()
        await bot_client.disconnect()
        logger.info("Clientes desconectados com segurança.")


if __name__ == "__main__":
    asyncio.run(main())
