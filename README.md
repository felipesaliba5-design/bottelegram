# Bot Caçador de Promoções e Bugs (Telegram)

Bot em Python usando [Telethon](https://docs.telethon.dev/) para monitorar canais e grupos do Telegram em tempo real, detectar ofertas/bugs de preço, expandir links de lojas, destacar cupons e enviar alertas com botões interativos (além de disparo opcional para o MacroDroid).

## Principais Recursos

- **Monitoramento em tempo real (`NewMessage` + `MessageEdited`)**: detecta ofertas tanto no envio original quanto se o administrador editar a mensagem segundos depois.
- **Memória de curto prazo (5 min)**: recupera automaticamente o link de uma postagem anterior no mesmo canal caso o alerta atual venha sem URL.
- **Sniper de preços simples e composto**:
  - Regras simples por termo/regex + preço máximo (`/addteto`).
  - Regras compostas com termos obrigatórios e exclusões (`/addcomposto`), evitando falsos positivos (ex.: exigir `16gb + ddr4` e excluir `notebook, sodimm`).
  - Ignora valores de parcelas (`10x de R$ ...`), cupons (`R$ 50 off`) e preços antigos (`De R$ ...`) quando há preço atual.
- **Detector automático de desconto real**: dispara em quedas expressivas no formato `De R$ X por R$ Y` ou `~~R$ X~~ R$ Y` (percentual configurável via `/setdesconto` ou `.env`).
- **Botões grandes (`Button.url`) e cupons no topo**: destaca códigos de cupom em bloco copiável com 1 toque e inclui botões para **Abrir Oferta**, **Carrinho Amazon** (quando houver ASIN) e **Ver Post Original**.
- **Expansão de links e anti-duplicidade multi-loja**: resolve redirecionamentos de forma assíncrona (`asyncio.to_thread`), remove parâmetros de rastreamento e identifica produtos de **Amazon**, **Mercado Livre**, **Shopee**, **Kabum**, **Magalu** e **AliExpress** para evitar alertas repetidos entre canais diferentes.
- **Segurança e logs 24/7**: credenciais isoladas em `.env`, salvamento atômico do `banco_de_dados.json` e logs com rotação automática em `logs/bot.log`.

## Requisitos

- **Python 3.9+**
- **Telethon** (única dependência externa):
  ```bash
  pip install telethon
  ```

## Configuração

1. Copie o arquivo de exemplo para criar o seu `.env`:
   ```bash
   cp .env.example .env
   ```
   *(No Windows PowerShell: `Copy-Item .env.example .env`)*

2. Preencha o `.env` com seus dados:
   - `API_ID` e `API_HASH`: obtidos em [my.telegram.org](https://my.telegram.org).
   - `BOT_TOKEN`: token do seu bot criado no `@BotFather`.
   - `MEU_CHAT_ID`: seu ID numérico no Telegram.
   - `URL_MACRODROID` *(opcional)*: URL do webhook do MacroDroid (deixe vazio para desativar).
   - `TEMPO_DE_ESPERA`, `TEMPO_DUPLICATA` e `DESCONTO_MINIMO_AUTO` *(opcionais)*: intervalos em segundos e percentual mínimo de queda automática.

3. Inicie o bot:
   ```bash
   python bot.py
   ```
   Na primeira execução, o Telethon solicitará o login da sua conta de usuário para gerar os arquivos de sessão locais (`sessao_bot.session` e `sessao_carteiro.session`).

> **Dica para Termux (Android):** basta instalar `python` (`pkg install python`), instalar `telethon` (`pip install telethon`), colocar `bot.py` e `.env` na mesma pasta e rodar `python bot.py`.

## Comandos do Painel no Telegram

Envie os comandos abaixo diretamente no chat com o seu bot:

| Comando | Descrição |
| --- | --- |
| `/ajuda` | Lista todos os comandos disponíveis |
| `/lista` | Mostra canais, palavras, bloqueios, tetos e desconto automático |
| `/status` | Exibe estado atual, tempo ativo e total de alertas enviados |
| `/pausar` / `/retomar` | Pausa ou retoma o monitoramento sem fechar o script |
| `/addcanal @canal` / `/delcanal @canal` | Adiciona ou remove canal/grupo (ou ID numérico) |
| `/addpalavra termo` / `/delpalavra termo` | Adiciona ou remove palavra-chave (suporta regex) |
| `/addbloqueio termo` / `/delbloqueio termo` | Adiciona ou remove palavra negativa (suporta regex) |
| `/addteto item, valor` / `/delteto item` | Define teto de preço simples (ex.: `/addteto \bpc\b, 2000`) |
| `/addcomposto nome \| ter1 + ter2 \| ex1, ex2 \| valor` | Cria regra composta com exclusões |
| `/addcomposto nome \| ter1 + ter2 \| valor` | Cria regra composta sem exclusões |
| `/delcomposto nome` | Remove uma regra composta |
| `/setdesconto 65` | Define desconto mínimo automático (`0` desativa) |
| `/getid` | Enviado por você dentro de um grupo/canal privado para obter o ID no bot |

## Estrutura do Projeto

- `bot.py`: código principal do monitor e painel de comandos.
- `.env.example`: modelo das variáveis de ambiente.
- `.gitignore`: impede o envio de credenciais, sessões, logs e banco local ao Git.
- `test_bot.py`: suíte de testes unitários para regras de preço, descontos, cupons, links e comandos.
- Gerados em execução (ignorados pelo Git): `.env`, `banco_de_dados.json`, `*.session*` e `logs/bot.log`.

## Testes

Execute os testes unitários localmente (usa stubs leves caso o `telethon` não esteja instalado na máquina):

```bash
python -m unittest -v test_bot.py
```

*(No Windows, se usar o launcher `py`, rode `py -m unittest -v test_bot.py`.)*

## Segurança

Nunca publique seus arquivos `.env`, `*.session*` ou `banco_de_dados.json` em repositórios públicos — eles já estão bloqueados no `.gitignore`.
