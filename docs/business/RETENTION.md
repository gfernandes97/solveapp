# Solve — Retention Loop
**Versão:** v1.0.0 · **Data:** 2026-05-13

---

## O Problema de Retenção em Fintech

Apps de finanças pessoais têm um dos piores índices de retenção do mercado:
- **~70%** dos usuários abandonam em 30 dias
- **~15%** chegam ao terceiro mês
- **~5–8%** convertem para plano pago

**Dois modos de falha:**
1. App útil mas sem razão para voltar — nenhum trigger externo, nenhum hábito formado
2. App que pede esforço sem retornar valor — alto custo cognitivo, recompensa fraca

> Hábito não é uma feature. É um loop projetado.

---

## O Modelo: Hook Framework (Nir Eyal)

| Componente | O que é | Papel no Solve |
|-----------|---------|---------------|
| **Trigger** | O que dispara a ação (externo → interno) | Push, email, resumo automático |
| **Ação** | O menor esforço possível do usuário | Abrir o app e ver o resumo |
| **Recompensa Variável** | Surpresa + progresso visível | Insight novo, comparação, milestone |
| **Investimento** | O que o usuário deixa que aumenta o valor futuro | Categorias, metas, histórico |

O investimento aumenta a relevância do próximo trigger — o loop se fortalece a cada ciclo.

---

## Os 4 Loops do Solve

| # | Nome | Frequência | Gatilho | Propósito |
|---|------|-----------|---------|-----------|
| 01 | Alerta Contextual | Múltiplas vezes/semana | Gasto incomum ou fatura próxima | Intervenção antes do erro |
| 02 | Check-in Semanal | 1× por semana | Resumo automático gerado | Formação do hábito semanal |
| 03 | Fechamento Mensal | 1× por mês | Relatório mensal disponível | Ciclo de aprendizado e meta |
| 04 | Progresso de Metas | 2–3× por semana | Milestone ou prazo se aproximando | Retenção de longo prazo |

---

## Loop 01 — Alerta Contextual

**Frequência:** Múltiplas vezes por semana
**Objetivo:** Intervenção antes do erro — o insight chega antes da decisão ruim

| Etapa | O que acontece |
|-------|---------------|
| **Trigger** | Gasto incomum detectado ou fatura próxima do limite |
| **Ação** | Usuário abre o app para verificar e categorizar |
| **Recompensa** | Vê o impacto no orçamento em tempo real com contexto |
| **Investimento** | Transação categorizada enriquece histórico e padrões |

**Exemplo de notificação:**
> ⚡ Você gastou R$180 em delivery esta semana — 60% acima da sua média. Ainda dá tempo de ajustar antes do fim do mês.

---

## Loop 02 — Check-in Semanal

**Frequência:** 1× por semana (domingo ou segunda)
**Objetivo:** Criar o hábito de revisão financeira semanal

| Etapa | O que acontece |
|-------|---------------|
| **Trigger** | Resumo automático da semana gerado e enviado por push |
| **Ação** | Revisa a semana, confirma categorias |
| **Recompensa** | Semana em perspectiva, padrão novo descoberto |
| **Investimento** | Preferências de categorias aprimoram sugestões futuras |

**Exemplo de notificação:**
> 📊 Semana encerrada: R$1.840 gastos · 3 categorias acima do normal · R$420 economizados vs. semana passada.

---

## Loop 03 — Fechamento Mensal

**Frequência:** 1× por mês
**Objetivo:** Ciclo de aprendizado e definição de meta para o próximo mês

| Etapa | O que acontece |
|-------|---------------|
| **Trigger** | Relatório mensal gerado automaticamente no fechamento |
| **Ação** | Lê relatório, compara com mês anterior |
| **Recompensa** | Evolução visível, ranking pessoal, celebração |
| **Investimento** | Define meta para o próximo mês |

**Exemplo de notificação:**
> 🎯 Seu relatório de abril está pronto. Você gastou 12% menos que março e sobrou R$680 para investir.

---

## Loop 04 — Progresso de Metas

**Frequência:** 2–3× por semana
**Objetivo:** Retenção de longo prazo via comprometimento com objetivos pessoais

| Etapa | O que acontece |
|-------|---------------|
| **Trigger** | Milestone atingido ou prazo se aproximando |
| **Ação** | Vê progresso, atualiza aporte da meta |
| **Recompensa** | Barra de progresso, celebração de milestones |
| **Investimento** | Meta mais detalhada e prazo calibrado |

**Exemplo de notificação:**
> 🏆 Você chegou a 70% da reserva de emergência! Faltam R$1.200. No seu ritmo atual: mais 2 meses.

---

## Triggers por Persona

| Persona | Trigger principal | Exemplo de notificação |
|---------|------------------|----------------------|
| **P1 Jovem** | Gasto de impulso detectado | "Você gastou R$94 em compras hoje. Quer ver onde foi?" |
| **P2 Endividado** | Fatura se aproximando | "Fatura fecha em 3 dias. Você tem R$280 de margem — não ultrapasse." |
| **P3 Investidor** | Sobra calculada | "Sobrou R$530 este mês. Renderiam R$62 no CDB até dezembro." |
| **P5 Profissional** | Relatório disponível | "Relatório de maio pronto: 2 gastos incomuns detectados." |

---

## Jornada de Hábito

| Fase | Período | Marco | Loop ativado |
|------|---------|-------|-------------|
| **Ativação** | D1–D3 | Primeiro insight — aha moment | Alerta Contextual |
| **Formação** | D4–D14 | Primeira semana revisada | Check-in Semanal |
| **Consolidação** | D15–D30 | Primeiro relatório mensal | Fechamento Mensal |
| **Comprometimento** | D31–D60 | Primeira meta criada e acompanhada | Progresso de Metas |
| **Hábito formado** | D60+ | Ciclo mensal autossustentado | Todos os 4 loops |
| **Conversão** | M3 | Usuário percebe valor, converte para pago | — |

---

## Métricas de Retenção

| Métrica | Benchmark mercado | Meta Solve | O que otimizar se abaixo |
|---------|------------------|-----------|--------------------------|
| D1 (volta no dia seguinte) | 30–40% | 50% | Onboarding → primeiro insight mais rápido |
| D7 (completa primeira semana) | 15–25% | 30% | Trigger do check-in semanal |
| D30 (vê primeiro relatório) | 8–15% | 20% | Valor percebido na semana 2–3 |
| M3 (hábito formado) | 5–8% | 12% | Loop de metas + personalização |
| Conversão pago (M3) | 3–6% | 8% | Paywall no momento certo do ciclo |
