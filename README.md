# Integração do ZIP ajustado — 15/11/2026

A atualização incorpora ao aplicativo atual as melhorias operacionais presentes em `CapstoneLorealClean_ajustado (1).zip`, **mantendo a experiência de três áreas e as funcionalidades já existentes**. A integração foi feita sobre a branch principal atual, não por substituição cega de arquivos.

- **Motor e consistência:** sorteio de cenários por CRC32 da chave produto/fechamento/modelo para aproximar o notebook; cobertura futura do último mês do horizonte marcada `NaN`/não avaliada, sem tratá-la como ausência de excesso
- **Duas faixas de sinal:** aviso quando chance simulada >2,5% (acompanhar), alerta quando >20% (investigar ação); a regra de 20% é exploratória e deve ser validada em novos lançamentos
- **Critério de proteção do serviço:** cortes de lote em passos de 5%; parar no primeiro corte que gere sinal novo de ruptura ou eleve a probabilidade mensal de ruptura em mais de 2,5 p.p. Isso é um limite de cenário, **não um ótimo financeiro ou autorização para cancelar**
- **Consultor:** Central de decisões e gráficos diferenciam aviso/alerta, a comparação de alternativas exibe se o critério do TCC foi atendido e o limite de corte do lote
- **Validação:** painel histórico permite escolher aviso ou alerta. `tests/test_equivalencia_tcc.py` compara números de referência do ZIP ao notebook somente quando a planilha compatível é fornecida pela variável `TRIANGULO`. Sem ela, o teste é explicitamente `NÃO VERIFICADO`, não aprovado

**Governança:** nenhum dado confidencial foi incluído no GitHub. Dados reais devem ser usados apenas em implantação autorizada. A versão não foi homologada como substituto do plano Oficial, e probabilidades geradas por poucos resíduos históricos não devem ser interpretadas como calibradas.

---

# Métricas de antecedência e comparação com o Oficial — 14/11/2026

**Central de decisões:** o quarto indicador passou a ser **Alertas com oportunidade pelo LT** (N de M). O denominador é cada combinação produto × mês-alvo × tipo de risco (excesso ou ruptura), apenas na janela crítica de simulações válidas do fechamento selecionado. O numerador exige lote futuro positivo que chegue até o risco e prazo **posterior ao fechamento**, ou **no mês-limite** (sempre a confirmar). O detalhamento separa quantos são estritamente futuros e quantos estão no mês-limite. Não chama ausência de simulação de risco zero. A exportação Excel inclui aba `Prazo dos alertas` com ocorrências individuais.

**Resultados e confiabilidade:** preserva os números retrospectivos do TCC como bloco fixo, **sem misturá-los com o upload**. Acrescenta comparação **sob demanda e por produto** usando o Triângulo enviado: reconstrói até oito origens idênticas com a previsão operacional atual e com a previsão Oficial, usando o mesmo motor de simulação, limite de 2,5%, janela crítica e horizonte (9 meses). Considera somente meses-alvo com **excesso verificável por estoque registrado e vendas futuras disponíveis**; apresenta primeiro fechamento em alerta, antecedência em meses, condição pelo lead time e qual modelo sinalizou primeiro. Se não houver eventos verificáveis, retorna **sem evidência suficiente**, não zero. O fluxo operacional completo da L'Oréal **não é reconstruído**: a referência é a previsão Oficial combinada à regra de risco Smart Launch.

A validação de prazos históricos foi alinhada ao tratamento da competência **igual ao mês-limite**, classificada como oportunidade **dependente de confirmação da data de corte**, jamais como negociação autorizada. Essa métrica reflete oportunidades temporais teóricas, não taxa de decisões executadas ou resultado monetário.

Testes: `PYTHONPATH=. python tests/test_metrics.py`; `PYTHONPATH=. python tests/test_historical_validation.py`; `PYTHONPATH=. python tests/test_ui.py`. Nenhum dado real está versionado no repositório.

---

# Correção do diagnóstico de lotes e lead time — 14/11/2026

A interface distingue **(1) ausência de lote positivo futuro no Triângulo**, **(2) lote positivo com prazo teórico vencido**, **(3) lote no próprio mês-limite sujeito à data diária de corte** e **(4) lote com prazo teórico futuro**. Em todos os casos, a aprovação é humana. A ferramenta nunca afirma que a empresa não pode negociar pedidos externos ao arquivo.

