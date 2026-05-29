"""
Queries centralizadas para o dashboard Streamlit.
Todas retornam listas de dicts ou dicts simples — sem dependência de Streamlit.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import connect
from .text_utils import normalize_text, count_terms
from .ranker import (
    PUBLIC_ORG_TERMS, RISK_TERMS, MONEY_PUBLIC_TERMS,
    SOCIAL_IMPACT_TERMS, POLITICAL_TERMS, BRAZIL_TERMS,
    PIAUI_TERMS, TERESINA_TERMS, recency_score, extract_money_values,
)

SCORE_COLUMN = {
    "brasil": "final_score_brasil",
    "piaui": "final_score_piaui",
    "teresina": "final_score_teresina",
}

PRIORITY_ORDER = {"critica": 0, "alta": 1, "media": 2, "baixa": 3, "ruido": 4, None: 5, "": 5}


def _as_utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── Radar ─────────────────────────────────────────────────────────────────────

def radar_articles(
    hours: int = 24,
    scope: str = "brasil",
    limit: int = 50,
    priority: list[str] | None = None,
    with_ai: bool | None = None,
    source: str | None = None,
    search: str | None = None,
    entity: str | None = None,
) -> list[dict]:
    col = SCORE_COLUMN.get(scope, "final_score_brasil")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    conditions = ["(published_at >= %s OR published_at IS NULL)", f"{col} > 0"]
    params: list[Any] = [cutoff]

    if priority:
        ph = ",".join(["%s"] * len(priority))
        # Inclui artigos sem priority (não processados por IA) junto com os filtrados
        conditions.append(f"(priority IN ({ph}) OR priority IS NULL)")
        params.extend(priority)

    if with_ai is True:
        conditions.append("ai_score IS NOT NULL")
    elif with_ai is False:
        conditions.append("ai_score IS NULL")

    if source:
        conditions.append("source = %s")
        params.append(source)

    if search:
        conditions.append("(title ILIKE %s OR summary ILIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])

    if entity:
        conditions.append("(ai_json::text ILIKE %s OR title ILIKE %s OR summary ILIKE %s)")
        params.extend([f"%{entity}%", f"%{entity}%", f"%{entity}%"])

    where = "WHERE " + " AND ".join(conditions)
    params.append(limit)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM articles {where} ORDER BY {col} DESC, published_at DESC NULLS LAST LIMIT %s",
                params,
            )
            return [dict(r) for r in cur.fetchall()]


def update_editorial_status(article_id: str, status: str) -> None:
    from .db import utc_now
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE articles SET editorial_status=%s, updated_at=%s WHERE id=%s",
                (status, utc_now(), article_id),
            )


# ── Clusters ──────────────────────────────────────────────────────────────────

def _ai_entities(article: dict) -> list[str]:
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
    return [str(e).lower() for e in ents if e]


def compute_clusters(hours: int = 24, min_size: int = 2) -> list[dict]:
    """Agrupa artigos por: title_signature, entidades em comum, ou palavras-chave."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, source, published_at, summary,
                       final_score_brasil, final_score_piaui, final_score_teresina,
                       priority, source_scope, ai_json, title_signature, locality
                FROM articles
                WHERE published_at >= %s OR published_at IS NULL
                ORDER BY final_score_brasil DESC
                LIMIT 500
                """,
                (cutoff,),
            )
            articles = [dict(r) for r in cur.fetchall()]

    if not articles:
        return []

    # Agrupa por title_signature primeiro
    by_sig: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        sig = a.get("title_signature") or ""
        if sig:
            by_sig[sig].append(a)

    clusters = []
    used_ids: set[str] = set()

    # Clusters por assinatura de título
    for sig, arts in by_sig.items():
        if len(arts) >= min_size:
            ids = [a["id"] for a in arts]
            used_ids.update(ids)
            scores = [float(a.get("final_score_brasil") or 0) for a in arts]
            clusters.append(_build_cluster(arts, "titulo_similar"))

    # Clusters por entidades em comum
    remaining = [a for a in articles if a["id"] not in used_ids]
    entity_map: dict[str, list[dict]] = defaultdict(list)
    for a in remaining:
        for ent in _ai_entities(a):
            if len(ent) > 4:
                entity_map[ent].append(a)

    entity_used: set[str] = set()
    for ent, arts in sorted(entity_map.items(), key=lambda x: -len(x[1])):
        arts = [a for a in arts if a["id"] not in entity_used]
        if len(arts) >= min_size:
            ids = [a["id"] for a in arts]
            entity_used.update(ids)
            used_ids.update(ids)
            c = _build_cluster(arts, "entidade_comum")
            c["label"] = ent
            clusters.append(c)

    # Clusters por keywords do título
    remaining = [a for a in articles if a["id"] not in used_ids]
    kw_map: dict[str, list[dict]] = defaultdict(list)
    for a in remaining:
        text = normalize_text(a.get("title") or "")
        words = [w for w in text.split() if len(w) > 5]
        for w in words[:5]:
            kw_map[w].append(a)

    kw_used: set[str] = set()
    for kw, arts in sorted(kw_map.items(), key=lambda x: -len(x[1])):
        arts = [a for a in arts if a["id"] not in kw_used]
        if len(arts) >= min_size:
            kw_used.update(a["id"] for a in arts)
            used_ids.update(a["id"] for a in arts)
            c = _build_cluster(arts, "keyword_comum")
            c["label"] = kw
            clusters.append(c)

    return sorted(clusters, key=lambda c: -c["max_score"])


def _build_cluster(arts: list[dict], cluster_type: str) -> dict:
    scores = [float(a.get("final_score_brasil") or 0) for a in arts]
    priorities = [a.get("priority") or "" for a in arts]
    sources = list({a.get("source") for a in arts if a.get("source")})
    dates = [a.get("published_at") for a in arts if a.get("published_at")]
    entities: list[str] = []
    for a in arts:
        entities.extend(_ai_entities(a))
    top_ents = sorted(set(entities), key=lambda e: -entities.count(e))[:5]
    top_priority = min(priorities, key=lambda p: PRIORITY_ORDER.get(p, 5))
    return {
        "type": cluster_type,
        "label": arts[0].get("title", "")[:60],
        "size": len(arts),
        "articles": arts,
        "sources": sources,
        "max_score": max(scores, default=0),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "top_priority": top_priority,
        "entities": top_ents,
        "locality": arts[0].get("locality") or "",
        "first_pub": min(dates, default=None),
        "last_pub": max(dates, default=None),
        "has_ai": any(a.get("ai_score") for a in arts),
    }


# ── Entidades ─────────────────────────────────────────────────────────────────

def top_entities(hours: int = 24, limit: int = 30) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, source, published_at, priority,
                       final_score_brasil, ai_json, ai_score
                FROM articles
                WHERE (published_at >= %s OR published_at IS NULL)
                  AND ai_json IS NOT NULL
                ORDER BY final_score_brasil DESC
                LIMIT 500
                """,
                (cutoff,),
            )
            articles = [dict(r) for r in cur.fetchall()]

    entity_data: dict[str, dict] = {}
    for a in articles:
        ents = _ai_entities(a)
        score = float(a.get("final_score_brasil") or 0)
        for ent in ents:
            if len(ent) < 3:
                continue
            if ent not in entity_data:
                entity_data[ent] = {
                    "name": ent,
                    "count": 0,
                    "scores": [],
                    "priorities": [],
                    "sources": set(),
                    "articles": [],
                }
            d = entity_data[ent]
            d["count"] += 1
            d["scores"].append(score)
            d["priorities"].append(a.get("priority") or "")
            d["sources"].add(a.get("source") or "")
            if len(d["articles"]) < 5:
                d["articles"].append({"id": a["id"], "title": a.get("title", ""), "score": score})

    result = []
    for name, d in entity_data.items():
        result.append({
            "name": name,
            "count": d["count"],
            "avg_score": round(sum(d["scores"]) / len(d["scores"]), 1) if d["scores"] else 0,
            "max_score": round(max(d["scores"]), 1) if d["scores"] else 0,
            "top_priority": min(d["priorities"], key=lambda p: PRIORITY_ORDER.get(p, 5)),
            "sources": sorted(d["sources"]),
            "articles": d["articles"],
        })

    return sorted(result, key=lambda e: -e["count"])[:limit]


