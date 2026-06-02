"""
Classificador automático local — aproxima as dimensões da IA sem API externa.

Produz: gravidade, risco_investigativo, urgencia, impacto_social,
        dinheiro_publico, relevancia_politica, editoria, prioridade.

Precisão esperada: ~65-75% de concordância com IA real nos campos binários
(alta/crítica vs. baixa/ruído). Campos numéricos são estimativas.

NÃO sobrescreve ai_json nem campos de artigos com IA real.
Uso: preencher priority/category para artigos que ainda não passaram pela IA.
"""
from __future__ import annotations
from news_radar.core.text_utils import count_terms, normalize_text

# ── Listas de termos por dimensão ────────────────────────────────────────────

# Gravidade: crime grave, violência, desastre, crise institucional
CRIME_GRAVE_TERMS = [
    "homicídio", "homicidio", "assassinato", "assassinada", "assassinado",
    "feminicídio", "feminicidio", "latrocínio", "latrocinio",
    "sequestro", "extermínio", "exterminio", "chacina", "massacre",
    "estupro", "abuso sexual", "tortura", "maus-tratos", "baleado",
    "morreu baleado", "encontrado morto", "corpo encontrado",
    "vítima fatal", "vitima fatal", "óbito", "morte violenta",
    "suicídio coletivo", "suicidio",
]

CRIME_ORG_TERMS = [
    "tráfico de drogas", "trafico de drogas", "facção", "faccao",
    "crime organizado", "milícia", "milicia",
    "pcc", "comando vermelho", "cv ", "cv,", "bonde",
    "operação policial", "operacao policial",
    "mandado de prisão", "mandado de prisao",
    "deflagrada operação", "deflagrada operacao",
    "preso em flagrante", "detido", "capturado",
    "apreensão de drogas", "apreensao de drogas",
    "kilo de cocaína", "kilo de maconha",
]

CRISE_TERMS = [
    "estado de calamidade", "estado de emergência", "estado de emergencia",
    "epidemia", "surto", "contaminação", "contaminacao",
    "enchente", "inundação", "inundacao", "deslizamento", "desabamento",
    "desastre", "tragédia", "tragedia",
    "colapso", "colapso do sistema", "superlotação", "superlotacao",
    "explosão", "explosao", "incêndio", "incendio",
    "risco de morte", "risco iminente",
]

INSTITUTIONAL_CRISIS_TERMS = [
    "impeachment", "cassação", "cassacao", "afastamento do cargo",
    "intervenção federal", "intervencao federal",
    "dissolução", "dissolucao", "estado de sítio", "estado de sitio",
    "violação da constituição", "violacao da constituicao",
]

# Risco investigativo: fraude, corrupção, irregularidade
INVESTIGATIVO_TERMS = [
    # Já existentes mas agrupados aqui para a dimensão específica
    "superfaturamento", "cartel", "lavagem de dinheiro", "lavagem",
    "caixa dois", "propina", "suborno", "esquema",
    "desvio de verba", "desvio de recursos", "desvio de dinheiro",
    "fraude", "fraude em licitação", "fraude em licitacao",
    "irregularidade", "irregularidades",
    "corrupção", "corrupcao", "improbidade", "improbidade administrativa",
    "enriquecimento ilícito", "enriquecimento ilicito",
    "contrato suspeito", "superfaturado",
    "investigado", "indiciado", "denunciado",
    "inquérito", "inquerito", "ação penal", "acao penal",
    "pf investiga", "mp investiga", "tce aponta", "cgu aponta",
    "operação da pf", "policia federal investiga",
]

NEPOTISM_PATTERNS = [
    # Parente + cargo — detectado por co-ocorrência no texto
    "esposa do prefeito", "filho do prefeito", "filha do prefeito",
    "irmão do prefeito", "irmao do prefeito",
    "esposa do governador", "filho do governador",
    "esposa do vereador", "parente do prefeito",
    "contratação de parente", "contratacao de parente",
    "nepotismo",
]

# Urgência: breaking news, fato novo, decisão imediata
URGENCIA_TERMS = [
    "urgente", "agora", "ao vivo", "breaking",
    "alerta", "emergência", "emergencia",
    "confirmado", "confirmada",
    "deflagrada", "deflagrado", "preso nesta", "preso hoje",
    "hoje cedo", "nesta manhã", "nesta manha",
    "nesta tarde", "nesta noite", "há pouco", "ha pouco",
    "neste momento", "em andamento",
    "interrompido", "fechado", "suspenso",
    "greve", "paralisação", "paralisacao",
    "decisão do stf", "decisao do stf",
    "votação aprovada", "votacao aprovada",
    "aprovado hoje", "sancionado hoje",
]

