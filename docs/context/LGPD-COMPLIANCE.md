# Plano de Adequação à LGPD — Solve

> **Lei nº 13.709/2018 — Lei Geral de Proteção de Dados Pessoais**
> Última atualização: 2026-05-22

---

## Score de conformidade

| Data | Score | Situação |
|------|-------|----------|
| Auditoria inicial (2026-05-21) | 30/100 | Sem política, sem direitos, sem consentimento |
| Após sprint de implementação (2026-05-21) | 72/100 | Fundamentos legais implementados |
| Consentimento explícito + verificação de e-mail (2026-05-22) | 79/100 | Consentimento Art. 8º conforme; email verification configurado |
| Correção de dados, banner de cookies, bloqueio durante exclusão (2026-05-22) | 87/100 | Todos os direitos Art. 18 com UI; cookies informados; acesso bloqueado durante grace period |
| Log de auditoria completo — django-auditlog (2026-05-22) | **92/100** | Rastreamento de CREATE/UPDATE/DELETE em todos os modelos com dados pessoais |

---

## O que foi implementado

### Base técnica

| Item | Arquivo | Status |
|------|---------|--------|
| Campos LGPD no UserProfile (`pending_deletion`, `deletion_scheduled_at`, `lgpd_consent_at`, `lgpd_consent_version`) | `apps/accounts/models.py` | ✅ |
| Migration `0002_userprofile_lgpd` | `apps/accounts/migrations/0002_userprofile_lgpd.py` | ✅ |
| Registro de consentimento via sinal `user_signed_up` (email + Google OAuth) | `apps/accounts/signals.py`, `apps.py` | ✅ |

### Direitos do titular (Art. 18)

| Direito | Implementação | Status |
|---------|--------------|--------|
| **Portabilidade** — exportar dados em JSON | View `data_export` → GET `/accounts/exportar-dados/` | ✅ |
| **Eliminação** — excluir conta com grace period 30 dias | View `delete_account_request` → POST `/accounts/excluir-conta/` | ✅ |
| **Cancelamento da exclusão** | View `cancel_deletion_request` → POST `/accounts/cancelar-exclusao/` | ✅ |
| **Execução automática da exclusão** (após 30 dias) | Management command `purge_pending_deletions --dry-run` | ✅ |
| **Acesso** — visualizar dados cadastrais | Tela de Configurações → seção "Informações da conta" | ✅ |

### Transparência e comunicação

| Item | Localização | Status |
|------|-------------|--------|
| Página Política de Privacidade | `/privacidade/` → `legal/privacy.html` | ✅ |
| Página Termos de Uso | `/termos/` → `legal/terms.html` | ✅ |
| Links reais nos formulários de cadastro | `account/signup.html`, `accounts/register.html` | ✅ |
| Links no rodapé do site (base_marketing.html) | Política, Termos, LGPD | ✅ |
| UI de exclusão com banner de estado pendente | `dashboard/settings.html` | ✅ |
| DPO identificado com e-mail de contato | `privacidade@solve.com.br` na política e nas configurações | ✅ |
| Consentimento implícito com links visíveis no cadastro | Signup e register templates | ✅ |
| **Consentimento explícito** — checkbox obrigatório "Li e aceito os Termos e a Política de Privacidade" | `LGPDSignupForm` + `ACCOUNT_SIGNUP_FORM_CLASS` em settings; `account/signup.html`, `accounts/register.html` | ✅ |
| Verificação de e-mail configurável por ambiente | `ACCOUNT_EMAIL_VERIFICATION` via `.env` / Railway; `.env.example` documentado com instruções | ✅ |

---

## Pendências — O que falta fazer

### Prioridade Alta (bloqueia conformidade mínima)

| # | Item | Base LGPD | Esforço | Notas |
|---|------|-----------|---------|-------|
| 1 | **Preencher dados reais da empresa** — CNPJ, endereço físico do DPO, sede — atualmente com placeholders (`00.000.000/0001-00`) | Art. 41 (DPO) | < 1h | ⚠️ Aguardando CNPJ ativo. Editar `legal/privacy.html`, `legal/terms.html` e rodapé de `base_marketing.html` |
| ~~2~~ | ~~Consentimento explícito no cadastro~~ | ~~Art. 8º~~ | — | ✅ **Concluído** — `LGPDSignupForm` + `ACCOUNT_SIGNUP_FORM_CLASS` + checkbox no signup/register |
| ~~3~~ | ~~Verificação de e-mail em produção~~ | ~~Art. 6º, VII~~ | — | ✅ **Concluído** — Variável `ACCOUNT_EMAIL_VERIFICATION` configurável por env; Railway deve ter `mandatory` |

### Prioridade Média (boa prática e risco legal)