# ── Alertas ───────────────────────────────────────────────────────────────────

def compute_alerts() -> list[dict]:
    alerts = []
    now = datetime.now(timezone.utc)

    with connect() as conn:
        with conn.cursor() as cur:
            # Artigos de alto score sem IA
            cur.execute("""
                SELECT id, title, final_score_brasil, priority, source, published_at
                FROM articles
                WHERE final_score_brasil >= 80 AND ai_score IS NULL
                  AND (published_at >= %s OR published_at IS NULL)
                ORDER BY final_score_brasil DESC LIMIT 5
            """, (now - timedelta(hours=24),))
            for r in cur.fetchall():
                r = dict(r)
                alerts.append({
                    "type": "high_score_no_ai",
                    "severity": "alta",
                    "title": f"Score alto sem IA: {r['title'][:60]}",
                    "detail": f"Score {r['final_score_brasil']:.0f} — sem análise de IA",
                    "article_id": r["id"],
                    "article_title": r["title"],
                    "action": "Gerar lote de IA",
                    "time": r["published_at"],
                })

            # Artigos críticos sem card
            cur.execute("""
                SELECT id, title, final_score_brasil, source
                FROM articles
                WHERE priority = 'critica' AND card_status = 'none'
                  AND (published_at >= %s OR published_at IS NULL)
                ORDER BY final_score_brasil DESC LIMIT 5
            """, (now - timedelta(hours=24),))
            for r in cur.fetchall():
                r = dict(r)
                alerts.append({
                    "type": "critica_no_card",
                    "severity": "critica",
                    "title": f"Notícia CRÍTICA sem card: {r['title'][:55]}",
                    "detail": "Prioridade crítica mas ainda sem card gerado",
                    "article_id": r["id"],
                    "article_title": r["title"],
                    "action": "Gerar card",
                    "time": now,
                })

            # Lotes pendentes antigos
            cur.execute("""
                SELECT batch_id, scope, article_count, created_at
                FROM ai_batches
                WHERE status = 'pending'
                ORDER BY created_at ASC LIMIT 10
            """)
            for r in cur.fetchall():
                r = dict(r)
                created_at = _as_utc_datetime(r.get("created_at"))
                age_h = ((now - created_at).total_seconds() / 3600) if created_at else 0
                if age_h > 2:
                    alerts.append({
                        "type": "pending_batch",
                        "severity": "media" if age_h < 24 else "alta",
                        "title": f"Lote pendente há {age_h:.0f}h: {r['batch_id']}",
                        "detail": f"{r['article_count']} artigos aguardando análise de IA ({r['scope']})",
                        "article_id": None,
                        "article_title": r["batch_id"],
                        "action": "Processar lote",
                        "time": r["created_at"],
                    })

            # Feeds com erro recente
            cur.execute("""
                SELECT DISTINCT ON (source) source, status, error, finished_at
                FROM feed_runs
                WHERE status = 'error'
                ORDER BY source, id DESC
                LIMIT 5
            """)
            for r in cur.fetchall():
                r = dict(r)
                alerts.append({
                    "type": "feed_error",
                    "severity": "baixa",
                    "title": f"Feed com erro: {r['source']}",
                    "detail": str(r.get("error") or "")[:100],
                    "article_id": None,
                    "article_title": r["source"],
                    "action": "Verificar feed",
                    "time": r["finished_at"],
                })

            # Cobertura de IA muito baixa
            cur.execute("SELECT COUNT(*) n FROM articles")
            total = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) n FROM articles WHERE ai_score IS NOT NULL")
            with_ai = cur.fetchone()["n"]
            pct = round(with_ai / total * 100) if total else 0
            if pct < 10:
                alerts.append({
                    "type": "low_ai_coverage",
                    "severity": "media",
                    "title": f"Cobertura de IA baixa: {pct}%",
                    "detail": f"Apenas {with_ai} de {total} artigos com análise de IA",
                    "article_id": None,
                    "article_title": None,
                    "action": "Processar lotes pendentes",
                    "time": now,
                })

            # Aprovados sem publicar
            cur.execute("""
                SELECT COUNT(*) n FROM articles
                WHERE card_status = 'approved' AND editorial_status != 'published'
            """)
            n_approved = cur.fetchone()["n"]
            if n_approved > 0:
                alerts.append({
                    "type": "approved_not_published",
                    "severity": "info",
                    "title": f"{n_approved} card(s) aprovado(s) aguardando publicação",
                    "detail": "Cards aprovados no Telegram mas ainda não marcados como publicados",
                    "article_id": None,
                    "article_title": None,
                    "action": "Marcar como publicado",
                    "time": now,
                })

    severity_order = {"critica": 0, "alta": 1, "media": 2, "baixa": 3, "info": 4}
    return sorted(alerts, key=lambda a: severity_order.get(a["severity"], 5))


