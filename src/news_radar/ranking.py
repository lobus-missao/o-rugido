"""
Ranking explicável — Fase 6.

Funções para ranking e explicação de scores de artigos e clusters.
Complementa score_explainer.py (scores automáticos de artigos) com:
  - explain_cluster_score() — explica o score de um cluster
  - rank_clusters_by_dimension() — reordena clusters por dimensão
  - score_summary() — resumo compacto do score de um artigo

Pesos configuráveis via DEFAULT_WEIGHTS (tabela score_weights reservada para Fase 7).
"""
from __future__ import annotations

import json
import math
from typing import Any


# ── Dimensões disponíveis ─────────────────────────────────────────────────────

RANKING_DIMENSIONS: dict[str, str] = {
    "cluster_score":      "Score do cluster",
    "source_count":       "Quantidade de fontes",
    "article_count":      "Quantidade de artigos",
    "final_score":        "Score final médio",
    "interesse_publico":  "Interesse público (IA)",
    "impacto_social":     "Impacto social (IA)",
    "gravidade":          "Gravidade (IA)",
    "risco_investigativo": "Risco investigativo (IA)",
    "dinheiro_publico":   "Dinheiro público (IA)",
    "urgencia":           "Urgência (IA)",
    "relevancia_local":   "Relevância local (IA)",
    "relevancia_politica": "Relevância política (IA)",
}

# Dimensões numéricas do ai_json
AI_NUMERIC_DIMENSIONS = [
    "interesse_publico",
    "impacto_social",
    "gravidade",
    "risco_investigativo",
    "dinheiro_publico",
    "relevancia_politica",
    "polemica",
    "urgencia",
    "relevancia_local",
    "confiabilidade",
]

# Pesos padrão por dimensão (substituível por tabela score_weights na Fase 7)
DEFAULT_WEIGHTS: dict[str, float] = {
    "dinheiro_publico":    1.3,
    "risco_investigativo": 1.3,
    "gravidade":           1.1,
    "urgencia":            1.1,
    "interesse_publico":   1.0,
    "impacto_social":      1.0,
    "relevancia_local":    1.0,
    "relevancia_politica": 0.9,
    "polemica":            0.8,
    "confiabilidade":      0.7,
}

