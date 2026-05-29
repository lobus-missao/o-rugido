# Template — Prompt de Análise de Lote de Notícias

Este é o template de referência Markdown do prompt para análise editorial por IA.
O arquivo operacional em uso é `prompts/ai_batch_prompt_template.txt`.

---

## Template Completo

```
Voce analisa somente o lote de noticias RSS fornecido abaixo.

Regras obrigatorias:
- Use apenas o conteudo do lote.
- Nao busque, nao verifique e nao cite fontes externas.
- Nao mencione cookies, sessoes, credenciais, arquivos locais ou contexto do sistema.
- Nao use markdown.
- Devolva apenas JSON valido, sem texto antes ou depois.
- Se algum campo nao puder ser inferido pelo texto, use valor neutro ou lista vazia.

Objetivo:
- Ajudar um sistema jornalistico piauiense que ranqueia noticias para redatores.
- Organizar cada noticia em uma editoria util para exibicao.
- Destacar informacoes praticas para painel e triagem editorial.

Para cada noticia, devolva um objeto JSON com os seguintes campos:

- id: o mesmo id recebido, nao altere nunca
- editoria: classifique em uma destas opções: "Governos e politica", "Contas publicas", "Justica e controle", "Saude", "Educacao", "Seguranca", "Infraestrutura", "Cidades", "Economia", "Esporte", "Cultura", "Outros"
- categoria: classificacao mais especifica e objetiva (ex: "Licitacao municipal", "Operacao policial", "Crise hospitalar")
- localidade: cidade, estado ou regiao mencionada. Use "Nacional" se for de alcance federal. Use "Internacional" se for externo.
- entidades: lista de orgaos publicos, pessoas politicas, empresas e instituicoes citadas
- interesse_publico: numero de 0 a 10 — quanto a noticia afeta a vida dos cidadaos
- impacto_social: numero de 0 a 10 — quanto afeta servicos como saude, educacao, transporte
- gravidade: numero de 0 a 10 — severidade do fato (crime, crise, risco coletivo)
- risco_investigativo: numero de 0 a 10 — potencial de irregularidade, desvio, investigacao
- dinheiro_publico: numero de 0 a 10 — envolve contrato, licitacao, verba, obra, desvio
- relevancia_politica: numero de 0 a 10 — envolve mandatarios, partidos, eleicoes
- polemica: numero de 0 a 10 — gera debate, polarizacao ou repercussao publica
- urgencia: numero de 0 a 10 — fato novo, crise imediata, decisao urgente
- relevancia_local: numero de 0 a 10 — impacto direto em Piaui, Teresina ou municipios piauienses
- confiabilidade: numero de 0 a 10 — credibilidade da fonte e verificabilidade do fato
- prioridade: classifique em uma destas opcoes: "ruido", "baixa", "media", "alta", "critica"
- resumo_curto: uma frase objetiva de ate 120 caracteres descrevendo o fato central
- titulo_sugerido: titulo editorial de ate 80 caracteres, direto e impactante
- subtitulo_sugerido: subtitulo editorial de ate 120 caracteres com contexto adicional
- pontos_chave: lista de 2 a 4 pontos concretos, objetivos e factuais
- tags: lista de 3 a 6 palavras-chave editoriais para indexacao
- justificativa_score: uma frase curta explicando a prioridade atribuida

Criterios gerais de pontuacao:

interesse_publico sobe quando:
- Envolve governo, servicos publicos, direitos, fiscalizacao
- Envolve politica administrativa, contratos, obras, decisoes que afetam a populacao

impacto_social sobe quando:
- Afeta diretamente saude, educacao, transporte, seguranca, moradia, renda, agua, energia

urgencia sobe quando:
- Ha fato novo, crise, denuncia relevante, interrupcao de servico, risco coletivo, decisao imediata

relevancia_local sobe quando:
- A noticia tem efeito claro em Piaui, Teresina ou municipios piauienses

dinheiro_publico sobe quando:
- Ha contrato, licitacao, verba, repasse, obra, gasto, orcamento ou orgao de controle

polemica sobe quando:
- Assunto gera debate publico intenso, polarizacao politica ou forte repercussao nas redes

Noticias de esporte, celebridades e entretenimento vao para prioridade "ruido" ou "baixa",
exceto se houver forte interesse publico (escandalo, desvio de verba publica, investigacao).

Devolva a resposta como uma lista JSON valida:
[
  { "id": "...", "editoria": "...", ... },
  { "id": "...", "editoria": "...", ... }
]
```

---

## Contextos por Escopo (Adicionados ao Prompt)

### Brasil

```
ESCOPO: BRASIL (visao nacional)
Foco em noticias de alcance nacional com impacto em politica, economia, justica e servicos publicos federais.
Principais orgaos de referencia: STF, STJ, TCU, CGU, PF, MPF, Senado, Camara dos Deputados, ministerios federais.
Relevancia_local alta quando afeta diretamente o Piaui ou o Nordeste.
```

### Piauí

```
ESCOPO: PIAUI (visao estadual)
Foco em noticias do estado do Piaui. Relevancia_local alta quando envolve Teresina, Parnaiba, Picos ou municipios piauienses.
Principais orgaos: ALEPI (Assembleia Legislativa), TCE-PI, MPPI, TJPI, Governo do Estado, Secretarias estaduais.
Governador atual: Rafael Fonteles. Partido: PT.
Siglas importantes: SEDUC-PI (educacao), SESAPI (saude), SSP-PI (seguranca), SEMAR (meio ambiente).
Prioridade alta para contratos estaduais, operacoes do MPPI/TCE-PI, decisoes da ALEPI.
```

### Teresina

```
ESCOPO: TERESINA (visao municipal)
Foco exclusivo em noticias da capital Teresina e sua area metropolitana.
Principais orgaos: Prefeitura de Teresina, Camara Municipal de Teresina, FMS (Fundacao Municipal de Saude), SEMEC (educacao municipal), STRANS (transporte), SEMDUH (habitacao), ETURB (urbanismo).
Siglas: HUT (Hospital de Urgencia de Teresina), UPA, ARSETE, SAAD.
Prioridade alta para: licitacoes municipais, obras na cidade, denuncias envolvendo vereadores ou servidores, interrupcao de servicos publicos municipais.
```

---

## Campos Obrigatórios na Resposta

| Campo | Tipo | Obrigatório |
|-------|------|-------------|
| id | string | Sim — mesmo ID recebido |
| editoria | string enum | Sim |
| prioridade | string enum | Sim |
| interesse_publico | número 0-10 | Sim |
| impacto_social | número 0-10 | Sim |
| urgencia | número 0-10 | Sim |
| relevancia_local | número 0-10 | Sim |
| dinheiro_publico | número 0-10 | Sim |
| resumo_curto | string ≤120 chars | Sim |
| justificativa_score | string | Sim |
| entidades | lista | Não (mas recomendado) |
| pontos_chave | lista 2-4 itens | Não (mas recomendado) |
| titulo_sugerido | string ≤80 chars | Não |
| tags | lista 3-6 itens | Não |
