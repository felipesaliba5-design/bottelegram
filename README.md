# Bot Caçador de Promoções e Bugs (Telegram)

Bot em Python usando [Telethon](https://docs.telethon.dev/) para monitorar canais e grupos do Telegram em tempo real, filtrar ofertas com alta precisão, expandir links de lojas, destacar cupons e enviar alertas com fotos e botões interativos (além de disparo prioritário para o MacroDroid).

## Principais Recursos

- **Monitoramento em tempo real (`NewMessage` + `MessageEdited`)**: detecta ofertas tanto no envio original quanto após edições rápidas.
- **Memória de curto prazo (5 min)**: recupera automaticamente o link de uma postagem anterior no mesmo canal caso o alerta venha sem URL.
- **Sniper com faixa mínima/máxima e regras compostas**:
  - Suporta faixa `min-max` no `/addteto` e `/addcomposto` (ex.: `400-1300` para evitar acessórios como cabos/capinhas por R$ 35).
  - Regras compostas com termos obrigatórios e exclusões (`/addcomposto ram16 | 16gb + ddr4 | notebook, sodimm | 120-220`).
  - Ignora valores de parcelas (`10x de R$ ...`), descontos (`R$ 50 off`) e preços antigos (`De R$ ...`) quando há preço atual.
- **Prioridade inteligente (Telegram vs MacroDroid) + Modo Madrugada (DND)**:
  - **Alta prioridade** (som normal no Telegram + abre no MacroDroid): Teto Atingido, Combo, Queda Real ≥ 75% e palavras explícitas de bug.
  - **Prioridade normal** (notificação silenciosa no Telegram, sem MacroDroid): palavras genéricas (`imperdível`, `corre`, `surreal`) ou quedas entre 65% e 74%.
  - **Modo Não Perturbe (`/dnd 0-7`)**: de madrugada, ignora palavras genéricas e deixa passar apenas bugs reais, tetos e combos.
- **Filtros extras rápidos (`/filtro`)**: opção para bloquear itens usados/recondicionados e compras internacionais/Remessa Conforme.
- **Alertas ricos e mais rápidos de decidir**:
  - Envia a **foto original** do post quando existir.
  - Destaca **cupons** no topo em bloco copiável (`<code>`), inclusive nos formatos `OFF: CODIGO`, `Código: XXX` e quebras de linha.
  - **Botões URL**: **Abrir Oferta**, **🛒 Carrinho Amazon** (via ASIN), **📊 Comparar Preço** (Keepa na Amazon BR ou Buscapé nas demais lojas) e **Post Original**.
  - **Botões inline no alerta**: **🤫 Silenciar 3h** (bloqueia repetições da oferta) e **🔕 Parar de monitorar "..."** (remove na hora a palavra, teto ou combo que gerou aquele alerta).
  - **Teclado fixo e assistentes visuais**: barra fixa embaixo do chat (`➕ Adicionar`, `➖ Remover`, `📋 Minhas listas`, `🎛️ Painel`, `⚡ Prioridades`, `🕘 Histórico`) para gerenciar tudo tocando em botões, sem precisar digitar `/`.
  - **Enriquecimento automático de alertas vagos**: se a postagem tiver só `"CORRE BUG + link"`, envia na hora e edita o alerta logo em seguida com o título e preço lidos da página.
- **Expansão de links e persistência 24/7**:
  - Resolve redirecionamentos de forma assíncrona (`asyncio.to_thread`), remove parâmetros de rastreamento e identifica produtos de **Amazon**, **Mercado Livre**, **Shopee**, **Kabum**, **Magalu** e **AliExpress**.
  - Persiste histórico de deduplicação, silenciamentos de 3h, últimos alertas e estatísticas diárias em `estado_bot.json` (resiste a reinícios).
  - Envia **resumo diário automático** (`/resumo 21`) e logs rotativos em `logs/bot.log`.

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
   - `TEMPO_DE_ESPERA`, `TEMPO_DUPLICATA`, `TEMPO_SILENCIO_HORAS`, `DESCONTO_MINIMO_AUTO`, `DESCONTO_CRITICO_MACRODROID` *(opcionais)*.

3. Inicie o bot:
   ```bash
   python bot.py
   ```

### Rodando 24/7 no Termux (Android)

Para evitar que o Android suspenda o processo ou pare o bot em caso de queda:
```bash
pkg install python
pip install telethon
chmod +x iniciar_termux.sh
./iniciar_termux.sh
```
O script [`iniciar_termux.sh`](iniciar_termux.sh) ativa o `termux-wake-lock` (se disponível) e reinicia `bot.py` automaticamente após 5 segundos se o processo encerrar por falha de rede.

## Comandos do Painel no Telegram

Ao iniciar, o bot registra os comandos automaticamente no menu `/` do Telegram. Você também pode abrir o painel visual `/menu` (ou usar os atalhos curtos, remoção por número e adição em lote com `;`):

| Comando (Atalho) | Descrição |
| --- | --- |
| `/menu` (`/m`, `/start`) | Abre painel visual interativo com botões e ativa o teclado fixo |
| `/teclado` | Reexibe o teclado fixo na parte inferior do chat |
| `/add` / `/rem` | Abre o assistente interativo para adicionar ou remover por botões |
| `/prioridade` (`/prio`) | Edita prioridades (ALTA vs NORMAL) de Teto, Combo, Quedas e Palavras |
| `/ajuda` (`/h`) | Lista todos os comandos e atalhos |
| `/lista` (`/l`) | Mostra listas numeradas (para remover pelo número) |
| `/status` (`/s`) | Estado atual, tempo online e estatísticas do dia |
| `/ranking` (`/rank`) | Ranking dos canais que mais geram alertas vs. canais mudos |
| `/ping` | Verifica se o bot está vivo na VPS/Termux e mede a latência |
| `/teste` (`/t`) | Envia alerta simulado com botões e testa o MacroDroid |
| `/simular` (`/sim texto`) | Simula extração (preço, desconto, parcelamento, cupom) e mostra se a regra dispararia |
| `/snooze` (`amazon 60`, `off`) | Silencia alertas de uma loja temporariamente sem afetar as demais |
| `/ultimos` (`/u`) | Exibe os últimos 10 alertas enviados |
| `/logs [30]` | Mostra as últimas linhas de `logs/bot.log` |
| `/backup` (`/b`) | Envia o `banco_de_dados.json` no chat (envie um `.json` de volta para restaurar) |
| `/pausar` (`/p` alterna) / `/retomar` (`/r`) | Pausa ou retoma o monitoramento |
| `/addcanal` (`/ac @c1 @c2`) / `/delcanal` (`/dc 1`) | Adiciona em lote ou remove por nº/nome |
| `/addpalavra` (`/ap t1; t2`) / `/delpalavra` (`/dp 1, 3`) | Adiciona em lote ou remove por nº/texto |
| `/addbloqueio` (`/ab t1; t2`) / `/delbloqueio` (`/db 1`) | Adiciona em lote ou remove por nº/texto |
| `/addteto` (`/at item, 400-1300`) / `/delteto` (`/dt 1`) | Define faixa min-max (ou só máx) e remove por nº/nome |
| `/addcomposto` (`/ax nome \| ter1 + ter2 \| ex \| 120-220`) / `/delcomposto` (`/dx 1`) | Cria regra composta e remove por nº/nome |
| `/setdesconto` (`/sd 65, 75`) | Define mínimo normal e crítico para MacroDroid (`off` desativa crítico, `0` desativa tudo) |
| `/dnd 0-7` / `/dnd off` | Configura horário do modo madrugada (Não Perturbe) |
| `/filtro usados on\|off` / `/filtro importacao on\|off` | Liga/desliga bloqueio automático de usados e importações |
| `/resumo` (`/res 21` / `off`) | Define a hora do resumo diário automático |
| `/getid` | Enviado por você dentro de um grupo/canal privado para receber o ID no bot |

## Estrutura do Projeto

- `bot.py`: clientes Telethon, painel de comandos, callbacks inline, envio de fotos e loop principal.
- `core.py`: lógica pura (configuração `.env`, banco JSON, persistência de estado, preços, filtros, cupons, links, scraping de título).
- `iniciar_termux.sh`: script de vigília com `termux-wake-lock` e reinício automático no Termux.
- `.env.example`: modelo das variáveis de ambiente.
- `.gitignore`: bloqueia `.env`, `*.session*`, `banco_de_dados.json`, `estado_bot.json`, backups `.bak`, chaves e `logs/`.
- `test_bot.py`: suíte de testes unitários.

## Testes

Execute os testes unitários localmente (usa stubs leves caso o `telethon` não esteja instalado na máquina):

```bash
python -m unittest -v test_bot.py
```

*(No Windows, se usar o launcher `py`, rode `py -m unittest -v test_bot.py`.)*

## Segurança

Nunca envie `.env`, `*.session*`, `banco_de_dados.json` ou `estado_bot.json` para repositórios públicos — todos já estão bloqueados no `.gitignore`.