# Impacto social: serviços essenciais afetados
IMPACTO_SOCIAL_TERMS = [
    "hospital", "ubs", "upa", "pronto-socorro", "pronto socorro",
    "falta de médico", "falta de medico", "falta de remédio", "falta de remedios",
    "falta de água", "falta de agua", "desabastecimento",
    "escola fechada", "aula suspensa", "creche",
    "ônibus", "onibus", "transporte público", "transporte publico",
    "falta de energia", "apagão", "apagao",
    "saneamento", "esgoto a céu aberto", "esgoto a ceu aberto",
    "moradia", "habitação", "habitacao", "sem-teto",
    "fome", "insegurança alimentar", "inseguranca alimentar",
    "benefício cortado", "beneficio cortado", "auxílio suspenso",
]

# Dinheiro público: contratos, licitações, verbas
DINHEIRO_PUBLICO_TERMS = [
    "licitação", "licitacao", "pregão", "pregao",
    "contrato", "aditivo contratual",
    "dispensa de licitação", "dispensa de licitacao",
    "inexigibilidade",
    "convênio", "convenio", "repasse federal", "repasse estadual",
    "emenda parlamentar", "emenda", "obra pública", "obra publica",
    "verba", "recurso federal", "recurso estadual",
    "orçamento", "orcamento",
    "r$ ", "milhões", "bilhões", "milhoes", "bilhoes",
    "rombo", "déficit", "deficit",
    "prestação de contas", "prestacao de contas",
    "tce", "tcu", "cgu", "auditoria",
]

# Relevância política
POLITICA_TERMS = [
    "eleição", "eleicao", "eleições 2026", "eleicoes 2026",
    "candidato", "candidatura", "campanha",
    "partido", "pt ", "pl ", "psdb ", "mdb ", "pp ", "union ",
    "governador", "prefeito", "vereador", "deputado", "senador", "ministro",
    "mandato", "reeleição", "reeleicao",
    "reforma ministerial", "articulação política", "articulacao politica",
    "base aliada", "oposição", "oposicao",
]

# ── Mapeamento editoria ───────────────────────────────────────────────────────

EDITORIA_RULES: list[tuple[str, list[str]]] = [
    ("Segurança", CRIME_GRAVE_TERMS + CRIME_ORG_TERMS + [
        "polícia", "policia", "segurança pública", "seguranca publica",
        "violência", "violencia", "bandido", "assalto", "roubou",
    ]),
    ("Justiça e controle", INVESTIGATIVO_TERMS + NEPOTISM_PATTERNS + [
        "stj", "stf", "tribunal", "juiz", "sentença", "sentenca",
        "condenado", "absolvido", "ação civil", "acao civil",
        "ministério público", "ministerio publico", "mppi", "mpf",
    ]),
    ("Contas públicas", DINHEIRO_PUBLICO_TERMS + [
        "transparência", "transparencia", "fiscalização", "fiscalizacao",
    ]),
    ("Saúde", [
        "saúde", "saude", "hospital", "ubs", "upa", "sus",
        "remédio", "remedio", "vacina", "vacinação", "vacinacao",
        "epidemia", "surto", "doença", "doenca", "covid",
        "leitos", "internação", "internacao",
    ]),
    ("Educação", [
        "educação", "educacao", "escola", "professor", "professores",
        "aluno", "alunos", "universidade", "enem", "pnld",
        "merenda", "transporte escolar", "creche",
    ]),
    ("Infraestrutura", [
        "obra", "pavimentação", "pavimentacao", "asfalto",
        "ponte", "viaduto", "rodovia", "estrada",
        "saneamento", "água", "agua", "esgoto",
        "energia elétrica", "energia eletrica",
    ]),
    ("Governos e política", POLITICA_TERMS + [
        "governo federal", "governo estadual", "governo municipal",
        "secretaria", "secretário", "secretario",
    ]),
    ("Economia", [
        "economia", "inflação", "inflacao", "desemprego",
        "emprego", "renda", "pib", "banco central",
        "juros", "taxa selic", "dólar", "dolar",
        "empresa", "indústria", "industria",
    ]),
    ("Cidades", [
        "cidade", "município", "municipio", "bairro",
        "moradores", "prefeitura", "câmara municipal", "camara municipal",
        "zoneamento", "urbanismo",
    ]),
]


# ── Funções de pontuação ──────────────────────────────────────────────────────

def _score(text: str, terms: list[str], max_score: float = 10.0, per_hit: float = 2.5) -> float:
    hits = count_terms(text, terms)
    return min(hits * per_hit, max_score)


def classify_gravidade(text: str) -> float:
    """0–10: severidade do fato (crime, crise, risco coletivo)."""
    grave = _score(text, CRIME_GRAVE_TERMS, 10, 3.5)
    org = _score(text, CRIME_ORG_TERMS, 8, 2.5)
    crise = _score(text, CRISE_TERMS, 8, 3.0)
    inst = _score(text, INSTITUTIONAL_CRISIS_TERMS, 8, 4.0)
    return min(max(grave, org * 0.9, crise * 0.85, inst * 0.9), 10.0)


