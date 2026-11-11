import asyncio
import datetime
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest


def _instalar_stub_telethon():
    """Fornece stubs leves de telethon quando executado sem o pacote instalado."""
    if "telethon" in sys.modules:
        return

    telethon_mod = types.ModuleType("telethon")
    tl_mod = types.ModuleType("telethon.tl")
    tl_types_mod = types.ModuleType("telethon.tl.types")
    functions_mod = types.ModuleType("telethon.functions")
    functions_bots_mod = types.ModuleType("telethon.functions.bots")
    types_mod = types.ModuleType("telethon.types")

    class _Button:
        @staticmethod
        def url(text, url):
            return {"type": "url", "text": text, "url": url}

        @staticmethod
        def inline(text, data):
            return {"type": "inline", "text": text, "data": data}

        @staticmethod
        def text(text, resize=True, single_use=False):
            return {"type": "text", "text": text, "resize": resize, "single_use": single_use}

    class _TelegramClient:
        def __init__(self, *args, **kwargs):
            pass

        def on(self, *args, **kwargs):
            return lambda fn: fn

    class _Events:
        @staticmethod
        def NewMessage(*args, **kwargs):
            return ("NewMessage", args, kwargs)

        @staticmethod
        def MessageEdited(*args, **kwargs):
            return ("MessageEdited", args, kwargs)

        @staticmethod
        def CallbackQuery(*args, **kwargs):
            return ("CallbackQuery", args, kwargs)

    class _MessageEntityTextUrl:
        def __init__(self, url=""):
            self.url = url

    class _BotCommand:
        def __init__(self, command="", description=""):
            self.command = command
            self.description = description

    class _BotCommandScopeDefault:
        pass

    class _SetBotCommandsRequest:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    telethon_mod.Button = _Button
    telethon_mod.TelegramClient = _TelegramClient
    telethon_mod.events = _Events
    telethon_mod.functions = functions_mod
    telethon_mod.types = types_mod
    functions_mod.bots = functions_bots_mod
    functions_bots_mod.SetBotCommandsRequest = _SetBotCommandsRequest
    types_mod.BotCommand = _BotCommand
    types_mod.BotCommandScopeDefault = _BotCommandScopeDefault
    tl_types_mod.MessageEntityTextUrl = _MessageEntityTextUrl

    sys.modules["telethon"] = telethon_mod
    sys.modules["telethon.tl"] = tl_mod
    sys.modules["telethon.tl.types"] = tl_types_mod
    sys.modules["telethon.functions"] = functions_mod
    sys.modules["telethon.types"] = types_mod


_instalar_stub_telethon()

# Testes não podem depender de um .env real presente no diretório do projeto.
for _k, _v in {
    "API_ID": "1",
    "API_HASH": "hash-teste",
    "BOT_TOKEN": "token-teste",
    "MEU_CHAT_ID": "777",
}.items():
    os.environ.setdefault(_k, _v)

import bot  # noqa: E402
import core  # noqa: E402
from telethon.tl.types import MessageEntityTextUrl  # noqa: E402


class FakeEvent:
    def __init__(self, text="", document=False, file_name="", doc_bytes=b""):
        self.raw_text = text
        self.document = document
        self.file = types.SimpleNamespace(name=file_name) if file_name else None
        self._doc_bytes = doc_bytes
        self.respostas = []
        self.mensagens_enviadas = []

    async def reply(self, text, **kwargs):
        self.respostas.append((text, kwargs))
        msg = FakeSentMessage(text, kwargs)
        self.mensagens_enviadas.append(msg)
        return msg

    async def download_media(self, file=bytes):
        return self._doc_bytes


class FakeBotClient:
    def __init__(self):
        self.mensagens = []
        self.arquivos = []

    async def send_message(self, chat_id, text, **kwargs):
        msg = FakeSentMessage(text, kwargs)
        self.mensagens.append((chat_id, text, kwargs))
        return msg

    async def send_file(self, chat_id, file_obj, **kwargs):
        msg = FakeSentMessage(kwargs.get("caption", ""), kwargs)
        self.arquivos.append((chat_id, file_obj, kwargs))
        return msg


class FakeUserClient:
    def __init__(self, media_bytes=b"fakejpg"):
        self.media_bytes = media_bytes

    async def download_media(self, media, file=None):
        file.write(self.media_bytes)
        return file


class FakeSentMessage:
    def __init__(self, text, kwargs):
        self.text = text
        self.kwargs = kwargs
        self.edicoes = []

    async def edit(self, text, **kwargs):
        self.edicoes.append((text, kwargs))


class FakeCallback:
    def __init__(self, data, sender_id=777):
        self.data = data.encode("utf-8")
        self.sender_id = sender_id
        self.edicoes = []
        self.answers = []

    async def edit(self, text=None, **kwargs):
        self.edicoes.append((text, kwargs))

    async def answer(self, text="", **kwargs):
        self.answers.append((text, kwargs))

    async def get_message(self):
        return types.SimpleNamespace(buttons=[])


