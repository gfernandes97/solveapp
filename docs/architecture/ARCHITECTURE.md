# Arquitetura Técnica — FinanceApp

> **Versão:** 1.0 | **Data:** 2026-05-10 | **Status:** Esboço inicial

## Princípios

- **Mobile-first:** React Native como plataforma primária
- **API-first:** backend desacoplado, suporta mobile + web
- **Incremental:** MVP simples, escala conforme usuários crescem
- **Open Finance:** integração nativa com o ecossistema regulado pelo Banco Central

---

## Stack Tecnológica Recomendada

### Backend
| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Linguagem | **TypeScript + Node.js** | Ecossistema amplo, mesmo time faz mobile |
| Framework API | **Fastify** ou **NestJS** | Fastify = performance; NestJS = estrutura enterprise |
| ORM | **Prisma** | Type-safe, migrações simples |
| Banco de dados | **PostgreSQL** | Relacional + JSONB para dados flexíveis |
| Cache | **Redis** | Sessões, rate limiting, cache de portfólios |
| Filas | **BullMQ** (sobre Redis) | Jobs assíncronos: sync bancário, notificações |
| Auth | **JWT + OAuth2** | Login social (Google) + email/senha |
| Storage | **AWS S3** ou **Cloudflare R2** | Avatares, extratos, recibos |

### Frontend Web
| Camada | Tecnologia |
|--------|-----------|
| Framework | **Next.js 15** (App Router) |
| Estilo | **TailwindCSS + shadcn/ui** |
| Estado | **Zustand** + **React Query** |
| Gráficos | **Recharts** ou **Tremor** |

### Mobile (Prioritário)
| Camada | Tecnologia |
|--------|-----------|
| Framework | **React Native + Expo** |
| Navegação | **React Navigation** |
| Estado | **Zustand** + **React Query** |
| UI | **NativeWind** (Tailwind no RN) |

### Infraestrutura
| Item | MVP | Escala |
|------|-----|--------|
| Hospedagem | **Railway** ou **Render** | **AWS ECS** ou **GCP Cloud Run** |
| Banco | Railway PostgreSQL | AWS RDS (Multi-AZ) |
| CDN | Cloudflare (free) | Cloudflare Pro |
| CI/CD | GitHub Actions | GitHub Actions + ArgoCD |
| Monitoramento | Sentry (free tier) | Sentry + Datadog |
| Logs | Logtail (free tier) | Logtail / CloudWatch |

---

## Arquitetura de Alto Nível

```
┌─────────────────────────────────────────────────────┐
│                    CLIENTES                         │
│   [App Mobile (RN)]   [Web (Next.js)]               │
└───────────────┬──────────────────┬──────────────────┘
                │  HTTPS/REST      │  HTTPS/REST
                ▼                  ▼
┌─────────────────────────────────────────────────────┐
│              API Gateway / Load Balancer             │
│              (Nginx ou AWS ALB)                      │
└─────────────────────┬───────────────────────────────┘
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   [Auth Service] [Core API]  [Notification Svc]
   (JWT/OAuth)   (Fastify)    (Email/Push)
        │             │
        └──────┬───────┘
               ▼
┌──────────────────────────────────────────┐
│              PostgreSQL (principal)       │
│              Redis (cache + filas)        │
└──────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│     Integrações Externas                 │
│  Open Finance (Belvo/Pluggy)             │
│  B3 / cotações (Alpha Vantage / Brapi)   │
│  Gateway de pagamento (Stripe/Asaas)     │
│  Push notifications (Expo / FCM / APNs) │
└─────────────────────────────────────────┘
```

---

## Domínios do Sistema

### 1. Auth & Usuários
- Cadastro, login (email + Google)
- Perfil financeiro (renda declarada, objetivos)
- KYC leve (nome, CPF — para Open Finance)

### 2. Controle de Gastos
- Lançamento manual de transações
- Categorização automática (ML básico ou regras)
- Importação via OFX/CSV
- Integração Open Finance (automação bancária)
- Orçamentos por categoria, alertas de limite
- Metas de economia

### 3. Investimentos
- Cadastro manual de posições (ações, FIIs, renda fixa, cripto)
- Cotações em tempo real/EOD via API
- Cálculo de rentabilidade (nominal, real, vs. IPCA/CDI/IBOVESPA)
- Importação de notas de corretagem (PDF parsing)

### 4. Educação Financeira
- Trilhas de conteúdo (texto + vídeo embed)
- Simuladores: juros compostos, aposentadoria, financiamento
- Glossário de termos
- Quizzes gamificados

### 5. Notificações & Alertas
- Contas a pagar
- Limites de orçamento atingidos
- Variação relevante em ativos
- Metas alcançadas

---

## Integrações-Chave

### Open Finance (Crítico)
O Banco Central obriga bancos a exporem dados via Open Finance. Usaremos um agregador:

| Opção | Custo | Notas |
|-------|-------|-------|
| **Pluggy** | R$0,50–1,50/conexão/mês | Mais completo no BR, ótima DX |
| **Belvo** | R$0,80–2,00/conexão/mês | Mais robusto, LA-focused |
| **Próprio** | Alto capex dev | Inviável no MVP |

**Recomendação MVP:** Pluggy

### Dados de Mercado
| Dado | API | Custo |
|------|-----|-------|
| Ações BR (B3) | **Brapi.dev** | Free até 15k req/mês |
| Ações EUA | **Alpha Vantage** | Free (25 req/dia) → $50/mês premium |
| Criptos | **CoinGecko** | Free tier generoso |
| Renda fixa (CDB/LCI/LCA) | Manual + APIs de corretoras | Negociação direta |

---

## Modelo de Dados Simplificado

```
User
  └─ Account (conta bancária / carteira)
       └─ Transaction (receita / despesa)
            └─ Category

User
  └─ Budget (orçamento mensal por categoria)
  └─ Goal (meta de economia)

User
  └─ Portfolio
       └─ Position (ativo + quantidade + preço médio)
            └─ Asset (ação, FII, crypto, renda fixa)

User
  └─ EducationProgress
       └─ CourseTrack
            └─ Lesson
```

---

## Decisões de Arquitetura (ADRs)

| # | Decisão | Escolha | Motivo |
|---|---------|---------|--------|
| 001 | Plataforma mobile | React Native + Expo | Mesmo time, código compartilhado, Expo simplifica build |
| 002 | Monolito vs. microsserviços | **Monolito modular** no MVP | Menor complexidade operacional; refatora depois |
| 003 | Open Finance | Pluggy (aggregator) | Terceiriza compliance, acelera MVP |
| 004 | Banco de dados | PostgreSQL único | JSONB para flexibilidade sem overhead de NoSQL |
| 005 | Hospedagem MVP | Railway | Zero DevOps overhead, pay-as-you-go |
