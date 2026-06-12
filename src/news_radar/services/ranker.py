from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from dateutil import parser as date_parser

from news_radar.core.text_utils import count_terms, extract_money_values

PUBLIC_ORG_TERMS = [
    "governo", "prefeitura", "câmara", "camara", "assembleia", "ministério", "ministerio",
    "secretaria", "tribunal", "justiça", "justica", "polícia federal", "policia federal",
    "pf", "mp", "ministério público", "ministerio publico", "tce", "tcu", "cgu",
    "stf", "stj", "congresso", "senado", "deputados", "vereador", "deputado",
    "governador", "prefeito", "alegando", "edital",
]

RISK_TERMS = [
    "denúncia", "denuncia", "investigação", "investigacao", "operação", "operacao",
    "fraude", "desvio", "corrupção", "corrupcao", "improbidade", "suspeita",
    "irregularidade", "prisão", "prisao", "mandado", "busca e apreensão", "cassação",
    "cassacao", "inelegível", "inelegivel", "ação civil pública", "acao civil publica",
    "tce", "mppi", "mpf", "pf", "polícia federal", "controladoria",
]

MONEY_PUBLIC_TERMS = [
    "contrato", "licitação", "licitacao", "pregão", "pregao", "dispensa",
    "inexigibilidade", "aditivo", "obra", "convênio", "convenio", "empenho",
    "orçamento", "orcamento", "verba", "recurso", "repasse", "milhões", "milhoes",
    "bilhões", "bilhoes", "r$", "compras públicas", "compras publicas",
]

SOCIAL_IMPACT_TERMS = [
    "saúde", "saude", "hospital", "ubs", "upa", "educação", "educacao", "escola",
    "creche", "transporte", "ônibus", "onibus", "segurança", "seguranca",
    "saneamento", "água", "agua", "energia", "moradia", "enchente", "lixo",
    "coleta", "asfalto", "obra", "mobilidade", "medicamento",
]

PIAUI_TERMS = [
    "piauí", "piaui", "teresina", "parnaíba", "parnaiba", "floriano",
    "piripiri", "campo maior", "alegrete do piaui", "governo do piauí", "governo do piaui",
    "alepi", "tce-pi", "tce pi", "mppi", "tjpi",
    "rafael fontes", "rafael fonteles",
    # "picos" removido — falso positivo em "picos de calor", "picos de energia", etc.
]

# ── Sinais de Teresina ────────────────────────────────────────────────────────
# Organizado em tiers de especificidade.
# Hard gate: artigo precisa de pelo menos 1 sinal aqui para receber score > 0.
#
# Tier 1 — Explícito / altíssima especificidade (peso máximo no scoring)
TERESINA_EXPLICIT = [
    "teresina", "teresinense",
    "prefeitura de teresina", "câmara de teresina", "camara de teresina",
    "câmara municipal de teresina", "camara municipal de teresina",
    "prefeito de teresina",
    "capital do piauí", "capital do piaui",
    "capital piauiense",
]

# Tier 2 — Instituições e órgãos exclusivos de Teresina
TERESINA_INSTITUTIONS = [
    # Saúde municipal
    "hut", "hospital de urgência de teresina", "hospital de urgencia de teresina",
    "fundação municipal de saúde", "fundacao municipal de saude",
    "fms teresina",
    "upa zona norte", "upa zona sul", "upa zona leste", "upa zona sudeste",
    "upa teresina",
    "policlínica teresina", "policlinica teresina",
    "cmu teresina",
    # Transporte e urbanismo
    "strans", "eturb",
    "terminal integração", "terminal de integração",
    "terminal de integracao", "terminal integracao",
    "ciretran teresina",
    # Educação
    "semec",
    "seduc teresina",
    "uespi teresina",
    # Assistência social / segurança
    "saad", "arsete",
    "semdec teresina",
    "creas teresina", "cras teresina",
    # Segurança
    "bpre", "batalhão de polícia de eventos",
    "pm teresina", "policia teresina",
    "delegacia teresina",
    # Obras e urbanização
    "semar teresina",
    "semplan teresina",
    "semduh",
]

# Tier 3 — Bairros, zonas e lugares com alta especificidade
TERESINA_PLACES = [
    # Bairros com alta frequência noticiosa
    "dirceu arcoverde", "bairro dirceu",
    "promorar", "bairro promorar",
    "mocambinho", "bairro mocambinho",
    "piçarreira", "picarreira",
    "parque piauí", "parque piaui",
    "pedra mole", "bairro pedra mole",
    "mafrense", "bairro mafrense",
    "santa maria da codipi", "codipi",
    "bairro fátima teresina", "bairro fatima teresina",
    "bairro jóquei", "bairro joquei",
    "satélite", "bairro satélite",
    "lourival parente",
    "ininga", "bairro ininga",
    "vale quem tem", "bairro vale quem tem",
    "cidade operária", "cidade operaria",
    "porenquanto",
    "redenção teresina",
    "campestre teresina",
    # Lugares públicos e regiões icônicas
    "potycabana", "parque potycabana",
    "parque da cidade teresina",
    "arena dirceu",
    "centro de teresina",
    "centro teresina",
    "av. frei serafim", "avenida frei serafim",
    "av. nossa senhora de fátima", "avenida nossa senhora de fatima",
    "rio poty", "rio parnaíba teresina",
    "ponte estaiada teresina",
    "mercado do peixe teresina",
    "shopping rio poty", "shopping riverside",
    "arena potilandia",
]

