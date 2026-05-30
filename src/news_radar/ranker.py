from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from dateutil import parser as date_parser

from .text_utils import count_terms, extract_money_values, normalize_text


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

BRAZIL_TERMS = [
    "brasil", "governo federal", "lula", "congresso", "senado", "câmara dos deputados",
    "camara dos deputados", "stf", "stj", "tcu", "planalto", "ministério", "ministerio",
    "pf", "polícia federal", "receita federal", "banco central",
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
    if hours <= 6:
        return 10
    if hours <= 24:
        return 8
    if hours <= 72:
        return 6
    if hours <= 168:
        return 4
    return 1


def clamp(value: float, min_value: float = 0, max_value: float = 100) -> float:
    return max(min_value, min(max_value, value))


def automatic_scores(article: dict[str, Any]) -> dict[str, Any]:
    title = article.get("title") or ""
    summary = article.get("summary") or ""
    source_scope = article.get("source_scope") or "brasil"
    trust = float(article.get("source_trust") or 0.5)
    published_at = article.get("published_at")
    text = f"{title}. {summary}"

    public_count = count_terms(text, PUBLIC_ORG_TERMS)
    risk_count = count_terms(text, RISK_TERMS)
    money_count = count_terms(text, MONEY_PUBLIC_TERMS)
    social_count = count_terms(text, SOCIAL_IMPACT_TERMS)
    political_count = count_terms(text, POLITICAL_TERMS)
    brazil_count = count_terms(text, BRAZIL_TERMS)
    piaui_count = count_terms(text, PIAUI_TERMS)
    teresina_count = count_terms(text, TERESINA_TERMS)
    ter_t1, ter_t2, ter_t3 = _teresina_signal_strength(text)
    money_values = extract_money_values(text)
    novelty = recency_score(published_at)

    reasons = []

    # Bônus de riqueza de conteúdo — fontes com resumos ricos (G1, Agência Brasil)
    # têm mais sinal para análise e devem ranquear levemente acima de feeds rasos (Google News).
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

    base_public = min(public_count * 3, 12)
    base_risk = min(risk_count * 4, 16)
    base_money = min(money_count * 3, 12)
    base_social = min(social_count * 2, 8)
    base_political = min(political_count * 2, 8)
    base_money_value = 6 if money_values else 0
    base_trust = trust * 6
    base_novelty = novelty

    if public_count:
        reasons.append(f"órgãos/vida pública: {public_count}")
    if risk_count:
        reasons.append(f"risco/investigação: {risk_count}")
    if money_count:
        reasons.append(f"dinheiro público/contratos: {money_count}")
    if social_count:
        reasons.append(f"impacto social: {social_count}")
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

    brasil_bonus = min(brazil_count * 4, 16)
    piaui_bonus = min(piaui_count * 7, 28)

    # Teresina: pontuação ponderada por tier de especificidade
    # Tier 1 (explícito) vale mais; tier 3 (bairros) vale menos
    teresina_bonus = min(ter_t1 * 12 + ter_t2 * 8 + ter_t3 * 5, 40)

    # Fonte local carrega relevância geográfica mesmo sem citar o lugar.
    if source_scope == "piaui":
        piaui_bonus += 10
    if source_scope == "teresina":
        piaui_bonus += 10
        teresina_bonus += 12  # amplifica quando fonte já é de Teresina

    score_brasil = clamp(common + brasil_bonus)
    score_piaui = clamp(common + piaui_bonus)

    # Hard gate: artigo sem sinal de Teresina no texto não entra no ranking de Teresina.
    # Garante que só artigos com menção real (título ou resumo) classificam a cidade.
    if teresina_count == 0:
        score_teresina = 0.0
    else:
        score_teresina = clamp(common + piaui_bonus * 0.45 + teresina_bonus)

    # Penaliza notícia nacional sem menção local no ranking piauiense.
    if piaui_count == 0 and teresina_count == 0 and source_scope == "brasil":
        score_piaui *= 0.55

    return {
        "auto_score_brasil": round(score_brasil, 2),
        "auto_score_piaui": round(score_piaui, 2),
        "auto_score_teresina": round(score_teresina, 2),
        "final_score_brasil": round(score_brasil, 2),
        "final_score_piaui": round(score_piaui, 2),
        "final_score_teresina": round(score_teresina, 2),
        "reasons": reasons,
    }


def ai_score_from_payload(payload: dict[str, Any]) -> float:
    modern_fields = [
        "interesse_publico",
        "impacto_social",
        "urgencia",
        "relevancia_local",
        "dinheiro_publico",
    ]
    legacy_fields = [
        "impacto_publico",
        "gravidade",
        "relevancia_politica",
        "risco_investigativo",
        "dinheiro_publico",
    ]
    fields = modern_fields if any(field in payload for field in modern_fields) else legacy_fields
    values = []
    for field in fields:
        try:
            values.append(float(payload.get(field, 0)))
        except Exception:
            values.append(0)
    if not values:
        return 0
    return clamp((sum(values) / len(values)) * 10)


def combine_with_ai(auto_score: float, ai_score: float | None) -> float:
    if ai_score is None:
        return round(float(auto_score), 2)
    return round(clamp(float(auto_score) * 0.58 + float(ai_score) * 0.42), 2)


# Thresholds para classificação automática (sem IA)
# Usa o maior score entre os 3 escopos — artigo relevante em qualquer escopo conta
AUTO_PRIORITY_THRESHOLDS = [
    (80, "critica"),
    (60, "alta"),
    (40, "media"),
    (20, "baixa"),
    (0,  "ruido"),
]


def auto_classify() -> int:
    """Classifica priority com base no score automático, sem chamar IA.

    Aplica apenas em artigos com priority IS NULL — nunca sobrescreve
    classificação feita pela IA. Usa GREATEST dos 3 final_scores para
    que artigos relevantes em qualquer escopo sejam bem classificados.

    Retorna o número de artigos classificados.
    """
    import psycopg2.extras

    from .db import connect

    with connect() as conn:
        with conn.cursor() as cur:
            # FOR UPDATE SKIP LOCKED: se outro processo já estiver classificando
            # os mesmos artigos, pula — evita dois rankers calculando o mesmo artigo.
            cur.execute("""
                SELECT id,
                    GREATEST(
                        COALESCE(final_score_brasil,   0),
                        COALESCE(final_score_piaui,    0),
                        COALESCE(final_score_teresina, 0)
                    ) AS best_score
                FROM articles
                WHERE priority IS NULL
                FOR UPDATE SKIP LOCKED
            """)
            rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return 0

    batch = []
    for row in rows:
        score = float(row["best_score"] or 0)
        priority = "ruido"
        for threshold, label in AUTO_PRIORITY_THRESHOLDS:
            if score >= threshold:
                priority = label
                break
        batch.append((priority, row["id"]))

    with connect() as conn:
        with conn.cursor() as cur:
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

    from .db import connect, init_db, json_dumps

    init_db()

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, summary, source_scope, source_trust,"
                " published_at, ai_score FROM articles"
            )
            rows = [dict(r) for r in cur.fetchall()]

    batch = []
    for article in rows:
        scores = automatic_scores(article)
        ai = float(article["ai_score"]) if article["ai_score"] is not None else None
        batch.append((
            scores["auto_score_brasil"],
            scores["auto_score_piaui"],
            scores["auto_score_teresina"],
            combine_with_ai(scores["auto_score_brasil"], ai),
            combine_with_ai(scores["auto_score_piaui"], ai),
            combine_with_ai(scores["auto_score_teresina"], ai),
            json_dumps(scores.get("reasons", [])),
            article["id"],
        ))

    with connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE articles SET
                    auto_score_brasil   = %s,
                    auto_score_piaui    = %s,
                    auto_score_teresina = %s,
                    final_score_brasil  = %s,
                    final_score_piaui   = %s,
                    final_score_teresina= %s,
                    score_reasons_json  = %s
                WHERE id = %s
                """,
                batch,
                page_size=100,
            )

    # Classifica artigos sem priority usando scores automáticos
    auto_classify()

    return len(batch)