# ── Cobertura de IA ───────────────────────────────────────────────────────────

def ai_coverage_stats() -> dict:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                  COUNT(*) total,
                  COUNT(*) FILTER (WHERE ai_score IS NOT NULL) with_ai,
                  COUNT(*) FILTER (WHERE ai_score IS NULL AND final_score_brasil >= 60) high_no_ai,
                  COUNT(*) FILTER (WHERE source_scope='brasil') total_brasil,
                  COUNT(*) FILTER (WHERE source_scope='brasil' AND ai_score IS NOT NULL) ai_brasil,
                  COUNT(*) FILTER (WHERE source_scope='piaui') total_piaui,
                  COUNT(*) FILTER (WHERE source_scope='piaui' AND ai_score IS NOT NULL) ai_piaui,
                  COUNT(*) FILTER (WHERE source_scope='teresina') total_teresina,
                  COUNT(*) FILTER (WHERE source_scope='teresina' AND ai_score IS NOT NULL) ai_teresina,
                  COUNT(*) FILTER (WHERE priority='critica' AND ai_score IS NOT NULL) ai_critica,
                  COUNT(*) FILTER (WHERE priority='critica') total_critica,
                  COUNT(*) FILTER (WHERE priority='alta' AND ai_score IS NOT NULL) ai_alta,
                  COUNT(*) FILTER (WHERE priority='alta') total_alta
                FROM articles
            """)
            r = dict(cur.fetchone())

            cur.execute("""
                SELECT status, COUNT(*) n, COALESCE(SUM(article_count),0) arts
                FROM ai_batches GROUP BY status
            """)
            batches = {row["status"]: {"count": row["n"], "articles": int(row["arts"])}
                       for row in cur.fetchall()}

    pending_arts = batches.get("pending", {}).get("articles", 0)
    total = r["total"] or 1
    with_ai = r["with_ai"]

    return {
        **r,
        "pct_total": round(with_ai / total * 100, 1),
        "pct_brasil": round(r["ai_brasil"] / (r["total_brasil"] or 1) * 100, 1),
        "pct_piaui": round(r["ai_piaui"] / (r["total_piaui"] or 1) * 100, 1),
        "pct_teresina": round(r["ai_teresina"] / (r["total_teresina"] or 1) * 100, 1),
        "pct_critica": round(r["ai_critica"] / (r["total_critica"] or 1) * 100, 1),
        "pct_alta": round(r["ai_alta"] / (r["total_alta"] or 1) * 100, 1),
        "batches": batches,
        "pending_articles": pending_arts,
        "projected_pct": round((with_ai + pending_arts) / total * 100, 1),
    }


# ── Saúde das fontes ──────────────────────────────────────────────────────────

def source_health() -> list[dict]:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                  source,
                  COUNT(*) total_runs,
                  COUNT(*) FILTER (WHERE status='ok') ok_runs,
                  COUNT(*) FILTER (WHERE status='error') error_runs,
                  COUNT(*) FILTER (WHERE status='warning') warn_runs,
                  COALESCE(SUM(collected_count),0) total_collected,
                  MAX(finished_at) last_run,
                  MAX(CASE WHEN status='error' THEN error END) last_error
                FROM feed_runs
                GROUP BY source
            """)
            runs = {row["source"]: dict(row) for row in cur.fetchall()}

            cur.execute("""
                SELECT
                  source, source_scope,
                  COUNT(*) total_arts,
                  COUNT(*) FILTER (WHERE final_score_brasil >= 60) relevant_arts,
                  COUNT(*) FILTER (WHERE priority IN ('alta','critica')) high_arts,
                  ROUND(AVG(final_score_brasil)::numeric, 1) avg_score,
                  MAX(final_score_brasil) max_score
                FROM articles
                GROUP BY source, source_scope
            """)
            arts = {row["source"]: dict(row) for row in cur.fetchall()}

    result = []
    all_sources = set(runs.keys()) | set(arts.keys())
    for src in all_sources:
        r = runs.get(src, {})
        a = arts.get(src, {})
        total = r.get("total_runs", 0)
        errors = r.get("error_runs", 0)
        error_rate = round(errors / total * 100) if total else 0

        # Classificação automática
        if total == 0:
            classification = "inativa"
        elif error_rate >= 50:
            classification = "instavel"
        elif error_rate >= 20:
            classification = "com_erro"
        elif float(a.get("avg_score") or 0) >= 50:
            classification = "quente"
        elif int(a.get("high_arts") or 0) >= 3:
            classification = "relevante"
        elif float(a.get("avg_score") or 0) < 20:
            classification = "ruidosa"
        else:
            classification = "normal"

        result.append({
            "source": src,
            "scope": a.get("source_scope", ""),
            "total_runs": total,
            "ok_runs": r.get("ok_runs", 0),
            "error_runs": errors,
            "warn_runs": r.get("warn_runs", 0),
            "error_rate": error_rate,
            "total_collected": int(r.get("total_collected") or 0),
            "last_run": r.get("last_run"),
            "last_error": r.get("last_error", ""),
            "total_arts": int(a.get("total_arts") or 0),
            "relevant_arts": int(a.get("relevant_arts") or 0),
            "high_arts": int(a.get("high_arts") or 0),
            "avg_score": float(a.get("avg_score") or 0),
            "max_score": float(a.get("max_score") or 0),
            "classification": classification,
        })

    return sorted(result, key=lambda s: (-s["high_arts"], -s["avg_score"]))