# Lista unificada usada pelo count_terms (mantém compatibilidade)
TERESINA_TERMS = TERESINA_EXPLICIT + TERESINA_INSTITUTIONS + TERESINA_PLACES


def _teresina_signal_strength(text: str) -> tuple[int, int, int]:
    """
    Retorna (tier1, tier2, tier3) com contagem de sinais por tier.
    Usado para pontuação ponderada no score de Teresina.
    """
    t = text.lower()
    t1 = count_terms(t, TERESINA_EXPLICIT)
    t2 = count_terms(t, TERESINA_INSTITUTIONS)
    t3 = count_terms(t, TERESINA_PLACES)
    return t1, t2, t3

POLITICAL_TERMS = [
    "eleição", "eleicao", "campanha", "partido", "vereador", "deputado", "senador",
    "prefeito", "governador", "ministro", "presidente", "mandato", "base aliada",
    "oposição", "oposicao", "votação", "votacao", "projeto de lei",
]


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.parse(value)
    except Exception:
        try:
            return parsedate_to_datetime(value)
        except Exception:
            return None


def recency_score(published_at: str | None) -> float:
    dt = parse_datetime(published_at)
    if not dt:
        return 3.0
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600)
    if hours <= 2:
        return 15  # breaking
    if hours <= 6:
        return 10
    if hours <= 24:
        return 5
    if hours <= 168:
        return 0
    return -10  # > 7 dias = velha, penaliza


def clamp(value: float, min_value: float = 0, max_value: float = 100) -> float:
    return max(min_value, min(max_value, value))


def automatic_scores(article: dict[str, Any]) -> dict[str, Any]:
    from .classifier import classify_article as _classify_article

    title = article.get("title") or ""
    summary = article.get("summary") or ""
    source_scope = article.get("source_scope") or "piaui"
    trust = float(article.get("source_trust") or 0.5)
    published_at = article.get("published_at")
    text = f"{title}. {summary}"

    # ── Contagens (foco em Piauí; Teresina conta como sinal local específico) ──
    public_count  = count_terms(text, PUBLIC_ORG_TERMS)
    money_count   = count_terms(text, MONEY_PUBLIC_TERMS)
    social_count  = count_terms(text, SOCIAL_IMPACT_TERMS)
    political_count = count_terms(text, POLITICAL_TERMS)
    piaui_count   = count_terms(text, PIAUI_TERMS)
    teresina_count = count_terms(text, TERESINA_TERMS)
    ter_t1, ter_t2, ter_t3 = _teresina_signal_strength(text)
    money_values  = extract_money_values(text)
    novelty       = recency_score(published_at)

    # ── Dimensões do classificador estruturado (substituem risk_count e outros) ──
    cl = _classify_article(article)
    gravidade    = cl["auto_gravidade"]           # 0-10: crime grave, crise, calamidade
    risco_inv    = cl["auto_risco_investigativo"] # 0-10: corrupção, fraude, nepotismo
    urgencia_cl  = cl["auto_urgencia"]            # 0-10: breaking, decisão imediata
    impacto      = cl["auto_impacto_social"]      # 0-10: serviços essenciais afetados
    dinheiro     = cl["auto_dinheiro_publico"]    # 0-10: verbas, contratos, desvio
    politica_cl  = cl["auto_relevancia_politica"] # 0-10: mandatários, eleições

    reasons = []

    # ── Riqueza de conteúdo ───────────────────────────────────────────────────
    summary_len = len(summary)
    if summary_len >= 500:
        base_content = 6
        reasons.append(f"conteúdo rico: {summary_len} chars")
    elif summary_len >= 200:
        base_content = 4
        reasons.append(f"conteúdo médio: {summary_len} chars")
    elif summary_len >= 50:
        base_content = 2
    else:
        base_content = 0
        if summary_len == 0:
            reasons.append("sem resumo")

    # ── Órgãos públicos: mantido pois PUBLIC_ORG_TERMS é altamente específico ─
    base_public = min(public_count * 3, 12)

    # ── Risco: gravidade + risco investigativo, mesmo teto de antes (16) ──────
    # Usar os dois independentemente permite que crime grave E corrupção
    # contribuam sem inflar além do cap original.
    base_risk = min(gravidade * 1.0 + risco_inv * 0.8, 16)

    # ── Dinheiro público: melhor entre contagem de termos e classifier ────────
    base_money = max(min(money_count * 3, 12), min(dinheiro * 1.2, 12))

    # ── Impacto social: melhor entre contagem e classifier ────────────────────
    base_social = max(min(social_count * 2, 8), min(impacto * 0.9, 9))

    # ── Política: melhor entre contagem e classifier ──────────────────────────
    base_political = max(min(political_count * 2, 8), min(politica_cl * 0.8, 8))

    # ── Valor monetário: sinal específico mantido ─────────────────────────────
    base_money_value = 6 if money_values else 0

    # ── Confiança da fonte: inalterado ────────────────────────────────────────
    base_trust = trust * 6

    # ── Urgência: blend de recência + sinal semântico de breaking news ────────
    base_novelty = (novelty + urgencia_cl) / 2

    # ── Reasons ───────────────────────────────────────────────────────────────
    if public_count:
        reasons.append(f"órgãos/vida pública: {public_count}")
    if gravidade >= 3:
        reasons.append(f"gravidade: {gravidade:.0f}/10")
    if risco_inv >= 3:
        reasons.append(f"risco investigativo: {risco_inv:.0f}/10")
    if urgencia_cl >= 3:
        reasons.append(f"urgência: {urgencia_cl:.0f}/10")
    if money_count:
        reasons.append(f"dinheiro público/contratos: {money_count}")
    if impacto >= 3:
        reasons.append(f"impacto social: {impacto:.0f}/10")
    if political_count:
        reasons.append(f"política: {political_count}")
    if money_values:
        reasons.append("valor monetário detectado")
    if piaui_count:
        reasons.append(f"termos Piauí: {piaui_count}")
    if teresina_count:
        reasons.append(f"termos Teresina: {teresina_count}")

    common = (
        base_content
        + base_public
        + base_risk
        + base_money
        + base_social
        + base_political
        + base_money_value
        + base_trust
        + base_novelty
    )

    piaui_bonus = min(piaui_count * 7, 28)

    # Teresina: como capital do PI, conta como sinal local extra ponderado por
    # especificidade. Tier 1 (explícito) vale mais que tier 3 (bairros).
    teresina_bonus = min(ter_t1 * 12 + ter_t2 * 8 + ter_t3 * 5, 40)

    # Fonte local carrega relevância geográfica mesmo sem citar o lugar.
    if source_scope == "piaui":
        piaui_bonus += 10

    # Exclusiva local: só uma fonte cobriu E é fonte do PI → potencial scoop
    coverage = int(article.get("coverage_count") or 1)
    if coverage == 1 and source_scope == "piaui":
        exclusivity_bonus = 5
        reasons.append("exclusiva local")
    else:
        exclusivity_bonus = 0

    score_piaui = clamp(
        common + piaui_bonus + teresina_bonus * 0.5 + exclusivity_bonus
    )

    # Penaliza notícia sem menção local nenhuma.
    if piaui_count == 0 and teresina_count == 0:
        score_piaui *= 0.55

    return {
        "auto_score_piaui": round(score_piaui, 2),
        "final_score_piaui": round(score_piaui, 2),
        "reasons": reasons,
    }


