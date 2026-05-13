# FinanceApp — Apresentações

Versionamento das apresentações PowerPoint do projeto.

## Como gerar

```bash
python scripts/generate_presentations.py
```

As versões são controladas pelas constantes `VERSION_MARKET` e `VERSION_COSTS`
no topo de `scripts/generate_presentations.py`. Para criar uma nova versão:
1. Incremente a constante relevante (ex: `v1.0.0` → `v1.1.0`)
2. Execute o script — o arquivo novo é gerado sem sobrescrever o anterior
3. Registre o changelog abaixo

---

## Apresentações

### Versão atual

| Arquivo | Versão | Data | Slides | Descrição |
|---------|--------|------|--------|-----------|
| [retention-v1.0.0.pptx](retention-v1.0.0.pptx) | v1.0.0 | 2026-05-13 | 10 | Retention loop · Hook Framework · 4 loops · triggers por persona · métricas |
| [positioning-v1.0.0.pptx](positioning-v1.0.0.pptx) | v1.0.0 | 2026-05-12 | 9 | Positioning statement · 5 componentes · vs. concorrência · proof points |
| [messaging-v1.0.0.pptx](messaging-v1.0.0.pptx) | v1.0.0 | 2026-05-12 | 11 | Messaging framework · hero universal · 4 personas · regras · lista negra |
| [brand-manual-v1.0.0.pptx](brand-manual-v1.0.0.pptx) | v1.0.0 | 2026-05-12 | 12 | Manual da marca Solve · paleta · logos · tipografia · voz |
| [prototype-v1.0.0.pptx](prototype-v1.0.0.pptx) | v1.0.0 | 2026-05-11 | 14 | Wireframes web MVP · 7 telas · personas × telas · métricas |
| [personas-v1.0.0.pptx](personas-v1.0.0.pptx) | v1.0.0 | 2026-05-11 | 15 | 8 perfis, ranking de dores, pain point central, problem statement |
| [market-research-v1.1.0.pptx](market-research-v1.1.0.pptx) | v1.1.0 | 2026-05-11 | 12 | + 3 slides de go-to-market |
| [costs-v1.1.0.pptx](costs-v1.1.0.pptx) | v1.1.0 | 2026-05-11 | 7 | Infra MVP com prestadores detalhados |

### Versões anteriores

| Arquivo | Versão | Data | Slides |
|---------|--------|------|--------|
| [market-research-v1.0.0.pptx](market-research-v1.0.0.pptx) | v1.0.0 | 2026-05-10 | 9 |
| [costs-v1.0.0.pptx](costs-v1.0.0.pptx) | v1.0.0 | 2026-05-10 | 7 |

---

## Changelog

### brand-manual

#### v1.0.0 — 2026-05-12
- Criação inicial
- Nome da marca: **Solve** · Tagline: **"Agora você sabe."**
- Paleta: Obsidian (#0F172A) · Solve Green (#00C97A) · Signal (#2563EB) · Solar (#F59E0B) · Cloud (#F8FAFC) · Smoke (#64748B)
- 8 variações de logo em `brand/logos/`: icon-only (3 variações), horizontal lockup (2), stacked (1), wordmark (2)
- Conceito do ícone: anel (ciclo do problema) + seta diagonal emergindo (saída com direção)
- 12 slides: Capa · Naming · Logo Concept · Logo Variants · Logo Rules · Colors · Color Combos · Typography · Voice & Tone · Tagline · Brand in Use · Principles

---

### market-research

#### v1.1.0 — 2026-05-11
- **Slide 9 novo:** Estratégia de entrada — posicionamento, canais orgânicos, pré-lançamento com lista de espera
- **Slide 10 novo:** Primeiros usuários 0→1.000 — funil de ativação em 5 passos, KPIs de onboarding, trabalho qualitativo
- **Slide 11 novo:** Escala 1.000→10.000+ — growth loops (upgrade/viral/content), canal B2B corporativo, paid acquisition
- Conclusão movida para slide 12

#### v1.0.0 — 2026-05-10
- Criação inicial
- Mercado brasileiro (TAM/SAM/SOM)
- Análise competitiva (Organizze, Mobills, Kinvo, Gorila, Guiabolso)
- Gap de mercado e benchmark YNAB
- 3 personas (Ana, Carlos, Lucas)
- Modelo de monetização freemium (Free / R$19,90 / R$34,90)
- Riscos de mercado
- Conclusão e próximos passos

---

### costs

#### v1.1.0 — 2026-05-11
- **Slide 3 redesenhado:** Infra MVP agora exibe 5 colunas — Componente, Prestador Principal, Por quê, Alternativas, Custo
- Prestadores detalhados: Railway · Upstash · Vercel · Cloudflare R2 · Pluggy · Asaas · Resend
- Nota sobre custo variável do Pluggy (por conexão ativa)

#### v1.0.0 — 2026-05-10
- Criação inicial
- Fases do projeto e custo por fase (MVP / Lançamento / Escala)
- Custos de infraestrutura Railway (MVP)
- Faixas salariais CLT Brasil 2026 com multiplicador 1,8×
- Break-even por número de usuários pagantes
- Unit economics (CAC / LTV / Payback)
- Resumo financeiro e recomendações
