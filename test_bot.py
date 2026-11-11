import asyncio
import http.server
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from types import SimpleNamespace


def _instalar_stub_telethon():
    """Fornece stubs leves de telethon quando executado sem o pacote instalado."""
    if "telethon" in sys.modules:
        return

    telethon_mod = types.ModuleType("telethon")
    tl_mod = types.ModuleType("telethon.tl")
    tl_types_mod = types.ModuleType("telethon.tl.types")

    class _Button:
        @staticmethod
        def url(text, url):
            return {"type": "url", "text": text, "url": url}

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

    class _MessageEntityTextUrl:
        def __init__(self, url=""):
            self.url = url

    telethon_mod.Button = _Button
    telethon_mod.TelegramClient = _TelegramClient
    telethon_mod.events = _Events
    tl_types_mod.MessageEntityTextUrl = _MessageEntityTextUrl

    sys.modules["telethon"] = telethon_mod
    sys.modules["telethon.tl"] = tl_mod
    sys.modules["telethon.tl.types"] = tl_types_mod


_instalar_stub_telethon()

import bot  # noqa: E402
from telethon.tl.types import MessageEntityTextUrl  # noqa: E402


class FakeEvent:
    def __init__(self, text):
        self.raw_text = text
        self.respostas = []

    async def reply(self, text, **kwargs):
        self.respostas.append((text, kwargs))


