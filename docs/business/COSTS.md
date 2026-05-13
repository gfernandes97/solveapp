# Levantamento de Custos — FinanceApp

> **Versão:** 1.0 | **Data:** 2026-05-10
> **ATENÇÃO:** Este documento deve ser atualizado a cada nova ideia ou decisão que impacte custos. Versionar com data.

---

## Sumário Executivo

| Fase | Custo Mensal Estimado | Observação |
|------|-----------------------|-----------|
| **MVP (pré-lançamento, 1 dev)** | R$1.500–3.000/mês | Só infra + ferramentas |
| **MVP com time mínimo** | R$25.000–45.000/mês | 2-3 devs + designer |
| **Pós-lançamento (1k usuários)** | R$4.000–8.000/mês | Infra cresce com usuários |
| **Escala (10k usuários pagantes)** | R$15.000–30.000/mês | Infra + suporte + marketing |

---

## 1. Custos de Infraestrutura (Fixos/Variáveis)

### 1.1 Hospedagem — Fase MVP (Railway/Render)

| Serviço | Custo/mês | Notas |
|---------|----------|-------|
| Backend (API) — 1 instância | R$60–150 | Railway ~$10–25/mês |
| Banco PostgreSQL | R$30–90 | Railway PostgreSQL |
| Redis (cache + filas) | R$30–60 | Railway Redis |
| Frontend (Vercel) | R$0–90 | Free tier suficiente no início |
| Storage (Cloudflare R2) | R$0–30 | 10GB free, depois $0.015/GB |
| **Total MVP infra** | **R$120–420/mês** | |

### 1.2 Hospedagem — Fase Escala (AWS/GCP)

| Serviço | Custo/mês | Notas |
|---------|----------|-------|
| ECS/Fargate (2 tasks) | R$300–600 | ~$50–100/mês |
| RDS PostgreSQL (t3.small) | R$200–400 | Multi-AZ custa o dobro |
| ElastiCache Redis (t3.micro) | R$120–250 | |
| CloudFront CDN | R$30–100 | Depende do tráfego |
| S3 Storage | R$10–50 | |
| Load Balancer | R$90–180 | |
| **Total escala (5–10k usuários)** | **R$750–1.580/mês** | |

---

## 2. Integrações Externas (Variáveis por Uso)

### 2.1 Open Finance — Agregador

| Provedor | Modelo de Cobrança | Estimativa |
|----------|-------------------|-----------|
| **Pluggy** | R$0,80–1,50 por conexão ativa/mês | 1.000 usuários conectados = R$800–1.500/mês |
| **Belvo** | R$1,00–2,00 por conexão ativa/mês | 1.000 usuários = R$1.000–2.000/mês |
| **Sem agregador (próprio)** | Custo dev alto (6–12 meses dev sênior) | Inviável no MVP |

> **Impacto:** Para cada 1.000 usuários com Open Finance ativo: +R$800–1.500/mês de custo variável

### 2.2 APIs de Dados de Mercado

| API | Free | Pago | Uso |
|-----|------|------|-----|
| **Brapi.dev** (B3) | 15.000 req/mês | R$50–200/mês | Cotações BR |
| **Alpha Vantage** (EUA) | 25 req/dia | ~R$280/mês (premium) | Ações US |
| **CoinGecko** (cripto) | Generoso | R$50–200/mês | Cripto |
| **Banco Central API** | Gratuito | — | SELIC, IPCA, CDI |

> **Estimativa combinada:** R$0 (MVP free tier) → R$500–1.000/mês (escala)

### 2.3 Comunicação com Usuário

| Canal | Custo | Volume estimado |
|-------|-------|----------------|
| Email (SendGrid/Resend) | R$0–150/mês | Free até 3k/mês; ~1k usuários = R$0 |
| Push notifications (Expo) | Gratuito | Expo Push é free |
| SMS (Twilio/Zenvia) | R$0,08–0,15/SMS | Só para autenticação crítica |

---

## 3. Gateway de Pagamento (para receber assinaturas)

| Provedor | Taxa | Observação |
|----------|------|-----------|
| **Stripe** | 3,4% + R$1,20/transação (cartão) | Melhor DX, suporte a PIX |
| **Asaas** | 2,99% (cartão) / R$2,00 flat (boleto) | Muito usado em SaaS BR |
| **Iugu** | 2,5% (cartão) / R$1,50 (boleto) | Boa API |
| **PagSeguro/PagarMe** | 3–4% | Mais complexo |

> **Estimativa com 1.000 assinantes a R$25/mês:**
> - Receita bruta: R$25.000/mês
> - Taxa gateway (3%): R$750/mês
> - **Receita líquida de gateway:** R$24.250/mês

---

