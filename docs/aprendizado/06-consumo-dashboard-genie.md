# 06 · Consumo: AI/BI Dashboard e Genie, com governança de ponta a ponta

## Em uma frase

A camada Gold chega ao negócio de duas formas: um **dashboard** (respostas prontas, sempre as mesmas perguntas) e o **Genie** (perguntas livres, em português, que viram SQL). Os dois **só existem em PROD**, são publicados pelo **bundle** e respeitam as permissões do **Unity Catalog** de quem está olhando.

## O que foi publicado

| Recurso | O que mostra | Arquivo no repositório |
|---|---|---|
| **Dashboard** "Indicadores Econômicos · BCB" | 4 KPIs (dólar, euro, Selic, IPCA 12m), dólar diário com média móvel, Selic × IPCA × juro real, IPCA mensal e tabela mensal; filtro de período | [`platform/src/dashboards/`](../../platform/src/dashboards) (gerado por `build_dashboard.py`) |
| **Genie** "Analista Econômico · BCB" | Perguntas livres sobre as 3 tabelas Gold | [`platform/src/genie/`](../../platform/src/genie) (gerado por `build_genie_space.py`) |

Os dois arquivos JSON são **gerados por scripts Python**, e não editados à mão. Assim fica fácil revisar mudanças num Pull Request e regenerar de forma consistente.

## Governança no consumo: `embed_credentials: false`

```yaml
dashboards:
  indicadores:
    embed_credentials: false      # cada pessoa consulta com a PRÓPRIA identidade
    permissions:
      - group_name: analysts
        level: CAN_RUN
```

| Configuração | Quem executa a consulta | Efeito |
|---|---|---|
| `embed_credentials: true` (padrão) | Quem **publicou** o dashboard | Qualquer pessoa com acesso ao dashboard vê os dados, mesmo sem grant na tabela |
| `embed_credentials: false` (**nosso**) | Quem está **vendo** | Valem os grants do Unity Catalog: o analista vê a Gold porque tem `SELECT` no schema `gold`, e só isso |

Ou seja: **ter acesso ao dashboard não dá acesso aos dados**. O acesso aos dados continua vindo do Unity Catalog. Para o analista abrir o dashboard, ele também precisa usar o SQL warehouse, e o grupo `users` do workspace já tem `CAN_USE` no *Serverless Starter Warehouse*.

## Como o Genie é "ensinado"

O Genie lê os metadados das tabelas e as instruções que demos a ele:

| Elemento | Para quê | Exemplo |
|---|---|---|
| **Descrição de coluna** | Dizer o que a coluna significa | `selic_meta_pct_aa`: "Meta da Selic no fim do mês, % ao ano" |
| **Sinônimos** | Ligar o vocabulário do usuário à coluna | "inflação anual" → `ipca_12m_pct` |
| **Instruções gerais** | Regras de negócio | "Nunca some taxas de meses diferentes: use EXP(SUM(LN(1+taxa)))" |
| **Exemplos de SQL** | Mostrar o jeito certo de responder perguntas difíceis | CDI acumulado no ano, juro real do último mês |
| **Perguntas sugeridas** | Ajudar o usuário a começar | "Em qual mês a Selic esteve mais alta?" |

Teste real, feito pelo terminal:

```text
Pergunta: "Qual foi o juro real no último mês disponível?"
SQL gerado: SELECT mes, selic_meta_pct_aa, ipca_12m_pct, juro_real_aprox_pct
            FROM econ_prod.gold.indicadores_mensais
            WHERE juro_real_aprox_pct IS NOT NULL ORDER BY mes DESC LIMIT 1
Resposta:   out/2026 · Selic 13,75% · IPCA 12m 4,63% · juro real 8,72%
```

## Um dado curioso que apareceu (e por que isso importa)

Ao testar os exemplos do Genie, apareceu uma **alta de 9,19% do dólar em 26/10/2026**. Antes de confiar ou descartar, conferimos direto na API: o BCB publica R$ 5,0377 em 23/10 e R$ 5,5007 em 26/10. Ou seja, **o pipeline reproduz a fonte fielmente**. Investigar se uma anomalia vem do pipeline ou da fonte, antes de "corrigir", é um hábito importante de engenharia de dados.

## Perguntas de entrevista (e como responder)

**"Como você garante que o dashboard não vaze dados?"**
> Publiquei com `embed_credentials: false`. Cada consulta roda com a identidade de quem está vendo, então valem os grants do Unity Catalog. O grupo de analistas só tem `SELECT` no schema `gold` de PROD; mesmo que alguém compartilhe o dashboard com outra pessoa, ela só vê o que o Unity Catalog permite.

**"Dashboard ou Genie: quando usar cada um?"**
> Dashboard para as perguntas recorrentes e para os KPIs que todo mundo acompanha (rápido, consistente, igual para todos). Genie para perguntas exploratórias que ninguém previu. O Genie mostra o SQL gerado, então a resposta é auditável.

**"Como você melhora a qualidade das respostas do Genie?"**
> Com metadados: descrição e sinônimos por coluna, instruções com as regras de negócio (por exemplo, como acumular taxas) e exemplos de SQL para as perguntas mais difíceis. Também testo as perguntas sugeridas e confiro o SQL gerado.

**"Como dashboard e Genie entram no CI/CD?"**
> Os dois são recursos do bundle, definidos por arquivos JSON gerados por script e versionados no Git. Só existem no target `prod`, com permissões declaradas no YAML.

## Para praticar sozinha depois

1. Abra o dashboard em PROD e mude o filtro de período para 2025. Veja os KPIs (último valor) e os gráficos (filtrados).
2. No Genie, pergunte "Quais foram os 5 dias de maior alta do dólar?" e clique em **Show code** para ver o SQL.
3. Entre com o usuário **analista** (`jen_maia@hotmail.com`) no workspace PROD e tente `SELECT * FROM econ_prod.bronze.bcb_series_raw`. O acesso deve ser **negado**. Esse é o print de governança do portfólio.