# Ícones por dimensão
DIMENSION_ICONS: dict[str, str] = {
    "interesse_publico":   "🏛️",
    "impacto_social":      "👥",
    "gravidade":           "⚠️",
    "risco_investigativo": "🔍",
    "dinheiro_publico":    "💰",
    "relevancia_politica": "🗳️",
    "polemica":            "📢",
    "urgencia":            "⏰",
    "relevancia_local":    "📍",
    "confiabilidade":      "📰",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_ai_json(article: dict) -> dict:
    """Retorna ai_json do artigo como dict (normaliza string→dict)."""
    ai = article.get("ai_json") or {}
    if isinstance(ai, str):
        try:
            ai = json.loads(ai)
        except Exception:
            ai = {}
    return ai if isinstance(ai, dict) else {}


def _extract_ai_dimension(article: dict, dimension: str) -> float:
    """Extrai valor numérico de uma dimensão do ai_json. Retorna 0 se ausente."""
    ai = _parse_ai_json(article)
    val = ai.get(dimension, 0)
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _avg_ai_dimensions(articles: list[dict]) -> dict[str, float]:
    """Calcula médias das dimensões IA para lista de artigos com IA."""
    ai_arts = [a for a in articles if a.get("ai_score") is not None]
    if not ai_arts:
        return {}
    result = {}
    for dim in AI_NUMERIC_DIMENSIONS:
        vals = [_extract_ai_dimension(a, dim) for a in ai_arts]
        result[dim] = round(sum(vals) / len(vals), 1)
    return result


# ── explain_cluster_score ─────────────────────────────────────────────────────

def explain_cluster_score(cluster: dict, articles: list[dict]) -> dict:
    """Retorna explicação estruturada do score de um cluster.

    cluster: dict de story_clusters (campos: id, title, cluster_score, source_count, article_count).
    articles: lista de artigos do cluster (de get_db_cluster_articles()).
    """
    cluster_score = float(cluster.get("cluster_score") or 0)
    source_count = int(cluster.get("source_count") or 0)
    article_count = int(cluster.get("article_count") or 0)

    if not articles:
        return {
            "total": cluster_score,
            "avg_score": 0.0,
            "source_count": source_count,
            "article_count": article_count,
            "ai_dimensions": {},
            "top_dimension": None,
            "explanation": f"Cluster com {article_count} artigo(s) de {source_count} fonte(s).",
            "signals": [],
            "has_ai": False,
            "ai_article_count": 0,
        }

    scores = [float(a.get("final_score_brasil") or 0) for a in articles]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    ai_arts = [a for a in articles if a.get("ai_score") is not None]
    ai_dims = _avg_ai_dimensions(articles)

    # Score ponderado das dimensões IA
    weighted_dims: list[tuple[str, float, float]] = []
    for dim, avg in ai_dims.items():
        weight = DEFAULT_WEIGHTS.get(dim, 1.0)
        weighted_dims.append((dim, avg, avg * weight))
    weighted_dims.sort(key=lambda x: -x[2])
    top_dimension = weighted_dims[0][0] if weighted_dims else None

    # Sinais de explicação
    signals: list[str] = []
    if source_count >= 4:
        signals.append(f"{source_count} fontes diferentes cobriram")
    elif source_count >= 2:
        signals.append(f"{source_count} fontes cobrindo")
    if article_count >= 5:
        signals.append(f"{article_count} artigos no cluster")
    if ai_dims.get("risco_investigativo", 0) >= 7:
        signals.append("alto risco investigativo")
    if ai_dims.get("dinheiro_publico", 0) >= 7:
        signals.append("alto envolvimento de dinheiro público")
    if ai_dims.get("gravidade", 0) >= 7:
        signals.append("fato grave")
    if ai_dims.get("urgencia", 0) >= 7:
        signals.append("urgência alta")
    if avg_score >= 70:
        signals.append("artigos com score alto")

    if signals:
        explanation = "Cluster relevante: " + ", ".join(signals[:4]) + "."
    elif ai_dims:
        explanation = f"Cluster com IA disponível para {len(ai_arts)} artigo(s). "
        if top_dimension:
            explanation += f"Dimensão mais relevante: {DIMENSION_ICONS.get(top_dimension,'')} {RANKING_DIMENSIONS.get(top_dimension, top_dimension)}."
    else:
        explanation = (
            f"Score calculado de {article_count} artigo(s) de {source_count} fonte(s). "
            "Sem análise de IA disponível."
        )

    return {
        "total": cluster_score,
        "avg_score": avg_score,
        "source_count": source_count,
        "article_count": article_count,
        "ai_dimensions": ai_dims,
        "top_dimension": top_dimension,
        "explanation": explanation,
        "signals": signals,
        "has_ai": len(ai_arts) > 0,
        "ai_article_count": len(ai_arts),
    }


# ── rank_clusters_by_dimension ────────────────────────────────────────────────

def rank_clusters_by_dimension(
    clusters: list[dict],
    articles_by_cluster: dict[str, list[dict]],
    dimension: str = "cluster_score",
) -> list[dict]:
    """Reordena clusters por dimensão, adicionando rank_value e rank_dimension.

    articles_by_cluster: {cluster_id: [artigo, ...]} pré-carregado.
    dimension: chave de RANKING_DIMENSIONS.
    """
    result: list[dict] = []
    for cluster in clusters:
        cid = cluster["id"]
        arts = articles_by_cluster.get(cid, [])

        if dimension == "cluster_score":
            rank_val = float(cluster.get("cluster_score") or 0)
        elif dimension == "source_count":
            rank_val = float(cluster.get("source_count") or 0)
        elif dimension == "article_count":
            rank_val = float(cluster.get("article_count") or 0)
        elif dimension == "final_score":
            sc = [float(a.get("final_score_brasil") or 0) for a in arts]
            rank_val = round(sum(sc) / len(sc), 2) if sc else 0.0
        else:
            # Dimensão do ai_json: média dos artigos com IA
            ai_arts = [a for a in arts if a.get("ai_score") is not None]
            vals = [_extract_ai_dimension(a, dimension) for a in ai_arts]
            rank_val = round(sum(vals) / len(vals), 2) if vals else 0.0

        c = dict(cluster)
        c["rank_value"] = rank_val
        c["rank_dimension"] = dimension
        result.append(c)

    return sorted(result, key=lambda x: -x["rank_value"])


# ── score_summary ─────────────────────────────────────────────────────────────

def score_summary(article: dict, scope: str = "brasil") -> dict:
    """Resumo compacto do score de um artigo: score auto, IA, final e top sinais.

    Complementa explain_score() (decomposto) com visão rápida para listas.
    """
    score_col = f"final_score_{scope}"
    auto_col = f"auto_score_{scope}"
    final = float(article.get(score_col) or 0)
    auto = float(article.get(auto_col) or 0)
    ai = float(article.get("ai_score") or 0) if article.get("ai_score") is not None else None

    ai_json = _parse_ai_json(article)

    top_dims: list[tuple[str, float]] = []
    for dim in ["risco_investigativo", "dinheiro_publico", "gravidade", "urgencia", "relevancia_local"]:
        val = ai_json.get(dim)
        if val is not None:
            try:
                top_dims.append((dim, float(val)))
            except (TypeError, ValueError):
                pass
    top_dims.sort(key=lambda x: -x[1])

    priority = article.get("priority") or ""
    resumo = ai_json.get("resumo_curto") or (article.get("summary") or "")[:120]
    justificativa = ai_json.get("justificativa_score") or ""

    return {
        "final": round(final, 1),
        "auto": round(auto, 1),
        "ai": round(ai, 1) if ai is not None else None,
        "has_ai": ai is not None,
        "priority": priority,
        "top_dimensions": top_dims[:3],
        "resumo": resumo,
        "justificativa": justificativa,
    }
