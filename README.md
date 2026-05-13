# FinanceApp — Plataforma de Finanças Pessoais e Educação de Investimentos

## Visão do Produto

Plataforma B2C com dois pilares integrados:
1. **Controle de Gastos** — rastreamento inteligente de despesas, metas e orçamentos
2. **Educação e Acompanhamento de Investimentos** — portfólio, trilhas educativas, simuladores

**Diferencial:** integrar os dois pilares em uma única experiência coesa. Os apps brasileiros existentes atendem um ou outro — nunca os dois com educação financeira integrada.

**Público-alvo:** Millennials e Gen-Z brasileiros (18–42 anos), especialmente quem está iniciando a vida financeira ou ainda não tem assessoria de investimentos.

## Estrutura do Repositório

```
financeapp/
├── docs/
│   ├── market-research/      # Estudos de mercado, concorrentes, TAM/SAM/SOM
│   ├── architecture/         # Arquitetura técnica, diagramas, ADRs
│   ├── business/             # Custos, modelo de receita, pricing
│   └── context/              # Contexto de sessões com Claude, decisões de produto
├── backend/                  # API e serviços back-end
├── frontend/                 # App web (Next.js)
├── mobile/                   # App mobile (React Native)
├── infra/                    # IaC, Docker, Kubernetes, CI/CD
└── scripts/                  # Scripts auxiliares
```

## Status

| Item | Status |
|------|--------|
| Conceito e visão | ✅ Definido |
| Pesquisa de mercado | ✅ Concluída (v1) |
| Arquitetura técnica | ✅ Esboçada (v1) |
| Modelo de custos | ✅ Levantado (v1) |
| MVP definido | 🔲 Pendente |
| Modelo de monetização | 🔲 Pendente |
| Protótipo | 🔲 Pendente |

## Próximos Passos

1. Definir escopo do MVP
2. Definir modelo de monetização (freemium vs. assinatura)
3. Prototipar as telas principais
4. Validar com usuários-alvo