class BotTests(unittest.TestCase):
    def test_env_e_configuracoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(
                    "API_ID=12345\n"
                    "API_HASH='abc'\n"
                    "BOT_TOKEN=\"999:tok\"\n"
                    "MEU_CHAT_ID=777\n"
                    "DESCONTO_MINIMO_AUTO=70\n"
                )
            backup = {k: os.environ.pop(k, None) for k in ("API_ID", "API_HASH", "BOT_TOKEN", "MEU_CHAT_ID", "DESCONTO_MINIMO_AUTO")}
            try:
                cfg = bot.carregar_configuracoes(env_path)
                self.assertEqual(cfg["API_ID"], 12345)
                self.assertEqual(cfg["API_HASH"], "abc")
                self.assertEqual(cfg["BOT_TOKEN"], "999:tok")
                self.assertEqual(cfg["MEU_CHAT_ID"], 777)
                self.assertEqual(cfg["DESCONTO_MINIMO_AUTO"], 70.0)
            finally:
                for k in ("API_ID", "API_HASH", "BOT_TOKEN", "MEU_CHAT_ID", "DESCONTO_MINIMO_AUTO"):
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
            dados = bot.carregar_dados(json_path, desconto_padrao=65.0)
            self.assertEqual(dados["canais"], ["@teste"])
            self.assertEqual(dados["alvos_preco"][r"\bpc\b"], 2000.0)
            self.assertEqual(dados["alvos_compostos"], [])
            self.assertEqual(dados["desconto_minimo"], 65.0)

    def test_extracao_preco_ignora_parcelas_e_descontos(self):
        self.assertEqual(bot.extrair_preco("De R$ 2.500,00 por R$ 1.199,90 (10x de R$ 130)"), 1199.90)
        self.assertEqual(bot.extrair_preco("Placa por R$ 1.250 usando cupom de R$ 50 off"), 1250.0)
        self.assertEqual(bot.extrair_preco("Frete grátis acima de R$ 79 - Mouse R$ 49,90"), 49.90)
        self.assertEqual(bot.extrair_preco("Produto R$ 199.90"), 199.90)
        self.assertIsNone(bot.extrair_preco("Sem preço aqui"))

    def test_detector_desconto_real(self):
        res = bot.detectar_desconto_real("Monitor De R$ 2.000,00 por R$ 500,00!", 65)
        self.assertIsNotNone(res)
        self.assertAlmostEqual(res[0], 75.0, places=1)

        res_strikethrough = bot.detectar_desconto_real("~~R$ 1.000~~ R$ 300 hoje!", 65)
        self.assertIsNotNone(res_strikethrough)
        self.assertAlmostEqual(res_strikethrough[0], 70.0, places=1)

        self.assertIsNone(bot.detectar_desconto_real("De R$ 500 por R$ 250", 65))
        self.assertIsNone(bot.detectar_desconto_real("De R$ 500 por 10x de R$ 50", 65))

    def test_sniper_composto_e_regex_pc(self):
        banco = {
            "palavras": [r"\bbug\b"],
            "negativas": [r"\besgotado\b"],
            "alvos_preco": {r"\bpc\b": 2000.0},
            "alvos_compostos": [
                bot.parsear_comando_composto("ram16 | 16gb + ddr4 | notebook, sodimm | 220")
            ],
            "desconto_minimo": 65.0,
        }

        ok, motivo = bot.avaliar_gatilhos("PC Gamer Ryzen por R$ 1.899", banco)
        self.assertTrue(ok)
        self.assertIn("Teto Atingido", motivo)

        ok_falso, _ = bot.avaliar_gatilhos("Opção de capinha por R$ 100", banco)
        self.assertFalse(ok_falso)

        ok_combo, motivo_combo = bot.avaliar_gatilhos("Memória Desktop 16GB DDR4 3200MHz R$ 199,90", banco)
        self.assertTrue(ok_combo)
        self.assertIn("Combo (ram16", motivo_combo)

        ok_excluido, _ = bot.avaliar_gatilhos("Memória Notebook SODIMM 16GB DDR4 R$ 180", banco)
        self.assertFalse(ok_excluido)

        ok_pendrive, _ = bot.avaliar_gatilhos("Pendrive 16GB USB R$ 35", banco)
        self.assertFalse(ok_pendrive)

        ok_neg, _ = bot.avaliar_gatilhos("BUG absurdo esgotado R$ 10", banco)
        self.assertFalse(ok_neg)

    def test_cupons_e_html(self):
        texto = (
            "Corre! Cupom: SUPER20\n"
            "Código: VALE-50\n"
            "🎟️ Cupom 👇\n"
            "MAGALU100\n"
            "Use o cupom no site ou abaixo! <script>alert(1)</script>"
        )
        cupons = bot.extrair_cupons(texto)
        self.assertEqual(cupons, ["SUPER20", "VALE-50", "MAGALU100"])

        msg, botoes = bot.montar_mensagem_e_botoes(
            nome_grupo="Canal <Bugs>",
            motivo_disparo="Palavra-Chave (\\bbug\\b)",
            texto_bruto=texto,
            cupons=cupons,
            info_produto={
                "loja": "Amazon",
                "produto_id": "amazon:B09V3KXJPB",
                "link_limpo": "https://www.amazon.com.br/dp/B09V3KXJPB",
                "carrinho_amazon": "https://www.amazon.com.br/gp/aws/cart/add.html?ASIN.1=B09V3KXJPB&Quantity.1=1",
            },
            link_oferta="https://www.amazon.com.br/dp/B09V3KXJPB",
            link_origem="https://t.me/teste/123",
        )
        self.assertIn("🎟️ <b>Cupom(ns):</b> <code>SUPER20</code> <code>VALE-50</code> <code>MAGALU100</code>", msg)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", msg)
        self.assertEqual(len(botoes), 3)
        self.assertEqual(botoes[0][0]["text"], "🔥 Abrir Oferta")
        self.assertEqual(botoes[1][0]["text"], "🛒 Carrinho Amazon")
        self.assertEqual(botoes[2][0]["text"], "📢 Ver Post Original")

    def test_identificacao_lojas_e_prioridade_link(self):
        links = bot.extrair_links_mensagem(
            "Entre em https://t.me/canalpromo e veja https://amzn.to/abc123",
            [MessageEntityTextUrl("https://t.me/canalpromo")],
        )
        self.assertEqual(bot.escolher_link_oferta(links), "https://amzn.to/abc123")

        amz = bot.identificar_produto("https://www.amazon.com.br/dp/B09V3KXJPB?tag=xxx&ref=yyy")
        self.assertEqual(amz["produto_id"], "amazon:B09V3KXJPB")
        self.assertEqual(amz["link_limpo"], "https://www.amazon.com.br/dp/B09V3KXJPB")
        self.assertIn("ASIN.1=B09V3KXJPB", amz["carrinho_amazon"])

        ml1 = bot.identificar_produto("https://produto.mercadolivre.com.br/MLB-3847192045-ssd-_JM?matt_tool=123")
        ml2 = bot.identificar_produto("https://www.mercadolivre.com.br/ssd/p/MLB3847192045?pdp_filters=1")
        self.assertEqual(ml1["produto_id"], "ml:MLB3847192045")
        self.assertEqual(ml2["produto_id"], "ml:MLB3847192045")
        self.assertNotIn("matt_tool", ml1["link_limpo"])

        shp = bot.identificar_produto("https://shopee.com.br/Produto-Legal-i.12345.678901?sp_atk=aaa")
        self.assertEqual(shp["produto_id"], "shopee:12345.678901")
        self.assertEqual(shp["link_limpo"], "https://shopee.com.br/product/12345/678901")

        kbm = bot.identificar_produto("https://www.kabum.com.br/produto/520368/placa?utm_source=abc")
        self.assertEqual(kbm["produto_id"], "kabum:520368")
        self.assertEqual(kbm["link_limpo"], "https://www.kabum.com.br/produto/520368/placa")

        mag = bot.identificar_produto("https://www.magazineluiza.com.br/fone/p/237481900/ea/fblt/?partner_id=9")
        self.assertEqual(mag["produto_id"], "magalu:237481900")

        ali = bot.identificar_produto("https://pt.aliexpress.com/item/1005006123456789.html?spm=a2g0o")
        self.assertEqual(ali["produto_id"], "aliexpress:1005006123456789")
        self.assertEqual(ali["link_limpo"], "https://pt.aliexpress.com/item/1005006123456789.html")

    def test_expandir_link_redirect_e_fallback_get(self):
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
            expandida = bot.expandir_link(f"http://127.0.0.1:{port}/html-redirect")
            self.assertEqual(expandida, "https://www.kabum.com.br/produto/112233/ssd")

            unwrapped = bot.expandir_link(
                "https://shopee.com.br/universal-link?redir=https%3A%2F%2Fshopee.com.br%2Fproduct%2F111%2F222"
            )
            self.assertEqual(unwrapped, "https://shopee.com.br/product/111/222")

            # Garante que redirect + 405 no destino ainda preserva a URL redirecionada
            com_405 = bot.expandir_link(f"http://127.0.0.1:{port}/short")
            self.assertEqual(com_405, f"http://127.0.0.1:{port}/p/MLB98765432")
        finally:
            server.shutdown()
            server.server_close()

    def test_deduplicacao_entre_links_diferentes_mesmo_produto(self):
        info_canal_a = bot.identificar_produto("https://www.amazon.com.br/dp/B09V3KXJPB?tag=canalA-20")
        info_canal_b = bot.identificar_produto("https://www.amazon.com.br/gp/product/B09V3KXJPB?ref=canalB")
        chave_a = bot.montar_chave_duplicata(info_canal_a, info_canal_a["link_limpo"], "Palavra-Chave", "x")
        chave_b = bot.montar_chave_duplicata(info_canal_b, info_canal_b["link_limpo"], "Palavra-Chave", "y")
        self.assertEqual(chave_a, "amazon:B09V3KXJPB")
        self.assertEqual(chave_a, chave_b)

    def test_composto_sem_exclusao_e_compatibilidade_banco_real(self):
        regra = bot.parsear_comando_composto("ssd1tb | ssd + 1tb | 350,00")
        self.assertEqual(regra["excluir"], [])
        self.assertEqual(regra["teto"], 350.0)

        banco_real_path = os.path.join(bot.BASE_DIR, "banco_de_dados.json")
        if os.path.exists(banco_real_path):
            with tempfile.TemporaryDirectory() as tmp:
                copia = os.path.join(tmp, "banco_copia.json")
                with open(banco_real_path, "r", encoding="utf-8") as orig:
                    conteudo = orig.read()
                with open(copia, "w", encoding="utf-8") as dst:
                    dst.write(conteudo)
                dados = bot.carregar_dados(copia, desconto_padrao=65.0)
                ok, _ = bot.avaliar_gatilhos("PC completo por R$ 1.800", dados)
                self.assertTrue(ok)
                ok_obsid, _ = bot.avaliar_gatilhos("BUG PC obsid R$ 100", dados)
                self.assertFalse(ok_obsid)

    def test_comandos_painel_composto_e_desconto(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "banco.json")
            banco = bot.carregar_dados(json_path)
            cfg = {"URL_MACRODROID": ""}
            estado = {"pausado": False, "alertas_enviados": 0, "inicio": 0.0}

            orig_salvar = bot.salvar_dados
            bot.salvar_dados = lambda d, caminho_json=json_path: orig_salvar(d, json_path)
            try:
                ev1 = FakeEvent("/addcomposto ram | 16gb + ddr4 | notebook | 210")
                asyncio.run(bot.processar_comando_painel(ev1, banco, cfg, estado))
                self.assertEqual(len(banco["alvos_compostos"]), 1)
                self.assertEqual(banco["alvos_compostos"][0]["teto"], 210.0)

                ev2 = FakeEvent("/setdesconto 75")
                asyncio.run(bot.processar_comando_painel(ev2, banco, cfg, estado))
                self.assertEqual(banco["desconto_minimo"], 75.0)

                ev3 = FakeEvent("/addpalavra [invalido")
                asyncio.run(bot.processar_comando_painel(ev3, banco, cfg, estado))
                self.assertIn("Expressão inválida", ev3.respostas[0][0])

                ev4 = FakeEvent("/delcomposto ram")
                asyncio.run(bot.processar_comando_painel(ev4, banco, cfg, estado))
                self.assertEqual(banco["alvos_compostos"], [])
            finally:
                bot.salvar_dados = orig_salvar


if __name__ == "__main__":
    unittest.main()
