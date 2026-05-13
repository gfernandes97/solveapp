from django.shortcuts import render


def home(request):
    # SVG icons
    def svg(path_d, extra=""):
        return f'<svg class="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="{path_d}" {extra}/></svg>'

    features = [
        {
            "icon": svg("M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"),
            "title": "Análise Inteligente",
            "description": "O Solve lê seus extratos, categoriza automaticamente e entrega um panorama completo da sua vida financeira — sem você mover um dedo.",
        },
        {
            "icon": svg("M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"),
            "title": "Orientação Contextual",
            "description": "Mais que dados: o Solve entende seu momento financeiro e entrega orientação relevante na hora certa. Você sabe o que fazer, não só o que aconteceu.",
        },
        {
            "icon": svg("M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"),
            "title": "Sem Julgamento",
            "description": "Sem alertas agressivos, sem culpa. O Solve mostra sua realidade financeira com clareza para que você tome decisões — não se sinta mal.",
        },
    ]

    pain_points = [
        {"stat": "48%",   "label": "dos brasileiros não sabem para onde o dinheiro vai",         "source": "SPC Brasil"},
        {"stat": "85%",   "label": "dos endividados têm o cartão como principal dívida",          "source": "CNC"},
        {"stat": "82,8M", "label": "de CPFs negativados no Brasil — um recorde histórico",        "source": "Serasa"},
    ]

    steps = [
        {"title": "Crie sua conta", "description": "Menos de 2 minutos. Só precisa do seu e-mail."},
        {"title": "Adicione suas contas", "description": "Importe seu extrato. O Solve lê, categoriza e organiza tudo automaticamente."},
        {"title": "Agora você sabe.", "description": "Veja para onde vai cada real. Entenda seus padrões. Tome decisões com clareza."},
    ]

    stats = [
        {"value": "< 2 min", "label": "para ter seu panorama financeiro completo"},
        {"value": "R$ 0", "label": "de taxa de adesão ou fidelidade"},
        {"value": "30 dias", "label": "de garantia incondicional, sem perguntas"},
        {"value": "98%", "label": "de satisfação dos usuários na fase beta"},
    ]

    shield_svg = svg("M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z")
    lock_svg   = svg("M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z")
    eye_svg    = svg("M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z")

    security_items = [
        "Criptografia AES-256 em todos os dados",
        "Autenticação em dois fatores (2FA)",
        "Conformidade total com a LGPD",
        "Monitoramento de fraudes em tempo real",
        "Dados nunca vendidos a terceiros",
    ]

    security_badges = [
        {"icon": shield_svg, "title": "Banco Central do Brasil", "description": "Operamos sob regulação do BCB"},
        {"icon": lock_svg,   "title": "Criptografia ponta-a-ponta", "description": "AES-256 em trânsito e em repouso"},
        {"icon": eye_svg,    "title": "Dados nunca vendidos", "description": "Suas informações são suas — jamais repassadas a terceiros"},
    ]

    avatar_colors = ["bg-violet-500", "bg-indigo-500", "bg-emerald-500", "bg-amber-500", "bg-rose-500"]

    return render(request, "marketing/home.html", {
        "features": features,
        "pain_points": pain_points,
        "steps": steps,
        "stats": stats,
        "security_items": security_items,
        "security_badges": security_badges,
        "avatar_colors": avatar_colors,
    })


def pricing(request):
    plans = [
        {
            "name": "Grátis",
            "price": "R$0",
            "period": "para sempre",
            "description": "Para começar a se organizar.",
            "features": ["Até 2 contas", "Controle de gastos básico", "Resumo mensal"],
            "cta": "Começar grátis",
            "href": "/accounts/register/",
            "highlight": False,
        },
        {
            "name": "Essencial",
            "price": "R$19,90",
            "period": "por mês",
            "description": "Para quem quer visibilidade real das finanças.",
            "features": [
                "Contas ilimitadas",
                "Importação ilimitada de extratos",
                "Categorização automática inteligente",
                "Relatórios mensais completos",
                "Alertas de limite e vencimento",
            ],
            "cta": "Assinar Essencial",
            "href": "/accounts/register/?plan=essencial",
            "highlight": True,
        },
        {
            "name": "Pro",
            "price": "R$34,90",
            "period": "por mês",
            "description": "Para quem quer controle total e orientação personalizada.",
            "features": [
                "Tudo do Essencial",
                "Portfólio de investimentos",
                "Metas financeiras",
                "Orientação personalizada",
                "Relatórios avançados",
                "Suporte prioritário",
            ],
            "cta": "Assinar Pro",
            "href": "/accounts/register/?plan=pro",
            "highlight": False,
        },
    ]
    faqs = [
        {"question": "Preciso de cartão de crédito para criar minha conta?", "answer": "Não. O plano Grátis não exige nenhuma forma de pagamento. Você só precisa de um cartão caso queira fazer upgrade para o plano Pro."},
        {"question": "Posso cancelar a qualquer momento?", "answer": "Sim, sem fidelidade e sem multa. Basta acessar as configurações da conta e cancelar com um clique. Seus dados ficam disponíveis por 30 dias após o cancelamento."},
        {"question": "Como adiciono minhas contas e extratos?", "answer": "Você importa o extrato do seu banco em formato CSV ou OFX. O Solve lê, categoriza e organiza tudo automaticamente — você só precisa conferir."},
        {"question": "Meus dados financeiros estão seguros?", "answer": "Sim. Todos os dados são criptografados com AES-256 em trânsito e em repouso, seguindo os mesmos padrões de grandes bancos e em conformidade com a LGPD."},
        {"question": "O que acontece se eu ultrapassar o limite do plano Grátis?", "answer": "Você receberá um aviso e poderá fazer upgrade para o Pro. Nunca bloqueamos seu acesso ou cobraremos sem aviso prévio."},
    ]
    return render(request, "marketing/pricing.html", {"plans": plans, "faqs": faqs})
