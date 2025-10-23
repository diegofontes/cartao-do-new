# Django 5 + Stripe (Consumo Mensal) — Exemplo Completo

Stack: **Django 5**, **Poetry**, **Taskipy**, **Pytest**, **HTMX**, **Tailwind CSS**, **Redis (cache/filas)**, **Celery**.

## O que este exemplo cobre

- Cadastro/login de usuário (Django auth).
- Criação do **Customer no Stripe** ao cadastrar.
- **Cadastro de cartão** via **SetupIntent** (Stripe Elements).
- Dashboard com **consumo do mês** e **faturas**.
- **Cobrança mensal por consumo** (modelo *pay-as-you-go*):
  - Eventos de uso fictício (botão para simular).
  - Fechamento de ciclo mensal (calendário: 1º ao último dia do mês).
  - Geração de **Invoice** no Stripe com **InvoiceItem** baseado no consumo agregado do período.
  - Cobrança **automática** (collection_method = charge_automatically).
- **Rotinas**: faturamento (Celery/beat ou comando), cancelamento, atualização de forma de pagamento, simulação de consumo.
- **DX** com Poetry + Taskipy (dev/worker/beat/test/lint).
- **Testes** Pytest para o fluxo principal (com *mocks* do Stripe).

> **Observação**: Para simplificar o exemplo e manter legibilidade, usamos **Invoice + InvoiceItem** na virada do mês em vez de *subscription metered*. A experiência do usuário é a mesma (cobrança recorrente por consumo) e o código fica mais didático.

---

## Pré‑requisitos

- Python 3.11+
- Redis acessível (local ou Docker)
- Conta Stripe + chaves de API (test mode)
- (Opcional) Node não é necessário; **Tailwind** é via CDN (play).

### Subindo um Redis rápido com Docker

```bash
docker run -p 6379:6379 --name redis -d redis:7-alpine
```

---

## Setup

1) **Instalar dependências (com dev)**

```bash
poetry install --with dev
```

2) **Configurar variáveis** (copie `.env.example` para `.env` e edite):

```bash
cp .env.example .env
```

3) **Migrar e criar superuser**

```bash
poetry run python manage.py migrate
poetry run python manage.py createsuperuser
```

4) **Rodar os serviços** (em terminais separados):

```bash
poetry run task dev     # Django
poetry run task worker  # Celery worker
poetry run task beat    # Celery beat (agenda mensal)
```
%
5) **Webhook do Stripe** (opcional, mas recomendado para atualizar status de faturas)

Em outra janela, usando a CLI do Stripe:

```bash
stripe listen --forward-to localhost:8000/stripe/webhook/
```

---

## Fluxo de uso

1. Acesse `http://localhost:8000/` → cadastre-se.
2. No primeiro login, o sistema cria um **Customer** no Stripe.
3. Vá em **Pagamento** e cadastre um cartão (SetupIntent + Elements). 
4. Na **Dashboard**, use o botão **"Simular Consumo"** (HTMX) algumas vezes.
5. Feche o ciclo manualmente com:

```bash
poetry run python manage.py run_billing
```

Ou deixe o **Celery Beat** executar todo dia 1º às 00:05.
6. Veja as **faturas** na Dashboard; clique para abrir a versão hospedada no Stripe.

---

## Estrutura resumida

```
config/
apps/
  accounts/
  billing/
  dashboard/
templates/
tests/
```

---

## Variáveis (.env)

Veja `.env.example`. Principais:
- `SECRET_KEY`: qualquer string para dev
- `DEBUG`: `1` para dev
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET` (se usar webhook)
- `REDIS_URL` (padrão: `redis://localhost:6379/0`)
- `UNIT_PRICE_CENTS` (preço por unidade de consumo; padrão 25 = $0.25)
- `DEFAULT_CURRENCY` (padrão `usd`)

---

## Testes

```bash
poetry run task test
```

Os testes fazem *mock* das chamadas ao Stripe.

---

## Lint

```bash
poetry run task lint
```

---

## Tailwind CSS (django-tailwind)

Este projeto pode usar Tailwind localmente (sem CDN) usando o pacote de integração com Django.

Comandos úteis (Taskipy):

```bash
# Inicializar o app de tema do Tailwind (cria app `theme/`)
poetry run task tw-init

# Instalar dependências do tema (tailwind cli e afins)
poetry run task tw-install

# Build de CSS para produção
poetry run task tw-build

# Dev server (watch) para rebuild automático
poetry run task tw-dev
```

Após inicializar, aponte seu template base para o CSS gerado pelo app `theme` (ex.: `{% static 'css/dist/styles.css' %}` ou caminho gerado pelo tema).

Observação: este projeto usa `django-tailwind`. Instale a lib e siga o `init` para criar o app `theme`.

### Instalação

1) Adicionar dependência (Poetry):

```bash
poetry add -G dev django-tailwind
```

2) Ativar no settings:

- `config/settings.py`: já contém `"tailwind"` em `INSTALLED_APPS` e `TAILWIND_APP_NAME = "theme"`.
- Após o passo de init, adicione `"theme"` em `INSTALLED_APPS` também.

3) Inicialização do app de tema e build:

```bash
poetry run task tw-init   # cria app theme/
poetry run task tw-install
poetry run task tw-dev    # watch para desenvolvimento
# ou
poetry run task tw-build  # build para produção
```

4) Uso no template:

O arquivo base já referencia `{% static 'css/dist/styles.css' %}`.
Garanta que seu app `theme` esteja gerando a saída nesse caminho (ajuste output se necessário).

---

### Campo "Sobre" (Markdown)

Cards possuem agora uma aba **Sobre** com suporte a Markdown sanitizado:

- O conteúdo é editado no dashboard em uma tela com preview ao vivo.
- O editor utiliza **EasyMDE** para oferecer barra de ferramentas Markdown.
- Limite de **20.000 caracteres** para Markdown (HTML sanitizado máximo 100.000).
- Tags permitidas: títulos (`h1`–`h6`), parágrafos, listas, blockquote, code/pre, tabelas, links e imagens com URLs públicas.
- Links externos abrem em nova aba com `rel="noopener noreferrer nofollow"`.
- A aba só aparece no viewer quando houver conteúdo válido.

Se precisar ajustar a ordem das outras abas (Links, Galeria, Serviços/Menu), use a seção “Ordem das abas”; o “Sobre” sempre é exibido automaticamente quando houver texto.

---

## Notas

- Este projeto é **educacional**. Antes de ir a produção, trate *idempotência*, *retries*, *observabilidade*, segurança de webhooks, etc.
- Se preferir **metered billing** nativo, substitua a fatura manual por **Subscription + metered Price + usage_records**.




## Daily via CLI:

python manage.py billing_run_daily