# ── Operação / Pipeline ───────────────────────────────────────────────────────

def pipeline_health() -> dict:
    now = datetime.now(timezone.utc)
    cutoffs = {
        "2h": now - timedelta(hours=2),
        "6h": now - timedelta(hours=6),
        "24h": now - timedelta(hours=24),
    }

    with connect() as conn:
        with conn.cursor() as cur:
            # Última coleta
            cur.execute("""
                SELECT MAX(finished_at) last, SUM(collected_count) total_collected,
                       COUNT(*) FILTER (WHERE status='error') errors
                FROM feed_runs
                WHERE finished_at >= %s
            """, (now - timedelta(hours=3),))
            last_collect = dict(cur.fetchone())

            # Artigos por janela
            windows = {}
            for label, cutoff in cutoffs.items():
                cur.execute(
                    "SELECT COUNT(*) n FROM articles WHERE created_at >= %s",
                    (cutoff,)
                )
                windows[label] = cur.fetchone()["n"]

            # Cards gerados e aprovados
            cur.execute("""
                SELECT
                  COUNT(*) FILTER (WHERE card_status != 'none') total_cards,
                  COUNT(*) FILTER (WHERE card_status = 'approved') approved,
                  COUNT(*) FILTER (WHERE card_status = 'rejected') rejected,
                  COUNT(*) FILTER (WHERE card_status = 'pending') pending_tg
                FROM articles
            """)
            card_stats = dict(cur.fetchone())

            # Feeds com erro hoje
            cur.execute("""
                SELECT COUNT(DISTINCT source) n
                FROM feed_runs
                WHERE status = 'error' AND finished_at >= %s
            """, (now - timedelta(hours=24),))
            feeds_with_error = cur.fetchone()["n"]

            # Tamanho do banco
            cur.execute("SELECT COUNT(*) n FROM articles")
            total_articles = cur.fetchone()["n"]

    return {
        "last_collect": last_collect,
        "articles_by_window": windows,
        "card_stats": card_stats,
        "feeds_with_error_24h": feeds_with_error,
        "total_articles": total_articles,
    }