def classify_risco_investigativo(text: str) -> float:
    """0–10: potencial de irregularidade, desvio, investigação."""
    inv = _score(text, INVESTIGATIVO_TERMS, 10, 2.0)
    nep = _score(text, NEPOTISM_PATTERNS, 8, 4.0)
    return min(max(inv, nep), 10.0)


def classify_urgencia(text: str, recency_hours: float = 48.0) -> float:
    """0–10: urgência do fato (breaking, decisão imediata, crise em curso)."""
    content_urgency = _score(text, URGENCIA_TERMS, 8, 2.0)
    # Penaliza artigos velhos mesmo que o texto seja urgente
    if recency_hours <= 6:
        time_bonus = 2.0
    elif recency_hours <= 24:
        time_bonus = 1.0
    elif recency_hours <= 72:
        time_bonus = 0.0
    else:
        time_bonus = -1.0
    return min(max(content_urgency + time_bonus, 0), 10.0)


def classify_impacto_social(text: str) -> float:
    """0–10: quanto afeta serviços essenciais da população."""
    return _score(text, IMPACTO_SOCIAL_TERMS, 10, 2.5)


def classify_dinheiro_publico(text: str) -> float:
    """0–10: envolve verba, contrato, licitação, desvio."""
    return _score(text, DINHEIRO_PUBLICO_TERMS, 10, 1.5)


def classify_relevancia_politica(text: str) -> float:
    """0–10: envolve mandatários, partidos, eleições."""
    return _score(text, POLITICA_TERMS, 10, 2.0)


def classify_editoria(text: str) -> str:
    """Classifica em uma das editorias padrão por contagem de termos."""
    best_score = 0
    best_editoria = "Outros"
    for editoria, terms in EDITORIA_RULES:
        score = count_terms(text, terms)
        if score > best_score:
            best_score = score
            best_editoria = editoria
    return best_editoria


def classify_prioridade(
    gravidade: float,
    risco: float,
    urgencia: float,
    impacto: float,
    dinheiro: float,
) -> str:
    """
    Classifica prioridade com base nas dimensões estimadas.
    Lógica conservadora: evita falsos positivos (critica/alta).
    """
    combined = (gravidade * 0.35 + risco * 0.30 + urgencia * 0.15 +
                impacto * 0.12 + dinheiro * 0.08)

    # Regras de gatilho direto
    if gravidade >= 8 or (gravidade >= 6 and risco >= 7):
        return "critica"
    if gravidade >= 6 or risco >= 7 or combined >= 6.5:
        return "alta"
    if combined >= 4.0 or gravidade >= 3 or risco >= 4:
        return "media"
    if combined >= 2.0:
        return "baixa"
    return "ruido"


# ── Função principal ──────────────────────────────────────────────────────────

def classify_article(article: dict, recency_hours: float = 48.0) -> dict:
    """
    Classifica um artigo com as mesmas dimensões que a IA produziria.

    Retorna dict com campos compatíveis com ai_json (prefixo 'auto_' para
    distinguir de classificações reais de IA).

    Não altera o artigo original.
    """
    title = article.get("title") or ""
    summary = article.get("summary") or ""
    content = article.get("content") or ""
    text = f"{title}. {summary}. {content[:500]}"

    gravidade = classify_gravidade(text)
    risco = classify_risco_investigativo(text)
    urgencia = classify_urgencia(text, recency_hours)
    impacto = classify_impacto_social(text)
    dinheiro = classify_dinheiro_publico(text)
    politica = classify_relevancia_politica(text)
    editoria = classify_editoria(text)
    prioridade = classify_prioridade(gravidade, risco, urgencia, impacto, dinheiro)

    return {
        "auto_gravidade": round(gravidade, 1),
        "auto_risco_investigativo": round(risco, 1),
        "auto_urgencia": round(urgencia, 1),
        "auto_impacto_social": round(impacto, 1),
        "auto_dinheiro_publico": round(dinheiro, 1),
        "auto_relevancia_politica": round(politica, 1),
        "auto_editoria": editoria,
        "auto_prioridade": prioridade,
    }


def enrich_article_without_ai(article: dict, recency_hours: float = 48.0) -> dict:
    """
    Para artigos sem IA: preenche priority e category usando o classificador local.
    Retorna cópia do artigo com priority e category preenchidos se estiverem vazios.
    """
    if article.get("ai_score"):
        return article  # já tem IA real — não sobrescreve

    result = dict(article)
    classification = classify_article(article, recency_hours)

    if not result.get("priority"):
        result["priority"] = classification["auto_prioridade"]
    if not result.get("category"):
        result["category"] = classification["auto_editoria"]

    result["_auto_classification"] = classification
    return result
