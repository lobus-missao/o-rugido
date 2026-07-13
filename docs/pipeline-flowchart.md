# Pipeline do O Rugido

Portal de notícias do Piauí com foco em polêmica política. Três edições por dia (7h, 12h, 18h), sete dias por semana. Cada edição tenta ter uma polêmica política e mais até duas notícias de outras áreas. Se o dia tá calmo, publica menos.

## Fluxo em uma tela

```mermaid
flowchart LR
    RSS[RSS dos portais do PI] --> Ing[Ingestão + dedupe por URL]
    Ing --> Rank[Ranker + sinal de polêmica]
    Rank --> LLM

    subgraph LLM[Ollama nos finalistas]
        C1[Confirma polêmica]
        C2[Agrupa mesmo caso]
        C3[Reescreve título e resumo]
        C1 --> C2 --> C3
    end

    LLM --> Mix[Seleciona 1 polêmica + 2 outras]
    Mix --> Card[Playwright gera card 1080x1080]
    Card --> Tg[Manda no Telegram do editor]
    Tg -->|aprovar| Pub
    Tg -->|editar| Card
    Tg -->|rejeitar| Fim((arquiva))

    Pub[Publica no canal + Instagram]
    Pub --> Metric[Coleta views e engajamento em batch]
```

## Passo a passo detalhado

```mermaid
flowchart TD
    Start([Cron n8n 7h / 12h / 18h])

    Start --> A1[/pipeline/collect na API/]
    A1 --> A2[Lê feeds ativos do configs/feeds.yaml]
    A2 --> A3[feedparser puxa título, resumo, url, data]
    A3 --> A4{Já tem esse artigo?}
    A4 -->|sim| Skip[skip]
    A4 -->|não| A5[Salva em articles]

    A5 --> B1[Ranker calcula score base do Piauí]
    B1 --> B2[Marca candidato a polêmica<br/>regex + categoria + fontes curadas]
    B2 --> B3[Ordena por score final]

    B3 --> C1[Top 8 vão pro Ollama]
    C1 --> C2[LLM: é polêmica política?<br/>timeout 15s]
    C2 -->|deu ruim| Cfb1[cai pro score bruto]
    C2 -->|ok| C3[LLM agrupa mesmo caso<br/>pega o representante do grupo]
    C3 --> C4[LLM reescreve no tom O Rugido]
    C4 -->|deu ruim| Cfb2[usa texto original + marca no card]
    C4 -->|ok| C5[Texto reescrito]

    C5 --> D1[Aplica a cota]
    Cfb1 --> D1
    Cfb2 --> D1
    D1 --> D2[1 slot: polêmica política]
    D1 --> D3[Até 2 slots: outras categorias]
    D2 --> D4[Cria dispatch pending_article]
    D3 --> D4

    D4 --> E1[Busca imagem no SearXNG<br/>filtra domínios que bloqueiam crawler]
    E1 --> E2[Playwright renderiza HTML → PNG 1080x1080]
    E2 --> E3[Salva em data/cards/]

    E3 --> F1[Manda no Telegram do editor<br/>Aprovar / Editar / Rejeitar]
    F1 --> F2{Editor}
    F2 -->|Aprovar| F3[ready_to_publish]
    F2 -->|Editar| F4[Dashboard reescreve]
    F4 --> E2
    F2 -->|Rejeitar| F5[article_rejected]

    F3 --> G1[Publica no canal do Telegram]
    F3 --> G2[Cross-post no feed do Instagram]
    G1 --> G3[Registra em editorial_actions]
    G2 --> G3

    G3 --> H1[Job puxa views do Telegram 24h e 7d]
    G3 --> H2[Job puxa engajamento do Insta]
    H1 --> H3[Salva em post_metrics]
    H2 --> H3
```

## O que o editor vê no Telegram

```mermaid
stateDiagram-v2
    [*] --> pending_article: card chega pro editor

    pending_article --> editing: Editar
    pending_article --> ready_to_publish: Aprovar
    pending_article --> article_rejected: Rejeitar

    editing --> pending_article: salvou, volta pra revisar

    ready_to_publish --> published: cron publica nos canais
    article_rejected --> [*]
    published --> [*]
```

## Regras que definimos

| O quê | Como fica |
|---|---|
| Público | Piauiense comum, celular na mão, tempo curto |
| Diferencial | Polêmica política do PI (mas cobre resto também) |
| Cadência | 3 edições/dia (7h, 12h, 18h) todo dia |
| Cota por edição | 1 polêmica política + até 2 outras |
| Dia sem polêmica | Publica menos. Não força volume. |
| Tom | Direto, sem rodeio, sem sarcasmo, sem opinião |
| Reescrita | Ollama mexe em título + resumo antes do editor ver |
| Timeout LLM | 15s. Se estourar, publica com o texto do feed original |
| Dedupe entre fontes | LLM agrupa "mesmo caso" nos finalistas |
| Editor | Fila humana no Telegram, aprova/edita/rejeita |
| Auditoria | editorial_actions guarda quem aprovou e quando |
| Onde publica | Canal do Telegram + feed do Instagram (cross-post) |
| Formato do card | 1080x1080. Insta feed corta, aceita por ora. |
| Sucesso = | Views no Telegram + engajamento no Insta |

## Sobre a detecção de polêmica

Duas camadas: primeiro uma regra barata (regex de palavras tipo "operação", "denúncia", "indiciado", "MP", "PF", "corrupção", "escândalo" + categoria política + lista de fontes que cobrem esse tipo), depois o Ollama confirmando nos ~8 finalistas. A regra barata evita rodar LLM em 50 artigos por coleta.

## Exportar pra apresentação

Abre no GitHub que ele renderiza direto. Se precisar PNG em alta pra colar em slide, copia o bloco ```mermaid...``` e joga em https://mermaid.live/ — tem botão de Export lá.