**Exemplo metodológico:** se o fechamento é julho e o lead time é de quatro meses, uma entrega de novembro tem mês-limite em julho (incerteza da data de corte). Uma entrega de dezembro tem mês-limite em agosto. Lotes existentes nesses meses são apresentados como cenários possíveis de avaliação, não como cancelamentos automaticamente executáveis. Um lote que chega após o primeiro excesso não elimina o estoque que já estava acumulado naquele mês; pode afetar períodos posteriores.

**No P1**, quando não há produção futura positiva no Triângulo, o painel deve explicar que a simulação de excesso está relacionada ao estoque existente e às vendas futuras; orienta análise comercial e confirmação de compromissos não presentes no arquivo. Exibe uma tabela com os meses futuros, inclusive quantidades zeradas, no simulador e no impacto.

Os cálculos de previsão, probabilidade e balanço de estoque não foram modificados. A elegibilidade por mês foi ajustada para **prazo >= fechamento**, com aviso obrigatório para casos de igualdade. Testes de regressão: `PYTHONPATH=. python tests/test_supply.py` e `PYTHONPATH=. python tests/test_impact.py`.

---

# Smart Launch — experiência para consultores da L'Oréal (14/11/2026)

**Objetivo da interface:** em cada fechamento, permitir que o planejador responda: qual SKU apresenta risco, em que mês, se ainda existe prazo operacional e qual alternativa mitiga excesso sem provocar ruptura.

A navegação principal tem apenas **três áreas**:

1. **Central de decisões:** apresenta produtos analisados, sinais de excesso e ruptura, encaminhamentos (fornecedor, comercial ou monitoramento), prazo teórico e exportação do resumo do fechamento em Excel.
2. **Análise do produto:** concentra diagnóstico de P1/P2/P3, risco por mês, previsão em comparação ao Oficial e alternativas de lotes com excesso evitado, vendas perdidas e fill rate. Os detalhes técnicos ficam recolhidos por padrão. A planilha Excel da alternativa inclui resumo para reunião e todas as opções.
3. **Resultados e confiabilidade:** comunica o benefício **retrospectivo** perante a regra baseada no plano Oficial, o desempenho diferente por produto, os falsos alarmes, as limitações, a validação reconstruída e a auditoria. Os resultados do TCC ficam explicitamente separados dos cálculos feitos a partir do upload.

**Rotina:** carregar a versão mensal do Triângulo na lateral → identificar produtos prioritários → abrir a análise do produto → comparar cenários de decisão → baixar o resumo para reunião.

**Nota de governança:** o Smart Launch é uma camada de apoio ao plano Oficial. Os alertas não autorizam mudanças, os prazos são aproximações mensais e qualquer ação requer confirmação de contrato, capacidade, lote mínimo e política comercial. O TCC demonstrou antecipação retrospectiva em dois de três episódios, mas não redução realizada de estoque; a precisão dos alertas fora da amostra foi de 48%. Estes dados históricos não mudam quando se carrega outro arquivo.

**Testes:** em um ambiente com `pip install -r requirements.txt`:

```bash
python -m compileall -q app.py smartlaunch_ui.py smartlaunch_core.py smartlaunch_priority.py smartlaunch_impact.py smartlaunch_monthly.py smartlaunch_validation.py
PYTHONPATH=. python tests/test_smoke.py
PYTHONPATH=. python tests/test_impact.py
PYTHONPATH=. python tests/test_ui.py
```

---

# Ajustes do aplicativo — 14/11/2026

A interface atual mantém as seções já publicadas de **Validação histórica dos alertas** e **Impacto operacional**, com os cálculos de excesso, ruptura, fill rate e análise de alternativas de produção.

**Adaptação incorporada do pacote Smart Launch enviado:** além dos arquivos CSV, o painel agora permite baixar arquivos **Excel (.xlsx)** diretamente em duas análises: comparação de alternativas de lotes (Impacto operacional) e riscos do fechamento (Histórico e metodologia). As planilhas são geradas em memória a partir do Triângulo carregado pelo usuário, sem publicação de dados empresariais no repositório.

