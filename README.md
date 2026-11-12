# Bot Caçador de Promoções e Bugs (Telegram)

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Telethon](https://img.shields.io/badge/Library-Telethon-2CA5E0?style=flat&logo=telegram&logoColor=white)](https://docs.telethon.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Architecture](https://img.shields.io/badge/Architecture-AsyncIO%20%7C%20Zero--Dep-blue)](core.py)
[![Tests](https://img.shields.io/badge/Tests-Unit%20Tests%20(Coverage)-success)](test_bot.py)

Sistema em Python assíncrono para monitoramento em tempo real de canais e grupos do Telegram, desenvolvido para detecção, filtragem e enriquecimento de ofertas relâmpago e bugs de preço com priorização multicanal (Telegram e webhook para automação no MacroDroid).

---

## 🎯 Destaques de Engenharia e Boas Práticas

Este projeto foi desenhado focando em performance, baixo consumo de recursos e segurança defensiva:

- **Arquitetura Assíncrona & Reativa (`asyncio` + Telethon)**: processamento não-bloqueante de múltiplos streams de eventos de mensagens (`NewMessage` e `MessageEdited`) via MTProto, com workers assíncronos para tarefas de I/O de rede.
- **Segurança de Rede Defensiva**:
  - **Anti-SSRF**: validação rigorosa de endereços IP contra redes privadas, loopback e metadados de nuvem (`169.254.169.254`) antes de qualquer expansão de link HTTP.
  - **DNS Pinning**: resolução antecipada de nomes e amarração de IP durante redirecionamentos, impedindo ataques de DNS rebinding.
  - **Mitigação de ReDoS**: sanitização e limites estruturais para expressões regulares dinâmicas cadastradas pelo usuário.
- **Persistência Confiável e I/O Atômico**: gravação de estado com `fsync` em disco para evitar corrupção de dados em caso de reinicialização abrupta ou falta de energia do host.
- **Design Desacoplado**:
  - `core.py`: Lógica de domínio pura (sanitização de links, extração de preços/descontos/cupons, banco de dados JSON e regras de filtragem), desacoplada de frameworks de mensageria.
  - `bot.py`: Camada de aplicação e apresentação (handlers de comandos, interfaces com botões inline e integração com webhooks).
- **Testes Automatizados**: suíte extensa de testes unitários com fakes de eventos e stubs para validação isolada de toda a lógica de parsing e fluxo de alertas sem dependência de rede externa.

---

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

## Instalação e Requisitos

- **Python 3.9+**
- Instalação via `requirements.txt`:
  ```bash
  pip install -r requirements.txt
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
| `/buscar termo` | Pesquisa nos últimos alertas por loja, motivo, canal ou link |
| `/logs [30]` | Mostra as últimas linhas de `logs/bot.log` |
| `/backup` (`/b`) | Envia o `banco_de_dados.json` no chat (envie um `.json` de volta para restaurar) |
| `/pausar [min]` (`/p` alterna) / `/retomar` (`/r`) | Pausa (com retorno automático opcional em X min) ou retoma o monitoramento |
| `/addcanal` (`/ac @c1 @c2`) / `/delcanal` (`/dc 1`) | Adiciona em lote ou remove por nº/nome |
| `/addpalavra` (`/ap t1; t2`) / `/delpalavra` (`/dp 1, 3`) | Adiciona em lote ou remove por nº/texto |
| `/addbloqueio` (`/ab t1; t2`) / `/delbloqueio` (`/db 1`) | Adiciona em lote ou remove por nº/texto |
| `/addteto` (`/at item, 400-1300`) / `/delteto` (`/dt 1`) | Define faixa min-max (ou só máx) e remove por nº/nome *(com botão rápido de excluir após criar)* |
| `/addcomposto` (`/ax nome \| ter1 + ter2 \| ex \| 120-220`) / `/delcomposto` (`/dx 1`) | Cria regra composta e remove por nº/nome *(com botões `+ Exclusão` e `Excluir Combo` após criar)* |
| `/exc` (`/addexc nome t1, t2`) | Acrescenta novas exclusões a um combo existente sem reescrever o `/ax` inteiro |
| `/setdesconto` (`/sd 65, 75`) | Define mínimo normal e crítico para MacroDroid (`off` desativa crítico, `0` desativa tudo) |
| `/dnd` / `/dnd 23-7` / `/dnd off` | Abre editor visual por botões ou ajusta o horário do Não Perturbe |
| `/filtro usados on\|off` / `/filtro importacao on\|off` | Liga/desliga bloqueio automático de usados e importações |
| `/resumo` (`/res 21` / `off`) | Define a hora do resumo diário automático |
| `/getid` | Enviado por você dentro de um grupo/canal privado para receber o ID no bot |

## Estrutura do Projeto

- `bot.py`: interface com Telegram, handlers de eventos e comandos, callbacks inline e loop principal.
- `core.py`: regras de negócio puras (parsing de preços, cupons, persistência com fsync, anti-SSRF, DNS pinning, ranking).
- `requirements.txt`: declaração de dependências do projeto.
- `LICENSE`: termos de licença open-source (MIT).
- `iniciar_termux.sh`: script de vigília com `termux-wake-lock` e reinício automático no Termux.
- `.env.example`: modelo documentado das variáveis de ambiente.
- `.gitignore`: proteção contra commits acidentais de segredos (`.env`, `.session*`, `.key`, logs e bancos locais).
- `test_bot.py`: suíte completa de testes unitários automatizados.

## Testes

Execute os testes unitários localmente (usa stubs leves caso o `telethon` não esteja instalado na máquina):

```bash
python -m unittest -v test_bot.py
```

*(No Windows, se usar o launcher `py`, rode `py -m unittest -v test_bot.py`.)*

## Segurança

Nunca envie `.env`, `*.session*`, `banco_de_dados.json` ou `estado_bot.json` para repositórios públicos — todos já estão bloqueados no `.gitignore`.