| # | Item | Base LGPD | Esforço | Notas |
|---|------|-----------|---------|-------|
| 4 | **Registro de Atividades de Tratamento (RAT)** — documento interno obrigatório para controladores com > 250 funcionários ou cujo tratamento apresente risco | Art. 37 | ~3h | Criar `docs/context/LGPD-RAT.md` descrevendo cada atividade: finalidade, base legal, dados, retenção, destinatários |
| 5 | **Cron job em produção** para `purge_pending_deletions` | Art. 18, IV (eliminação) | ~15min | ⚙️ Ver instruções abaixo — configuração no Railway Dashboard |
| ~~6~~ | ~~Direito de correção — UI para editar nome/e-mail~~ | ~~Art. 18, III~~ | — | ✅ **Concluído** — Formulário em `/dashboard/settings/` (nome, sobrenome, telefone + link para alterar e-mail via allauth) |
| ~~7~~ | ~~Log de auditoria de acesso a dados~~ | ~~Art. 6º, VII / Art. 46~~ | — | ✅ **Concluído** — `django-auditlog` 3.4.1; registra CREATE/UPDATE/DELETE em `User`, `UserProfile`, `Account`, `Transaction`, `RecurringTransaction`, `Goal`, `Investment`; visível no admin Django |
| ~~8~~ | ~~Aviso de cookies~~ | ~~Art. 6º, I / Art. 8º~~ | — | ✅ **Concluído** — Banner em `base.html`, estado em `localStorage`, link para seção de cookies da política |

### Prioridade Baixa (maturidade e escala)

| # | Item | Base LGPD | Esforço | Notas |
|---|------|-----------|---------|-------|
| 9 | **DPA (Data Processing Agreement) com subprocessadores** — Railway, AWS, Google | Art. 50 (boas práticas) | ~2h | Revisar contratos com Railway/AWS; o Google já possui DPA padrão |
| 10 | **RIPD — Relatório de Impacto à Proteção de Dados** | Art. 38 (ANPD pode solicitar) | ~4h | Mapear riscos por atividade de tratamento; necessário quando o tratamento for de alto risco |
| 11 | **Procedimento de resposta a incidentes** — playbook documentado | Art. 48 (notificação em 72h) | ~2h | Criar `docs/context/LGPD-INCIDENT-RESPONSE.md` com passo a passo: identificação → contenção → notificação ANPD → comunicação aos titulares |
| 12 | **Política de senhas e 2FA** — requisitos mínimos de segurança | Art. 46 (medidas de segurança) | ~3h | Adicionar validadores mais fortes; 2FA opcional via allauth-2fa |
| 13 | **Direito à informação sobre decisões automatizadas** — se o produto usar IA/ML para sugerir ações | Art. 20 | Futuro | Ainda não há IA no produto; documentar quando implementar |

---

## Cronograma sugerido

```
Sprint atual — concluído
  ├── #1 Preencher dados reais da empresa  ⚠️ aguardando CNPJ
  ├── #2 Checkbox de consentimento explícito  ✅
  └── #3 Email verification em produção  ✅ (setar ACCOUNT_EMAIL_VERIFICATION=mandatory no Railway)

Próximo sprint
  ├── #4 RAT (Registro de Atividades de Tratamento)
  ├── #5 Cron no Railway
  ├── #6 UI de correção de dados na tela de Configurações
  └── #7 Log de auditoria no admin

Roadmap (antes de escalar)
  ├── #8 Banner de cookies
  ├── #9 DPA com subprocessadores
  ├── #10 RIPD
  └── #11 Playbook de incidentes
```

---

## Configuração do Cron no Railway (item #5)

O Railway não suporta cron no `railway.toml` — cron jobs são serviços separados criados pelo dashboard.

### Passo a passo

1. Acesse [railway.app](https://railway.app) → abra o projeto **Solve**
2. Clique em **"+ New"** → **"Empty Service"**
3. Na aba **Settings** do novo serviço:
   - **Service Name**: `purge-deletions`
   - **Source**: mesmo repositório da aplicação principal
   - **Root Directory**: `frontend`
4. Na aba **Variables**, copie todas as variáveis de ambiente do serviço principal (especialmente `DATABASE_URL` e `SECRET_KEY`)
5. Na aba **Deploy** → **"Start Command"**:
   ```
   python manage.py purge_pending_deletions
   ```
6. De volta em **Settings** → role até **"Cron Schedule"** → ative e defina:
   ```
   0 3 * * *
   ```
   _(executa todo dia às 03h00 horário UTC — 00h00 BRT)_

7. Clique em **Deploy** — o Railway vai rodar o comando no horário configurado sem manter um servidor em pé.

### Verificar execução

- Railway → serviço `purge-deletions` → aba **Deployments** mostra cada execução com logs
- Para testar manualmente sem deletar nada: adicione `--dry-run` ao start command temporariamente

---

## Referência rápida — Bases legais em uso no Solve

| Atividade | Base Legal |
|-----------|-----------|
| Criação e manutenção da conta | Art. 7º, V — Execução de contrato |
| Prestação do serviço de gestão financeira | Art. 7º, V — Execução de contrato |
| Autenticação Google OAuth | Art. 7º, V — Execução de contrato |
| Segurança e prevenção a fraudes | Art. 7º, IX — Legítimo interesse |
| Registros fiscais e obrigações legais | Art. 7º, II — Obrigação legal |
| Melhoria do produto (dados agregados/anonimizados) | Art. 7º, IX — Legítimo interesse |

---

## Contatos

| Papel | Contato |
|-------|---------|
| DPO (Encarregado de Dados) | privacidade@solve.com.br |
| Suporte ao usuário | suporte@solve.com.br |
| ANPD (autoridade reguladora) | www.gov.br/anpd |