## 4. Ferramentas e SaaS

| Ferramenta | Custo/mês | Função |
|-----------|----------|--------|
| GitHub (Team) | R$50 | Repositório + CI/CD |
| Sentry | R$0–150 | Monitoramento de erros |
| Figma | R$100–200 | Design de produto |
| Linear / Jira | R$50–100 | Gestão de projeto |
| Notion | R$0–50 | Documentação interna |
| Intercom / Crisp | R$150–500 | Chat de suporte |
| Mixpanel / PostHog | R$0–300 | Analytics de produto |
| **Total ferramentas** | **R$350–1.300/mês** | |

---

## 5. Custos de Desenvolvimento (Se Contratar)

### Perfis e faixas salariais (CLT, São Paulo, 2026)

| Perfil | Júnior | Pleno | Sênior |
|--------|--------|-------|--------|
| Backend (Node/Python) | R$4.000–7.000 | R$8.000–13.000 | R$14.000–22.000 |
| Frontend (React/Next.js) | R$3.500–6.000 | R$7.000–12.000 | R$12.000–20.000 |
| Mobile (React Native) | R$4.000–7.000 | R$8.000–13.000 | R$14.000–22.000 |
| Designer UI/UX | R$3.500–6.000 | R$6.000–10.000 | R$10.000–16.000 |
| Product Manager | — | R$8.000–14.000 | R$15.000–25.000 |

> **Custo real CLT = Salário × ~1,8** (encargos: FGTS, férias, 13°, INSS, etc.)

### Cenários de time

| Cenário | Composição | Custo/mês |
|---------|------------|----------|
| **Solo (founder dev)** | Você + freelancers pontuais | R$5.000–15.000 |
| **Time mínimo MVP** | 1 fullstack + 1 designer | R$25.000–40.000 |
| **Time produto** | 2 devs + designer + PM | R$55.000–90.000 |
| **Time escala** | 4 devs + 2 designers + PM + QA | R$120.000–200.000 |

---

## 6. Marketing e Aquisição de Usuários (CAC)

| Canal | CPL estimado | Observação |
|-------|-------------|-----------|
| SEO / Conteúdo orgânico | R$5–20/lead | Mais lento, melhor ROI longo prazo |
| Instagram/TikTok Ads | R$15–60/lead | Efetivo para Gen-Z |
| Google Ads | R$20–80/lead | Boa intenção de compra |
| Influenciadores de finanças | R$30–100/lead | Alto alcance, menor conversão |
| Indicação (referral) | R$5–15/lead | Melhor CAC se NPS alto |

> **Meta realista:** CAC de R$30–80 com LTV de R$600–1.800 (2–4 anos de retenção a R$25/mês)

---

## 7. Resumo — Burn Rate por Fase

### Fase 1: MVP Solo (0–6 meses)
| Item | Custo/mês |
|------|----------|
| Infra (Railway) | R$200–400 |
| Pluggy (Open Finance) | R$0–500 (teste) |
| APIs dados mercado | R$0–200 |
| Ferramentas dev | R$200–500 |
| **TOTAL** | **R$400–1.600/mês** |

### Fase 2: Lançamento com Time (6–18 meses)
| Item | Custo/mês |
|------|----------|
| 2 devs + designer | R$40.000–60.000 |
| Infra (Railway/AWS) | R$500–1.500 |
| Pluggy (1k usuários) | R$800–1.500 |
| Gateway pagamento | R$500–1.000 |
| Marketing | R$3.000–10.000 |
| Ferramentas | R$500–1.000 |
| **TOTAL** | **R$45.000–75.000/mês** |

### Fase 3: Escala (18 meses+)
| Item | Custo/mês |
|------|----------|
| Time (5–8 pessoas) | R$80.000–150.000 |
| Infra AWS | R$1.500–5.000 |
| Pluggy (5k+ usuários) | R$4.000–8.000 |
| Marketing | R$15.000–40.000 |
| Outras | R$3.000–8.000 |
| **TOTAL** | **R$103.000–211.000/mês** |

---

## 8. Ponto de Break-Even (Projeção)

Com plano médio de R$25/mês:

| Usuários pagantes | Receita/mês | Break-even? |
|-------------------|-------------|-------------|
| 500 | R$12.500 | Não (infra solo barely) |
| 2.000 | R$50.000 | Sim (fase solo) |
| 5.000 | R$125.000 | Sim (time pequeno) |
| 10.000 | R$250.000 | Sim (time médio) |

> **Meta de 18 meses:** 5.000 usuários pagantes = sustentável com time de 4–6 pessoas

---

## Histórico de Atualizações

| Data | Versão | O que mudou |
|------|--------|-------------|
| 2026-05-10 | 1.0 | Levantamento inicial |
