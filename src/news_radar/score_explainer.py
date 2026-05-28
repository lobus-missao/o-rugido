"""
Explicabilidade do score automático de um artigo.
Recalcula dinamicamente os componentes sem alterar o banco.
"""
from __future__ import annotations
from typing import Any

from .text_utils import count_terms, extract_money_values, normalize_text
from .ranker import (
    PUBLIC_ORG_TERMS, RISK_TERMS, MONEY_PUBLIC_TERMS, SOCIAL_IMPACT_TERMS,
    POLITICAL_TERMS, BRAZIL_TERMS, PIAUI_TERMS, TERESINA_TERMS,
    recency_score, clamp,
)


COMPONENT_LABELS = {
    "public":    ("🏛️ Órgãos públicos",       "Governo, prefeitura, tribunal, MP, câmara..."),
    "risk":      ("⚠️ Risco / investigação",  "Fraude, denúncia, operação, prisão, desvio..."),
    "money":     ("💰 Dinheiro público",       "Contrato, licitação, obra, verba, repasse..."),
    "social":    ("👥 Impacto social",         "Saúde, educação, transporte, moradia..."),
    "political": ("🗳️ Político",               "Eleição, vereador, deputado, governador..."),
    "money_val": ("💲 Valor monetário",        "Valor financeiro detectado no texto"),
    "trust":     ("📰 Fonte confiável",        "Peso da confiabilidade da fonte"),
    "novelty":   ("🕐 Recência",               "Quão recente é a notícia"),
    "brasil":    ("🇧🇷 Bônus Brasil",          "Referências ao cenário nacional"),
    "piaui":     ("🟣 Bônus Piauí",           "Referências ao estado do Piauí"),
    "teresina":  ("🏙️ Bônus Teresina",        "Referências à capital Teresina"),
    "scope":     ("📍 Escopo da fonte",        "A própria fonte é local/estadual"),
}


def explain_score(article: dict[str, Any], scope: str = "brasil") -> dict:
    """
    Retorna decomposição completa do score automático de um artigo.
    """
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
    money_values = extract_money_values(text)
    novelty = recency_score(str(published_at) if published_at else None)

    base_public = min(public_count * 3, 12)
    base_risk = min(risk_count * 4, 16)
    base_money = min(money_count * 3, 12)
    base_social = min(social_count * 2, 8)
    base_political = min(political_count * 2, 8)
    base_money_val = 6 if money_values else 0
    base_trust = trust * 6
    base_novelty = novelty
    base_content = 0
    summary_len = len(summary)
    if summary_len >= 500:
        base_content = 6
    elif summary_len >= 200:
        base_content = 4
    elif summary_len >= 50:
        base_content = 2

    brasil_bonus = min(brazil_count * 4, 16)
    piaui_bonus = min(piaui_count * 7, 28)
    teresina_bonus = min(teresina_count * 9, 36)
    scope_bonus = 0
    if source_scope == "piaui":
        piaui_bonus += 10
        scope_bonus = 10
    if source_scope == "teresina":
        piaui_bonus += 10
        teresina_bonus += 14
        scope_bonus = 14

    common = (base_public + base_risk + base_money + base_social +
              base_political + base_money_val + base_trust + base_novelty + base_content)

    geo_bonus = {"brasil": brasil_bonus, "piaui": piaui_bonus, "teresina": teresina_bonus}.get(scope, brasil_bonus)
    total = clamp(common + geo_bonus)

    components = {
        "public":    {"value": base_public,   "max": 12, "count": public_count},
        "risk":      {"value": base_risk,     "max": 16, "count": risk_count},
        "money":     {"value": base_money,    "max": 12, "count": money_count},
        "social":    {"value": base_social,   "max": 8,  "count": social_count},
        "political": {"value": base_political,"max": 8,  "count": political_count},
        "money_val": {"value": base_money_val,"max": 6,  "count": len(money_values)},
        "trust":     {"value": round(base_trust, 1), "max": 6, "count": None},
        "novelty":   {"value": round(base_novelty, 1), "max": 10, "count": None},
    }
    if scope == "brasil":
        components["brasil"] = {"value": brasil_bonus, "max": 16, "count": brazil_count}
    elif scope == "piaui":
        components["piaui"] = {"value": piaui_bonus, "max": 38, "count": piaui_count}
    elif scope == "teresina":
        components["teresina"] = {"value": teresina_bonus, "max": 50, "count": teresina_count}

    # Gera explicação em linguagem natural
    signals = []
    if risk_count:
        signals.append("investigação/risco")
    if money_count or money_values:
        signals.append("dinheiro público")
    if public_count:
        signals.append("órgão público")
    if social_count:
        signals.append("impacto social")
    if novelty >= 8:
        signals.append("notícia recente")
    if piaui_count and scope in ("piaui", "teresina"):
        signals.append("relevância local")
    if teresina_count and scope == "teresina":
        signals.append("contexto Teresina")
    if trust >= 0.8:
        signals.append("fonte confiável")

    if signals:
        explanation = "Esta notícia recebeu score alto porque " + ", ".join(signals[:4]) + "."
    else:
        explanation = "Score baseado em recência e confiabilidade da fonte."

    return {
        "total": round(total, 1),
        "common": round(common, 1),
        "geo_bonus": round(geo_bonus, 1),
        "components": components,
        "explanation": explanation,
        "signals": signals,
        "money_values_found": money_values[:3],
        "summary_chars": summary_len,
    }