PRIORITY_THRESHOLDS = [
    (80.0, "critica"),
    (60.0, "alta"),
    (40.0, "media"),
    (20.0, "baixa"),
    (0.0, "ruido"),
]


def classify_priority(score: float) -> str:
    for threshold, label in PRIORITY_THRESHOLDS:
        if score >= threshold:
            return label
    return "ruido"


def auto_classify() -> int:
    import psycopg2.extras

    from news_radar.core.db import connect

    with connect() as conn, conn.cursor() as cur:
        # FOR UPDATE SKIP LOCKED: evita dois rankers calculando o mesmo artigo.
        cur.execute("""
                SELECT id, COALESCE(final_score_piaui, 0) AS best_score
                FROM articles
                WHERE priority IS NULL
                FOR UPDATE SKIP LOCKED
            """)
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return 0

    batch = [
        (classify_priority(float(row["best_score"] or 0)), row["id"])
        for row in rows
    ]

    with connect() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            # Double-check priority IS NULL no UPDATE para evitar race condition
            "UPDATE articles SET priority = %s WHERE id = %s AND priority IS NULL",
            batch,
            page_size=200,
        )

    return len(batch)


def rank_all() -> int:
    """Recalcula auto_score_* e final_score_* para todos os artigos no banco.

    Extrai a mesma lógica de cmd_rank() do CLI, tornando-a reutilizável
    pelo scheduler interno e por qualquer outro chamador Python.

    Retorna o número de artigos atualizados.
    """
    import psycopg2.extras

    from news_radar.core.db import connect, init_db, json_dumps

    init_db()

    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, title, summary, source_scope, source_trust,"
            " published_at, coverage_count FROM articles"
        )
        rows = [dict(r) for r in cur.fetchall()]

    batch = []
    for article in rows:
        scores = automatic_scores(article)
        batch.append((
            scores["auto_score_piaui"],
            scores["final_score_piaui"],
            json_dumps(scores.get("reasons", [])),
            article["id"],
        ))

    with connect() as conn, conn.cursor() as cur:
        psycopg2.extras.execute_batch(
            cur,
            """
                UPDATE articles SET
                    auto_score_piaui   = %s,
                    final_score_piaui  = %s,
                    score_reasons_json = %s
                WHERE id = %s
                """,
            batch,
            page_size=100,
        )

    # Classifica artigos sem priority usando scores automáticos
    auto_classify()

    return len(batch)