O ZIP `smartlaunch_app_pronto_github.zip` contém uma implementação independente com motor de simulação e validação. Não foi usado para substituir integralmente o site existente, porque essa substituição excluiria as funcionalidades incorporadas nas atualizações de 13/11/2026. A migração completa do motor do ZIP exige validação de equivalência metodológica e integração dos testes antes da troca.

---

# Impacto Operacional — 2026-11-13

**Nova página** no menu lateral, acessível também pelo simulador. Processa exclusivamente o arquivo Triângulo carregado pelo usuário, sem planilhas empresariais no GitHub.

**Indicadores disponíveis:**
- **Estoque excedente esperado no mês-alvo (unidades):** por cenário, estoque final no mês-alvo menos a soma das demandas simuladas dos **seis meses seguintes**, truncado em zero. A média dos 1.000 cenários é o excesso projetado. Não se somam excessos entre meses, pois isso contaria o mesmo estoque repetidas vezes.
- **Excesso potencialmente evitado:** diferença entre o plano inalterado e o plano alternativo para o **mesmo mês-alvo** e a **mesma demanda**. Pode ser negativa (agravamento).
- **Vendas perdidas adicionais:** diferença entre perdas simuladas totais na **janela crítica** dos planos (unidades, não eventos). Nunca incluir meses fora da janela na taxa de atendimento.
- **Fill rate projetado:** 1 − (soma das vendas perdidas / soma da demanda simulada), ambos sobre os mesmos meses da janela crítica.
- **Fronteira física estoque-serviço:** gráfico das alternativas de corte/aumento de um lote, em unidades esperadas de excesso vs. vendas perdidas. Identifica alternativas não dominadas; **não** é fronteira de custo em R$ sem custos fornecidos.
- **Prazo do fornecedor:** exibe apenas lotes positivos com prazo futuro pelo lead time arredondado. Ajustes não são executados; contratos, lote mínimo e capacidade continuam por confirmar.
- **Planejamento Oficial:** diferença histórica de MAPE entre previsão operacional e Oficial, em **pares iguais de origem/alvo** (apenas quatro modelos no backtest preliminar). Não confundir com política de compra/produção comprovadamente utilizada na empresa.
- **Antecedência operacional histórica:** percentual de **primeiros alertas reconstruídos** (produto × mês-alvo × tipo), nos quais havia lote ajustável pelo lead time. Não é taxa de decisões executadas ou benefício realizado.

**Limitação importante:** ao estimar seis meses de consumo após o mês-alvo, o motor extrapola o último mês simulado se o horizonte terminar antes. A interface comunica quantos meses tiveram extrapolação. A meta exploratória de fill rate é ajustável pelo usuário; não é padrão de serviço aprovado pela L'Oréal e não determina ação automática. A simulação depende da incerteza estimada com poucos erros históricos, e precisa ser homologada.

**Referência operacional:** o cenário "Manter plano" é o plano de produção carregado **sem alteração**, não é uma comprovação de que essa seja a política ótima nem o comportamento oficial da empresa. O ganho de unidade é potencial/simulado, não redução observada de estoque ou custo real.

