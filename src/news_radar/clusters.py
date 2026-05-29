"""
Clustering de artigos similares — Fase 5.

Algoritmo incremental e conservador:
  1. Agrupa por title_signature exato (maior confiança).
  2. Agrupa por entidades comuns significativas (confiança média).
  3. Agrupa por keywords do título (menor confiança).

Princípio: melhor não agrupar do que agrupar errado.
Cada cluster persiste em story_clusters + cluster_articles.
Clustering é idempotente: re-rodar não duplica clusters.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import connect, utc_now
from .text_utils import normalize_text

_logger = logging.getLogger(__name__)

# Tamanho mínimo de entidade para evitar falso positivo (siglas curtas)
_MIN_ENTITY_LEN = 5
# Tamanho mínimo de keyword do título
_MIN_KEYWORD_LEN = 6


# ── Helpers internos ──────────────────────────────────────────────────────────

def _cluster_id(label: str, scope: str, cluster_type: str) -> str:
    """ID determinístico: mesmos parâmetros → mesmo ID. Permite idempotência."""
    key = f"{cluster_type}:{scope}:{label.lower().strip()}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:24]


def _compute_cluster_score(articles: list[dict]) -> float:
    """cluster_score = avg(final_score_brasil) × log2(source_count + 1)."""
    scores = [float(a.get("final_score_brasil") or 0) for a in articles]
    sources = len({a.get("source") for a in articles if a.get("source")})
    if not scores:
        return 0.0
    avg = sum(scores) / len(scores)
    return round(avg * math.log2(sources + 1), 2)


def _extract_entities(article: dict) -> list[str]:
    """Extrai entidades do ai_json. Retorna lista em lowercase."""
    ai = article.get("ai_json") or {}
    if isinstance(ai, str):
        try:
            ai = json.loads(ai)
        except Exception:
            ai = {}
    ents = ai.get("entidades") or ai.get("entities") or []
    if isinstance(ents, str):
        try:
            ents = json.loads(ents)
        except Exception:
            ents = [ents]
    return [str(e).lower().strip() for e in ents if e and len(str(e)) >= _MIN_ENTITY_LEN]


def _extract_tags(article: dict) -> list[str]:
    """Extrai tags do ai_json."""
    ai = article.get("ai_json") or {}
    if isinstance(ai, str):
        try:
            ai = json.loads(ai)
        except Exception:
            ai = {}
    tags = ai.get("tags") or []
    return [str(t).lower().strip() for t in tags if t]


def _extract_title_keywords(article: dict) -> set[str]:
    """Palavras significativas do título (sem stopwords)."""
    _STOPWORDS = {
        "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
        "com", "por", "para", "que", "se", "ao", "aos", "à", "às",
        "um", "uma", "uns", "umas", "e", "é", "ou", "mas", "foi", "são",
        "ser", "ter", "mais", "após", "sobre", "até", "pela", "pelo",
    }
    text = normalize_text(article.get("title") or "")
    return {
        w for w in text.split()
        if len(w) >= _MIN_KEYWORD_LEN and w not in _STOPWORDS
    }


def _select_primary(articles: list[dict]) -> str:
    """Retorna o article_id do artigo mais relevante (maior final_score_brasil)."""
    best = max(articles, key=lambda a: float(a.get("final_score_brasil") or 0))
    return best["id"]


# ── Agrupamento em memória ─────────────────────────────────────────────────────

def _group_by_title_signature(articles: list[dict]) -> list[dict]:
    """Grupos por title_signature exato. Mais confiável."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        sig = a.get("title_signature") or ""
        if sig:
            groups[sig].append(a)
    return [
        {"type": "titulo_similar", "label": arts[0].get("title", "")[:80], "articles": arts}
        for sig, arts in groups.items()
        if len(arts) >= 2
    ]


def _group_by_entities(
    articles: list[dict],
    already_clustered: set[str],
    min_shared: int = 2,
) -> list[dict]:
    """Grupos por entidades compartilhadas. Confiança média."""
    remaining = [a for a in articles if a["id"] not in already_clustered]
    entity_map: dict[str, list[dict]] = defaultdict(list)
    for a in remaining:
        for ent in _extract_entities(a):
            entity_map[ent].append(a)

    groups = []
    used: set[str] = set()
    for ent, arts in sorted(entity_map.items(), key=lambda x: -len(x[1])):
        arts = [a for a in arts if a["id"] not in used]
        if len(arts) >= min_shared:
            for a in arts:
                used.add(a["id"])
            groups.append({"type": "entidade_comum", "label": ent, "articles": arts})
    return groups