# ── Score de oportunidade editorial ──────────────────────────────────────────

def opportunity_score(article: dict) -> tuple[float, str]:
    """
    Retorna (score 0-100, explicacao).
    Responde: vale transformar isso em card agora?
    """
    score = 0.0
    reasons = []
    text = f"{article.get('title','')}. {article.get('summary','')}"
    pub_at = article.get("published_at")

    # Recência
    rec = recency_score(str(pub_at) if pub_at else None)
    if rec >= 8:
        score += 20
        reasons.append("recente")
    elif rec >= 5:
        score += 10

    # Score automático alto
    auto = float(article.get("final_score_brasil") or 0)
    if auto >= 70:
        score += 20
        reasons.append("score alto")
    elif auto >= 50:
        score += 10

    # Score de IA
    ai_s = float(article.get("ai_score") or 0)
    if ai_s >= 7:
        score += 15
        reasons.append("IA validou")
    elif ai_s >= 5:
        score += 8

    # Dinheiro público
    if count_terms(text, MONEY_PUBLIC_TERMS):
        score += 10
        reasons.append("dinheiro público")

    # Investigação/risco
    if count_terms(text, RISK_TERMS):
        score += 10
        reasons.append("investigação/risco")

    # Órgão de controle
    control_terms = ["tce", "cgu", "tcu", "mppi", "mpf", "pf", "controladoria"]
    if any(t in text.lower() for t in control_terms):
        score += 10
        reasons.append("órgão de controle")

    # Fonte confiável
    trust = float(article.get("source_trust") or 0.5)
    if trust >= 0.8:
        score += 5
        reasons.append("fonte confiável")

    # Já rejeitado penaliza
    if article.get("card_status") == "rejected" or article.get("editorial_status") == "rejected":
        score -= 30
        reasons.append("foi rejeitado")

    # Já publicado penaliza
    if article.get("editorial_status") == "published":
        score -= 50

    score = max(0, min(100, score))

    if not reasons:
        explanation = "Score baixo para oportunidade editorial"
    elif score >= 60:
        explanation = "Alta oportunidade: " + ", ".join(reasons[:3])
    elif score >= 35:
        explanation = "Oportunidade moderada: " + ", ".join(reasons[:2])
    else:
        explanation = "Baixa oportunidade"

    return round(score, 1), explanation