class BotTests(unittest.TestCase):
    def setUp(self):
        core.PERMITIR_REDE_LOCAL = True

    def tearDown(self):
        core.PERMITIR_REDE_LOCAL = False

    def test_env_e_configuracoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(
                    "API_ID=12345\n"
                    "API_HASH='abc'\n"
                    "BOT_TOKEN=\"999:tok\"\n"
                    "MEU_CHAT_ID=777\n"
                    "DESCONTO_MINIMO_AUTO=65\n"
                    "DESCONTO_CRITICO_MACRODROID=80\n"
                    "TEMPO_SILENCIO_HORAS=4\n"
                )
            chaves = (
                "API_ID", "API_HASH", "BOT_TOKEN", "MEU_CHAT_ID",
                "DESCONTO_MINIMO_AUTO", "DESCONTO_CRITICO_MACRODROID", "TEMPO_SILENCIO_HORAS",
            )
            backup = {k: os.environ.pop(k, None) for k in chaves}
            try:
                cfg = core.carregar_configuracoes(env_path)
                self.assertEqual(cfg["API_ID"], 12345)
                self.assertEqual(cfg["DESCONTO_MINIMO_AUTO"], 65.0)
                self.assertEqual(cfg["DESCONTO_CRITICO_MACRODROID"], 80.0)
                self.assertEqual(cfg["TEMPO_SILENCIO_HORAS"], 4.0)
            finally:
                for k in chaves:
                    os.environ.pop(k, None)
                    if backup[k] is not None:
                        os.environ[k] = backup[k]

    def test_migracao_banco_preserva_dados(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "canais": ["@teste"],
                        "palavras": [r"\bbug\b"],
                        "negativas": ["obsid"],
                        "alvos_preco": {r"\bpc\b": 2000.0},
                    },
                    f,
                )
            dados = core.carregar_dados(json_path, desconto_padrao=65.0, desconto_critico=75.0)
            self.assertEqual(dados["canais"], ["@teste"])
            self.assertEqual(dados["alvos_preco"][r"\bpc\b"], 2000.0)
            self.assertEqual(dados["nao_perturbe"], {"ativo": True, "inicio": 0, "fim": 7})
            self.assertEqual(dados["filtros_extras"], {"bloquear_usados": False, "bloquear_importacao": False})
            self.assertEqual(dados["resumo_hora"], 21)

    def test_faixa_min_max_prioridade_e_filtros(self):
        banco = {
            "palavras": [r"\bbug\b", r"\bimperd[íi]vel\b", r"\bcorre+\b"],
            "negativas": [r"\besgotado\b"],
            "alvos_preco": {"placa de vídeo": {"min": 400.0, "max": 1300.0}, r"\bpc\b": 2000.0},
            "alvos_compostos": [
                core.parsear_comando_composto("ram16 | 16gb + ddr4 | notebook, sodimm | 120-220")
            ],
            "desconto_minimo": 65.0,
            "desconto_critico": 75.0,
            "filtros_extras": {"bloquear_usados": True, "bloquear_importacao": True},
        }

        # Cabo/suporte de R$ 35 não pode disparar faixa 400-1300
        res_cabo = core.avaliar_gatilhos("Suporte para placa de vídeo por R$ 35,00", banco)
        self.assertFalse(res_cabo["disparar"])

        # Placa real dentro da faixa dispara prioridade ALTA mesmo se tiver palavra genérica "CORRE"
        res_placa = core.avaliar_gatilhos("CORRE! Placa de vídeo RTX por R$ 1.150,00", banco)
        self.assertTrue(res_placa["disparar"])
        self.assertEqual(res_placa["prioridade"], "alta")
        self.assertIn("Teto Atingido", res_placa["motivo"])

        # Palavra genérica dispara prioridade NORMAL (silenciosa, sem MacroDroid)
        res_gen = core.avaliar_gatilhos("Oferta imperdível de cafeteira por R$ 199", banco)
        self.assertTrue(res_gen["disparar"])
        self.assertEqual(res_gen["prioridade"], "normal")

        # Queda >= 75% vira prioridade ALTA, queda de 68% fica NORMAL
        res_75 = core.avaliar_gatilhos("Monitor De R$ 2.000 por R$ 480", banco)
        self.assertTrue(res_75["disparar"])
        self.assertEqual(res_75["prioridade"], "alta")

        res_68 = core.avaliar_gatilhos("Monitor De R$ 1.000 por R$ 320", banco)
        self.assertTrue(res_68["disparar"])
        self.assertEqual(res_68["prioridade"], "normal")

        # Filtros usados & compra internacional
        res_usado = core.avaliar_gatilhos("BUG PC gamer usado por R$ 1.500", banco)
        self.assertFalse(res_usado["disparar"])
        self.assertEqual(res_usado["bloqueado_por"], "filtro_usado")

        res_import = core.avaliar_gatilhos("BUG SSD 16GB DDR4 Compra Internacional Remessa Conforme R$ 180", banco)
        self.assertFalse(res_import["disparar"])
        self.assertEqual(res_import["bloqueado_por"], "filtro_importacao")

        # "usando" não deve ser bloqueado pelo filtro de usado
        res_usando = core.avaliar_gatilhos("BUG PC gamer usando cupom por R$ 1.500", banco)
        self.assertTrue(res_usando["disparar"])

    def test_horario_dnd(self):
        dnd_padrao = {"ativo": True, "inicio": 0, "fim": 7}
        self.assertTrue(core.eh_horario_dnd(dnd_padrao, datetime.datetime(2026, 11, 11, 3, 30)))
        self.assertFalse(core.eh_horario_dnd(dnd_padrao, datetime.datetime(2026, 11, 11, 7, 0)))

        dnd_noite = {"ativo": True, "inicio": 23, "fim": 7}
        self.assertTrue(core.eh_horario_dnd(dnd_noite, datetime.datetime(2026, 11, 11, 23, 15)))
        self.assertTrue(core.eh_horario_dnd(dnd_noite, datetime.datetime(2026, 11, 11, 2, 0)))
        self.assertFalse(core.eh_horario_dnd(dnd_noite, datetime.datetime(2026, 11, 11, 15, 0)))

    def test_persistencia_historico_e_silenciamento_3h(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho_est = os.path.join(tmp, "estado_bot.json")
            est = core.carregar_estado_persistente(caminho_est)
            chave = "amazon:B09V3KXJPB"
            h_curto = core.hash_curto_chave(chave)
            self.assertLessEqual(len(f"sil:{h_curto}"), 64)

            core.registrar_historico(est, chave, 10800, caminho_est, agora=1000000000.0)
            # Simula registro com timestamp futuro real
            futuro = time.time() + 3600
            est["dedup"][chave] = futuro
            est["dedup"][f"sil_hash:{h_curto}"] = futuro
            core.salvar_estado_persistente(est, caminho_est)

            # Simula reinício carregando do disco
            est_recarregado = core.carregar_estado_persistente(caminho_est)
            self.assertTrue(core.esta_no_historico(est_recarregado, chave))
            self.assertTrue(core.esta_no_historico(est_recarregado, f"sil_hash:{h_curto}"))

    def test_cupons_comparacao_e_botoes(self):
        texto = "25% OFF em R$ 79, Limite de R$ 50 OFF: OPORTUNIDADEML\nCupom: SUPER20\n🎟️ Cupom 👇\nMAGALU100\n50% off apenas hoje\nPlaca RTX 4060"
        cupons = core.extrair_cupons(texto)
        self.assertEqual(cupons, ["OPORTUNIDADEML", "SUPER20", "MAGALU100"])

        info_amz = core.identificar_produto("https://www.amazon.com.br/dp/B09V3KXJPB?tag=123")
        url_keepa = core.gerar_url_comparacao(info_amz, texto, info_amz["link_limpo"])
        self.assertEqual(url_keepa, "https://keepa.com/#!product/12-B09V3KXJPB")

        info_kbm = core.identificar_produto("https://www.kabum.com.br/produto/520368/placa-de-video-rtx-4060")
        url_buscape = core.gerar_url_comparacao(info_kbm, texto, info_kbm["link_limpo"])
        self.assertIn("buscape.com.br/search?q=", url_buscape)

        msg, legenda, spec = core.montar_mensagem_e_botoes_spec(
            nome_grupo="Grupo Bugs",
            motivo_disparo="Teto Atingido",
            prioridade="alta",
            texto_bruto=texto,
            cupons=cupons,
            info_produto=info_amz,
            link_oferta=info_amz["link_limpo"],
            link_origem="https://t.me/teste/1",
            url_comparacao=url_keepa,
            chave_silenciar="abc123def456",
            tipo_gatilho="palavra",
            alvo_gatilho=r"\bcorre+\b",
        )
        self.assertIn("<code>OPORTUNIDADEML</code>", msg)
        self.assertIn("<code>SUPER20</code>", msg)
        self.assertLessEqual(len(legenda), 1000)
        botoes = bot.converter_botoes_telethon(spec)
        self.assertEqual(len(botoes), 5)
        self.assertEqual(botoes[2][0]["text"], "📊 Comparar Preço")
        self.assertEqual(botoes[3][0]["data"], b"sil:abc123def456")
        self.assertIn("Parar de monitorar", botoes[4][0]["text"])
        self.assertTrue(botoes[4][0]["data"].startswith(b"stop:p:"))

    def test_alerta_vago_metadados_e_edit(self):
        self.assertTrue(core.alerta_eh_vago("CORRE BUG https://amzn.to/abc"))
        self.assertFalse(core.alerta_eh_vago("Placa de vídeo RTX 4060 Asus por R$ 1.899 https://amzn.to/abc"))

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    b'<html><head>'
                    b'<meta property="og:title" content="SSD Kingston NV2 1TB M.2 | Amazon.com.br">'
                    b'<meta property="product:price:amount" content="349.90">'
                    b'</head></html>'
                )

            def log_message(self, format, *args):
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            url = f"http://127.0.0.1:{port}/produto-x"
            sent = FakeSentMessage("msg antiga", {})
            ctx = {
                "nome_grupo": "Canal",
                "motivo_disparo": "Palavra-Chave",
                "prioridade": "alta",
                "texto_bruto": f"CORRE BUG {url}",
                "cupons": [],
                "info_produto": {"loja": None, "produto_id": None, "link_limpo": url, "carrinho_amazon": None},
                "link_oferta": url,
                "link_origem": "https://t.me/canal/1",
                "links_extras": [url],
                "texto_recuperado": None,
                "url_comparacao": None,
                "chave_curta": "112233445566",
            }
            asyncio.run(bot._enriquecer_alerta_vago(sent, False, ctx))
            self.assertEqual(len(sent.edicoes), 1)
            self.assertIn("SSD Kingston NV2 1TB M.2", sent.edicoes[0][0])
            self.assertIn("349.90", sent.edicoes[0][0])
        finally:
            server.shutdown()
            server.server_close()

    def test_envio_com_foto_legenda_curta(self):
        fake_bot = FakeBotClient()
        fake_user = FakeUserClient(b"imagem_jpeg_teste")
        ev = types.SimpleNamespace(photo=object())
        msg_longa = "A" * 1500
        legenda = "B" * 950

        sent, foi_foto = asyncio.run(
            bot._enviar_alerta_telegram(fake_bot, fake_user, ev, 999, msg_longa, legenda, None, False)
        )
        self.assertTrue(foi_foto)
        self.assertEqual(len(fake_bot.arquivos), 1)
        self.assertLessEqual(len(fake_bot.arquivos[0][2]["caption"]), 1000)

    def test_expandir_link_405_e_redirect_html(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_HEAD(self):
                if self.path == "/short":
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/p/MLB98765432")
                    self.end_headers()
                elif self.path.startswith("/p/"):
                    self.send_response(405)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()

            def do_GET(self):
                if self.path == "/html-redirect":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(
                        b'<meta http-equiv="refresh" content="0;url=https://www.kabum.com.br/produto/112233/ssd">'
                    )
                else:
                    self.send_response(200)
                    self.end_headers()

            def log_message(self, format, *args):
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            self.assertEqual(
                core.expandir_link(f"http://127.0.0.1:{port}/html-redirect"),
                "https://www.kabum.com.br/produto/112233/ssd",
            )
            self.assertEqual(
                core.expandir_link(f"http://127.0.0.1:{port}/short"),
                f"http://127.0.0.1:{port}/p/MLB98765432",
            )
        finally:
            server.shutdown()
            server.server_close()

    def test_comandos_novos_painel_e_restore_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            log_path = os.path.join(tmp, "bot.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("linha 1\nlinha 2\n")

            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": ""}
            est_run = {"pausado": False, "inicio": time.time()}
            est_pers = core.carregar_estado_persistente(os.path.join(tmp, "estado.json"))
            est_pers["ultimos"].append({"hora": "15:00", "loja": "Amazon", "motivo": "BUG", "link": "https://amzn.to/x"})

            async def rodar():
                ev_teto = FakeEvent("/addteto placa de vídeo, 400-1300")
                await bot.processar_comando_painel(ev_teto, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(banco["alvos_preco"]["placa de vídeo"], {"min": 400.0, "max": 1300.0})

                ev_dnd = FakeEvent("/dnd 23-6")
                await bot.processar_comando_painel(ev_dnd, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(banco["nao_perturbe"], {"ativo": True, "inicio": 23, "fim": 6})

                ev_flt = FakeEvent("/filtro usados on")
                await bot.processar_comando_painel(ev_flt, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertTrue(banco["filtros_extras"]["bloquear_usados"])

                ev_res = FakeEvent("/resumo 20")
                await bot.processar_comando_painel(ev_res, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(banco["resumo_hora"], 20)

                ev_ult = FakeEvent("/ultimos")
                await bot.processar_comando_painel(ev_ult, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Amazon", ev_ult.respostas[0][0])

                ev_log = FakeEvent("/logs 10")
                await bot.processar_comando_painel(ev_log, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("linha 2", ev_log.respostas[0][0])

                ev_bak = FakeEvent("/backup")
                await bot.processar_comando_painel(ev_bak, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(len(fake_bot.arquivos), 1)

                ev_teste = FakeEvent("/teste")
                await bot.processar_comando_painel(ev_teste, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Teste Manual", ev_teste.respostas[0][0])

                # Restaurar backup via upload de .json
                payload = json.dumps({"canais": ["@novo"], "palavras": [r"\bbug\b"], "negativas": []}).encode("utf-8")
                ev_up = FakeEvent("", document=True, file_name="backup.json", doc_bytes=payload)
                ok = await bot.processar_backup_recebido(ev_up, banco, json_path)
                self.assertTrue(ok)
                self.assertEqual(banco["canais"], ["@novo"])
                self.assertTrue(os.path.exists(f"{json_path}.bak"))

            asyncio.run(rodar())

    def test_editar_prioridades_callbacks_e_atalhos(self):
        class FakeCallback:
            def __init__(self, data, sender_id=777):
                self.data = data.encode("utf-8")
                self.sender_id = sender_id
                self.edicoes = []
                self.answers = []
                self.respostas = []

            async def edit(self, text=None, **kwargs):
                self.edicoes.append((text, kwargs))

            async def answer(self, text="", **kwargs):
                self.answers.append((text, kwargs))

            async def respond(self, text, **kwargs):
                self.respostas.append((text, kwargs))

            async def get_message(self):
                return types.SimpleNamespace(buttons=[])

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {"pausado": False, "inicio": time.time()}
            est_pers = core.carregar_estado_persistente(est_path)
            mapa_sil = {}

            async def rodar():
                # Atalho /m abre menu
                ev_m = FakeEvent("/m")
                await bot.processar_comando_painel(ev_m, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Painel de Controle", ev_m.respostas[0][0])

                # /p alterna pausa -> ativo
                ev_p1 = FakeEvent("/p")
                await bot.processar_comando_painel(ev_p1, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertTrue(est_run["pausado"])
                ev_p2 = FakeEvent("/p")
                await bot.processar_comando_painel(ev_p2, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertFalse(est_run["pausado"])

                # Lote em /ac e remocao por indice em /dc
                ev_ac = FakeEvent("/ac @extra1 @extra2")
                await bot.processar_comando_painel(ev_ac, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("@extra1", banco["canais"])
                self.assertIn("@extra2", banco["canais"])

                ev_dc_vazio = FakeEvent("/dc")
                await bot.processar_comando_painel(ev_dc_vazio, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("1.", ev_dc_vazio.respostas[0][0])

                primeiro_canal = banco["canais"][0]
                ev_dc1 = FakeEvent("/dc 1")
                await bot.processar_comando_painel(ev_dc1, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertNotIn(primeiro_canal, banco["canais"])

                # Lote em /ap e remocao por indice em /dp
                ev_ap = FakeEvent("/ap oferta_relampago; queima_estoque")
                await bot.processar_comando_painel(ev_ap, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("oferta_relampago", banco["palavras"])
                self.assertIn("queima_estoque", banco["palavras"])

                # Promover palavra genérica para ALTA via /prio
                ev_prio_w = FakeEvent("/prio palavra oferta_relampago alta")
                await bot.processar_comando_painel(ev_prio_w, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                res_prom = core.avaliar_gatilhos("Super oferta_relampago agora!", banco)
                self.assertEqual(res_prom["prioridade"], "alta")

                # Rebaixar Teto para NORMAL via /prio e testar
                await bot.processar_comando_painel(FakeEvent("/at placa, 1300"), banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                await bot.processar_comando_painel(FakeEvent("/prio teto normal"), banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                res_teto_norm = core.avaliar_gatilhos("Placa por R$ 1.100", banco)
                self.assertEqual(res_teto_norm["prioridade"], "normal")

                # Queda 65-74 normal, 80% alta, e desativar alta com off
                await bot.processar_comando_painel(FakeEvent("/prio queda 65 off"), banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                res_queda_off = core.avaliar_gatilhos("Monitor De R$ 2.000 por R$ 400", banco)
                self.assertEqual(res_queda_off["prioridade"], "normal")

                # Callbacks inline alternam Teto, Combo, Dmin, Dcrit e Palavra
                cb_teto = FakeCallback("prio:teto")
                await bot.processar_callback_painel(cb_teto, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                self.assertEqual(banco["prioridades"]["teto"], "alta")

                cb_pal = FakeCallback("prio:w:0:0")
                antes_p0 = core.palavra_eh_alta(banco, banco["palavras"][0])
                await bot.processar_callback_painel(cb_pal, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                self.assertNotEqual(core.palavra_eh_alta(banco, banco["palavras"][0]), antes_p0)

                # Remover teto simples por indice /dt 1
                ev_dt = FakeEvent("/dt 1")
                await bot.processar_comando_painel(ev_dt, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(banco["alvos_preco"], {})

            asyncio.run(rodar())

    def test_teclado_fixo_wizard_e_parar_monitorar(self):
        class FakeCallback:
            def __init__(self, data, sender_id=777):
                self.data = data.encode("utf-8")
                self.sender_id = sender_id
                self.edicoes = []
                self.answers = []

            async def edit(self, text=None, **kwargs):
                self.edicoes.append((text, kwargs))

            async def answer(self, text="", **kwargs):
                self.answers.append((text, kwargs))

            async def get_message(self):
                return types.SimpleNamespace(buttons=[])

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {"pausado": False, "inicio": time.time(), "aguardando": None}
            est_pers = core.carregar_estado_persistente(est_path)
            mapa_sil = {}

            async def rodar():
                # 1. Teclado fixo aparece no /start e /teclado
                ev_tec = FakeEvent("/teclado")
                await bot.processar_comando_painel(ev_tec, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(ev_tec.respostas[0][1]["buttons"][0][0]["type"], "text")

                # 2. Fluxo Adicionar via botão do teclado fixo -> escolhe palavra -> digita texto
                ev_btn_add = FakeEvent("➕ Adicionar")
                await bot.processar_comando_painel(ev_btn_add, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("O que você deseja adicionar", ev_btn_add.respostas[0][0])

                cb_add_p = FakeCallback("wiz:add:p")
                await bot.processar_callback_painel(cb_add_p, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                self.assertEqual(est_run["aguardando"], "add:palavra")

                # Clicar outro botão do teclado fixo NÃO pode adicionar o texto do botão como palavra!
                ev_btn_rem = FakeEvent("➖ Remover")
                await bot.processar_comando_painel(ev_btn_rem, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertNotIn("➖ Remover", banco["palavras"])
                self.assertIsNone(est_run["aguardando"])

                # Agora volta para Adicionar -> Palavra -> digita termo válido
                await bot.processar_callback_painel(cb_add_p, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                ev_texto = FakeEvent("cupom_teste_novo")
                await bot.processar_comando_painel(ev_texto, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("cupom_teste_novo", banco["palavras"])
                self.assertIsNone(est_run["aguardando"])

                # 3. Fluxo Remover via botões
                cb_rem_list = FakeCallback("wiz:delcat:p:0")
                await bot.processar_callback_painel(cb_rem_list, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                idx_novo = banco["palavras"].index("cupom_teste_novo")
                cb_del_item = FakeCallback(f"wiz:del:p:{idx_novo}:0")
                await bot.processar_callback_painel(cb_del_item, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                self.assertNotIn("cupom_teste_novo", banco["palavras"])

                # 4. Botão "Parar de monitorar" direto no alerta
                alvo_corre = r"\bcorre+\b"
                self.assertIn(alvo_corre, banco["palavras"])
                cb_stop = FakeCallback(f"stop:p:{core.hash_curto_chave(alvo_corre)}")
                await bot.processar_callback_painel(cb_stop, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path)
                self.assertNotIn(alvo_corre, banco["palavras"])

                # 5. Demais botões do teclado fixo funcionam
                for txt_btn in ("📋 Minhas listas", "🎛️ Painel", "⚡ Prioridades", "🕘 Histórico"):
                    ev_b = FakeEvent(txt_btn)
                    await bot.processar_comando_painel(ev_b, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                    self.assertTrue(ev_b.respostas)

            asyncio.run(rodar())

    def test_ping_e_snooze_lojas(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {"pausado": False, "inicio": time.time(), "aguardando": None, "snooze_lojas": {}}
            est_pers = core.carregar_estado_persistente(est_path)

            async def rodar():
                ev_ping = FakeEvent("/ping")
                await bot.processar_comando_painel(ev_ping, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Pong", ev_ping.respostas[0][0])
                self.assertTrue(ev_ping.mensagens_enviadas[0].edicoes)
                self.assertIn("ms", ev_ping.mensagens_enviadas[0].edicoes[0][0])

                ev_snz_vazio = FakeEvent("/snooze")
                await bot.processar_comando_painel(ev_snz_vazio, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Nenhuma loja em snooze", ev_snz_vazio.respostas[0][0])

                ev_amz = FakeEvent("/snooze amazon 60")
                await bot.processar_comando_painel(ev_amz, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("amazon", est_run["snooze_lojas"])

                ev_ml = FakeEvent("/snooze ml 30")
                await bot.processar_comando_painel(ev_ml, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("mercado livre", est_run["snooze_lojas"])

                ev_ml2 = FakeEvent("/snooze mercado livre 45")
                await bot.processar_comando_painel(ev_ml2, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("45 min", ev_ml2.respostas[0][0])

                ev_off_amz = FakeEvent("/snooze amazon off")
                await bot.processar_comando_painel(ev_off_amz, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertNotIn("amazon", est_run["snooze_lojas"])
                self.assertIn("mercado livre", est_run["snooze_lojas"])

                ev_off = FakeEvent("/snooze off")
                await bot.processar_comando_painel(ev_off, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(est_run["snooze_lojas"], {})

            asyncio.run(rodar())

            agora = 1000.0
            ativos = {"amazon": agora + 120.0}
            # Mesmo com loja=None, não pode lançar AttributeError
            self.assertIsNone(core.loja_em_snooze({"loja": None}, "https://amzn.to/abc", ativos, agora))
            self.assertEqual(core.loja_em_snooze({"loja": None}, "https://www.amazon.com.br/dp/B0123", ativos, agora), "amazon")
            self.assertEqual(core.loja_em_snooze({"loja": "Amazon"}, "", ativos, agora), "amazon")
            # Expirado é limpo automaticamente
            self.assertIsNone(core.loja_em_snooze({"loja": "Amazon"}, "", ativos, agora + 200.0))
            self.assertEqual(ativos, {})

    def test_barra_progresso_resumo_e_aviso_buscando_vago(self):
        self.assertEqual(core.barra_progresso(0, 100), "⬜⬜⬜⬜⬜")
        self.assertEqual(core.barra_progresso(1, 100), "🟩⬜⬜⬜⬜")
        self.assertEqual(core.barra_progresso(60, 100), "🟩🟩🟩⬜⬜")
        self.assertEqual(core.barra_progresso(100, 100), "🟩🟩🟩🟩🟩")

        resumo = core.formatar_resumo_diario({
            "data": "2026-11-11",
            "mensagens_lidas": 100,
            "alertas_enviados": 2,
            "duplicatas_barradas": 40,
            "bloqueios_negativos": 20,
            "bloqueios_dnd": 1,
        })
        self.assertIn("🟩⬜⬜⬜⬜", resumo)
        self.assertIn("🟩🟩⬜⬜⬜", resumo)

        msg_inicial, _, _ = core.montar_mensagem_e_botoes_spec(
            nome_grupo="Canal",
            motivo_disparo="Palavra-Chave",
            prioridade="alta",
            texto_bruto="CORRE BUG https://amzn.to/abc",
            cupons=[],
            info_produto={"loja": None, "produto_id": None, "link_limpo": "https://amzn.to/abc", "carrinho_amazon": None},
            link_oferta="https://amzn.to/abc",
            link_origem="https://t.me/canal/1",
            links_extras=[],
            buscando_titulo=True,
        )
        self.assertIn("Buscando título e preço do produto...", msg_inicial)

        class EmptyMetaHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<html><body><p>Sem titulo</p></body></html>")

            def log_message(self, format, *args):
                return

        server = http.server.HTTPServer(("127.0.0.1", 0), EmptyMetaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/vazio"
            sent = FakeSentMessage(msg_inicial, {})
            ctx = {
                "nome_grupo": "Canal",
                "motivo_disparo": "Palavra-Chave",
                "prioridade": "alta",
                "texto_bruto": f"CORRE BUG {url}",
                "cupons": [],
                "info_produto": {"loja": None, "produto_id": None, "link_limpo": url, "carrinho_amazon": None},
                "link_oferta": url,
                "link_origem": "https://t.me/canal/1",
                "links_extras": [url],
                "texto_recuperado": None,
                "url_comparacao": None,
                "chave_curta": "abcdef123456",
                "buscando_titulo": True,
            }
            asyncio.run(bot._enriquecer_alerta_vago(sent, False, ctx))
            self.assertEqual(len(sent.edicoes), 1)
            self.assertNotIn("Buscando título e preço do produto...", sent.edicoes[0][0])
        finally:
            server.shutdown()
            server.server_close()

    def test_qa_auditoria_colisao_dnd_virada_e_link_invisivel(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {"pausado": False, "inicio": time.time(), "aguardando": None, "save_lock": None}
            est_pers = core.carregar_estado_persistente(est_path)
            mapa_sil = {}

            async def rodar_qa():
                # QA 1: Spam de 15 callbacks simultâneos de prioridade sem erro de escrita
                antes_p0 = core.palavra_eh_alta(banco, banco["palavras"][0])
                callbacks = [FakeCallback("prio:w:0:0") for _ in range(15)]
                await asyncio.gather(*(
                    bot.processar_callback_painel(
                        cb, banco, cfg, est_run, est_pers, mapa_sil, fake_bot, json_path, est_path, log_path
                    )
                    for cb in callbacks
                ))
                self.assertNotEqual(core.palavra_eh_alta(banco, banco["palavras"][0]), antes_p0)
                with open(json_path, "r", encoding="utf-8") as f:
                    self.assertIn("palavras", json.load(f))

                # Persistência assíncrona concorrente sem Race / dictionary changed size
                lock = asyncio.Lock()
                core.registrar_historico(est_pers, "chave-1", 300, est_path, time.time(), salvar=False)
                await asyncio.gather(*(bot._persistir_estado_async(est_pers, est_path, lock) for _ in range(10)))
                with open(est_path, "r", encoding="utf-8") as f:
                    self.assertIn("chave-1", json.load(f).get("dedup", {}))

                # QA 2: DND com virada de dia (/dnd 23-2 às 01:00)
                ev_dnd = FakeEvent("/dnd 23-2")
                await bot.processar_comando_painel(ev_dnd, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertEqual(banco["nao_perturbe"], {"ativo": True, "inicio": 23, "fim": 2})

            asyncio.run(rodar_qa())

            self.assertTrue(core.eh_horario_dnd(banco["nao_perturbe"], datetime.datetime(2026, 11, 11, 23, 30)))
            self.assertTrue(core.eh_horario_dnd(banco["nao_perturbe"], datetime.datetime(2026, 11, 12, 1, 0)))
            self.assertFalse(core.eh_horario_dnd(banco["nao_perturbe"], datetime.datetime(2026, 11, 12, 2, 0)))
            self.assertFalse(core.eh_horario_dnd(banco["nao_perturbe"], datetime.datetime(2026, 11, 12, 15, 0)))

            # QA 3: Link invisível embutido via MessageEntityTextUrl
            links = core.extrair_links_mensagem(
                "BUG! Preço errado: Clique aqui",
                [MessageEntityTextUrl("https://amzn.to/xxxx")],
                text_url_cls=MessageEntityTextUrl,
            )
            self.assertEqual(links, ["https://amzn.to/xxxx"])

    def test_snooze_dominio_netloc_menu_limpar_e_resumo_async(self):
        agora = 1000.0
        ativos = {"amazon": agora + 120.0}
        # Não dá falso positivo quando 'amazon' está só no slug do produto de outra loja
        self.assertIsNone(
            core.loja_em_snooze({"loja": None}, "https://www.kabum.com.br/produto/capa-amazon-kindle", ativos, agora)
        )
        self.assertEqual(
            core.loja_em_snooze({"loja": None}, "https://www.amazon.com.br/dp/B0123", ativos, agora),
            "amazon",
        )
        self.assertEqual(
            core.loja_em_snooze({"loja": None}, "www.amazon.com.br/dp/B0123", ativos, agora),
            "amazon",
        )

        # bot_bugs legado carrega sem iniciar cliente e usa sessão separada de sessao_bot
        import bot_bugs

        self.assertTrue(bot_bugs.sessao_legacy.endswith("sessao_bot_legacy"))

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            banco["resumo_hora"] = datetime.datetime.now().hour
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {
                "pausado": False,
                "inicio": time.time(),
                "aguardando": None,
                "snooze_lojas": {"amazon": time.time() + 1800},
            }
            est_pers = core.carregar_estado_persistente(est_path)

            texto_menu, spec_menu = core.montar_painel_menu_spec(banco, est_run, est_pers)
            self.assertIn("Snooze (1)", texto_menu)
            self.assertEqual(spec_menu[-1][0][2], "menu:limpar_snooze")

            async def rodar():
                cb_limpar = FakeCallback("menu:limpar_snooze")
                await bot.processar_callback_painel(
                    cb_limpar, banco, cfg, est_run, est_pers, {}, fake_bot, json_path, est_path, log_path
                )
                self.assertEqual(est_run["snooze_lojas"], {})
                self.assertNotIn("Snooze", cb_limpar.edicoes[0][0])

                # _loop_resumo_diario envia e persiste via _persistir_estado_async com save_lock
                from unittest.mock import patch

                chamadas = {"n": 0}

                async def fake_sleep(_):
                    chamadas["n"] += 1
                    if chamadas["n"] >= 2:
                        raise asyncio.CancelledError()

                lock = asyncio.Lock()
                with patch("bot.asyncio.sleep", side_effect=fake_sleep):
                    await bot._loop_resumo_diario(fake_bot, cfg, banco, est_pers, save_lock=lock, caminho_estado=est_path)

                self.assertEqual(len(fake_bot.mensagens), 1)
                self.assertIn("Resumo Diário", fake_bot.mensagens[0][1])
                with open(est_path, "r", encoding="utf-8") as f:
                    self.assertEqual(json.load(f).get("ultimo_resumo_data"), datetime.date.today().isoformat())

            asyncio.run(rodar())

    def test_parcelamento_e_comando_simular(self):
        self.assertEqual(core.extrair_parcelamento("Por R$ 1.299 ou 10x de R$ 129,90 sem juros!"), "10x de R$ 129,90 sem juros")
        self.assertEqual(core.extrair_parcelamento("Em até 12x R$ 99,90 s/ juros"), "12x R$ 99,90 s/ juros")
        self.assertEqual(core.extrair_parcelamento("Parcele em 10x sem juros de R$ 120,00"), "10x sem juros de R$ 120,00")
        self.assertEqual(core.extrair_parcelamento("10x sem juros"), "10x sem juros")
        self.assertIsNone(core.extrair_parcelamento("À vista 1x sem juros"))
        self.assertIsNone(core.extrair_parcelamento("Monitor Full HD 1080x1920"))

        msg_parcel, _, _ = core.montar_mensagem_e_botoes_spec(
            nome_grupo="Canal",
            motivo_disparo="Queda",
            prioridade="alta",
            texto_bruto="Notebook De R$ 4.000 por R$ 1.200 em 10x de R$ 120,00 sem juros",
            cupons=[],
            info_produto={"loja": "Amazon", "produto_id": None, "link_limpo": None, "carrinho_amazon": None},
            link_oferta="https://www.amazon.com.br/dp/B09V3KXJPB",
            link_origem="https://t.me/canal/1",
        )
        self.assertIn("Parcelamento:", msg_parcel)
        self.assertIn("10x de R$ 120,00 sem juros", msg_parcel)

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {"pausado": False, "inicio": time.time(), "aguardando": None, "snooze_lojas": {}}
            est_pers = core.carregar_estado_persistente(est_path)

            async def rodar():
                ev_vazio = FakeEvent("/simular")
                await bot.processar_comando_painel(ev_vazio, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Simulador de Regras", ev_vazio.respostas[0][0])

                ev_ok = FakeEvent(
                    "/sim Monitor Gamer De R$ 1.500 por R$ 450 10x sem juros Cupom: TESTE10 https://www.amazon.com.br/dp/B09V3KXJPB"
                )
                await bot.processar_comando_painel(ev_ok, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                resp_ok = ev_ok.respostas[0][0]
                self.assertIn("DISPARARIA", resp_ok)
                self.assertIn("450.00", resp_ok)
                self.assertIn("70%", resp_ok)
                self.assertIn("10x sem juros", resp_ok)
                self.assertIn("TESTE10", resp_ok)
                self.assertIn("Amazon", resp_ok)

                est_run["snooze_lojas"]["amazon"] = time.time() + 600
                ev_snz = FakeEvent("/simular CORRE BUG https://www.amazon.com.br/dp/B09V3KXJPB")
                await bot.processar_comando_painel(ev_snz, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("em snooze (amazon)", ev_snz.respostas[0][0])

                ev_blk = FakeEvent("/simular esgotado BUG R$ 10")
                await bot.processar_comando_painel(ev_blk, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("IGNORADO / BLOQUEADO", ev_blk.respostas[0][0])

            asyncio.run(rodar())

    def test_anti_ssrf_bloqueia_rede_local_e_redirect(self):
        import urllib.error
        import urllib.request

        core.PERMITIR_REDE_LOCAL = False
        try:
            for ruim in (
                "http://127.0.0.1:8080/admin",
                "http://localhost/teste",
                "http://192.168.1.1/",
                "http://10.0.0.5/",
                "http://169.254.169.254/latest/meta-data",
                "http://[::1]/",
                "http://[::ffff:127.0.0.1]/",
                "file:///etc/passwd",
                "ftp://example.com/a",
            ):
                self.assertFalse(core.url_destino_publico(ruim), msg=f"Deveria bloquear: {ruim}")

            req = urllib.request.Request("https://exemplo.com/short")
            with self.assertRaises(urllib.error.URLError):
                core._RedirecionamentoSeguro().redirect_request(
                    req, None, 302, "Found", {}, "http://127.0.0.1:8000/interno"
                )

            hits = []

            class SpyHandler(http.server.BaseHTTPRequestHandler):
                def do_HEAD(self):
                    hits.append(("HEAD", self.path))
                    self.send_response(200)
                    self.end_headers()

                def do_GET(self):
                    hits.append(("GET", self.path))
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"<title>Secreto</title>")

                def log_message(self, format, *args):
                    return

            server = http.server.HTTPServer(("127.0.0.1", 0), SpyHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}/probe"
                self.assertEqual(core.expandir_link(url), url)
                self.assertEqual(core.buscar_metadados_pagina(url), {"titulo": None, "preco": None})
                self.assertEqual(hits, [])
            finally:
                server.shutdown()
                server.server_close()
        finally:
            core.PERMITIR_REDE_LOCAL = True

    def test_qa_m2_m3_b1_b2_validacoes_wizard_e_backup(self):
        import bot_bugs

        # B2: corte seguro sem quebrar entidade HTML nem exceder LIMITE_CORPO
        corpo = bot_bugs._preparar_corpo("&" * 1200)
        self.assertLessEqual(len(corpo), bot_bugs.LIMITE_CORPO)
        self.assertTrue(corpo.endswith("&amp;"))

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            core.salvar_dados(banco, json_path)
            fake_bot = FakeBotClient()
            cfg = {"MEU_CHAT_ID": 777, "URL_MACRODROID": "", "TEMPO_SILENCIO_HORAS": 3}
            est_run = {"pausado": False, "inicio": time.time(), "aguardando": None, "aguardando_ate": None}
            est_pers = core.carregar_estado_persistente(est_path)

            async def rodar():
                # M2: regex genérica rejeitada
                for pat in (".*", ".", r"\w+", r"\s+"):
                    ev_gen = FakeEvent(f"/ap {pat}")
                    await bot.processar_comando_painel(ev_gen, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                    self.assertIn("genérica demais", ev_gen.respostas[0][0])

                ev_val = FakeEvent(r"/ap \bssd_novo\b")
                await bot.processar_comando_painel(ev_val, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn(r"\bssd_novo\b", banco["palavras"])

                # B1: /cancelar sem pendência vs com pendência + sugestão de comando errado
                ev_canc_vazio = FakeEvent("/cancelar")
                await bot.processar_comando_painel(ev_canc_vazio, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Nenhuma operação pendente", ev_canc_vazio.respostas[0][0])

                cb_add = FakeCallback("wiz:add:p")
                await bot.processar_callback_painel(cb_add, banco, cfg, est_run, est_pers, {}, fake_bot, json_path, est_path, log_path)
                self.assertEqual(est_run["aguardando"], "add:palavra")
                self.assertIsNotNone(est_run["aguardando_ate"])

                ev_canc = FakeEvent("/cancelar")
                await bot.processar_comando_painel(ev_canc, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Operação cancelada", ev_canc.respostas[0][0])
                self.assertIsNone(est_run["aguardando"])

                # M2: expiração do assistente após 5 min
                await bot.processar_callback_painel(cb_add, banco, cfg, est_run, est_pers, {}, fake_bot, json_path, est_path, log_path)
                est_run["aguardando_ate"] = time.time() - 10
                ev_exp = FakeEvent("oi")
                await bot.processar_comando_painel(ev_exp, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("expirou", ev_exp.respostas[0][0])
                self.assertNotIn("oi", banco["palavras"])

                # B1: comando desconhecido sugere comando próximo
                ev_typo = FakeEvent("/liste")
                await bot.processar_comando_painel(ev_typo, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("/lista", ev_typo.respostas[0][0])

                # M3: backup inválido em alvos_preco, regex ou combo é recusado sem alterar banco
                qtd_canais_antes = len(banco["canais"])
                invalidos = [
                    {"canais": ["@c"], "palavras": ["bug"], "negativas": [], "alvos_preco": []},
                    {"canais": ["@c"], "palavras": ["[invalida"], "negativas": []},
                    {"canais": ["@c"], "palavras": ["bug"], "negativas": [], "alvos_compostos": [{"nome": "x"}]},
                    {"canais": ["@c"], "palavras": ["bug"], "negativas": [], "desconto_minimo": True},
                ]
                for payload in invalidos:
                    ev_bak = FakeEvent(
                        document=True,
                        file_name="bad.json",
                        doc_bytes=json.dumps(payload).encode("utf-8"),
                    )
                    await bot.processar_backup_recebido(ev_bak, banco, json_path)
                    self.assertIn("Falha ao restaurar JSON", ev_bak.respostas[0][0])
                    self.assertEqual(len(banco["canais"]), qtd_canais_antes)

            asyncio.run(rodar())

    def test_fluxo_cacador_macrodroid_dedup_digest_ranking_e_sentinela(self):
        from unittest.mock import patch

        class FakeCanalEvent:
            def __init__(self, chat_id, msg_id, title, username, text, entities=None):
                self.chat_id = chat_id
                self.id = msg_id
                self.raw_text = text
                self.entities = entities or []
                self.photo = None
                self.is_private = False
                self.out = False
                self._chat = types.SimpleNamespace(title=title, username=username)

            async def get_chat(self):
                return self._chat

        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            est_path = os.path.join(tmp, "estado.json")
            log_path = os.path.join(tmp, "bot.log")
            banco = core.carregar_dados(json_path)
            banco["canais"] = ["@canalteste"]
            banco["palavras"].append(r"\boferta_normal\b")
            core.salvar_dados(banco, json_path)

            cfg = {
                "MEU_CHAT_ID": 777,
                "URL_MACRODROID": "https://trigger.macrodroid.com/teste/bug",
                "TEMPO_DE_ESPERA": 0,
                "TEMPO_DUPLICATA": 900,
                "TEMPO_SILENCIO_HORAS": 3,
            }
            est_pers = core.carregar_estado_persistente(est_path)
            memoria = {}
            mapa_sil = {}

            async def rodar():
                lock = asyncio.Lock()
                est_run = {
                    "ultimo_disparo": 0.0,
                    "pausado": False,
                    "inicio": time.time(),
                    "aguardando": None,
                    "aguardando_ate": None,
                    "snooze_lojas": {},
                    "ultima_leitura": time.time(),
                    "adiados": [],
                    "save_lock": lock,
                }
                eventos_ordem = []
                falhar_envio = {"ativo": False}

                class BotClientOrdem(FakeBotClient):
                    async def send_message(self, chat_id, text, **kwargs):
                        if falhar_envio["ativo"]:
                            raise RuntimeError("Telegram indisponivel")
                        macrodroid_iniciado = bool(eventos_ordem and eventos_ordem[0][0] == "macrodroid") or any(
                            "_acionar_macrodroid" in repr(t.get_coro()) for t in bot._TAREFAS_BG
                        )
                        eventos_ordem.append(("telegram", macrodroid_iniciado))
                        return await super().send_message(chat_id, text, **kwargs)

                fake_bot = BotClientOrdem()
                fake_user = FakeUserClient()

                def fake_macrodroid(url, link):
                    eventos_ordem.append(("macrodroid", link))
                    return 200

                # M1 + F3: MacroDroid parte antes do envio ao Telegram e atualiza ranking por canal
                ev_bug = FakeCanalEvent(
                    -100123,
                    10,
                    "Canal Teste",
                    "canalteste",
                    "BUG SSD NVMe R$ 50 https://www.amazon.com.br/dp/B09V3KXJPB?ref=teste1234567890",
                )
                with patch("bot.disparar_macrodroid", side_effect=fake_macrodroid):
                    await bot.processar_mensagem_cacador(
                        ev_bug, fake_user, fake_bot, cfg, banco, est_run, est_pers, memoria, mapa_sil, est_path
                    )
                    for _ in range(20):
                        if any(e[0] == "macrodroid" for e in eventos_ordem):
                            break
                        await asyncio.sleep(0.01)

                tg_evt = next(e for e in eventos_ordem if e[0] == "telegram")
                self.assertTrue(tg_evt[1])
                self.assertTrue(any(e[0] == "macrodroid" for e in eventos_ordem))
                self.assertEqual(est_pers["por_canal"]["Canal Teste"], {"lidas": 1, "alertas": 1})

                # M1: falha ao entregar no Telegram libera chave de duplicata para o repost
                falhar_envio["ativo"] = True
                ev_repost = FakeCanalEvent(
                    -100123,
                    11,
                    "Canal Teste",
                    "canalteste",
                    "BUG Monitor 4K R$ 99 https://www.amazon.com.br/dp/B09V3REPOST?ref=teste1234567890",
                )
                with patch("bot.disparar_macrodroid", side_effect=fake_macrodroid):
                    await bot.processar_mensagem_cacador(
                        ev_repost, fake_user, fake_bot, cfg, banco, est_run, est_pers, memoria, mapa_sil, est_path
                    )
                self.assertEqual(len(est_pers["dedup"]), 1)  # apenas o 1o alerta continua no dedup

                falhar_envio["ativo"] = False
                with patch("bot.disparar_macrodroid", side_effect=fake_macrodroid):
                    await bot.processar_mensagem_cacador(
                        ev_repost, fake_user, fake_bot, cfg, banco, est_run, est_pers, memoria, mapa_sil, est_path
                    )
                self.assertEqual(len(est_pers["dedup"]), 2)

                # F3: comando /ranking exibe canal com taxa e /ranking mudo
                ev_rank = FakeEvent("/rank")
                await bot.processar_comando_painel(ev_rank, banco, cfg, est_run, est_pers, fake_bot, json_path, log_path)
                self.assertIn("Canal Teste", ev_rank.respostas[0][0])

                # F2: DND guarda oferta normal em adiados e envia Digest quando DND termina
                hora_atual = datetime.datetime.now().hour
                banco["nao_perturbe"] = {"ativo": True, "inicio": hora_atual, "fim": (hora_atual + 1) % 24}
                ev_norm = FakeCanalEvent(
                    -100123,
                    12,
                    "Canal Teste",
                    "canalteste",
                    "oferta_normal Mouse Gamer https://www.amazon.com.br/dp/B09MOUSE123?ref=teste1234567890",
                )
                await bot.processar_mensagem_cacador(
                    ev_norm, fake_user, fake_bot, cfg, banco, est_run, est_pers, memoria, mapa_sil, est_path
                )
                self.assertEqual(len(est_run["adiados"]), 1)

                banco["nao_perturbe"]["ativo"] = False
                chamadas_d = {"n": 0}

                async def sleep_digest(_):
                    chamadas_d["n"] += 1
                    if chamadas_d["n"] >= 2:
                        raise asyncio.CancelledError()

                with patch("bot.asyncio.sleep", side_effect=sleep_digest):
                    await bot._loop_digest_dnd(fake_bot, cfg, banco, est_run, intervalo=0)
                self.assertEqual(est_run["adiados"], [])
                self.assertTrue(any("Digest do Não Perturbe" in m[1] for m in fake_bot.mensagens))

                # F1: Sentinela avisa uma vez quando ultima_leitura passa de limite_horas
                est_run["ultima_leitura"] = time.time() - (4 * 3600)
                chamadas_s = {"n": 0}

                async def sleep_sent(_):
                    chamadas_s["n"] += 1
                    if chamadas_s["n"] >= 3:
                        raise asyncio.CancelledError()

                with patch("bot.asyncio.sleep", side_effect=sleep_sent):
                    await bot._loop_sentinela(fake_bot, cfg, banco, est_run, limite_horas=3.0, intervalo=0)
                avisos_sent = [m for m in fake_bot.mensagens if "Sentinela:" in m[1]]
                self.assertEqual(len(avisos_sent), 1)

            asyncio.run(rodar())


if __name__ == "__main__":
    unittest.main()