def _group_by_keywords(
    articles: list[dict],
    already_clustered: set[str],
    min_shared: int = 2,
) -> list[dict]:
    """Grupos por keywords do título. Menor confiança."""
    remaining = [a for a in articles if a["id"] not in already_clustered]
    kw_map: dict[str, list[dict]] = defaultdict(list)
    for a in remaining:
        for kw in _extract_title_keywords(a):
            kw_map[kw].append(a)

    groups = []
    used: set[str] = set()
    for kw, arts in sorted(kw_map.items(), key=lambda x: -len(x[1])):
        arts = [a for a in arts if a["id"] not in used]
        if len(arts) >= min_shared:
            for a in arts:
                used.add(a["id"])
            groups.append({"type": "keyword_comum", "label": kw, "articles": arts})
    return groups


# ── Persistência ──────────────────────────────────────────────────────────────

def _upsert_cluster(
    cluster_id: str,
    title: str,
    scope: str,
    cluster_type: str,
    label: str,
    articles: list[dict],
) -> None:
    """Cria ou atualiza um cluster no banco. Idempotente por cluster_id."""
    now = utc_now()
    article_count = len(articles)
    source_count = len({a.get("source") for a in articles if a.get("source")})
    score = _compute_cluster_score(articles)
    primary_id = _select_primary(articles)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO story_clusters
                    (id, title, scope, cluster_type, label, article_count,
                     source_count, cluster_score, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title        = EXCLUDED.title,
                    article_count = EXCLUDED.article_count,
                    source_count = EXCLUDED.source_count,
                    cluster_score = EXCLUDED.cluster_score,
                    updated_at   = EXCLUDED.updated_at
                """,
                (cluster_id, title, scope, cluster_type, label,
                 article_count, source_count, score, now, now),
            )

            for article in articles:
                is_primary = article["id"] == primary_id
                cur.execute(
                    """
                    INSERT INTO cluster_articles (cluster_id, article_id, is_primary, created_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (cluster_id, article_id) DO UPDATE SET
                        is_primary = EXCLUDED.is_primary
                    """,
                    (cluster_id, article["id"], is_primary, now),
                )


# ── API pública ───────────────────────────────────────────────────────────────

def cluster_articles_to_db(
    hours: int = 72,
    min_size: int = 2,
    scope: str | None = None,
) -> dict[str, Any]:
    """Calcula clusters e persiste em story_clusters + cluster_articles.

    Idempotente: executar múltiplas vezes não duplica clusters (IDs determinísticos).
    Retorna contagens para relatório.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    conditions = [
        "(published_at >= %s OR published_at IS NULL)",
        "editorial_status NOT IN ('rejected', 'archived')",
        "title_signature IS NOT NULL",
    ]
    params: list[Any] = [cutoff]

    if scope:
        conditions.append("source_scope = %s")
        params.append(scope)

    where = "WHERE " + " AND ".join(conditions)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, title, source, published_at,
                       final_score_brasil, final_score_piaui, final_score_teresina,
                       priority, source_scope, ai_json, title_signature, locality,
                       editorial_status
                FROM articles {where}
                ORDER BY final_score_brasil DESC
                LIMIT 2000
                """,
                params,
            )
            articles = [dict(r) for r in cur.fetchall()]

    if not articles:
        return {"clusters_created": 0, "clusters_updated": 0, "articles_clustered": 0, "hours": hours}

    effective_scope = scope or "brasil"
    clusters_saved = 0
    articles_clustered: set[str] = set()

    # Fase 1: agrupamento por title_signature (maior confiança)
    for group in _group_by_title_signature(articles):
        if len(group["articles"]) < min_size:
            continue
        cid = _cluster_id(group["label"], effective_scope, group["type"])
        _upsert_cluster(
            cluster_id=cid,
            title=group["label"],
            scope=effective_scope,
            cluster_type=group["type"],
            label=group["label"],
            articles=group["articles"],
        )
        clusters_saved += 1
        for a in group["articles"]:
            articles_clustered.add(a["id"])

    # Fase 2: agrupamento por entidades comuns
    for group in _group_by_entities(articles, articles_clustered):
        if len(group["articles"]) < min_size:
            continue
        cid = _cluster_id(group["label"], effective_scope, group["type"])
        _upsert_cluster(
            cluster_id=cid,
            title=group["label"].capitalize(),
            scope=effective_scope,
            cluster_type=group["type"],
            label=group["label"],
            articles=group["articles"],
        )
        clusters_saved += 1
        for a in group["articles"]:
            articles_clustered.add(a["id"])

    # Fase 3: agrupamento por keywords do título (menor confiança)
    for group in _group_by_keywords(articles, articles_clustered):
        if len(group["articles"]) < min_size:
            continue
        cid = _cluster_id(group["label"], effective_scope, group["type"])
        _upsert_cluster(
            cluster_id=cid,
            title=group["label"].capitalize(),
            scope=effective_scope,
            cluster_type=group["type"],
            label=group["label"],
            articles=group["articles"],
        )
        clusters_saved += 1
        for a in group["articles"]:
            articles_clustered.add(a["id"])

    _logger.info(
        "Clustering concluído: %d clusters, %d artigos agrupados (janela=%dh, scope=%s)",
        clusters_saved, len(articles_clustered), hours, scope or "todos",
    )
    return {
        "clusters_created": clusters_saved,
        "articles_clustered": len(articles_clustered),
        "total_articles_analyzed": len(articles),
        "hours": hours,
        "scope": scope,
    }


def list_db_clusters(
    scope: str | None = None,
    status: str = "active",
    cluster_type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Lista clusters persistidos no banco, ordenados por score."""
    conditions = ["sc.status = %s"]
    params: list[Any] = [status]

    if scope:
        conditions.append("sc.scope = %s")
        params.append(scope)

    if cluster_type:
        conditions.append("sc.cluster_type = %s")
        params.append(cluster_type)

    where = "WHERE " + " AND ".join(conditions)
    params.append(limit)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT sc.*
                FROM story_clusters sc
                {where}
                ORDER BY sc.cluster_score DESC, sc.article_count DESC
                LIMIT %s
                """,
                params,
            )
            return [dict(r) for r in cur.fetchall()]


def get_db_cluster_articles(cluster_id: str) -> list[dict]:
    """Artigos de um cluster específico, do mais relevante ao menos."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.title, a.source, a.published_at, a.canonical_url,
                       a.final_score_brasil, a.priority, a.ai_score, a.source_scope,
                       a.editorial_status, a.ai_json,
                       ca.is_primary, ca.similarity_score
                FROM cluster_articles ca
                JOIN articles a ON ca.article_id = a.id
                WHERE ca.cluster_id = %s
                ORDER BY ca.is_primary DESC, a.final_score_brasil DESC
                """,
                (cluster_id,),
            )
            return [dict(r) for r in cur.fetchall()]


def set_primary_article(cluster_id: str, article_id: str) -> None:
    """Define o artigo primário do cluster. Desmarca todos os outros."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cluster_articles SET is_primary = FALSE WHERE cluster_id = %s",
                (cluster_id,),
            )
            cur.execute(
                "UPDATE cluster_articles SET is_primary = TRUE WHERE cluster_id = %s AND article_id = %s",
                (cluster_id, article_id),
            )


def archive_cluster(cluster_id: str) -> None:
    """Arquiva um cluster (não apaga artigos)."""
    now = utc_now()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE story_clusters SET status = 'archived', updated_at = %s WHERE id = %s",
                (now, cluster_id),
            )


def cluster_stats() -> dict:
    """Contagens resumidas para métricas da dashboard."""
    _empty = {"total": 0, "active": 0, "articles_clustered": 0, "by_type": {}}
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, COUNT(*) n, SUM(article_count) arts
                    FROM story_clusters GROUP BY status
                    """
                )
                rows = cur.fetchall()
                total = sum(r["n"] for r in rows)
                active = next((r["n"] for r in rows if r["status"] == "active"), 0)
                arts = sum(int(r["arts"] or 0) for r in rows if r["status"] == "active")

                cur.execute(
                    "SELECT cluster_type, COUNT(*) n FROM story_clusters WHERE status='active' GROUP BY cluster_type"
                )
                by_type = {r["cluster_type"]: r["n"] for r in cur.fetchall()}
        return {"total": total, "active": active, "articles_clustered": arts, "by_type": by_type}
    except Exception:
        return _empty