# ── Fontes (tabela sources — Fase 2) ─────────────────────────────────────────

def sources_summary() -> dict:
    """Estatísticas da tabela sources. Retorna zeros se a tabela estiver vazia ou não existir."""
    _empty: dict = {"total": 0, "enabled": 0, "with_error": 0, "by_scope": {}}
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) total,
                        COUNT(*) FILTER (WHERE enabled = TRUE) enabled,
                        COUNT(*) FILTER (WHERE last_status = 'error') with_error
                    FROM sources
                """)
                row = dict(cur.fetchone())
                cur.execute(
                    "SELECT scope, COUNT(*) n FROM sources GROUP BY scope ORDER BY scope"
                )
                by_scope = {r["scope"]: r["n"] for r in cur.fetchall()}
        return {
            "total": int(row["total"]),
            "enabled": int(row["enabled"]),
            "with_error": int(row["with_error"]),
            "by_scope": by_scope,
        }
    except Exception:
        return _empty


# ── Auditoria editorial (tabela editorial_actions — Fase 2) ───────────────────

def recent_editorial_actions(limit: int = 10) -> list[dict]:
    """Últimas ações editoriais registradas. Lista vazia se tabela não existir."""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ea.id, ea.article_id, ea.dispatch_id, ea.action, ea.actor,
                           ea.from_status, ea.to_status, ea.notes, ea.created_at,
                           a.title AS article_title
                    FROM editorial_actions ea
                    LEFT JOIN articles a ON ea.article_id = a.id
                    ORDER BY ea.created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ── Auditoria detalhada (Fase 8) ──────────────────────────────────────────────

def article_audit_history(article_id: str, limit: int = 50) -> list[dict]:
    """Histórico completo de ações para um artigo específico."""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ea.id, ea.action, ea.actor, ea.from_status, ea.to_status,
                           ea.notes, ea.metadata, ea.created_at,
                           ea.dispatch_id
                    FROM editorial_actions ea
                    WHERE ea.article_id = %s
                    ORDER BY ea.created_at DESC
                    LIMIT %s
                    """,
                    (article_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def dispatch_audit_history(dispatch_id: int, limit: int = 20) -> list[dict]:
    """Histórico de ações registradas para um dispatch específico."""
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT ea.id, ea.action, ea.actor, ea.from_status, ea.to_status,
                           ea.notes, ea.created_at, ea.article_id,
                           a.title AS article_title
                    FROM editorial_actions ea
                    LEFT JOIN articles a ON ea.article_id = a.id
                    WHERE ea.dispatch_id = %s
                    ORDER BY ea.created_at ASC
                    LIMIT %s
                    """,
                    (dispatch_id, limit),
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def audit_page_actions(
    days_back: int = 7,
    action_filter: str | None = None,
    actor_filter: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Lista ações editoriais para a página de auditoria, com filtros opcionais."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        conditions = ["ea.created_at >= %s"]
        params: list[Any] = [cutoff]

        if action_filter:
            conditions.append("ea.action = %s")
            params.append(action_filter)
        if actor_filter:
            conditions.append("ea.actor ILIKE %s")
            params.append(f"%{actor_filter}%")

        where = "WHERE " + " AND ".join(conditions)
        params.append(limit)

        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT ea.id, ea.article_id, ea.dispatch_id, ea.action, ea.actor,
                           ea.from_status, ea.to_status, ea.notes, ea.created_at,
                           a.title AS article_title,
                           a.source AS article_source,
                           a.priority AS article_priority
                    FROM editorial_actions ea
                    LEFT JOIN articles a ON ea.article_id = a.id
                    {where}
                    ORDER BY ea.created_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def audit_metrics(days_back: int = 7) -> dict:
    """Métricas de auditoria: totais por tipo de ação e por ator."""
    empty: dict = {"total": 0, "by_action": {}, "by_actor": {}, "approvals": 0, "rejections": 0}
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT action, COUNT(*) n
                    FROM editorial_actions
                    WHERE created_at >= %s
                    GROUP BY action
                    ORDER BY n DESC
                    """,
                    (cutoff,),
                )
                by_action = {r["action"]: r["n"] for r in cur.fetchall()}

                cur.execute(
                    """
                    SELECT actor, COUNT(*) n
                    FROM editorial_actions
                    WHERE created_at >= %s
                    GROUP BY actor
                    ORDER BY n DESC
                    LIMIT 10
                    """,
                    (cutoff,),
                )
                by_actor = {r["actor"]: r["n"] for r in cur.fetchall()}

        total = sum(by_action.values())
        approvals = by_action.get("approve_article", 0) + by_action.get("approve_card", 0)
        rejections = by_action.get("reject_article", 0) + by_action.get("reject_card", 0)

        return {
            "total": total,
            "by_action": by_action,
            "by_actor": by_actor,
            "approvals": approvals,
            "rejections": rejections,
        }
    except Exception:
        return empty