\`\`\`bash
PYTHONPATH=. python tests/test_impact.py
PYTHONPATH=. python tests/test_ui.py
\`\`\`

---

## Cards de decisão — atualização de UX (2026-11-13)

A **Visão geral** agora organiza cada produto com três blocos:
- **O que está acontecendo:** tipo de risco, probabilidade máxima do mesmo tipo na janela crítica, mês do pico, primeiro mês que acionou o gatilho e cobertura mediana nesse pico. Todos saem das mesmas 1.000 trajetórias exibidas em **Riscos de estoque**.
- **Até quando agir:** mês de prazo teórico do lote que poderia chegar até o **primeiro** mês alertado, usando o lead time em meses arredondados do Triângulo. Se não houver lote positivo alterável, a interface informa que não existe ação viável pelo critério temporal.
- **O que pode fazer:** orientação de análise, não ordem para fornecedor. Excesso permite avaliar redução/adiamento; ruptura permite estudar reforço/antecipação apenas se houver lote relevante e em prazo. Quando não há prazo, encaminha a monitoramento, alocação ou comercial.

No Triângulo atual **não há data diária contratual de alteração**; por isso os cards não mostram datas específicas no formato DD/MM/AAAA nem contagem de dias fictícia. Essa informação deve ser ligada aos sistemas e contratos da L'Oréal antes de uso operacional. O texto do ranking indica que o melhor modelo resulta de comparação **experimental de quatro candidatos**, não de seleção completa homologada.

Teste: `PYTHONPATH=. python tests/test_priority_cards.py`.

---

## Validação histórica dos alertas (2026-11-13)

A nova seção **Validação histórica dos alertas**, acessível pelo menu lateral, reconstrói retrospectivamente o que um modelo teria previsto em cada fechamento, usando o Triângulo histórico e seus meses disponíveis. Os valores são reprocessados, e **não equivalem a alertas originalmente persistidos**: esta versão ainda não armazena o modelo aprovado por fechamento nem a previsão emitida na operação real.

- **Previsões versus realizados:** previsão do mês-alvo na origem, venda realizada recuperada da revisão seguinte, erro absoluto/percentual e estoque da revisão posterior.
- **Cobertura observada:** exclusivamente vendas realizadas posteriores. Marca excesso como verificável somente quando há estoque registrado e informação suficiente para saber se a cobertura alcançou 180 dias. Se as vendas futuras estiverem incompletas, permanece **pendente**, sem completar com previsões.
- **Ruptura:** não conclui ruptura ou acerto sem dado real de venda perdida. Estoque zerado, por si só, não comprova perda de venda.
- **Antecedência da decisão:** mostra quantos meses antes do risco o alerta foi reconstruído, o próximo prazo teórico de lote e se havia lote positivo modificável pelo critério de lead time (sem assegurar viabilidade contratual).
- **Sem contagem dupla:** indicadores resumidos usam a primeira emissão por produto × mês-alvo × tipo de risco. Existe tabela expandida com todos os fechamentos, inclusive alertas repetidos.
- **Arquivo e data separados:** selecione a revisão histórica que deseja reconstruir e a data de dados posteriores disponível para verificação. A página permite avaliar maio/26 sem ter que apagar os meses seguintes da planilha.
- **Exportações:** previsões × realizados e primeiros alertas em CSV, sem envio de dados ao repositório.

Cuidado metodológico: o Triângulo deve conter as revisões originais. Para considerar o estoque da revisão seguinte como efetivamente realizado, **é necessário confirmar essa convenção com a L'Oréal**. A avaliação da cobertura observada pode permanecer indefinida até existirem seis meses de vendas futuras conhecidas, mesmo que estoques registrados pareçam altos.

```bash
PYTHONPATH=. python tests/test_historical_validation.py
```

---

# Smart Launch — Central de Alertas (interface clara, novembro/2026)

**Execute:** `streamlit run app.py`. A interface atual usa **seis áreas** em menu lateral e só apresenta valores calculados a partir do Triângulo carregado. O app original de quatro/cinco abas foi preservado em `smartlaunch_app.py`, enquanto o motor compartilhado foi extraído para `smartlaunch_core.py`.

## O que mudou nesta versão

1. **Central de Alertas:** indicadores reais dos três produtos, cards sincronizados com os gráficos, classificação de risco e ação, linha do tempo E/R/P restrita à janela crítica.
2. **Atualização mensal:** upload do Excel, auditoria dos blocos, fechamento/revisão comum aos produtos, diagnóstico de falhas e nenhuma simulação inventada quando a amostra é insuficiente.
3. **Previsão e modelos:** ranking experimental de quatro métodos (MEA-P, MEA, Oficial, Naive), seleção e modelo operacional separados, aprovação explícita da troca.
4. **Riscos de estoque:** gráficos de excesso e ruptura com linha de 2,5%, tabela por mês e evolução retrospectiva do risco para um mesmo mês-alvo quando há fechamentos avaliáveis.
5. **Simulador de decisões:** destaque para prazo teórico do lote; cortes/adiamentos/antecipações só aparecem quando o lote está dentro do prazo. Com prazo vencido, a tela orienta encaminhamento comercial ou monitoramento, sem oferecer redução como ação executável.
6. **Histórico e metodologia:** parâmetros de sensibilidade, registro temporário de aprovações e exportação de riscos CSV.

## Atenção antes de usar com a L'Oréal

- **Não é homologado para produção:** reproduzir previsões, cenários, coberturas e gatilhos contra o notebook final e o Excel de resultados é obrigatório.
- **Ranking reduzido e provisório:** os quatro candidatos e a elegibilidade simplificada não equivalem aos 49 modelos testados no TCC.
- **Sem persistência corporativa:** uploads e decisões duram somente a sessão Streamlit; sem controle de acesso, histórico entre sessões ou notificações externas.
- **Repositório público:** **não inserir planilhas reais no GitHub**. Qualquer implantação com dados reais exige um ambiente protegido autorizado. O processamento ocorre no servidor da aplicação.
- Os prazos calculados são teóricos (lead time), não garantia de viabilidade contratual.

## Testes

```bash
pip install -r requirements.txt
python -m py_compile app.py smartlaunch_core.py smartlaunch_ui.py smartlaunch_monthly.py
python tests/test_alert_rules.py
python tests/test_monthly.py
python tests/test_smoke.py
python tests/test_ui.py
```

---

# Smart Launch — Painel mensal de apoio à decisão (implementação incremental)

## O que está implementado nesta branch
- Upload do triângulo e leitura das revisões de PV, produção e estoque na **sessão Streamlit**, sem commit de dados empresariais.
- Seleção de produto e competência; previsões MEA/MEA-P/Oficial e Naive.
- **Nova aba Modelos:** backtest com origem rolante h1–h3 em pares comparáveis; MAPE, MAE, RMSE, viés, contagem de previsões, origens e meses-alvo; indicação de vencedor experimental.
- **Modelo operacional separado do vencedor estatístico**: aprovação explícita, com histórico apenas na sessão e opção de restaurar o modelo original.
- Simulação de 1.000 demandas Normal(0,s) e alternativa bootstrap centralizado, com erros históricos conhecidos; estoque, cobertura futura, probabilidades, gatilhos e simulação de lotes.
- Exportação CSV dos riscos mensais e auditoria dos blocos por produto.

## Limites importantes antes de homologar com a L'Oréal
1. **Ranking ainda não é o algoritmo definitivo do notebook**: são quatro candidatos (MEA-P, MEA, Oficial, Naive) e uma elegibilidade complementar (ao menos 3 previsões em 2 origens). A seleção definitiva do TCC tinha 49 modelos e regras específicas. Antes de usar a escolha operacional como evidência, confrontar e substituir este ranking pelo protocolo do `SmartLaunch_TCC_final.ipynb`.
2. Esta implementação **não possui persistência entre sessões**. A cada execução o usuário deve carregar o Excel novamente; versões passadas devem estar contidas no triângulo carregado. Aprovações registradas em memória não são um registro corporativo.
3. Ainda não foram implementados controle de acesso, armazenamento privado, trilha de auditoria permanente, relatórios PDF, notificação automática nem onboarding de produtos arbitrários.
4. Paridade do motor de previsão/risco com o notebook do TCC **não foi certificada**. Não usar em decisões de abastecimento sem homologação.
5. Alterações em lotes são simulações teóricas e dependem de contratos, capacidades e confirmação da L'Oréal.
6. O repositório é **público**: nunca commitar dados reais. Mesmo com processamento em memória, o upload trafega pelo servidor Streamlit; use apenas implantação autorizada e protegida para dados reais.

## Rodar
```bash
pip install -r requirements.txt
streamlit run app.py
python tests/test_smoke.py
python tests/test_monthly.py
python tests/test_ui.py
```

## Atualização mensal
Carregue o arquivo do novo fechamento na aba **Atualização mensal**. Selecione a revisão e o produto. O sistema recalcula o ranking dos candidatos elegíveis usando apenas alvos realizados até o fechamento selecionado. O modelo operacional aprovado permanece em uso até uma troca expressamente autorizada na aba **Modelos**. A nova previsão alimenta os cenários, os riscos e o simulador de lotes.

## Próximos passos obrigatórios
- Conectar e validar integralmente o notebook final e seus resultados, especialmente o backtest de 49 modelos, definição do período de arranque e amostragem dos erros.
- Integrar armazenamento seguro de versões mensais e decisões com autenticação e controle de acesso.
- Criar visão consolidada de todos os produtos, prazos finais de intervenção, relatório PDF/Excel e avaliação retrospectiva de alertas.
- Validar novos produtos, novos formatos de arquivo e cobertura de competências após dezembro de 2026.

---

# Smart Launch — Painel Operacional (TCC L'Oréal)

## Navegação — quatro áreas

1. **Visão geral:** previsão do modelo fixo, faixa probabilística, estoque, cobertura, gatilhos e primeiro mês prioritário.
2. **Simulador de decisões:** lotes alteráveis pelo lead time, efeitos de manter/reduzir/cancelar/adiar/antecipar, ajuste de 5% em 5% e encaminhamento comercial/fornecedor/monitoramento.
3. **Atualização de dados:** upload do triângulo (sem commit), auditoria PV/produção/estoque, seleção de produto e fechamento e histórico conhecido.
4. **Metodologia e histórico:** fórmulas, premissas, limitações, sensibilidade Normal × bootstrap centralizado e exportação de resultados.

**Execução:** `streamlit run app.py` e carregar o triângulo atualizado na aba Atualização de dados. O app começa sem números fictícios.

**Importante:** o teste de interface usa planilha sintética e verifica o funcionamento básico, não a calibração nem a paridade numérica com o notebook do TCC. A decisão final continua sendo humana.


Aplicativo Streamlit para análise mensal de lançamentos (metodologia consolidada em novembro de 2026).

## Uso
1. Instale as dependências: `pip install -r requirements.txt`.
2. Execute: `streamlit run app.py`.
3. Faça upload **na própria aplicação** do arquivo `Triangulo_Produtos_V2.xlsx` (não inclua dados reais no GitHub).
4. Escolha produto e revisão mensal. O fechamento usado corresponde ao mês anterior à revisão.
5. Observe previsão, P2,5/P50/P97,5, estoque, cobertura, alertas e alternativas em lotes fora do lead time.

## Lógica implementada
- P1: MEA-P; P2: MEA, seleção provisória; P3: plano Oficial.
- Realizado: mês `m` obtido da revisão `m+1`; nenhuma venda posterior ao fechamento é usada nas previsões.
- MEA e MEA-P: analogia com média de log10; MEA-P ajusta os meses de pipe M1–M3 com benchmark global conhecido na data.
- Simulação: 1.000 cenários, erros `Normal(0, s)` da sacola de erros do arranque, limitado a demanda não negativa.
- Estoque com demanda perdida e cobertura por consumo futuro; limite de excesso 180 dias.
- Janela crítica: `ceil(LT_semanas*7/30) + ceil(cobertura_dias/30) + 1`.
- Gatilhos dentro da janela crítica: excesso se P97,5 da cobertura ≥ 180 dias; ruptura se P97,5 das vendas perdidas > 0.
- Lotes somente testados se além do lead time, com os mesmos cenários entre alternativas.
- Bootstrap centralizado e erros persistentes disponíveis **apenas para sensibilidade**.

## Atenção metodológica
Este painel é uma **implementação operacional inicial** baseada no notebook `SmartLaunch_TCC_final.ipynb`, não uma substituição do notebook nem uma certificação de paridade numérica. A interface calcula os erros rolantes da fase de arranque novamente; as diferenças de recorte/sacolas devem ser comparadas com a planilha de resultados do notebook antes de uso real. A classificação de ação é uma interpretação simplificada para triagem; não considera contratos, lotes mínimos, capacidades ou confirmação de modificabilidade pela L'Oréal.

Não se usa o banco A–P antigo: o novo painel espera o triângulo P1–P3 e seus análogos. Em fechamentos com menos de dois erros elegíveis a simulação fica desabilitada; não fabrica desvios-padrão.

**Confidencialidade:** o arquivo enviado é processado em memória na sessão Streamlit; configure a infraestrutura e controle de acesso adequados antes de disponibilizá-lo à L'Oréal. O repositório é público. Não faça commit das planilhas reais.

## Estado
Versão inicial do painel; requer homologação com `SmartLaunch_TCC_final_resultados.xlsx`, especialmente gatilhos e ações do P3, antes de operação empresarial.
