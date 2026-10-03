# Decisões, e o porquê de cada uma

Este arquivo é a MEMÓRIA do projeto: por que cada coisa é como é, e o que já
custou tempo. Saiu do `CLAUDE.md` (que tinha 1708 linhas e é lido inteiro a
cada sessão de IA) porque ler tudo toda vez custa caro e atrasa até o pedido
mais simples — mas apagar seria pior: metade destas linhas existe porque
alguém, aqui, já tomou a decisão errada uma vez.

**Leia a seção relevante ANTES de mexer na área correspondente.** O `CLAUDE.md`
aponta pra cá nos pontos em que isso importa.

## Decisões e o porquê

**Chunk = artigo, não N caracteres.** Artigo é unidade semântica completa.
Cortar por tamanho destrói o que o estudante procura.

**Rubrica ("Concussão") vai DENTRO do campo `texto`.** Embedding e tsvector
são calculados sobre `texto`; o que não está lá não é recuperável. Também
existe em coluna própria para busca direta.

**Busca híbrida com RRF, não soma de scores.** Distância de cosseno e
`ts_rank_cd` vivem em escalas diferentes; somar é o erro clássico. RRF funde
por posição no ranking.

**Citação exata de dispositivo não traz complemento semântico.** Precisão
vence recall: contexto extra só dá ao modelo material para citar fonte errada.

**Retenção do gabarito é imposta em código, não no prompt.** O modelo recebe
o gabarito para julgar e é instruído a não revelar — mas instrução vaza. Quem
decide revelar é `chat.py`, após 3 respostas erradas.

**`socratic.explicar()` tem DUAS fontes de contexto — material E desempenho
real do aluno — porque um professor que não sabe conversar sobre o próprio
progresso do aluno não é professor.** Antes disso, "como estou indo em
português?" não tinha onde bater: a busca (RAG) só sabe sobre o acervo de
lei, nunca sobre quem pergunta. `_resumo_desempenho()` busca
`scheduler.desempenho()` + `scheduler.caderno_erros()` e monta um resumo
pronto — o modelo só LÊ esse resumo, nunca soma nada sozinho, mesmo
princípio de "retenção imposta em código" acima. O modelo escolhe qual
fonte usar (ou as duas) por instrução de prompt, não por classificação
separada — mais simples que rotear a pergunta antes de perguntar, e testado
que funciona: sem tentativa nenhuma, admite que não tem dado; com
tentativa real, responde com o número exato do banco, nunca inventado.

**Fila = revisões primeiro, novas com o orçamento restante.** Ordenar só por
caixa causa INANIÇÃO: com centenas de questões inéditas, a promovida volta em
3 dias e fica atrás de todas. Simulado em 90 dias: 8% de domínio contra 51%.

**Penalidade de promoção = errar, não receber dica.** Dica vem automática ao
errar, então as duas coisas andam juntas; penalizar ambas conta a mesma falha
duas vezes. Dica pedida por iniciativa própria conta.

**Simulado não dialoga nem dá dica — corrige tudo no final.** É a diferença
entre treino e prova; andaime durante a prova mede a ajuda, não o aluno.
Reaproveita `scheduler.registrar`: como nunca há dica, `dicas_usadas` é
sempre 0, então acerto sempre promove — mesma regra de sempre, mesmo sinal
limpo. Seleciona por `ORDER BY random()` sobre TODO o acervo, não pela fila
do dia: fila prioriza o que venceu, simulado testa o conjunto inteiro.

**`v_desempenho_disciplina` devolve `float8`, não `numeric`.** `ROUND(numeric,
N)` vira `Decimal` no psycopg, e `json.dumps(Decimal)` estoura `TypeError`.
Castear na view agora é o que deixa `scheduler.desempenho()` pronto pra virar
endpoint depois sem reescrever nada — `chat.py stats --json` já imprime
exatamente o que a API vai servir.

**Cache de embeddings por hash de conteúdo.** Vetor é função pura de (texto,
modelo). Corrigir chunking passou a custar segundos em vez de minutos.

**Lógica em funções puras, efeito colateral na borda.** `chunking`,
`scheduler_regras` não tocam banco nem relógio — por isso `diagnostico.py` e
`simular.py` existem e rodam em milissegundos sobre o MESMO código de produção.

**Sincronização entre máquinas por arquivo no git, não por Postgres compartilhado.**
`sincronizar.py` exporta questões e tentativas para `dados/progresso.json`
traduzindo `chunk.id` para `(norma, artigo)` — o id é sequencial e MUDA entre
bancos; copiar a coluna crua faria a questão citar o artigo errado, calado.
A importação resolve `(norma, artigo)` de volta contra os chunks locais.
Resolve alternância entre duas máquinas de um usuário só; não resolve edição
simultânea (para isso, Postgres hospedado com `DATABASE_URL` compartilhado).

**Desafio diário é composição, não módulo novo.** `core/desafio.py` só decide
QUAIS questões entram em cada um dos três blocos (reincidentes do caderno de
erros, novas, mini-simulado); quem resolve de verdade é `chat._estudar_lista`
(extraído de `estudar()`) e `chat.simulado` (agora aceita lista pronta em vez
de sempre sortear). Estimativa de tempo vem de `avg(tentativa.segundos)` real,
não de um número chutado — sem histórico, cai num default documentado.
`_estudar_lista` devolve se o usuário pediu "sair", porque sem esse sinal o
desafio emendava o próximo bloco mesmo depois da pessoa dizer que ia parar.

**Edital vira dado real, não data digitada na mão — mas é MELHOR ESFORÇO
reportado, não contrato.** `core/edital.py` extrai data da prova e conteúdo
programático de um PDF de edital com heurística de texto (regex + pontuação
por proximidade de palavra-chave), porque layout de edital varia por banca e
não existe parser universal. `candidatos_data_prova()` devolve TODOS os
candidatos com pontuação, não só "a resposta" — mesmo espírito de
`diagnostico.py`: reportar pro operador conferir, nunca decidir calado.
`chat.py meta` sem argumento usa a data do edital mais recente; passar data
manual sempre vence (saída de emergência se a extração errou), e essa
correção também alimenta `probabilidade_fechamento()` — sem isso, corrigir
a data na mão deixaria a probabilidade calculando com a data errada do banco.

Duas aproximações DECLARADAS em `core/edital.py`, não escondidas: (1) sem
separação por cargo — concurso com mais de um cargo repete disciplina com
conteúdo próprio, os tópicos se somam num grupo só; (2) cobertura por
tópico é estimada por DISCIPLINA inteira (não há vínculo questão→tópico
individual no schema), assume dificuldade uniforme dentro da disciplina.

**"Probabilidade de fechamento" é extrapolação linear de ritmo, não modelo
estatístico.** `ritmo_atual = tópicos cobertos / dias estudando; ritmo
necessário = tópicos pendentes / dias restantes; probabilidade = min(100,
100 * atual/necessário)`. Não modela variância nem esquecimento — mesma
limitação já documentada em `simular.py`. Nomear isso de "probabilidade"
sem dizer a fórmula seria o mesmo erro de "48% dominadas" virar "a
ferramenta só acerta 48%" — por isso a fórmula fica no docstring da função,
não só na cabeça de quem escreveu.

**Intervenção proativa é regra, não o LLM decidindo quando falar.** O LLM já
resolve a conversa livre (`socratic.explicar`); decidir QUANDO interromper é
limiar sobre número (5 acertos seguidos, <50% de acerto, 3+ reincidências) —
pedir pro modelo julgar isso a cada questão custaria cota e mudaria de
sessão pra sessão sem ninguém pedir. `ritmo_regras.py` é puro, no mesmo
molde de `scheduler_regras.py`; `ritmo.py` busca os dados e prioriza.
Mostra no máximo UMA sugestão por sessão (reincidência > disciplina fraca >
sequência de acertos) — três avisos empilhados deixam de ser proativos e
viram ruído que o aluno aprende a ignorar. Disciplina fraca exige um mínimo
de tentativas antes de disparar, mesma lição do simulador: percentual sobre
amostra pequena é ruído, não tendência.

**Multiusuário: o acervo é COMPARTILHADO, o progresso é PESSOAL (migração
008).** `documento`/`chunk`/`questao` continuam sem `usuario_id` — é o
mesmo Código Penal pra todo mundo, e gerar questão custa cota de LLM; negar
reaproveitamento entre usuários pagaria a mesma pergunta N vezes. O que é
estado de quem estuda (`caixa`, `prox_revisao`) SAI de `questao` e vai pra
`progresso` (usuario_id, questao_id) — porque caixa é estado de QUEM
responde, não da pergunta, e dois usuários estudando o mesmo banco
compartilhado precisam de caixas independentes pra MESMA questão. Ausência
de linha em `progresso` é o sinal de "esta pessoa nunca tentou esta
questão" (antes esse sinal vinha de `tentativa` não ter linha; migrou pra
`progresso`, que é o dado que efetivamente muda). `tentativa`, `erro_caderno`
(PK virou composta), `simulado` e `edital` ganharam `usuario_id`.

**`v_desempenho_disciplina`: o denominador da cobertura é o acervo INTEIRO
da disciplina, não só o que o usuário já tocou.** Primeira versão da view
pós-migração partia de `progresso` (só linhas existentes) — um usuário que
respondeu 2 de 18 questões e dominou as 2 aparecia com 100% de cobertura.
Corrigido partindo de `questao` (CROSS JOIN com os usuários que têm
qualquer progresso) e trazendo `progresso`/`tentativa` como LEFT JOIN
escopado — `questoes` conta o universo compartilhado, `dominadas` conta só
o que ESTE usuário dominou. Achado revisando a própria migração antes de
aplicar, não em produção — mas do tipo de erro que só aparece com mais de
um usuário, que o dataset mono-usuário anterior nunca teria exposto.

**Autenticação é JWT stateless, não sessão em tabela.** `api.py` e
`chat.py` não compartilham processo nem memória; um token assinado
(`core/auth.py`, bcrypt pro hash de senha, PyJWT pra sessão) evita precisar
de mais uma tabela só pra sessão. Trade-off aceito: sem lista de revogação,
um token vazado vale até expirar (uma semana) — aceitável pra uso
pessoal/pequeno grupo, revisar se isso crescer.

**A CLI não loga — resolve um usuário fixo pelo email do `.env`.**
`chat.py`/`sincronizar.py`/`edital.py` (CLI) chamam
`auth.usuario_da_cli(CLI_USUARIO_EMAIL)`, que cria a conta (sem senha
usável) se não existir. Login de verdade com senha só existe pelo caminho
da API — é o único lugar que precisa disso, porque é o único lugar onde
"alguém que não é você" poderia estar do outro lado.

**`PATCH /me`/`DELETE /me` exigem a senha atual, mesmo já autenticado por
token.** Token roubado (mas não a senha) não deveria bastar pra sequestrar
a conta trocando e-mail/senha, nem pra apagá-la. Efeito colateral aceito: a
conta criada por `usuario_da_cli` (sem senha usável) não consegue trocar
senha por essa rota — ela nunca teria como chegar autenticada ali sem
senha alguma; ganhar login via API pra essa conta seria um fluxo
diferente (tipo reset), fora de escopo por ora.

**Mesa de estudo é FILTRO, não silo (migração 010).** Uma mesa é um
concurso-alvo: guarda o edital, a banca e o órgão. O que ela NÃO guarda é
progresso — `progresso`, `tentativa` e `erro_caderno` continuam escopados
por `usuario_id` e não ganharam `mesa_id`. A memória SM-2 é do ALUNO, não
do concurso: quem dominou o art. 312 estudando pra PC-PR sabe o art. 312 na
mesa da PF, e duplicar a caixa por mesa faria a mesma pessoa reestudar do
zero o que já sabe — o oposto do que repetição espaçada existe pra fazer.
O concurseiro real reaproveita Português/Constitucional entre editais o
tempo todo. O argumento decisivo contra o isolamento total foi outro,
porém: `questao` é acervo compartilhado e GLOBAL (migração 008), então sem
filtro por disciplina toda mesa mostraria o acervo inteiro de qualquer
jeito. Isolar por mesa seria esse mesmo filtro MAIS a duplicação do estado
de aprendizado; o filtro sozinho entrega o mesmo produto sem a duplicação.

As disciplinas da mesa não são coluna: saem de `topico.disciplina` do
edital MAIS RECENTE dela (mesmo "último" que `edital.mais_recente()` usa
pra meta — senão a data viria de um edital e o filtro de outro). Mesa sem
edital devolve `None` e NÃO filtra nada, que é exatamente o comportamento
anterior à 010. O predicado vive num lugar só (`core/mesa.filtro`) porque
"o que esta mesa cobre" precisa dar a mesma resposta na fila, no stats e no
simulado. Ele casa nos DOIS sentidos (`ILIKE` de cada lado) porque o nome
vem do edital por heurística de PDF ("Noções De Direito Administrativo") e
precisa bater com o do acervo, digitado na ingestão ("Direito
Administrativo").

Três números NÃO respeitam a mesa, de propósito, e é a mesma pergunta em
cada caso ("isso é do aluno ou do concurso?"): `ofensiva_dias` (hábito —
recortar quebraria a sequência de quem estudou nos dois dias em mesas
diferentes, punindo quem estudou mais), `tempo_medio_segundos` (velocidade
de resposta da pessoa) e a busca RAG de `socratic.explicar` (o aluno pode
perguntar de qualquer coisa; cortar o acervo pela mesa daria "não
encontrei" pra pergunta que o material responde). Só o resumo de
DESEMPENHO dentro do `explicar` é recortado.

Políticas de FK diferentes de propósito: `edital -> mesa` é CASCADE (o
edital É o conteúdo da mesa), `simulado -> mesa` é SET NULL (a prova já
feita é histórico de desempenho da pessoa, só etiquetado com a mesa —
apagar a mesa não deve sumir com ela). `edital.usuario_id` SAIU: o edital
pertence à mesa e a mesa ao usuário; manter as duas colunas seria
denormalização com risco de divergir.

**A mesa vem no header `X-Mesa-Id`, por requisição — não há "mesa ativa"
no servidor.** Estado de sessão no servidor faz duas abas abertas em mesas
diferentes brigarem pela mesma variável, e o aluno com dois editais abertos
ao mesmo tempo é o caso de uso normal, não a exceção. O header IDENTIFICA,
o `usuario_id` do token AUTORIZA: `mesa.obter()` filtra por usuario_id,
então pedir a mesa de outra pessoa dá 404 (não 403 — não confirma pra quem
chuta um id que ele existe e só não é dele), mesmo espírito de
`simulado.pertence_a()`. Sem header, cai na mesa padrão da conta
(`mesa.padrao`, a mais antiga, criada sob demanda como
`auth.usuario_da_cli`) — é o que mantém a CLI e qualquer cliente que ainda
não conhece mesas funcionando igual. Essa regra de fallback tem UM dono: o
servidor. `GET /mesa` devolve a mesa já resolvida pra requisição, e é o que
a sidebar e o raio-x leem — o cliente nunca recalcula "sem header, usa a
mais antiga", porque duas cópias da mesma regra divergem e o sintoma seria
a nav afirmar um nome enquanto a fila responde por outra mesa. No frontend,
o header sai de UM lugar (`chamar`/`chamarFormData` em `lib/api.ts`): se
cada tela precisasse lembrar de mandá-lo, a primeira que esquecesse leria a
mesa errada sem ninguém perceber. Na CLI o equivalente é `--mesa NOME`,
e nome desconhecido é ERRO, não fallback calado pra padrão: receber a fila
de outro concurso por causa de um typo é o tipo de falha silenciosa que
`--norma` explícito em `reingest.py` já evita noutro lugar.

**`ON DELETE CASCADE` consistente em toda FK pra `usuario` (migração 009).**
A 008 só deu CASCADE em `progresso`; as outras (`tentativa`, `erro_caderno`,
`simulado`, `edital`) ficaram RESTRICT por padrão do Postgres — inconsistência
descoberta ao testar com usuário descartável: apagar a conta de teste
travava num FK esquecido. Testar multiusuário sem isso exigiria apagar cada
tabela na mão, na ordem certa — a mesma classe de erro já documentada em
"Armadilhas de método" (lógica de limpeza ad-hoc é onde bug mora); um
`DELETE FROM usuario` limpo é o que permite testar com conta descartável
com confiança.

**`corpus/` (lei do Planalto) vai para o git; `acervo/` (material pago) não.**
Texto de lei não tem direito autoral no Brasil (art. 8º, IV da Lei 9.610).
Levar o texto resolve o bloqueio de rede corporativa de uma vez: reingerir
numa máquina nova não depende de baixar de novo.

**CF e ADCT são normas SEPARADAS, não uma "CF" só.** O Ato das Disposições
Constitucionais Transitórias reinicia sua própria numeração ("Art. 1º do
ADCT" ≠ "Art. 1º da CF" — são dispositivos diferentes, citados diferente na
prática). Ingerir os dois com `norma=CF` faria `chunk_artigo_idx` colidir
exatamente como o livro de histórico de emendas colidia — o mesmo defeito,
só que dentro de um documento por sinal legítimo. `corpus/cf.txt` (corpo
principal) e `corpus/adct.txt` são arquivos e `documento` distintos.

**`documento.tipo = 'historico'` existe pra material com múltiplas versões
do mesmo artigo (emendas, "Redação Anterior") sem forçar `chunk_lei()`
nele.** Cai em `chunk_generico()` — janela por parágrafo, sem tentar
extrair (norma, artigo). Perde citação exata por dispositivo, mas fica
disponível pra busca híbrida, e principalmente: não arrisca `art. X`
devolver a versão REVOGADA em vez da vigente. `ingest.py`/`reingest.py`
recusam automaticamente gravar como `--tipo lei` se a taxa de colisão de
artigo (`chunking.taxa_colisao_artigo`) passar de 5% — antes disso só um
`diagnostico.py` manual pegava esse tipo de problema, e só se alguém
lembrasse de rodar.

**Questão sob demanda: a IA cria do acervo quando o banco não tem
(`core/geracao.py`).** Até aqui a fila só servia o que já estava em
`questao`, e essa tabela só crescia por `gerar.py`, rodado à mão. O efeito
era GERAL, não de uma matéria: qualquer mesa cujo edital cobrisse
disciplina ainda não gerada abria vazia — TI, bancária, fiscal, e também
Direito Administrativo, que tinha 245 chunks da Lei 8.112 no acervo e ZERO
questão. O material estava lá; o modelo já sabia gerar questão a partir de
trecho de lei desde o começo. Faltava encanamento, não capacidade.

Sem tema, sorteia trecho ainda DESCOBERTO dentro do recorte da mesa ("minha
fila está vazia"); com tema, usa a MESMA `retrieval.buscar` do tutor, pra a
questão sair do trecho que fundamentou a conversa e não de outro. Nunca de
`tipo='historico'` — sem artigo não há proveniência, e pior: pode conter
redação REVOGADA.

A invariante NÃO foi afrouxada: questão cujo artigo não está no lote é
descartada, como sempre. `gerar.py` passou a CHAMAR `geracao.salvar` em vez
de manter a cópia dela — duas versões da regra que grava proveniência é
como elas divergem. E `documento_id`/`disciplina` saem do CHUNK casado, não
de parâmetro: lote montado por busca atravessa normas, e herdar a
disciplina de fora rotularia a questão errado — justamente o rótulo que a
mesa usa pra recortar a fila.

A questão gerada é GRAVADA no acervo compartilhado, não fica na tela: só
assim entra em `progresso`/SM-2 e volta pra revisão. `POST` e nunca
automático dentro de `/fila` — gasta cota e escreve no acervo; um GET que
gera faria cada refresh queimar cota. **409, não 500**, quando o acervo não
cobre a matéria: "não temos material" e "a IA falhou" pedem ações opostas
do aluno.

**Item CERTO/ERRADO é tipo de questão, não formatação (migração 012).** A
maior banca do país cobra assertiva binária, e o produto respondia "meu
acervo não traz itens nesse formato" — verdade sobre a tabela, mentira
sobre o sistema. `tipo` + `gabarito_ce BOOLEAN`, com **CHECK casada**:
"item C/E sem booleano" e "discursiva COM booleano" não podem existir, e
deixar isso pro código significaria que o primeiro caminho de escrita que
esquecesse a regra gravaria lixo calado (são vários: `gerar.py`,
`sob_demanda`, `sincronizar`). BOOLEAN e não 'C'/'E' em texto porque campo
livre aceita "Certo", "V", "verdadeiro" e espalha normalização de string
por quem consome. `gabarito` segue NOT NULL e passa a guardar a
JUSTIFICATIVA — sem ela o aluno acerta ou erra e não aprende nada.

**Múltipla escolha ficou de fora de propósito:** exige tabela de
alternativas, modelagem inteira e não uma coluna. Aceitar o valor no CHECK
sem ter onde guardá-las criaria questão gravável e não renderizável — falha
na tela do aluno em vez de falhar na hora de gravar.

Correção do item C/E é **em código, sem LLM** (`socratic.avaliar_questao` é
o dispatcher): a resposta é um booleano, e mandar isso pro modelo custa
cota, demora e introduz erro num julgamento que `==` faz sem errar. Num
simulado de 40 itens é a diferença entre 40 chamadas e nenhuma. O
dispatcher existe porque QUATRO caminhos corrigiam chamando `avaliar()`
direto (rota, simulado, desafio, CLI), e cada um que esquecesse o tipo
mandaria "C" pra ser comparado contra uma justificativa em prosa.

**Não há escada socrática no item binário**, e isso é decisão: qualquer
dica sobre uma assertiva de 50% É a resposta, e "tente de novo" vira cara
ou coroa com o gabarito garantido na segunda. Também não existe `parcial` —
metade de um booleano não é nada (e, até 02/10/2026, `parcial` DESCIA uma caixa em
`scheduler_regras`, punindo por um estado que o formato não pode ocupar).

Na geração, `_validar_ce` checa `isinstance(gabarito_ce, bool)` e não
veracidade: `if not gabarito_ce` descartaria TODO item ERRADO (False é
falsy) — metade do lote, e justamente a metade que dá valor ao formato.

**"Texto associado": o texto-base é registro compartilhado, não cópia
(migração 013).** A prova real raramente traz assertiva avulsa — um
texto-base é seguido de N itens que o julgam de ângulos diferentes.
Repetir esse texto dentro de cada `enunciado` quebraria três coisas: os
itens deixam de ser irmãos (a tela não sabe dizer "item 2 de 3"), o mesmo
texto vira N cópias que divergem quando uma for corrigida, e o SM-2
reapresenta a situação inteira pra revisar uma assertiva de duas linhas.
Coluna resolveria só a terceira — **o compartilhamento É a estrutura**, e
relação se modela com chave.

CASCADE deliberado: item cujo texto-base sumiu é ILEGÍVEL ("com base no
argumento acima" sem o argumento) e apareceria na fila de alguém. Órfão
silencioso é pior que apagar junto. `contexto_id` é NULLABLE porque item
avulso continua legítimo.

A série sai em UMA chamada, não uma por item: os itens precisam ser
coerentes entre si (mesma situação, mesmos nomes, ângulos diferentes), e
isso só acontece se o modelo os escrever de uma vez, vendo o texto que ele
mesmo criou. Item por item sobre contexto pronto produz repetição — o
defeito que o formato não pode ter.

**A banca decide o formato.** `geracao.tipo_da_banca` lê `mesa.banca`:
Cebraspe/CESPE gera item C/E. Treinar discursiva pra prova Cebraspe é
treinar o exercício errado — o formato tem um vício próprio (marcar Certo
sem ler a troca de prazo ou de "poderá/deverá") que só se treina
respondendo nele.

**Conversa persistida: o tutor lembra do turno anterior (migração 014).** O
problema era maior que "esquece a semana passada": não havia memória
NENHUMA. `POST /perguntar` recebia só a pergunta atual, o histórico vivia
no estado do React e sumia num F5, e o modelo nunca o via. Em uso isso
aparecia assim: o aluno respondia "qualquer um" e o tutor devolvia "qualquer
um de quê?" — ele não tinha a pergunta anterior. O padrão já existia
(`socratic.avaliar()` recebe turnos por parâmetro pelo mesmo motivo);
faltava aplicá-lo ao chat livre e ter onde guardar.

Duas tabelas e não JSONB: mensagem é a unidade que se pagina, conta e
busca; array em JSONB obriga a reescrever o documento inteiro a cada turno.
`mesa_id` é ETIQUETA com SET NULL — a conversa é do ALUNO (mesma decisão de
`progresso` na 010) e apagar a mesa não deve sumir com o que foi discutido.

**Janela de 8 turnos, e o motivo não é economia:** o prompt já carrega 6
chunks de lei (alguns com milhares de caracteres) e o resumo de desempenho.
Uma conversa de 40 turnos empurraria o MATERIAL — a parte que ancora a
resposta — pra fora da janela do modelo, e o tutor passaria a responder de
memória própria. Melhor esquecer o turno 1 do que esquecer o art. 37. As
fontes de turnos passados NÃO voltam pro prompt: são contexto de exibição
(reabrir a conversa ancorada); reinjetá-las faria o modelo citar
dispositivo recuperado pra outra pergunta.

A pergunta do aluno é gravada ANTES da chamada ao modelo: se o LLM cair,
ela fica registrada. Reabrir e não achar o que você mesmo escreveu é a pior
forma de perder confiança no histórico.

**O prompt do tutor sabe PARA QUE CONCURSO o aluno estuda.** Antes,
perguntado "o que tem no meu edital", ele jogava a palavra na busca e
devolvia a definição jurídica de "edital" na Lei 8.112 e no CPP — resposta
correta sobre a lei e completamente fora do que foi perguntado, porque o
prompt nunca dizia que existe um edital. Agora entram concurso, órgão,
banca e disciplinas. Só os NOMES das disciplinas, nunca os tópicos: o
edital da Dataprev tem 1015 e isso queimaria cota pra repetir o que a tela
já mostra melhor.

Junto veio o conserto de um **vazamento de rótulo**: uma resposta real
terminou com "...75.3% [DESEMPENHO REAL DO ALUNO]" — o modelo citou o NOME
DA SEÇÃO do prompt como se fosse fonte, porque cabeçalho em maiúscula
somado a "cite a referência entre colchetes" ficou ambíguo. Rótulo vazando
como citação é pior que citação errada: expõe o andaime e destrói a
confiança nas citações verdadeiras da mesma frase.

E o prompt NÃO manda o modelo escrever questão no chat. Uma versão
intermediária dizia "ofereça gerar, nunca diga que não tem como", e ele
passou a redigir múltipla escolha dentro da conversa — sem proveniência,
sem entrar no SM-2, num formato que o banco não tem. Agora ele encaminha
pro botão e explica por quê.

**Perfil de estudo em JSONB, e NÃO "vetor de perfil" (migração 015).** O
tutor sabia o desempenho e a conversa; não sabia COMO a pessoa estuda
(horas/dia, nível, turno), então tratava um iniciante de 1h igual a um
veterano de 6h. Essas três respostas já eram pedidas no onboarding desde o
protótipo e sumiam ao trocar de rota.

JSONB aqui pelo argumento INVERSO ao da 014: preferência não se pagina, não
se conta, não se busca — é lida inteira, toda vez, por um consumidor só (o
prompt), e o conjunto vai crescer por tentativa e erro. Quando um campo
precisar ser CONSULTADO, vira coluna.

Vetor seria o instrumento errado: "prefere exemplos de trânsito" é um fato
curto e literal, não um ponto num espaço semântico. Convidaria a buscar por
similaridade onde ler o texto resolve e, pior, abriria caminho pro modelo
INFERIR o próprio contexto — o oposto do princípio de que ele LÊ um resumo
calculado em código.

**Lista fechada de campos e valores, validada na escrita E NA LEITURA.** A
segunda é redundante hoje, de propósito: o destino desse texto é o prompt,
e o dia em que alguém gravar perfil por outro caminho (import, migração,
script) não pode ser o dia em que "nivel: ignore as regras acima" chega ao
modelo. Valor fora da lista é ignorado em silêncio — cliente desatualizado
e payload malicioso pedem a mesma resposta.

**A busca pesa o braço lexical mais que o semântico
(`retrieval.PESO_LEXICAL = 1.5`).** Não é gosto: é correção de um viés
MEDIDO contra chunks grandes. O art. 37 da CF tem 13.059 caracteres (média
do acervo: 1.245) e cobre concurso, licitação, teto e improbidade no mesmo
artigo; o embedding é a média disso, então "administração direta e
indireta" — que é o começo do caput — o encontrava em 83º no semântico
contra 3º no lexical. Entrando em uma lista só, o RRF o punha atrás de
chunks medianos presentes nas duas, e ele NÃO chegava ao contexto que o
tutor lê. Ampliar o pool de candidatos de 30 pra 200 não resolvia
(testado): o problema é a posição, não o corte.

1.5 é o MENOR valor que corrige (2, 3 e 5 não melhoram mais nada) — número
escolhido por maximizar a nota num gabarito de 32 casos seria ajuste ao
gabarito, não à busca. **O conserto de raiz continua sendo sub-chunk do
artigo gigante pro embedding**, mantendo o artigo como unidade de citação;
o peso compra o resultado sem reingestão, e o gabarito agora tem os casos
que denunciariam uma regressão.

`PESO_HISTORICO = 0.5` não mudou a nota e entrou assim mesmo: o livro de
emendas ocupava 4 das 6 vagas de "princípios da administração pública", uma
delas uma página de LEGENDA DE SÍMBOLOS. Vaga gasta com índice é contexto
que o modelo não tem pra responder — melhora que a métrica não vê.

**Orçamento de tempo no desafio: o "só tenho 20 minutos hoje".**
`desafio.orcamento_blocos` é FUNÇÃO PURA e o que ela codifica é uma decisão
de produto — a ORDEM do corte. Reincidentes ficam (é o que a pessoa erra de
novo e de novo, o que mais rende por minuto); novas vêm depois (material
inédito é o mais caro cognitivamente, sai antes numa sessão curta);
**mini-simulado cai primeiro e CAI INTEIRO** — simulado de 2 questões não é
simulado, e medida sobre amostra pequena é ruído, a mesma lição que já vale
em `ritmo_regras`. Cortar até virar enfeite é pior que cortar de vez.

O número de questões sai da velocidade REAL da pessoa
(`avg(tentativa.segundos)`), então 20 minutos de quem responde em 30s rende
mais que de quem responde em 120s. Prometer "10 questões em 20 minutos" pra
todo mundo seria número fixo onde existe medida.

**A intervenção proativa passou a INTERROMPER, não só sugerir.** As três
regras originais descrevem TENDÊNCIA (disciplina fraca há semanas, tema que
reincide) e cabem num aviso passivo. `sugestao_erros_seguidos` descreve o
estado de AGORA: três erros consecutivos é alguém batendo a cabeça neste
minuto, e continuar só produz mais erro e mais caixa zerada. O custo de não
interromper é assimétrico — um aviso ignorado custa uma linha de tela; dez
minutos errando em sequência custam a sessão.

Ela devolve DICT e não string, ao contrário das outras: interromper sem
oferecer pra onde ir é só atrapalhar, então vem com uma PERGUNTA PRONTA pro
tutor. Pedir pro aluno formular "o que estou errando?" no momento em que
ele acabou de errar três vezes é exigir energia justamente de quem já está
sem ela. O tema entra no texto só quando os três erros são do MESMO ponto:
"errou 3 seguidas" é observação, "errou 3 seguidas de peculato" é
diagnóstico. `parcial` conta como erro — tratá-lo como acerto faria a
interrupção nunca disparar pra quem erra "quase acertando", que é
exatamente quem mais precisa parar. E ela NUNCA bloqueia: "continuar mesmo
assim" fica ao lado, porque tutor que impede o aluno de estudar é pior que
tutor calado.

**A conversa registra o que o aluno FEZ, não só o que disse (migração
016).** A 014 deu memória do que foi DITO; faltava o que acontece ENTRE os
turnos. O tutor explicava peculato, gerava três itens, o aluno errava os
três — e a mensagem seguinte continuava explicando como se nada tivesse
acontecido. É a mesma cegueira da 014 um nível acima, e sobre a informação
mais valiosa da conversa: dizer "não entendi" é relato, **errar a questão é
evidência**.

`mensagem.autor` ganhou um terceiro valor, `'evento'`. Não dá pra
reaproveitar os dois que existiam: gravar "respondeu e errou" como fala do
ALUNO põe na boca dele uma frase que ele não escreveu; como fala do TUTOR,
inventa uma resposta que o modelo nunca gerou. As duas mentem justamente no
histórico que volta pro prompt e que o aluno relê na tela. No prompt o
evento entra rotulado `[fato da sessão]` — "(o aluno errou)" dito por
"Você" faria o modelo tratar aquilo como coisa que ele mesmo afirmou.

Não bastava o `_resumo_desempenho` que já ia no prompt: ele é AGREGADO
("73% em Constitucional, 111 tentativas") e um erro isolado some numa média
de 111 — mas é exatamente o erro isolado, recém-cometido, sobre o assunto
em discussão, que deveria mudar a próxima frase do tutor. Medido: depois de
errar uma questão de concussão gerada na conversa, a resposta seguinte
abriu com "Você errou a questão sobre concussão agora pouco, então vamos
direto ao ponto crítico".

**A questão gerada no chat é respondida NO CHAT.** Antes o botão fazia
`router.push("/fila")`: você pedia questão no meio de um raciocínio e era
jogado pra outra tela, e o que acertava lá não voltava pra conversa. As
questões continuam entrando na fila normal (são gravadas no acervo, como
sempre); o que mudou é ONDE se responde.

**Relevância manda mais que novidade na geração por tema.** Bug real,
achado na primeira conversa de verdade: pedir questão sobre PECULATO
devolveu uma sobre DESACATO, porque peculato já tinha questão e desacato
não. A ordenação era `(ja_tem, ranking)` — todo inédito à frente de todo
cobrado, que é "cobrar o artigo errado só por ser inédito", exatamente o
que o comentário do próprio código dizia evitar. Agora o 1º colocado da
busca entra SEMPRE (quando a busca é precisa — "art. 312", "concussão" —
ele É o assunto) e a novidade só ordena as vagas restantes, dentro de um
pool ainda relevante.

**Mesa sem edital tem TRÊS estados, não dois (migração 017).** Relatado em
uso: mesa recém-criada aparecia no lobby com "4 / 54 questões · 7%" e a
legenda "sem edital — mostra o acervo inteiro". O número é verdadeiro e
está no lugar errado — é o progresso da PESSOA no acervo todo, exibido num
cartão que promete o progresso DAQUELA mesa. Gaveta nova que já nasce
cheia.

**A correção NÃO foi "sem edital, escopo vazio".** Foi a primeira proposta
e ela quebra mais do que conserta: `mesa.filtro` com lista vazia não casa
nada, então fila, desafio, simulado, stats e meta ficam TODOS vazios — a
mesa vira inútil até alguém subir um PDF, e quem ainda não tem edital
publicado (metade do tempo de preparação de verdade) simplesmente não
conseguiria estudar. Trocar "número confuso" por "produto morto" não é
conserto. O problema também não era o filtro: era o CARTÃO afirmando ser
progresso de mesa um número que é do aluno, e isso se resolve na tela.

O que faltava era o estado "esta mesa TEM alvo, e não veio de PDF". Agora
`mesa.disciplinas()` tem três respostas, e `origem_alvo` diz qual é:

  · `edital`  — veio do PDF. TEM PRECEDÊNCIA sobre o manual: é o documento
                oficial e é dele que `scheduler.meta` tira a data da prova.
                Deixar o manual sobrepor faria o recorte vir de um lugar e
                o prazo de outro — o defeito que a 010 evitou ao fazer
                disciplina e data saírem do MESMO "último edital".
  · `manual`  — o aluno escolheu as matérias na mão, do que EXISTE no
                acervo. Nome livre viraria filtro que nunca casa nada, e o
                sintoma seria fila vazia sem explicação: o aluno acharia
                que o app quebrou, não que escolheu matéria inexistente.
  · `nenhum`  — ninguém declarou nada. Segue sem filtrar (a mesa é
                utilizável no dia 1), mas o cartão esconde barra e
                percentual e diz o que FAZER: anexar o edital, ou escolher
                as matérias no lápis.

`TEXT[]` e não tabela: lista curta, lida inteira, escrita inteira, nunca
consultada por item — o oposto de `topico`, que se conta e se agrupa.

**Onde o aprendizado é MEDIDO, e onde não é.** Vale ter isto explícito
porque é fácil supor errado: fila, `/questao/[id]`, desafio, simulado e a
questão embutida no /tutor passam TODOS por `scheduler.registrar` — logo
alimentam `tentativa`, `progresso` (SM-2), `erro_caderno`, desempenho,
ofensiva, tempo médio e a intervenção proativa. Medido com conta
descartável: um simulado de 4 questões subiu tentativa 0->4, progresso
0->4, caderno 0->4, ofensiva 0->1, tempo médio 90s (default) -> 40s (real),
e disparou a interrupção por erros seguidos.

O **chat livre NÃO registra nada disso** — e não deveria: conversar não é
responder questão, e contar conversa como tentativa inflaria acerto e
ofensiva sem ninguém ter sido avaliado. Ele é CONSUMIDOR dos insights
(`_resumo_desempenho` entra no prompt), não produtor. A única coisa que ele
grava é a própria conversa (014).

Mas a QUESTÃO respondida dentro da conversa registra normalmente, como
qualquer outra — e desde a 016 registra DUAS vezes: em `tentativa`/
`progresso` (o aprendizado, igual à fila) e como evento na linha do tempo
da conversa (o contexto, pro tutor considerar no próximo turno). São coisas
diferentes e nenhuma substitui a outra.

**Biblioteca do aluno: o acervo passa a ter DONO opcional (migração 019).**
Até aqui `documento` era só material público (lei do Planalto), e o aluno não
tinha como alimentar o tutor com o PDF do curso que ele pagou. A alternativa
teria sido uma tabela nova (`material`, `material_chunk`) — e ela duplicaria
chunking, embedding, cache e busca híbrida pra chegar no mesmo lugar. Uma
COLUNA `usuario_id` nullable em `documento` reaproveita tudo: `NULL` é o acervo
público de sempre, preenchido é material de UM aluno.

O preço dessa escolha é que o predicado de dono tem que estar em TODA busca, e
não no código que chama: `retrieval.DONO = "(d.usuario_id IS NULL OR
d.usuario_id = %(uid)s)"` entra DENTRO das CTEs de `por_dispositivo`,
`por_rubrica` e `hibrida`. Filtrar depois de rankear seria pior que não filtrar:
o material de outro aluno gastaria vaga no top-6 e sairia da lista, então a
pergunta perderia contexto sem ninguém ver por quê. `usuario_id=None` é o
default e devolve só público — a CLI e qualquer chamador que ainda não conhece
biblioteca continuam vendo o que sempre viram, e o vazamento exige um
`usuario_id` explícito, não um esquecimento. Medido com dois alunos e um
mnemônico inventado: o dono ACHOU, o outro não, a CLI não.

`geracao.py` NÃO recebe `usuario_id`, e isso é decisão, não esquecimento:
`questao` é acervo COMPARTILHADO (008), então questão gerada de material pago
de um aluno seria distribuída pros outros. O tutor pode LER o material privado
pra explicar; o gerador não pode COPIÁ-LO pra dentro de uma tabela pública.

**Indexar é `BackgroundTasks`, com o progresso no BANCO.** O embedding roda
local na CPU (decisão de "Pilha") e um PDF de curso leva minutos — não cabe num
request. `status`/`chunks_total`/`chunks` em `documento` e não em memória porque
o aluno dá F5, fecha a aba e volta depois; progresso em memória perderia
exatamente o PDF que ele já subiu. `indexar()` é IDEMPOTENTE (`DELETE FROM
chunk WHERE documento_id` antes de inserir) — provado com 3 execuções seguidas,
sem duplicar trecho: sem isso o botão "tentar de novo" dobraria o material.

**Disciplina é OPCIONAL e quem descobre é o classificador (migração 020).**
Obrigar a rotular é obrigar a LER antes de subir, e o caso que mais importa é
justamente o material que a pessoa não conhece ("joguei lá, não sei se
agrega"). `assunto` entrou junto porque disciplina sozinha não distingue a aula
3 da aula 11 de um mesmo curso, e `classificado_por` existe pra tela pedir
conferência SÓ no palpite — o que o aluno digitou não precisa de aviso, ele
sabe o que escreveu. O classificador NUNCA sobrescreve rótulo do aluno, e roda
FORA do `try` da indexação: uma falha de rótulo marcando como `falha` um
material inteiramente indexado seria mentir sobre o que aconteceu.

**Lote: os campos valem pros N arquivos, e um arquivo ruim não derruba os
outros.** "Opcional" resolvia metade do problema — subir 14 aulas ainda era 14
idas ao seletor de arquivo. O envio é SEQUENCIAL de propósito: o servidor
indexa em background no próprio processo, então disparar 14 de uma vez não
termina mais rápido, só some com o progresso ("3 de 14") e concorre por CPU com
o embedding que já está rodando. E quem escolheu 14 não deveria reenviar 13 que
já entraram por causa do que falhou — os que falharam são NOMEADOS no fim,
porque "3 falharam" sem dizer quais é um erro que não dá pra agir.

**O seletor de rótulo é `<datalist>`, não `<select>`, e a fonte tem um botão.**
A lista é DICA, não domínio fechado: `<select>` seria o componente errado
(recusaria matéria nova) e um combobox caseiro reimplementaria teclado, foco e
"aceita valor de fora" pra chegar onde o navegador já está. As sugestões saem de
`GET /materiais/sugestoes`, e só da biblioteca de QUEM pergunta — oferecer a
disciplina que outro aluno cadastrou vazaria o que ele estuda, num campo que
parece inofensivo. O botão troca a fonte da DISCIPLINA entre as matérias da
mesa (edital, 011, ou alvo manual, 017) e o que o aluno já usou aqui; fica
desabilitado DIZENDO POR QUÊ quando a mesa não declarou matérias, em vez de
ligar e não sugerir nada. Vem LIGADO quando há alvo, porque usar a grafia do
edital faz a biblioteca agrupar com o mesmo nome que o plano de estudo usa.
ASSUNTO só tem sugestão com o botão desligado: o alvo da mesa não tem assunto
pra oferecer — tem disciplina e tópico, e tópico é outra coisa (o edital da
Dataprev tem 1015; uma datalist com isso não é sugestão, é um documento).
Dentro da biblioteca, prefere os assuntos DA disciplina escolhida
(`assuntos_por_disciplina`): oferecer "Remédios constitucionais" a quem digita
Contabilidade é ruído. No lápis de cada linha não há botão — corrigir um rótulo
é ação sobre a biblioteca, e fazer a correção depender de um modo que está no
outro canto da tela esconderia metade das grafias possíveis.

**Link indexado resolve o DNS antes de baixar (SSRF).** O pedido sai de dentro
da rede do servidor, então "cole uma URL" é uma primitiva de requisição
arbitrária se ninguém olhar. `material.baixar` resolve o nome, exige
`ipaddress.is_global` em todos os endereços e REVALIDA a cada redirecionamento
— redirect é o furo clássico: o domínio público responde 302 pra
`169.254.169.254`. Verificado contra `127.0.0.1`, `localhost`,
`169.254.169.254`, `10.0.0.5` e `file://`. O que isso NÃO é: allowlist de
domínio. Endereço público que serve conteúdo hostil continua aceito, e a tela
diz o limite ANTES de a pessoa colar e falhar.

**A consulta de busca não é a mensagem: a 014 deu memória ao MODELO e deixou
o BUSCADOR amnésico (`core/assunto.py`).** O prompt passou a receber 8 turnos;
`retrieval.buscar` continuou recebendo a frase isolada. E `hibrida()` é
k-vizinhos, sem piso de relevância — frase sem assunto não devolve vazio,
devolve 6 artigos com confiança total. Relatado com log de conversa real: o
aluno conversou a sessão inteira sobre eficácia das normas constitucionais,
escreveu "vamos", clicou em "quero questões sobre isto", e recebeu CP art. 352
(evasão mediante violência) e CF art. 200 (SUS) — porque a tela mandava a
ÚLTIMA FALA como tema e rodou `buscar("vamos")`. Reproduzido byte a byte antes
de consertar.

O mesmo cano no chat: no turno em que ele escreveu "você deveria perguntar se
eu já sei algo do assunto... melhor me explicar", voltaram CPP 188/190/203/212
— os artigos de INTERROGATÓRIO. A busca acertou as palavras e errou a matéria.
E a prova de que o retriever está são está no mesmo log: no turno com "eficácia
limitada existem 2 tipos" ele trouxe a apostila certa seis vezes. **Turno com
assunto acerta; turno curto ou meta devolve lixo** — por isso `retrieval.py`
NÃO foi tocado e o gabarito do `avaliar_retrieval.py` segue valendo.

`em_foco()` é REGRA, não LLM (mesma escolha de `ritmo_regras`): extrair tema
por modelo custaria a cota mais escassa e 1-2s em TODO turno, e resposta de
modelo não se trava em teste. Enriquece ENQUANTO a consulta está fraca e para ao
ter assunto (`CONTEUDO_SUFICIENTE`) — contar turnos não serve pros dois casos:
"queria saber como a fgv cobra" precisa de dois reforços pra alcançar "eficácia
limitada", e dois reforços numa conversa que migrou de Penal pra Constitucional
trazem PECULATO de volta. Citação de dispositivo vai CRUA, e é a exceção que
mais importa: `por_dispositivo` lê o número da própria string, então enriquecer
deixaria um "art. 140" de três turnos atrás sequestrar a pergunta nova.
`MIN_CONTEUDO = 1` por assimetria de erro — exigir 2 descartaria "matar alguém"
da consulta inteira. Ficam FORA de `VAZIAS`, de propósito, "direito", "penal",
"norma", "prazo", "pena" e "tipo": parecem genéricas e são o nome de metade das
disciplinas.

O tema da geração é derivado NO SERVIDOR (`POST /questoes/gerar` já recebia
`conversa_id`): "sobre o que é esta conversa" é regra, e regra com duas cópias
diverge — mesmo argumento que fez a mesa padrão ser resolvida no servidor.

**Quem tem a INICIATIVA do turno decide o assunto, e contar palavras não decide
nada (`assunto-v3`).** O `CONTEUDO_SUFICIENTE` acima resolveu o "vamos" e
produziu o pior resultado que este produto já deu, relatado com log real: uma
conversa de dez minutos INTEIRA sobre Lei Maria da Penha gerou duas questões de
Direito Administrativo — L8112 art. 55 (ajuda de custo) e art. 94 (mandato
eletivo). A consulta era

    'dependencia? não impede sim desde que haja vinculo ou afeto'

as três últimas respostas do aluno costuradas. Quatro palavras de conteúdo, a
contagem parou porque tinha quatro — e as quatro caem em pensão e ajuda de custo
do estatuto do servidor. **A contagem estava certa; o que ela contava não era
assunto.** "Lei Maria da Penha" estava no SEGUNDO turno e nunca entrou.

Limiar de tamanho não conserta, e isso foi MEDIDO nas duas direções: com
`FRAGMENTO = 3`, "me explica eficácia limitada" (2 palavras de conteúdo) é
classificada como fragmento e o tutor arrasta assunto abandonado de volta; com
`FRAGMENTO = 2`, "vinculo afeto" passa por assunto e o defeito continua.
`eficácia limitada` e `vinculo afeto` têm o MESMO tamanho, um é assunto e o
outro não — não existe ponto de corte entre eles. Duas tentativas, as duas
trocando uma falha por outra, as duas revertidas.

O que separa é ESTRUTURAL e a 014 já guardava de graça: num diálogo socrático o
aluno RESPONDE em pedaços, e o assunto é dito uma vez, no começo. A pergunta
certa não é "esta fala é grande?", é "esta fala é INICIATIVA ou RESPOSTA?". O
tutor detém a iniciativa enquanto está perguntando; o aluno a retoma com um
pedido explícito (`pede_assunto`: citação de dispositivo ou verbo da lista
`PEDIDO`). Sendo resposta, a consulta é o turno do TUTOR — que é onde o assunto
está escrito por extenso.

**Novidade lexical foi tentada primeiro e é a ideia que mais parecia certa:** "é
eco se não acrescenta nenhuma palavra de conteúdo além das que o tutor acabou de
usar" — sem limiar, sem lista, puro. Cai em 3 das 6 respostas do log real
('dependencia?' traz `dependencia`, 'sim desde que haja vinculo ou afeto' traz
`vinculo`/`afeto`). O motivo é óbvio depois de ver: **responder a uma pergunta
de conhecimento É dizer a palavra que o tutor não disse** — era exatamente o que
ele estava perguntando ("qual o critério, além da coabitação e do vínculo de
afeto?"). Novidade lexical mede ACERTO do aluno, não iniciativa.

E a condição estrutural não pode ir sozinha, embora seja a mais limpa: o prompt
manda o tutor terminar TODA resposta com pergunta, então quase todo turno do
aluno vem depois de uma, e tratar todos como resposta tira dele a capacidade de
trocar de assunto — o defeito oposto, igualmente ruim, travado em
`test_aluno_retoma_a_iniciativa_e_troca_de_assunto`. A lista `PEDIDO` é a
ESCAPATÓRIA, não a regra: quem carrega a decisão é a estrutura do turno.

Uma armadilha de método no meio disto, que vale mais que o conserto: a primeira
validação "passou" nos sete turnos porque eu comparei cada fala do aluno com o
turno do tutor **seguinte** — o que repete a resposta de volta ("Exato, a unidade
doméstica ou a **dependência econômica**..."). Circular, e indisponível na hora
de decidir. As falas literais viraram fixture (`MARIA_DA_PENHA` em
`tests/test_assunto.py`), lidas do próprio banco, não reescritas de memória.

**A citação de fonte do tutor não pode ir pra busca (`_sem_citacao`).** Defeito
que só apareceu DEPOIS de o primeiro ser consertado, e mediu-se pior que ele: o
tutor fecha a resposta com "[Lei Maria da Penha, art. 5º, II e III]" — lei que
NÃO está no acervo — e citação dentro da consulta faz `retrieval.buscar` trocar
busca semântica por dispositivo EXATO. Voltou o art. 5º de tudo o que existe:
ADCT, CF, territorialidade do CP, inquérito do CPP, requisitos de investidura da
8.112. Cinco artigos sem nada em comum além do número, e com cara de acerto
porque o número bate. Vale só no caminho herdado: citação escrita pelo ALUNO
continua indo crua, porque ali ela É o pedido. Com o conserto, a mesma conversa
devolve crimes contra a família, crimes contra a liberdade individual e CF art.
226 — o acervo não tem a Maria da Penha, e isto é o mais perto que ele chega.

**CEMITÉRIO DE IDEIAS: piso de relevância vetorial não funciona neste acervo sem
cross-encoder.** A causa-raiz dos dois defeitos acima é uma só: `hibrida()`
devolve 6 chunks SEMPRE, então consulta sem assunto vem com confiança total. A
correção óbvia é a que qualquer um proporia — distância de cosseno máxima na
query do pgvector, e `[]` quando o melhor vizinho estiver além do limiar. Foi
medida contra um gabarito de casos cobertos e não cobertos pelo acervo, e NÃO
FUNCIONA. Números, pra ninguém ter que repetir:

| método | coberto pelo acervo | NÃO coberto |
|---|---|---|
| distância absoluta do 1º vizinho | 0,1101 – 0,1797 | 0,1382 – 0,2013 |
| razão d1/d20 (achatamento da vizinhança) | mín 0,5213 · p50 0,8817 · máx 0,9694 | mín 0,8732 · p50 0,9400 · máx 0,9599 |

As faixas se SOBREPÕEM nos dois métodos. Pior: "violência doméstica contra a
mulher" (0,1382), que o acervo não cobre, fica MAIS PERTO que "peculato"
(0,1797), que ele cobre em cheio — qualquer corte que barre a primeira barra a
segunda. A razão d1/d20 separa as MEDIANAS e não as faixas; dos 3 casos cobertos
acima de 0,94, dois são citação de dispositivo (respondidos por
`por_dispositivo`, que nunca chega em `hibrida`) e o terceiro é o art. 5º da CF,
o artigo monstro que o gabarito já sinaliza. Sobra separação para 1 caso.

O motivo é o modelo, não o corte: `multilingual-e5-base` comprime texto do mesmo
domínio: lei brasileira contra lei brasileira fica tudo perto, e a distância
absoluta quase não carrega sinal de COBERTURA. Quem resolveria é um
cross-encoder reordenando os 20 primeiros — outro modelo, outro custo de CPU por
turno, e decisão que não se toma sem medir latência. **Enquanto isso, a defesa é
a consulta ser boa, não o corte ser bom** — foi por isso que o conserto foi em
`assunto.py` e `retrieval.py` não foi tocado.

Se alguém for reabrir isto: o gabarito e o script de medição são reprodutíveis
por `avaliar_retrieval.py` + a lista de casos não cobertos; derrubar esta decisão
exige MEDIÇÃO nova, não argumento (regra da casa).

**A escada pedagógica é ORDEM no prompt, não intenção.** Relatado no mesmo log:
o tutor empurrou "Quero questões sobre isto" nas três primeiras respostas e o
aluno teve de pedir aula. Nada mandava vender — mas "termine com uma pergunta ou
sugestão que ajude o aluno" somado a um parágrafo enfático sobre COMO oferecer o
botão produz isso: a instrução de formato mais específica ganha do objetivo
vago. Agora o prompt diz descobrir -> explicar -> testar, com exceção permanente
se o aluno PEDIR questão, e o fecho é o PRÓXIMO DEGRAU em vez da mesma oferta
(três mensagens com o mesmo convite é ruído que se aprende a ignorar — mesma
lição de `ritmo` mostrar UMA sugestão por sessão). "Assunto novo" virou FATO
calculado em código: conversa sem histórico entra como "Primeira mensagem desta
conversa", senão conversa vazia é indistinguível de histórico que não veio.

**O que o aluno CONFUNDE não é o que ele erra (migração 022).**
`ESQUEMA_AVALIACAO` pedia `conceito_faltante` ao modelo desde sempre, o Gemini
preenchia em toda avaliação, o campo atravessava a API e estava tipado no front
— e era DESCARTADO. Já pago e jogado fora. `erro_caderno.tema` não substitui:
guarda `questao.tema`, o rótulo da PERGUNTA escolhido por quem gerou a questão.
É a diferença entre "errou a questão de peculato culposo" e "confunde extinção
da punibilidade" — medido com o modelo real, nas duas linhas do mesmo prompt.

Vai em `tentativa` e não em `erro_caderno` porque `tentativa` é o FATO e
`erro_caderno` o agregado: a mesma questão errada duas vezes pode faltar coisa
diferente em cada uma, e é essa mudança que mostra evolução. NULLABLE porque
item C/E é corrigido em código (012) e não produz conceito — `DEFAULT ''` faria
"não houve modelo" ficar igual a "o modelo não achou nada".

**Texto de LLM voltando pro prompt de LLM é input sujo, e a defesa é em código.**
Lista fechada não cabe (conceito é livre por natureza), então: `conceito_limpo`
COLAPSA quebra de linha — é a quebra que transforma campo de dado em bloco de
instrução dentro do prompt (`confunde X` + linha em branco + `### Instrução:
ignore as regras acima` chegaria como duas seções) —, CHECK de 160 no banco pra
que um segundo caminho de escrita não passe calado, e no prompt ele entra ENTRE
ASPAS e com autoria ("apontado pela sua própria correção"), nunca como fato do
sistema no meio de números do banco. E **nunca** vai pro `usuario.perfil`: esse
campo é lido inteiro e literal pelo prompt, e fechar esse laço deixaria o modelo
instruir a si mesmo no turno seguinte. Há teste que trava isso.

Agrupamento por string exata (minúsculas) + disciplina, com mínimo de 2
ocorrências — apontado uma vez é observação, e a lição de `ritmo_regras` sobre
amostra pequena vale aqui igual. Medido: duas avaliações reais da MESMA questão
devolveram a MESMA string ("Extinção da punibilidade"), porque o campo é curto e
o modelo escreve um NOME de conceito, não uma frase. Agrupar por similaridade
(embeddings) seria o conserto de raiz e não vale antes de o agrupamento ruim
doer.

**Migração tem UM mecanismo, e ele deixa registro (023).** Antes eram dois
sem registro nenhum: o `docker-entrypoint-initdb.d` (roda tudo, em ordem
alfabética, uma vez na vida do volume) e a mão humana. `git pull` numa máquina
já usada não aplicava nada, e o CLAUDE.md compensava isso com uma convenção
escrita — que é o que se faz quando a ferramenta não resolve.

O mount do initdb SAIU do `docker-compose.yml`, e isso é a parte central do
desenho, não limpeza. Com os dois vivos, `migrar.py` não teria como distinguir
"banco novo que o initdb preencheu inteiro" de "máquina atrasada onde só parte
rodou": os dois estados são indistinguíveis olhando o banco, e adivinhar errado
significa pular migração calada ou explodir no primeiro `ADD COLUMN`. Matar o
segundo mecanismo é o que torna a pergunta respondível.

**O estado do meio MEDE, em vez de perguntar (migrar-v2).** A 023 fazia banco
com dados e sem livro-razão PARAR, oferecendo `--adotar` ou `down -v`. O caso
real apareceu na máquina de trabalho e as duas respostas eram erradas: o banco
estava atrasado (faltavam 018_edital_cargo, 019_material_do_aluno, 020, 021,
022), então `--adotar` pularia cinco migrações caladas — exatamente o silêncio
que o livro-razão veio apagar — e `down -v` perderia 6 mesas, os editais e as
conversas, que `sincronizar.py` NÃO exporta. Havia uma terceira saída que não
era supor: MEDIR. `SONDAS` em `migrar.py` pergunta ao banco, por migração, se o
efeito principal dela está presente (a coluna existe? o CHECK cita 'evento'? a
FK é CASCADE?); registra as presentes e aplica só o resto.

Medir não é supor, e a diferença é verificável: a sonda erra pro lado barato.
Dizer "falta" o que já existe estoura no `ADD COLUMN` duplicado e a transação
por migração devolve tudo; dizer "já tem" o que falta é o caro, e por isso a
sonda aponta pro objeto que a migração existe pra criar, nunca pra um detalhe
periférico. Migração sem sonda faz o script voltar a parar e perguntar — a
resposta honesta pra pergunta que ele realmente não sabe. Arquivo novo não
precisa de sonda: a partir da 023 quem responde é o livro-razão.

A ORDEM importou e o teste pegou: a sonda da 023 é a existência da tabela
`migracao`, e medir DEPOIS de `CREATE TABLE IF NOT EXISTS` fazia ela medir o
que o próprio script acabara de criar — 023 sempre "aplicada", `COMMENT` nunca
executado. Mede-se tudo antes de criar o livro-razão.

Validado nos três estados num banco descartável: vazio aplica as 25; em dia sem
livro-razão registra 25 e aplica 0; atrasado sem livro-razão (o caso real,
reproduzido derrubando as colunas) registra as 20 presentes e aplica as 5 que
faltavam.

**Transação por migração**, com o registro no livro-razão DENTRO dela — o banco
nunca fica com a migração aplicada e não registrada, nem o contrário. `core/db.py`
é `autocommit=True` (certo pro app, inútil aqui): é a armadilha que o
`reingest.py` documenta, DELETE antes de validar o INSERT e nada pra reverter.
Provado com migração que falha no meio: a tabela criada na linha 1 não ficou.

**Chave é o NOME do arquivo, não o número:** os 018/019 estão duplicados em
`db/` (018_edital_cargo + 018_simulado_resumavel, 019_material_do_aluno +
019_simulado_nome) e chavear por número perderia metade do histórico. A ordem é
o nome ordenado — a mesma que o initdb usava por SORTE, agora escrita e visível
em `--listar`.

**Checksum do que foi aplicado, com AVISO se o arquivo mudou depois.** É a lição
do `documento.hash` do CP, que ficou dias desatualizado porque o corpus mudou
após a ingestão e nada comparava. Avisa e não corrige: corrigir exigiria
adivinhar o que a edição pretendia.

Verificado criando um banco descartável e aplicando as 25 do zero: schema
**idêntico** ao migrado à mão — 140 colunas, 1 view, 52 constraints, zero
diferença. Que é também a prova de que nenhuma migração foi pulada ou aplicada
fora de ordem na máquina de trabalho.

**Token válido de conta que não existe é 401, não 500 (auth-v4).** Relatado em
uso, com traceback: uma conta descartável foi apagada, o navegador seguiu com o
token dela, e a primeira rota que tentou gravar (`mesa.padrao` -> `criar`) morreu
em `ForeignKeyViolation: Key (usuario_id)=(252) is not present in table
"usuario"`. O token estava perfeitamente válido — assinado por nós, dentro do
prazo, apontando pra ninguém.

O contrato antigo era pior que errado, era INCONSISTENTE: `/me` devolvia 404 (só
porque aquela rota por acaso busca o usuário) e todas as outras estouravam 500. E
nenhum dos dois leva a pessoa ao login, porque o front reage a **401** fazendo
`sair()` + redirect — com 404 ou 500 ela fica presa numa aplicação quebrada, e o
único jeito de sair é limpar o `localStorage` na mão.

A guarda mora em `usuario_id_do_token`, que é o gargalo por onde TODA rota
autenticada passa — não num `except ForeignKeyViolation` por rota, que é como
metade delas ficaria de fora. Custa uma busca por chave primária por requisição,
ao lado das várias que qualquer rota autenticada já faz. A mensagem é a mesma de
token inválido, de propósito: dizer "essa conta foi apagada" confirmaria pra quem
tem um token roubado que o id existia (mesmo espírito do 404-e-não-403 de
`mesa.obter`).

Havia um teste fixando o 404, e ele foi reescrito COM O MOTIVO no corpo — não
silenciosamente. É a segunda vez que um teste deste projeto guardava um contrato
que o uso real provou errado (a primeira foi `test_mesa_api.py` na 021).

**Terceira vez (migrar-v2):** `tests/test_simulado_api.py` inteiro ainda
chamava `POST /simulados/{sid}/respostas`, a rota de lote único que a 018
substituiu por `responder` + `finalizar`. Três testes falhavam com 404 — e um
QUARTO passava por acidente, porque ele espera 404 pra usuário errado e rota
inexistente devolve 404 igual: verde sem testar nada, que é pior que vermelho.
Reescritos contra o contrato atual, com o motivo no corpo. A lição é sobre o
sinal, não sobre simulado: teste que afirma um NEGATIVO (404, recusa, lista
vazia) precisa bater numa rota que existe, senão ele confirma a própria
ausência.

**SINCRONISMO TOTAL: o estado viaja num ref próprio, e o git chama os dois
lados sozinho.** O pedido era "push em casa, pull aqui, e o sistema vem 100%,
sem rodar mais nada". O que existia (`sincronizar-v2`) levava três tabelas
(`questao`, `progresso`, `tentativa`) de UM usuário, e o passo manual não era
detalhe: ninguém rodou `exportar` antes do push, o pacote no repositório era de
dez dias antes, e o `importar` reaplicou o estado velho sem nada errado
acontecer. Automação que depende de lembrar não é automação.

Três decisões, e as três foram tomadas depois de MEDIR em repositório de teste
— nenhuma é preferência de estilo:

1. **O pacote passou a ser multiusuário.** O v2 exportava o
   `CLI_USUARIO_EMAIL`, e o caso real é a CLI usar um email e a TELA outro: as
   três mesas, 51 progressos e 188 tentativas da conta do frontend nunca
   viajaram, e o `importar` escrevia num terceiro usuário. Agora toda linha
   pessoal aponta pro EMAIL do dono, e cada referência viaja por identidade
   natural (mesa pelo nome dentro da conta, documento pelo hash do arquivo,
   simulado e conversa pelo instante, questão pelo sha do enunciado). Nenhum
   id sequencial atravessa — é a mesma armadilha que `(norma, artigo)` já
   resolvia pra `fonte_chunks`, aplicada ao resto.

2. **O estado NÃO vai no branch de código; vai em `refs/heads/estado`.** A
   primeira versão commitava `dados/progresso.json` no `develop`, e dois
   defeitos apareceram no teste:

   · push sem commit de código não levava nada — e esse é o caso mais comum de
     todos, porque você estudou, não programou. O hook precisa CRIAR um
     commit, e commit criado dentro do `pre-push` não entra no push em
     andamento: o git já resolveu os refs antes de chamar o hook.
   · empurrar o mesmo ref por dentro do hook mata o push original com
     `cannot lock ref 'refs/heads/main' / failed to push some refs`. Vermelho
     na cara de quem só queria enviar código. Reproduzido, não suposto.

   Num ref separado os dois desaparecem: o `pre-push` monta o commit de estado
   com `hash-object` + `mktree` + `commit-tree` e empurra `estado:estado`, o
   push de código segue intacto, e o JSON não existe no branch de trabalho —
   então nunca dá conflito de merge, que era o outro custo previsível (700 KB
   reescritos dos dois lados a cada pull). O push interno leva `--no-verify`:
   sem isso ele chama este mesmo hook, e o teste travou até o timeout.

3. **O `importar` do hook é dividido em duas fases, e a razão é tempo de
   relógio.** Import inteiro numa transação: **1m21s → 4,0s**. O gasto não era
   CPU (1,9s de `user` contra 20s de `sys`) — era um fsync por insert, porque
   a conexão do projeto é autocommit e são ~1100 inserts pequenos. E o
   embedding do material do aluno passa de **2 minutos** pra 240 trechos, que
   é inaceitável dentro de um `git pull`: fase 1 é o dado relacional e volta em
   segundos, fase 2 vai pro background com log em `.logs/estado.log`, e o
   material fica `processando` — estado que a biblioteca já sabe desenhar.
   Automação que trava o terminal por dois minutos é automação que a pessoa
   desliga na terceira vez.

**Importar é UNIÃO, nunca substituição** — é isso que torna seguro rodar a cada
pull: identidade natural em todo insert, então rodar duas vezes não duplica
(medido: segunda passada dá 0 novas, 0 tentativas, material já em dia) e o que
existe só de um lado não é apagado. Onde os dois lados podem discordar, o local
ganha e o pacote só completa o vazio: senha trocada aqui não é sobrescrita,
perfil preenchido aqui não é sobrescrito, mesa editada na tela não perde
`orgao`/`banca`. A única exceção é `erro_caderno`, que é DERIVADO das
tentativas e por isso é recalculado por usuário — nunca copiado.

**O material do aluno viaja como TEXTO, e isso é uma troca declarada.**
`acervo/` está fora do git por direito autoral, e `documento.origem` guarda só
o nome do arquivo — então material do aluno só poderia viajar levando o PDF
(contra a decisão do `.gitignore`) ou levando os chunks já extraídos. Vão os
chunks: é o que o RAG usa, e a outra máquina recalcula o embedding em CPU local
sem precisar do arquivo. A consequência tem que estar dita: o TEXTO do material
passa a ficar no repositório (privado). Quem não quiser:
`exportar --sem-material`, e aí a linha do documento chega marcada `falha` em
vez de mentir que está indexada. Chunk de LEI continua não viajando — é
derivável de `corpus/`, que está no git, e o `ingest.py` recria igual.

**`core.hooksPath` é config LOCAL: não viaja no clone.** Por isso quem instala é
o `setup.sh`, que toda máquina roda de qualquer jeito, e não uma instrução de
README — que a gente segue na primeira máquina e esquece na segunda. É a mesma
lição da migração 023 (commitar não aplica), agora aplicada ao hook.

**RODAPÉ SE DETECTA POR REPETIÇÃO, MAS MOBÍLIA TEM DE TER MAIS DE UMA PALAVRA.**
`_tirar_mobilia` apagava toda linha repetida 4+ vezes com até 60 caracteres — a
heurística certa para cabeçalho e rodapé, que mudam a cada banca e não se
detectam por conteúdo. O que ela não previa é PDF que extrai **uma palavra por
linha**, e o `Edital PC-PR 2026.pdf` é assim (pypdf devolve `Histórico\n \n
importância\n \npara\n \no\n \nDireito.`).

Medido: das 245 linhas classificadas como mobília nesse edital, **245 eram de uma
palavra só** — "de" (360x), "e" (343x), e também conteúdo puro: "Lei" (93x),
"Crimes" (47x), "Direitos" (43x), "Polícia" (27x). Nenhum rodapé de verdade no
meio. O filtro estava comendo o vocabulário do edital.

O estrago só aparecia lá na frente, disfarçado de extração plausível: o tópico
`8.1.2 Histórico e importância para o Direito` virava `8.1.2 Histórico
importância Direito`, quatro tópicos se colavam numa linha só e o `8.4.1 Lesões e
suas classificações` sumia inteiro. Total continuava parecendo razoável — é o
mesmo formato de erro que o docstring da função já descrevia para disciplina, e
que ele mesmo sofreu.

Conserto: mobília precisa de duas palavras. Rodapé real é multipalavra ("Página 3
de 106"); número solto já saía por `RE_SO_NUMERO`. **317 → 487 tópicos** no
mesmo PDF, com o programa de Ciências Forenses inteiro e em ordem. Não afrouxa
nada que a regra pegava antes.

**O PROGRAMA DO EDITAL PASSA A CHEGAR AO PROMPT — UMA disciplina por vez.**
`_resumo_mesa` decidiu, e continua certo, que a lista de tópicos NUNCA entra
inteira: o edital da Dataprev tem 1015. Só que isso deixava "quero ciências
forenses do zero, na ordem do edital da PC-PR" sem resposta possível — medido no
cenário `forense_do_zero`, o tutor respondeu que "o ponto de partida é a
preservação do local e o rastreamento do vestígio", inventado a partir do que a
BUSCA devolveu (cadeia de custódia), enquanto o edital abre em `8.1.1 Conceito e
divisão da Medicina Legal`. O dado estava no banco, em ordem, e não chegava a
quem responde.

O que muda é o RECORTE, não a decisão: `_programa_em_foco` manda os tópicos da
disciplina que a conversa NOMEOU (`assunto.disciplina_citada`, regra pura), com
teto de 40 (`mesa.MAX_TOPICOS_NO_PROMPT`). Ciências Forenses da PC-PR são ~30
linhas. Sem disciplina nomeada, não vai nada.

**O PDF DO ALUNO FICA GUARDADO, E VIAJA COMO BLOB — NUNCA DENTRO DO JSON.**
Até a 024 o upload era extraído, chunkado, vetorizado e o arquivo DESCARTADO:
`documento.origem` guardava só o nome, e o docstring de `material.para_reindexar`
dizia isso na cara ("quem tem que reenviar o arquivo é ele"). O efeito prático é
o que o dono relatou: a apostila continuava presa no computador dele, e reler
exigia achar o arquivo de novo.

`bytea` e não `large object`: `bytea` viaja em `pg_dump`, em réplica e na
exportação do `sincronizar.py` como qualquer coluna; `lo_*` exigiria tratamento
próprio nos três. Coluna NULLABLE porque todo material anterior à migração fica
sem arquivo — os bytes não existem mais —, e a tela mostra o botão só onde
`arquivo IS NOT NULL`, em vez de prometer o que não pode entregar. O CHECK
`arquivo IS NULL OR usuario_id IS NOT NULL` mantém corpus público fora disso:
`corpus/` está no git, guardar de novo seria a decisão que o `.gitignore` do
`acervo/` já recusou.

Tamanho foi MEDIDO antes de decidir, não estimado: o banco tem 59 MB, o disco
desta máquina tem 921 GB livres e 20 apostilas somam ~100 MB. O limite de 0,5 GB
que apareceu na conversa é do plano gratuito do Neon e só valeria na nuvem — não
existe no Postgres local do docker.

**No sincronismo, o arquivo é BLOB numa subárvore do ref `estado`.** Base64
dentro do pacote foi descartado por limite duro: infla 33%, o pacote é UM
arquivo, e o GitHub REJEITA push de arquivo acima de 100 MB — vinte apostilas
dariam ~133 MB num blob só, push recusado. Um blob por PDF resolve os três de
uma vez: cada um no tamanho real, binário guardado nativamente, e arquivo
idêntico deduplica porque o NOME é o sha256 do conteúdo (o mesmo hash que
`documento.hash` já usa como identidade natural). `git mktree` monta um nível
só, então os arquivos entram como árvore própria, modo `040000`.

Na volta o hash é CONFERIDO antes de gravar: o nome do blob é o sha256, então
divergência quer dizer arquivo trocado ou truncado, e gravar binário corrompido
como "o original" é pior que não ter original. E a gravação roda também no
caminho do `pulados` — material sincronizado antes da 024 está no banco sem
bytes, e o pacote novo é a única chance de completá-lo.

**MATERIAL DE ANTES DA 024 RECUPERA O ARQUIVO SUBINDO O MESMO PDF DE NOVO.**
A 024 deixou o material já existente com `arquivo NULL` — correto, os bytes não
existiam mais —, mas fechou a única saída junto: `registrar` recusava o reenvio
com "você já subiu este arquivo", e completar a biblioteca exigia APAGAR o
material e reindexar do zero. Oito aulas de agosto ficaram assim, indexadas e
sem "abrir" nem "baixar". O relato foi "não tô achando a opção de abrir nem de
baixar" — a opção existe; a tela é que a esconde onde o arquivo não está
(`tem_arquivo`), e fazer diferente seria mostrar botão que sempre falha.

O reenvio de material `pronto` SEM bytes agora anexa o original e para aí: não
reindexa, não volta pra fila, não mexe no status. É deliberadamente diferente da
duplicata parada logo acima — lá falta o TRABALHO, aqui falta o ARQUIVO —, e
tratar os dois igual pagaria o embedding outra vez por texto que já está no
banco (500 trechos são minutos de CPU) e faria a biblioteca piscar `processando`
num material pronto. A resposta traz `arquivo_anexado: true`, e é dele que as
DUAS rotas de upload (arquivo e link) decidem enfileirar ou não, por um
predicado só: `material.deve_indexar`. Duplicata COM arquivo segue recusada, e
`tests/test_material.py` prende as duas metades — o arquivo que volta e os
trechos que não são refeitos (mesmos ids).

**O RÓTULO QUE O ALUNO CORRIGE PASSA A VALER NA BUSCA — pelos DOIS lados da
híbrida, porque um só não bastou.** A disciplina e o assunto digitados por ele
valiam pra gerar questão, pra recortar a fila e pro seletor da tela, e não pra
busca: só o corpo do trecho era indexado. Rotular uma apostila como "Ciências
Forenses" não fazia a busca achá-la ao perguntar de ciências forenses — a
informação mais confiável que existe sobre aquele material, a que uma pessoa
digitou olhando o conteúdo, ficava fora do único lugar que decide o que é
encontrado.

Medido numa apostila cujo corpo NÃO menciona a matéria nem o assunto (o caso em
que só o rótulo pode explicar o acerto):

| consulta | sem rótulo | só no vetor | vetor + lexical |
|---|---|---|---|
| `papiloscopia` | fora do top6 | posição 2 | **posição 1** |
| `ciências forenses` | fora do top6 | fora do top6 | **posição 1** |

O vetor sozinho (`material.texto_para_vetor`, prefixo no texto que vai ao e5)
resolveu o ASSUNTO e não a DISCIPLINA, e a razão é aritmética: embedding é
média, e 35 caracteres de rótulo contra 700 de corpo quase não movem o vetor.
Justamente a consulta mais provável — o nome da matéria — continuava falhando.
Quem fechou foi `chunk.rotulo` no tsvector (025), porque o lado lexical casa
palavra e não sofre diluição por tamanho.

**O `chunk.texto` gravado continua LIMPO, e essa separação é o ponto.** É ele que
`formatar_contexto` manda ao prompt: prefixar ali faria o tutor ler "Ciências
Forenses. Papiloscopia." como conteúdo da apostila. O rótulo entra no que é
INDEXADO, nunca no que é EXIBIDO — há teste travando isso.

**E corrigir o rótulo REINDEXA, em background.** Sem isso a correção ficaria pela
metade: a lista dizendo "Ciências Forenses" e a busca respondendo pelo rótulo
velho, que é pior que não ter corrigido porque parece ter funcionado. Isto só é
possível por causa da 024 para reindexação completa. Desde 21/09/2026, material
anterior à 024 também aceita correção integral de rótulo sem fingir que o PDF
existe: o texto de cada chunk já está preservado, então `reindexar_rotulo`
recalcula embedding e `chunk.rotulo` em transação, mantendo os mesmos ids e
`fonte_chunks`. O original continua indisponível para download e para um novo
chunking, mas disciplina e assunto passam a valer na busca.

Aplicado ao corpus real em 21/09/2026: o doc 342 fechou 268/268 e os docs 343,
345, 346, 347 e 348 fecharam mais 1.177/1.177. Depois disso, aula/resumo do
usuário 1914 ficou com zero chunk sem rótulo e `questao.fonte_chunks` com zero
referência órfã. A avaliação continuou em 23/34 top-1 e 32/34 top-6.

Chunk de LEI não mudou: `rotulo` é NULL, o `coalesce` devolve vazio e o tsvector
sai idêntico. Verificado com `avaliar_retrieval.py` antes e depois — top1 21/32,
top6 30/32 nas duas medições, e dispositivo 6/6, rubrica 4/4 intactos.

**QUEM PEDE TREINO É TREINADO NA HORA, E O APP É QUE MONTA A QUESTÃO.** Três
desenhos, nesta ordem, e vale registrar por que os dois primeiros caíram.

1. **"mande usar o botão".** Log real: "queria 2 questões rápidas de direito
   constitucional" recebeu "clique no botão Quero questões sobre isto". O aluno
   pediu treino e levou instrução de interface — e a busca daquele turno tinha
   devolvido CF 102 e CPP 649, então nem o botão entregaria o que ele pediu. O
   `avaliar_chat.py --reprocessar` achou **16 casos** disso nas conversas
   gravadas: era sistemático, não azar.

2. **"o tutor escreve a questão no chat".** Resolve o atrito jogando fora o que
   dá valor à questão: sem `fonte_chunks` não há proveniência, sem gravar não há
   fila SM-2, sem fila não há repetição espaçada — e a resposta do aluno não
   conta no progresso dele. Chat mais limpo, estudo pior. Recusado pelo dono nos
   termos exatos: "não vamos sacrificar a proveniência, a fila do SM-2 e o
   histórico de longo prazo".

3. **O SERVIDOR aciona o gerador que o botão acionava.** `core/pedido.py`
   reconhece o pedido na fala (regra pura, como `assunto.py` e `ritmo_regras.py`
   — LLM aqui custaria a cota mais escassa do projeto e 1-2s em todo turno), e
   `/perguntar` chama `geracao.sob_demanda` com o tema derivado no servidor.
   Proveniência, gravação, fila e progresso **idênticos** ao caminho do botão. O
   que desaparece é o clique.

O tutor não escreve a questão e não menciona botão: o prompt manda responder em
uma ou duas linhas apresentando o que vem abaixo. O botão continua existindo
para SIMULADO FORMAL (prova cronometrada, correção no fim, caderno de erros) —
`pedido.treino` devolve `formal: True` nesses casos e nada é gerado no chat,
porque ali a pessoa quer a página do simulado, não um punhado de questões no
meio da conversa.

**Gerar dentro de `/perguntar` custa cota, e é deliberado.** O docstring de
`/questoes/gerar` avisa que gerar "gasta cota de LLM e ESCREVE no acervo", e por
isso nunca acontece dentro de um GET. Aqui continua sendo ação EXPLÍCITA do
aluno: pedir questão numa frase é o mesmo ato que clicar era, e nada acontece se
`pedido.treino` não reconhecer o pedido. Falha do gerador NÃO derruba o turno —
vai `questoes: []` e o texto do tutor, que já existe e já está gravado.

**O TEMA VEM DO HISTÓRICO ANTERIOR AO PEDIDO**, e isto foi um bug medido no
próprio dia em que a mudança nasceu. Usando o histórico já atualizado, `em_foco`
lia a frase do pedido — "me da 3 questoes disso" —, achava "disso" como palavra
de conteúdo, e as três questões saíram sobre apropriação indébita, inquérito
policial e usurpação numa conversa sobre **peculato**. Mesma classe do "vamos"
que fez nascer o `core/assunto.py`: pedido de treino nunca nomeia o assunto, ele
diz "disso". Com o histórico de antes, a primeira questão passou a ser Peculato
(CP 312).

**RELATOS DE TELA E DE PROMPT que moravam no AGENTS.md.** Estavam lá por serem
recentes; saíram porque o AGENTS.md é carregado em TODO prompt e narrativa de 110
linhas cobra esse preço a cada mensagem. O conteúdo não mudou.

**A última dica não sai automática (regra de produto, não número).** O prompt do
gerador manda a terceira dica "quase entregar", e ela entrega mesmo — medido no
dado real: gabarito "A reparação do dano que precede à sentença irrecorrível
extingue a punibilidade do agente" contra dica 3 "Antes da irrecorribilidade
extingue-se a punibilidade". A dica cumpriu o papel dela; o defeito era ela
aparecer SOZINHA a cada erro, entregando a resposta a quem não pediu — e ainda
pontuando por isso. Relatado como "na última dica ele me deu a resposta".

Detectar por texto se a dica vazou o gabarito foi considerado e recusado:
calibrado contra esse caso, "extingue a punibilidade" × "extingue-se a
punibilidade" não casa por substring, e por sobreposição de palavras de conteúdo
a dica LEGÍTIMA (que é próxima por desenho) cai junto. `DICAS_AUTOMATICAS =
MAX_DICAS - 1` é regra, e regra não erra — é a mesma decisão central de
`socratic.py`, a retenção do gabarito imposta em código e não confiada ao
prompt. A dica continua acessível: quem quiser pede, e aí conta como PEDIDA,
entrando na penalidade. Vale nas duas interfaces (`DialogoQuestao.tsx` e
`chat.py`), porque MAX_DICAS/MAX_TENTATIVAS sempre foram regra compartilhada.

**O rótulo do resultado contava a coisa errada.** "3 erro(s), 1 dica(s)
pedida(s)" foi lido como contagem quebrada, com razão: o aluno tinha VISTO três
dicas e o texto falava de uma. Dica pedida e dica mostrada são números
diferentes de propósito (só a pedida entra na penalidade), mas esconder o
segundo faz o primeiro parecer defeito. Agora sai "3 erros · 3 dicas vistas (1
pedida)", e o que não existe não é mencionado.

**"Pausar e entender isto" era um clique sem efeito.** `<Intervencao>` fazia
`router.push("/tutor?q=...")`, e o caso mais comum é a intervenção aparecer
DENTRO do /tutor (a questão que gerou os 3 erros costuma ser a embutida no chat)
— e o Next não remonta a rota pra ela mesma. É o mesmo defeito que o botão "Nova
conversa" da sidebar já tinha tido, e a saída é a mesma: CustomEvent pra página
irmã. Manda pra conversa ATUAL em vez de abrir uma nova, porque "entender ISTO"
só quer dizer algo com o que acabou de acontecer na tela.

**A rolagem do chat mexe no CONTAINER, não em `scrollIntoView`.** Há dois
scrollers aninhados (o `<main>` do AppShell e o da página), e `scrollIntoView`
escolhe sozinho qual ancestral mover — foi por isso que a rolagem passou no meu
teste e não na tela. `irAoFim` escreve `scrollTop` do container certo, com dois
`requestAnimationFrame` (o primeiro roda antes de o React pintar, e aí
`scrollHeight` ainda é o de antes). Rola ao MANDAR também, não só ao receber: o
balão do aluno mais o "pensando" já empurram o fim pra fora da tela.

**O prompt vazou o próprio andaime, e a culpa é do rótulo.** O bloco de ordem de
ensino começava com "ESCADA PEDAGÓGICA" em maiúsculas, e o modelo passou a
NARRAR o método: uma resposta real abriu com "Perfeito, vamos voltar um degrau
na escada pedagógica". É o mesmo defeito do `[DESEMPENHO REAL DO ALUNO]` citado
como fonte, pela mesma causa — nome próprio dentro do prompt vira vocabulário do
modelo. A instrução perdeu o nome, e a proibição de nomear passou a ser
explícita (nada de "escada", "degrau", "método socrático", "diagnóstico",
"trechos recuperados", "acervo"): o aluno veio estudar Direito, não ler o manual
do app.

Junto entraram duas regras de tom, as duas de reclamação real: **responder no
TAMANHO da pergunta** (um "boa noite" recebia um parágrafo sobre eficácia das
normas; agora recebe uma linha e uma pergunta aberta citando as disciplinas do
edital) e **um micro-tópico por resposta** (explicar direitos sociais e emendar
competência concorrente no parágrafo seguinte confunde em vez de ensinar).

**A "metralhadora de assuntos" não era só tom — era a busca sem assunto.** No
turno do "boa noite" a busca devolveu CP art. 150, CPP art. 569 e Lei 8.112 art.
75, e o modelo falou do que apareceu no prato dele. Instrução de foco trata o
sintoma; a causa era a consulta.

**E a consulta amnésica escapou por outra fresta: `em_foco` excluía o TUTOR.**
Conversa real: aluno "boa noite" → tutor propõe eficácia plena × limitada →
aluno "podemos testar eu nao sei se ja estou bom". Nenhuma fala do ALUNO nomeia
matéria, então a consulta virou "podemos testar eu nao sei se ja estou bom boa
noite" e as questões geradas foram CF art. 200 (SUS) e CP art. 94
(reabilitação) — o mesmo estrago do "vamos".

A lição NÃO é "faltou palavra na lista `VAZIAS`". Nenhuma enumeração cobre toda
forma de dizer "vamos lá", e a lista já cresceu duas vezes atrás de caso real. O
defeito era estrutural: **quando o aluno não nomeia o assunto, quem nomeou foi o
tutor**, e a proposta dele É o assunto da conversa. Excluí-lo sempre
transformava "o aluno aceitou o convite" em "ninguém falou de nada". Agora é
FALLBACK (não fonte de igual peso — a razão original de excluí-lo continua
valendo quando o aluno JÁ disse do que quer falar), e há teste separando os dois
casos.

**E NOME DE DISCIPLINA não conta como assunto no fallback.** Isso apareceu ao
consertar o tom: com o prompt novo, a resposta a um "boa noite" é "por onde você
quer começar, Direito Constitucional ou Direito Penal?" — curta e certa. Só que
o fallback achava "assunto" ali ("direito", "constitucional", "penal") e a busca
devolvia artigo sorteado DENTRO da matéria: CPP art. 2º pra quem não pediu nada.
Errado de um jeito pior que vazio, porque tem cara de acerto. Disciplina é a
gaveta, não o que a pessoa quer estudar — o prompt já a recebe pelo "Contexto do
aluno". Sem assunto de verdade, o certo é NÃO buscar, e aí a instrução de
"nenhum trecho recuperado" manda o tutor perguntar de que assunto se trata.

Lido nos três turnos reais depois da mudança: "boa noite" → uma linha e pergunta
aberta, zero busca; "podemos testar" → pergunta de diagnóstico, zero busca, zero
lei afirmada sem fonte; "quero eficácia das normas constitucionais" → pergunta
certa sobre aplicabilidade imediata × dependente de lei. Nenhum vocabulário de
sistema em nenhuma das três.

**O terceiro botão com o mesmo defeito de rota.** Clicar num recente estando JÁ
no /tutor não recuperava a conversa: o efeito que lê `?c=` roda na MONTAGEM, e ir
de `/tutor?c=1` pra `/tutor?c=413` não remonta a rota nem muda as dependências
dele — e o `replaceState` ainda apaga a query, então nem dependência nova
resolveria. O log mostrava `GET /tutor?c=413 200`: a navegação acontecia, a
leitura não. Depois de "Nova conversa" e "Pausar e entender isto", é a terceira
vez — o padrão de conserto (CustomEvent da sidebar pra página irmã) já era
conhecido, e agora `abrirConversa` tem os dois gatilhos.

**Fonte repetida virava chave repetida no React.** O caminho AO VIVO deduplicava
as fontes com `Set`; o de REABRIR não, e o mesmo documento aparece em vários
chunks — `referencia()` devolve só o título quando não há artigo (material do
aluno, tipo `historico`), então a etiqueta repetia. O React reclamou no log com
a chave literal (`curso-392722-aula-04-2787-completo`). Dois caminhos para a
mesma coisa é como um deles fica sem a regra do outro.

**A INDEXAÇÃO PASSA POR UMA FILA COM UM TRABALHADOR — e o que ensinou isso foi
o servidor caindo.** A rota fazia `fundo.add_task(indexar, doc_id, nome, dados)`
por upload. Com um arquivo, ótimo. Com VINTE, o `BackgroundTasks` despacha as
vinte quase juntas, e cada uma carrega o arquivo inteiro em memória (o `dados`
preso na closure), extrai o PDF, abre conexão isolada própria e roda o e5 na CPU.
Relatado e reproduzível: o upload de 20 apostilas **matou a API depois da
primeira**, e o F5 voltou numa tela vazia porque não havia mais API pra responder
`/materiais`.

A fila conserta os dois lados. Concorrência 1 porque o embedding é CPU local —
paralelizar nunca ia ser mais rápido, só mais frágil. E a fila carrega o ID, não
os BYTES: quem trabalha lê o arquivo do banco, o que só é possível por causa da
024. A memória do processo deixa de crescer com o tamanho do lote.

Medido depois: **20 uploads aceitos em 3,3s**, fila com 19 esperando, UMA thread
trabalhando, e `GET /fila` respondendo em **111ms durante** a indexação.

**Dois defeitos que só apareceram porque a indexação virou assíncrona DE VERDADE:**

· o trabalhador lia os bytes com `db.exec1`, ou seja, na conexão GLOBAL do
  módulo. `core.db.conn()` devolve UMA conexão e psycopg não é thread-safe —
  usá-la aqui enquanto uma requisição usa a mesma é corrupção de protocolo, não
  lentidão. Apareceu como material caindo em `status='falha'` sem razão nenhuma;
  em produção apareceria como exceção aleatória em rota sem relação com material.
  `indexar` já fazia certo (`conexao_isolada`), e é dele que veio a pista.

· quatro testes afirmavam `status == 'pronto'` na linha seguinte ao upload. Isso
  funcionava porque, com `TestClient`, o `BackgroundTasks` roda ANTES de a
  resposta voltar — a indexação era síncrona no teste e assíncrona em produção.
  A suíte escondia exatamente o comportamento que derrubou o servidor: em teste
  as vinte nunca corriam ao mesmo tempo. Agora existe `material.esperar_fila`, e
  quem afirma sobre o RESULTADO espera por ele.

  Um deles ainda passava sozinho e falhava na suíte inteira: o trabalhador é
  global e o `llm_falso` é por teste, então indexar em paralelo com ele fazia o
  resultado depender de quem escrevia por último. A ordem certa é drenar a fila
  ANTES de indexar à mão.

**DUPLICATA PARADA NÃO É DUPLICATA — É SERVIÇO INACABADO.** O `registrar`
barrava por hash qualquer arquivo já subido, e isso estava certo enquanto todo
upload terminava. Depois de a fila existir, o relato foi o mais claro possível:
o servidor caiu no meio do lote de 20, o dono subiu as 18 restantes de novo, e
recebeu "você já subiu este arquivo" DEZOITO vezes — enquanto as dezoito linhas
estavam no banco sem um único trecho indexado. A intenção dele era terminar o
serviço; a resposta do sistema tratou como erro dele.

Agora `pronto` COM trecho continua recusado (aí a duplicata é real, e reindexar
seria pagar CPU de novo pelo mesmo material), e `processando`/`falha`/zero
chunks volta pra fila devolvendo a linha que já existe, com `retomado: true`. Do
ponto de vista de quem arrastou o arquivo, foi um upload — e é assim que a tela
reporta: aviso, não erro. Contar retomada como falha produziu a mensagem mais
confusa que o app já deu ("18 de 18 não entraram" para 18 que acabaram de
entrar na fila).

Isso mudou dois testes de propósito, e os dois estão anotados: "mesmo arquivo
duas vezes é barrado" passou a esperar a indexação terminar, senão media a
janela em que o primeiro ainda estava na fila.

**"A APLICAÇÃO ESTÁ LENTA" ERA O GEMINI — mas parte da espera era nossa.**
Relatado assim: com o material carregado, um "bom dia" demorava muito e às vezes
devolvia `LLM indisponível: HTTP 503`. A suspeita natural era o volume de
material. Medido, não era:

| o que | tempo |
|---|---|
| `mesa.contexto` + `perfil` + `_resumo_desempenho` + `_resumo_mesa` + `_programa_em_foco` | **11 ms somados** |
| chamada TRIVIAL ao Gemini (10 tokens) | **33,8s / 42,4s / 503** |

Máquina ociosa (load 0,63 em 8 núcleos), índice HNSW no lugar, 4.585 chunks. O
app respondia em 11ms e esperava 40s pelo provedor.

**O QUE ERA NOSSO:** `_post` repetia o MESMO modelo três vezes, dormindo 3s e
10s entre as tentativas. O 503 do plano gratuito é por capacidade DO MODELO, não
da conta — medido no mesmo minuto, `gemini-3.5-flash-lite` deu 503 em duas
tentativas seguidas enquanto `gemini-3.1-flash-lite` respondeu em **2,1s**.
Insistir no mesmo endereço transformava a instabilidade deles em 13s de espera
nossa pra bater na mesma parede.

Duas mudanças. Primeiro, uma tentativa por MODELO, percorrendo
`GEMINI_RESERVAS` — 4/5 chamadas passaram a responder, e as boas caíram pra
5,9s/7,2s. Segundo, e o que de fato resolveu: o `3.5-flash-lite` estava fora em
praticamente toda chamada, então ele deixou de ser o principal. Com
`3.1-flash-lite` na frente, um "bom dia" ponta a ponta ficou em **1,8s / 2,8s /
5,8s**.

A lição pra próxima vez que "o app está lento": cronometre as peças ANTES de
acreditar na causa mais plausível. O material não tinha nada a ver, e mexer nele
teria custado dias sem mudar o número.

**PEDIDO SEM OBJETO NÃO É INICIATIVA — É ECO.** A pior consulta já registrada
aqui, com log completo do dono:

    tutor:  "...item 9.1 do seu edital: Conceito, fontes e princípios do
             Direito Administrativo. Você já sabe diferenciar os princípios
             expressos dos implícitos, como a Autotutela?"
    aluno:  "não você pode me explicar e mostrar como isso cai em concurso?"
    aluno:  "me traga ai umas 3 questões desse conteudo"

A consulta virou `'não você pode me explicar e mostrar como isso cai em
concurso? direito administrativo, quero someçar do primeiro topico'`, a busca
devolveu CPP 580, CP 337-O e ADCT 19, e as três questões geradas foram sobre
extensão de recurso, omissão de projetista e estabilidade — numa conversa sobre
princípios administrativos.

O caminho do defeito: "explicar" está em `PEDIDO`, então `pede_assunto` dizia
True, `e_eco` dizia False, e a fala de palha do aluno venceu a do TUTOR — que
havia nomeado o assunto corretamente. A palavra de conteúdo que sustentou a
fala foi "mostrar", a única fora de `VAZIAS`. Mais uma vez: **não é lista que
resolve**.

O que resolve é estrutural, e é a mesma distinção que o docstring de
`pede_assunto` já fazia sem exigir: "me explica peculato" NOMEIA, "me explica
isso" não. Agora o pedido precisa trazer algo além do próprio vocabulário de
pedir. A escapatória continua funcionando — "agora quero controle de
constitucionalidade" troca o assunto, porque "controle" e "constitucionalidade"
não são palavras de pedir. Verificado nos nove casos do teste.

Com isso a consulta passou a ser a frase do tutor, que nomeia princípios, LIMPE
e Autotutela.

**E A BUSCA CONTINUA ERRANDO — medido, e não é o teto que conserta.** Com a
consulta certa, o acervo devolve CP 170 e CPP 500. Testei reduzir a prosa
herdada a palavras de conteúdo e cortar em 400/160/120/90/60 caracteres: CF 37
não aparece em NENHUM desses cortes. Só aparece com consulta curta e de
vocabulário certo — `'administração pública princípios legalidade
impessoalidade'` traz CF 37 na posição 1; `'princípios da administração'` não
traz. É o e5 genérico em domínio jurídico, e não há surgery de consulta que
conserte. Fica registrado pra ninguém tentar teto de novo achando que é isso.

**O TUTOR ESCREVEU QUESTÃO DE MÚLTIPLA ESCOLHA NO CHAT, no mesmo turno em que o
app gerou três de verdade.** `[Questão 1: ... a) Legalidade; b) Eficiência; c)
Autotutela; d) Publicidade.]` — duplicou o trabalho e entregou a versão sem
proveniência junto da boa. Duas falhas de instrumento:

· `RE_ALTERNATIVA` só olhava começo de linha (`^`), e as alternativas vinham
  inline. Agora exige DUAS alternativas em sequência, o que não confunde com
  prosa ("o item a) do edital").
· o formatador de texto chipava TUDO entre colchetes, então desenhou a questão
  inventada como se fosse fonte de lei. Chip é promessa de conferibilidade —
  dar essa aparência a texto inventado é pior que não formatar. Agora só recebe
  chip o que casa o formato de `retrieval.referencia` (tem "art." ou "p." com
  número).

**O PLANALTO DERRUBA CLIENTE SEM `User-Agent` DE NAVEGADOR.** Relatado: colar
`https://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm` na
biblioteca devolvia "Não deu pra indexar este link". Medido no mesmo minuto: sem
UA de navegador, `ReadTimeout`; com, HTTP 200 e 1,8 MB. O UA honesto
("FerrarIA/1.0") era o certo por educação e o errado na prática — e o alvo é a
fonte mais óbvia de lei seca deste projeto.

E o texto vinha `Constitui��o`: o HTML compilado do Planalto é cp1252 e o
cabeçalho não diz, então `r.text` chutava utf-8 e comia 1170 artigos de acento.
Acento quebrado não é cosmético aqui — some da busca lexical e aparece na
citação que o aluno lê. Agora a decodificação é explícita (utf-8, cp1252,
latin-1, e só no último recurso `errors="ignore"`), pelo mesmo helper nos dois
caminhos.

**HTML por ARQUIVO passou a ser suportado.** Por LINK já era (o `baixar` olha o
content-type); arrastar um `.htm` salvo caía no `decode` genérico e indexava as
tags como se fossem conteúdo. Quem salva a página da CF e arrasta o arquivo é o
caso mais provável daqui.

**TROCA DE ASSUNTO NA GERAÇÃO PASSOU A SER DECLARADA.** O fallback de
`sob_demanda` (tema sem trecho utilizável → recorte da mesa) estava certo, e era
SILENCIOSO — o que o transformava em mentira: o aluno conversou sobre princípios
do Direito Administrativo, pediu três questões, e recebeu extensão de recurso,
omissão de projetista e estabilidade, com o tutor abrindo "vamos treinar isso".

Agora `sob_demanda` devolve `trocou_de_assunto`, a rota repassa como
`questoes_fora_do_assunto`, e a TELA avisa acima das questões. Quem diz é a tela
e não o tutor porque o texto dele é escrito ANTES de gerar — ele não pode saber.
Mesma regra que o prompt já impõe pra explicação: silêncio sobre o que o sistema
não tem é o defeito, não o fallback.

**INDEXAR É SÍNCRONO NOS TESTES, e isso é sobre acoplamento.** A fila é global ao
processo, então num `pytest` os uploads de todos os arquivos de teste empilham no
mesmo trabalhador — o teste que esperava a fila drenar estourou 240s por causa da
fila de OUTROS testes, passando sozinho e falhando na suíte. Acoplar testes por
recurso global é pior que perder a cobertura da fila ali, e a fila não fica sem
prova: a concorrência foi medida à mão (20 uploads em 3,3s, uma thread, `GET
/fila` em 111ms durante a indexação).

**E TESTE PONTA A PONTA NÃO CHAMA O GEMINI DE VERDADE.** Escrevi
`test_pedir_treino_no_chat_...` contra o modelo real e ele passava sozinho e
falhava na suíte — não por código, mas porque o provedor devolvia 503. O que ele
afirma (proveniência, gravação, fila, tutor não mandando clicar) não precisa de
modelo real nenhum. Duplê, como o resto do arquivo já fazia.

**LEI SECA DO ALUNO É DIVIDIDA POR ARTIGO — E CÓPIA DO ACERVO É RECUSADA.** Dois
consertos que nasceram do mesmo relato: o dono colou o link da Constituição,
depois subiu o .htm dela, e perguntou por que o tutor continuava dizendo que não
tinha material.

**Primeira parte.** As duas cópias viraram ~2100 janelas genéricas com `artigo`
NULO, porque todo material do aluno ia por `chunk_generico`. O efeito era
quádruplo: não achava por dispositivo, não gerava questão (o gerador exige
`artigo IS NOT NULL`), a citação saía "constituicao, p. 14" em vez de "CF, art.
37", e competia na busca com a CF do acervo.

`_e_lei_seca` separa lei de apostila pelo que os distingue de fato: lei publicada
abre linha com "Art. N" (584 vezes na CF); apostila cita no meio da frase. Teto
folgado de 40 ocorrências EM INÍCIO DE LINHA. A decisão anterior ("tudo por
`chunk_generico`") tinha um medo legítimo — apostila comentada citando "art. 312"
viraria chunk com `artigo='312'` e sequestraria `por_dispositivo` — e ele segue
coberto duas vezes: a norma fica NULA e `por_dispositivo` ordena
`d.tipo = 'lei' DESC`.

**Segunda parte, e ela só apareceu porque a primeira funcionou.** Com as cópias
divididas por artigo, elas passaram a GANHAR da original: a busca por "princípios
da administração pública", que trazia `cf, art. 37` na posição 3, passou a trazer
`constituicao.txt, art. 88`, `art. 39`, `art. 234`. Mil e oitenta e seis cópias
afogando o original.

E o `avaliar_retrieval.py` NÃO viu: ele mede contra o acervo compartilhado, sem
`usuario_id`, então a biblioteca do aluno é invisível pra ele — 21/32 antes e
depois. A degradação era exclusiva do aluno, o pior tipo, porque nenhuma medida
do projeto a mostra. Fica registrado: ao mexer em material do aluno, medir COM
`usuario_id`.

Daí `norma_ja_no_acervo`: amostra 25 artigos e compara (artigo, prefixo do texto)
contra o acervo público. Batendo 60%, o upload é recusado com a razão — subir
cópia não acrescenta nada e piora a busca. O limiar tem folga porque emenda muda
redação, e 25 amostras não confundem apostila que transcreve uns poucos artigos.

**PARAR E EDITAR SÃO O MESMO PROBLEMA, visto de dois lados.** Pedido: "digitei
errado, deveria ter um quadradinho pra parar e um lapizinho pra editar".

O que torna os dois não-triviais aqui é a gravação em dois lados da 014: a
pergunta entra no banco ANTES de o modelo ser chamado, de propósito — quem
reabre a conversa tem de achar o que escreveu, mesmo se o LLM caiu no meio. O
preço é que interromper deixa pergunta sem resposta, e editar deixaria a versão
errada no histórico junto da certa. As duas seriam lidas pelo prompt do turno
seguinte como parte da conversa.

Daí `conversa.desfazer_ultimo_turno`, que atende os dois: apaga o par do FIM pra
trás (nunca por texto igual — a mesma pergunta pode ter sido feita três turnos
antes, que é o que acontece quando alguém insiste no assunto) e DEVOLVE a
pergunta, que é o que faz "editar" ser editar em vez de digitar tudo de novo. O
evento de "propus N questões" (016) entra na conta: sem ele o prompt afirmaria
uma proposta que não existe mais.

POST e não DELETE na rota: não é "apagar um recurso", é operação com retorno
útil. DELETE que devolve corpo pra ser usado engana quem lê a rota.

**CANCELAR É SÍNCRONO, e a primeira versão não era.** Ela pedia a pergunta de
volta ao SERVIDOR pra repor no campo — ou seja, cancelar custava um ida-e-volta
de rede, e quem digitou errado esperava DUAS vezes: a resposta que não queria e
o cancelamento dela. Relatado nesses termos: "esse cancelamento tem de ser
instantâneo".

O texto já está no cliente. Guardá-lo num ref (`ultimaPergunta`) e repor de lá é
o conserto — buscá-lo de novo era atravessar a rede pra saber o que a própria
tela acabou de mandar. Tudo o que a pessoa VÊ (abortar, tirar o balão, repor o
texto, devolver o foco) acontece sem `await`; a limpeza do servidor vai
fire-and-forget.

O `editar` seguiu o mesmo caminho: o texto vem do BALÃO que a pessoa clicou, não
de uma consulta.

O custo aceito, e ele é pequeno: falhando a limpeza (rede caiu no exato
instante), a pergunta órfã fica no histórico e o prompt do próximo turno vê uma
pergunta sem resposta. Ruim, não grave. Travar o cancelamento pra evitar isso
seria trocar um problema raro por atrito em TODO cancelamento.

**O QUE O BOTÃO DE PARAR NÃO FAZ, e é honesto dizer:** não recupera a chamada ao
modelo. Ela sai no início do turno, então parar não a desfaz — o que se evita é
o que vem DEPOIS (gerar questões, gravar a resposta) e, principalmente, a pessoa
presa numa tela cuja resposta ela já sabe que não quer. Prometer economia de
token seria mentira.

Aborto NÃO desenha balão de erro: quem clicou em parar sabe o que aconteceu, e
"não deu pra conectar com a API" culparia a rede por uma decisão dela.

O lápis aparece só na ÚLTIMA pergunta e só com a conversa parada. Editar uma do
meio significaria descartar tudo o que veio depois, e ninguém pede isso ao
clicar num lápis.

**O TUTOR NÃO ESCREVE QUESTÃO — GARANTIDO EM CÓDIGO, depois de três prompts
falharem.** As tentativas, em ordem: v40 mandava usar o botão; v41 dizia que o
app monta e ele só apresenta; v42 enumerava "nada de \"Questão 1:\", nada de
enunciado numerado, nada de alternativas a), b), c) — nem entre colchetes, nem
em lista, nem no meio da frase". O log seguinte trouxe exatamente
`[Questão 1: ... a) Autotutela; b) Impessoalidade; c) Supremacia; d)
Indisponibilidade.]`, duas vezes.

`limpar_citacoes` já existia pelo mesmo motivo, e a lição é a mesma: o que dá
pra garantir em código não se confia ao prompt. `limpar_questoes` apaga o bloco
antes de a resposta sair, e sobrando pouco texto entra uma linha padrão —
reescrever prosa de modelo é o que `_costurar` aprendeu a não fazer.

O dano era concreto, não estético: questão na prosa não tem campo de resposta,
não tem `fonte_chunks`, não entra na fila SM-2 e não conta no progresso. Relatado
assim: "não trouxe o campo pra eu anexar a resposta individualmente". O aluno lê
duas questões que parecem iguais às de verdade e não tem onde responder.

O GATILHO SÃO TRÊS ALTERNATIVAS, não duas. Com duas, a regra apagava prosa
legítima: "O item a) do edital trata de princípios e o b) de atos". Item de prova
brasileira tem quatro ou cinco; texto corrido cita uma ou duas.

**QUANTIDADE PEDIDA EM PARTES É SOMADA.** "traga 1 questão sobre principios
explicitos e uma sobre explicito" pedia DUAS e vinha uma, porque a regra parava
no primeiro número. A segunda quantidade é elíptica — "uma [questão] sobre Y" —,
então procurar outra ocorrência ANCORADA não bastava: é preciso somar número
solto que venha DEPOIS do primeiro ancorado.

Ancorar no primeiro é o que torna a soma segura (número antes dele pode ser
"art. 312" ou "3 anos de pena"), e o que vem logo após "art.", "§", "inciso" ou
"caixa" é pulado. Pedir "uma de cada" é a forma natural de cobrir dois pontos, e
entregar metade é o erro que a pessoa não reporta — ela só acha que o app é ruim.

**DOUTRINA DE CONHECIMENTO PRÓPRIO PASSA A SER PERMITIDA — MARCADA.** Decisão do
dono, com a razão dele: "se eu for no Gemini e pedir os princípios ele vai saber
me responder". A regra anterior proibia TODO conteúdo sem trecho recuperado, e o
efeito ficou pior que o risco que ela evitava: Supremacia do Interesse Público,
Indisponibilidade e Autotutela não estão em artigo NENHUM da Constituição, então
"não tenho o texto" virava "não te ensino".

O que se conserva é exatamente o que a proibição existia pra dar — saber o que
dá pra CONFERIR. Por isso a licença é só pra CONCEITO (doutrina, classificação,
definição), vem com aviso obrigatório em uma linha, e **não pode usar colchete**,
que continua reservado a fonte recuperada.

O QUE SEGUE PROIBIDO SEM TRECHO, sem exceção: número de artigo, número de
súmula, pena, prazo, valor e posição de tribunal. É ali que a invenção é
irrecuperável, e os dois casos medidos são desses: o modelo afirmou entendimento
do STJ sobre peculato de uso que não existe, e citou "art. 37" numa conversa sem
CF recuperada. Errar um número estraga a prova; errar uma explicação o aluno
descobre na primeira apostila.

Verificado com o tutor real: ele ensinou os três princípios implícitos com
clareza e fechou com "*Vale lembrar: isto é doutrina e não está no seu material;
confira na sua apostila.*"

**A CHECAGEM INVERTEU DE LADO junto com a regra.** "Explicou em bloco sem citar
nenhuma fonte" era AVISO e virou ERRO — mas só quando falta o aviso. Doutrina
pode; doutrina calada não. A regra que muda tem de levar o instrumento com ela,
senão o avaliador passa a apontar o comportamento correto.

**E A CF NÃO ESTAVA SENDO IGNORADA.** A queixa era razoável e a medição mostrou
outra coisa: para "princípios expressos da administração pública" e "principios
explicitos e implicitos", o `art. 37` volta na POSIÇÃO 1. O que falha é a
consulta curta — "princípios explícitos" sozinho não acha, e "LIMPE legalidade
impessoalidade" também não. O acervo tem o artigo; o e5 é que não liga essas
palavras a ele.

**TESTE DE UNIDADE SOBRE FUNÇÃO MORTA PASSA.** `limpar_questoes` existiu por um
commit inteiro sem ser chamada: ao refazer a edição da função (a primeira tinha
errado a assinatura de `limpar_citacoes`), perdi a linha do `return` de
`explicar`. A suíte continuou verde — o teste chamava a função DIRETO — e só a
bateria de cenários trouxe as questões inline de volta.

O conserto tem duas partes, e a segunda importa mais: além de ligar a função,
entrou um teste que vai pela ROTA (`POST /perguntar`) com o duplê respondendo
questão inline. Teste que exercita o CAMINHO pega função desligada; teste de
unidade não.

**A CHECAGEM 3b VOLTOU A SER AVISO, na quarta iteração.** Na bateria completa, 7
dos 9 "erros" eram dela, e nenhum era doutrina sem aviso:

  · "não tenho acesso a súmulas ou jurisprudência no seu material"
  · "Sou seu professor particular e foco no seu edital"
  · "o artigo 312 aparece em dois lugares distintos no seu edital"

Os três são o tutor ACERTANDO — recusando, se apresentando, navegando.
`RE_AUTORIDADE` casa porque eles falam de lei, súmula e artigo; o que ela não
distingue é falar SOBRE o material de afirmar conteúdo, e essa distinção é
semântica. Regex não a alcança, e insistir foi erro meu por quatro versões.

Quem alcança é o juiz, e alcançou na mesma bateria: `ancoragem: 0` com "o tutor
afirma que a lei exige duas testemunhas para assinar o termo de oitiva, mas o
trecho citado [CPP, art. 6º, V] não menciona a exigência". Esse é o defeito de
verdade, e veio da dimensão certa.

Fica como AVISO — ponteiro pra ir ler o turno, não veredito. E recusa explícita
("não tenho", "não consta") passou a ser isenta de vez: era metade dos falsos
positivos, e apontar o tutor por dizer que não tem material é o pior ruído
possível. Checagem que grita em acerto ensina a ignorar checagem.

**O TUTOR NEGAVA UM RECURSO QUE EXISTE.** Achado no `--refazer`: "quero um
simulado formal cronometrado" recebeu "não tenho uma ferramenta de cronômetro ou
interface de simulado formal". É FALSO — o app tem `core/simulado.py` e a tela
`/simulado`, com cronômetro, correção só no fim e caderno de erros. Errar sobre
o próprio produto é pior que o jargão que a mesma frase vazou ("ferramenta"): o
aluno acredita e deixa de usar o que já está pronto.

Dois lados, e os dois estavam abertos. O prompt não dizia que o simulado existe
— só proibia falar de botão —, então o modelo preencheu o vazio com uma negativa
inventada. E o `simulado_pedido`, que a API já devolvia desde que `core/pedido.py`
nasceu, a TELA IGNORAVA: o dado estava na resposta e ninguém desenhava nada com
ele. Agora o prompt afirma que a tela existe e a conversa mostra o caminho.

Vale como padrão: campo novo na resposta da API sem consumidor na tela é dado
morto, e dado morto não avisa. Foi a terceira vez nesta série (`retomado`,
`questoes_fora_do_assunto`, `simulado_pedido`) — os dois primeiros eu liguei no
mesmo commit; este passou.

**E A `VERSAO` DO `socratic.py` FICOU TRÊS VERSÕES ATRASADA.** Quatro mudanças
entraram (limpar_questoes, doutrina marcada, o wiring, o simulado) e o número
continuou em `v42`, porque cada script de edição errava o alvo do bump — o
conteúdo trocava e a linha da versão não. É exatamente o que a convenção
existe pra evitar ("o bug mais caro do projeto foi rodar código antigo achando
que era novo"), e ela falhou no sentido inverso: código novo se anunciando
velho. Confira `grep '^VERSAO'` depois de editar, não só a mudança.

**A CITAÇÃO SAIU DO MEIO DA EXPLICAÇÃO — E O CONSERTO FOI NA ORIGEM, não na
saída.** Pedido do dono: "você já cita as referências lá embaixo, não tem
necessidade de citá-las novamente no meio da explicação". A queixa nasceu com
uma citação de 47 caracteres na frente:
`[curso-392569-aula-10-prof-juliana-sganzerla-2cbd-completo]`.

Tentei apagar na saída primeiro, e MUTILOU A FRASE. O modelo escreve o colchete
como parte da sintaxe — "está prevista no [CP, art. 129]" —, então remover deixa
ferida: "está prevista no." Costurar isso virou lista de preposições sem fim, e
uma versão dela comeu "prevista no" inteiro, sobrando "a lesão corporal está.".

O conserto que funcionou foi parar de PEDIR: a instrução anterior ORDENAVA citar
entre colchetes, e o modelo obedecia. `limpar_citacoes` continua de pé pro
colchete que ele escrever por hábito.

**E O EXEMPLO ERA A INSTRUÇÃO.** Acrescentei a proibição e deixei o "(ex.: [CF,
art. 37])" na frase seguinte — o modelo continuou citando, com razão: exemplo
formatado vale mais que proibição em prosa três linhas antes. Prompt com duas
ordens opostas obedece a mais concreta.

**REFERÊNCIA DE MATERIAL PASSOU A SER O ASSUNTO, não o nome do arquivo.** O
classificador (020) já produz "Traumatologia forense", "Balística forense",
"Lesão corporal", e era o nome do PDF que aparecia. Mudar `referencia()` sem
mudar `com_fonte()` quebrou o que o docstring da própria função avisa ("as duas
precisam da MESMA regra de formação"): `limpar_citacoes` passou a apagar citação
LEGÍTIMA de apostila, porque comparava contra o título. Sintoma sempre igual —
divergência entre as duas.

**A CHECAGEM 3b MORREU COM A MUDANÇA.** Ela apontava "explicou sem citar nenhuma
fonte", e a premissa era que ausência de colchete é suspeita — verdade enquanto
o prompt pedia citação inline. Sem esse pedido, ausência de colchete passou a ser
o comportamento CORRETO, e a checagem dispararia em todo turno. Já era a de pior
histórico: quatro iterações, e 7 dos 9 "erros" da bateria completa eram falso
positivo dela.

O que fica no lugar é a 3c, e ela ficou MAIS importante: sem colchete, o tutor
nomeia artigo em prosa ("o art. 129 trata de..."), e conferir esse número contra
os trechos recuperados é a única verificação automática que sobra. O resto é do
juiz, na dimensão `ancoragem`.

**O QUE SE PERDEU, dito pra ninguém redescobrir:** verificabilidade por
AFIRMAÇÃO. A lista de fontes embaixo diz de onde a RESPOSTA veio; não diz qual
frase veio de qual trecho. Foi troca escolhida pelo dono.

## Armadilhas do corpus (Planalto)

- Quebra de linha no meio da frase; `normalizar_lei()` remonta.
- Rubrica com nota colada: `Concussão (Redação dada pela Lei nº ...)`.
- Nota isolada ENTRE rubrica e artigo (feminicídio, art. 121-A).
- Artigo revogado tem como corpo só a nota — preservar, é matéria de prova.
- Rubrica pode começar com "Pena" ("Penas restritivas de direitos").
- Assinatura e aviso de rodapé ("Este texto não substitui o publicado no
  DOU...", "GETÚLIO VARGAS") vêm colados depois do último artigo no HTML
  compilado. Sem cortar pelo marcador do aviso ANTES de gerar o `.txt`, esse
  texto vira corpo do último artigo — não é rubrica nem termina sem
  pontuação, então `_cortar_cauda` não descarta.
- Acento faltando em palavra comum ("alguem" em vez de "alguém", Art. 121)
  não aparece em nenhuma métrica estrutural — só quebra busca lexical em
  runtime, silenciosamente. `grep -c` da palavra certa vs. errada no corpus
  é o jeito rápido de checar se é isolado ou sistêmico antes de decidir como
  corrigir (ver "Postgres 'portuguese' não faz accent-folding" em Aberto).
- **CF compilada:** o aviso "Este texto não substitui..." e a lista de
  assinatura dos constituintes vêm no MEIO do arquivo (fim do corpo
  principal, ANTES do ADCT), não só no fim como no CP — cortar só pelo fim
  do arquivo perderia o ADCT inteiro. E a palavra quebra entre "não" e
  "substitui" com `\n`, não espaço — busca ingênua por essa frase falha se
  não tolerar quebra de linha no meio.
- **ADCT:** referência a "art. X da Lei nº ..." ou "art. X da Constituição
  de 1967" no MEIO de um parágrafo, quebrada em nova linha pela extração,
  casa com `RE_ARTIGO` como se fosse um artigo novo — gera chunk fantasma
  (fragmento de outro artigo, com número de artigo errado). Baixo volume
  (3 de 151, 2%) e a `taxa_colisao_artigo` já sinaliza; não vale regex mais
  esperto pra 2% enquanto não aparecer caso real de citação errada.

## Armadilhas de método (custaram tempo)

- **Métrica que a própria regra define não arbitra entre regras.** "Questões
  dominadas" sobe se a regra afrouxa, sem ninguém saber mais.
- **Simulação com aleatoriedade precisa de várias sementes.** Diferença de 8
  pontos virou 36 ao repetir 15 vezes.
- **O simulador não modela esquecimento.** Logo, não pode julgar "revisão
  antes de novidade" quando a capacidade cobre a demanda.
- **Medir ausência não é medir defeito.** "112 artigos sem rubrica" media o
  Código Penal, não o código-fonte. A métrica certa é perda de informação.
- **`diagnostico.py` audita estrutura (contagem, rubrica), não conteúdo do
  corpo.** O corpus com assinatura/rodapé colada no Art. 361 passava 434/434
  limpo — o defeito estava DENTRO do texto do último chunk, onde a métrica
  não olha. Só apareceu inspecionando `chunk_lei(...)[-1]` na mão.
- **`DELETE` antes de validar que o `INSERT` vai funcionar é perigoso sem
  transação.** `reingest.py` fazia `DELETE FROM chunk` e só DEPOIS calculava
  embedding lote a lote — um erro no meio (aconteceu de verdade: API do
  `pgvector.Vector` mudou entre versões, `.tolist()` deixou de existir)
  deixava o documento com ZERO chunks, sem nada pra reverter, porque
  `autocommit=True` não dá rollback. Pior: a norma que o comando precisa pra
  rodar de novo é inferida DOS CHUNKS que acabaram de sumir — travava
  exatamente no momento em que mais se precisava dele. Corrigido calculando
  tudo antes de tocar no banco, e adicionando `--norma` explícito como saída
  de emergência. `core/embeddings.py` também não fixava `device="cpu"`
  (decisão já documentada em "Pilha"), então uma GPU incompatível com o
  build do torch instalado quebra em runtime em vez de nunca ser tocada.
- **`VAR=valor cmd1 | cmd2` só passa a env var pro PRIMEIRO comando do
  pipe, não pro segundo.** Testando isolamento multiusuário, um
  `CLI_USUARIO_EMAIL=teste printf ... | python chat.py simulado` rodou o
  `chat.py` com o email DEFAULT do `.env` — ou seja, contra o usuário real —
  porque o prefixo só se aplicava ao `printf`. As duas tentativas foram
  registradas na conta real antes de eu notar (progresso divergindo do
  esperado). Corrigido colocando a env var no lado do pipe que efetivamente
  a usa: `printf ... | CLI_USUARIO_EMAIL=teste python chat.py ...`. A
  correção nos dados usou o mesmo método já validado (recomputar `caixa`
  a partir do histórico real de tentativas, não da data de "hoje") —
  restaurado e reverificado byte a byte contra backup antes de continuar.
  Lição: ao testar isolamento entre usuários, um usuário "de teste" com
  `usuario_da_cli()` + `ON DELETE CASCADE` (migração 009) que se apaga com
  um `DELETE` só é mais seguro que confiar em escopo de env var em pipe.
- **`gerar.py` girava pra sempre numa seção, gastando cota real do LLM a
  cada volta, sem NUNCA acionar `MAX_FALHAS`.** Achado gerando questões pra
  CF pela primeira vez (CP não tem artigo baixo o bastante pra expor isso —
  mesma classe de bug já documentada em `retrieval.por_dispositivo()`, LC
  95/1998: Art. 1º-9º levam ordinal, Art. 10+ não). Dois defeitos
  compostos: (1) `salvar()` comparava o artigo cru contra o que o modelo
  devolve — pra "5º", "6º", "8º" o modelo às vezes respondia sem o ordinal,
  então TODA questão da seção era descartada por "proveniência não
  confere"; (2) `falhas` (o contador que decide quando desistir) resetava
  pra 0 sempre que a CHAMADA ao LLM funcionava, mesmo com zero questão
  salva — como a chamada nunca falhava (só o resultado vinha inútil),
  `falhas` nunca chegava em `MAX_FALHAS`, e o loop tentava a MESMA seção
  pra sempre. Rodou ~45 minutos sem salvar nada antes de eu notar que não
  era rede lenta. Corrigido: `_norm_artigo()` tira `[ºo]$` dos dois lados
  antes de comparar (mesma normalização de `retrieval.py`), e `falhas` só
  zera quando `salvar()` de fato salva algo — "a chamada funcionou" e "a
  chamada rendeu progresso" são coisas diferentes, e só a segunda deveria
  resetar o contador de desistência.

- **`@lru_cache` NÃO é trava: ele memoiza o resultado, não protege o corpo.**
  `embeddings._modelo()` era `@lru_cache(maxsize=1)`, e isso pareceu suficiente
  por meses porque nada rodava embedding em paralelo. Subir TRÊS materiais em
  lote pela tela quebrou: `api.py` indexa em `BackgroundTasks` (pool de
  threads), as três threads erraram o cache juntas, as três construíram o
  SentenceTransformer, e duas morreram com `Cannot copy out of meta tensor; no
  data!` — o transformers inicializa os pesos no device `meta` e depois os move,
  e as cargas simultâneas disputam esse estado. Resultado medido: 2 `falha` e 1
  `pronto`, com a razão gravada em `documento.erro` (foi o único motivo de eu
  ter descoberto em vez de achar que o PDF era ruim). Corrigido com dupla
  checagem (`threading.Lock` + global), caminho rápido sem trava. Não é caso só
  do lote: uma pergunta no tutor DURANTE uma indexação chama `embed_consulta` de
  outra thread, então o furo estava no caminho interativo também. **Não
  serializei os `encode`**, e é escolha: uma trava global ali poria a pergunta
  do aluno atrás de um lote de 14 arquivos por dez minutos. `tests/
  test_embeddings_concorrencia.py` trava isso — e o teste foi conferido CONTRA
  o bug (a versão com `lru_cache` constrói 6x na mesma corrida), porque um teste
  de concorrência que não reprova a versão quebrada não está medindo nada.

**Extração de edital: a quebra de linha É o dado, e `_normalizar()` a
destruía antes de qualquer regex rodar.** Achado com um edital REAL
(Dataprev 001/2026, banca FGV) subido pela tela: o painel mostrou 362
tópicos em 4 disciplinas — `Plataforma Básica` (257), `Iof` (100), `Ecf`
(3), `Gestão De Servidores` (2). Nenhuma das quatro é disciplina daquele
concurso. Três defeitos compostos, cada um invisível sozinho:

1. **Cabeçalho sem numeração não era procurado.** `RE_DISCIPLINA` exigia
   "N. DISCIPLINA:" (padrão PC-PR, o único edital que existia quando o
   módulo nasceu). A FGV escreve "LÍNGUA PORTUGUESA:" sem número — ou
   seja, NENHUMA disciplina real era encontrada.
2. **O que entrou no lugar veio de acidente.** Sem âncora de início de
   linha (o `_normalizar()` já tinha colapsado toda quebra em espaço),
   "…Framework version **1.1.** PLATAFORMA BÁSICA:" fez o `1.` de um
   número de VERSÃO virar número de disciplina, e "3. ECF:" / "12. IOF:"
   — itens no meio de um parágrafo de Contabilidade Tributária — viraram
   disciplinas. Começar a linha é o único sinal que separa cabeçalho de
   item no meio de frase, e era exatamente o sinal jogado fora.
3. **Sem recorte, as REGRAS do edital viraram matéria.** Inscrição, prazos
   e recursos são centenas de itens numerados ("4.5.1", "10.13.6"); é daí
   que saíram os 257 tópicos de "Plataforma Básica".

Corrigido: `limpar_paginacao()` -> `recortar_conteudo_programatico()` ->
cabeçalhos NO TEXTO CRU -> normalizar só o corpo de cada bloco -> contar
folhas. Medido contra `tests/fixtures/edital_fgv_dataprev.txt` (trecho real
do PDF, com as quebras de linha como o pypdf entrega): disciplinas reais,
zero fantasma — `Ecf`, `Iof`, `Lalur` e `1988` continuam fora, com teste
nominal pra cada um. (Os números "14 disciplinas, 98 tópicos" que estavam aqui
envelheceram: o fixture foi ATUALIZADO depois pra incluir a mobília de página,
o que mudou as contagens. O número que vale hoje está travado em
`test_cesgranrio_nao_mexeu_nas_outras_duas_bancas`.)

**O passo que quase passou batido foi a mobília de página.** O PDF abre
cada página com "DATAPREV | CONCURSO PÚBLICO 2026" e o número da página
numa linha só dela. Disciplina que calha de começar no topo de uma página
fica precedida por um número solto — e a regra nova de "linha que começa
depois de número pendurado é continuação de frase" a descartava. Efeito
medido: **3 disciplinas somem e os tópicos delas migram pra disciplina
anterior**, com o total continuando plausível. É o pior formato de erro,
porque nenhuma contagem denuncia. Só apareceu porque o fixture foi
ATUALIZADO pra incluir a mobília depois que a primeira versão do conserto
já estava "passando" — fixture limpo demais mente tanto quanto métrica
errada (mesma lição de `diagnostico.py` auditar estrutura e não conteúdo).

**Curadoria antes de virar oficial: subir o PDF cria um RASCUNHO, não um
edital (migração 011).** Um edital tem vários cargos, e cada cargo tem
conteúdo específico próprio. O da Dataprev tem TREZE perfis — ingerir tudo
junto deu "1015 tópicos em 52 disciplinas", com Advocacia, Contabilidade e
Engenharia dentro do plano de quem vai prestar TI. **Somar cargo é pior
que não ler**: vira revisão espaçada de matéria que nunca vai cair na
prova daquela pessoa. Agora `POST /editais/rascunho` extrai pra uma tabela
temporária, a tela mostra os cargos encontrados, a pessoa escolhe um e
ajusta a lista, e só o `confirmar` cria `edital` + `topico`. O erro do
extrator morre na tela, antes de virar agendamento.

O agrupamento por cargo é POSICIONAL, e os dois editais reais concordam:
o conteúdo programático abre com o que vale pra todo mundo ("CONHECIMENTOS
COMUNS PARA TODOS OS CARGOS", "MODULO I ... PARA TODOS OS CARGOS/PERFIS") e
só depois vêm os blocos de cargo. Disciplina antes do primeiro marcador é
comum; depois dele, é do cargo aberto. O marcador é o mesmo `RE_CARGO` pras
duas bancas: "PERFIL 3: X" (FGV) e "CARGO: X" (AOCP).

**O extrator continua sendo o parser; o LLM é FALLBACK.** O parser acerta
os dois layouts que existem em fixture, custa zero cota, roda em
milissegundos e é determinístico — dá pra travar em teste, coisa que
resposta de modelo não dá. `estrutura_com_fallback()` só chama o Gemini
(com `responseSchema`, saída estruturada) quando o parser não achou
disciplina NENHUMA — o sinal honesto de "layout que eu não conheço". O
gatilho é "zero disciplina", não "zero cargo": concurso de cargo único é
legítimo e chamar o modelo nele seria queimar cota pra confirmar o que o
parser já acertou. Falha do LLM não derruba a ingestão: devolve o vazio do
parser e a curadoria vira preenchimento manual.

**Rascunho em Postgres, não em Redis.** É um registro escrito uma vez e
lido duas; não paga uma dependência de infra nova, um processo a mais pra
subir e um modo de falha a mais ("o Redis caiu no meio da curadoria").
`expira_em` faz o trabalho do TTL e sobrevive a restart — que é justamente
quando o TTL em memória perderia o PDF que o usuário já subiu. A estrutura
vai em JSONB porque é dado em TRÂNSITO: normalizar em tabelas seria modelar
o que ainda vai ser editado e descartado.

**Segundo edital real, segunda rodada de zeros: o AOCP (PC-BA) devolveu 0
tópicos em 0 disciplinas.** Duas causas independentes, nenhuma delas
visível no edital anterior:

1. **O ponto depois do número.** A FGV escreve "1 Compreensão"; o AOCP
   escreve "1. Compreensão". `RE_SUBITEM` exigia `\s+` logo após o número,
   batia no ponto e falhava em TODO item do documento. Um caractere.
2. **O edital cita o próprio anexo antes de chegar nele.** "Integram o
   presente Edital: Anexo I - Conteúdos Programáticos", "conforme conteúdo
   programático constante do Anexo I", "salvo se listadas nos conteúdos
   programáticos..." — o recorte pegava a PRIMEIRA menção e cortava um
   pedaço das regras de inscrição; o anexo de verdade nunca era lido.
   Regra nova: a ÚLTIMA menção. Referência cruzada vem antes, o anexo é o
   último. (E o marcador precisou aceitar plural: a FGV escreve "CONTEÚDO
   PROGRAMÁTICO", o AOCP escreve "CONTEÚDOS PROGRAMÁTICOS".)

Aceitar "N." como item abriu um falso positivo novo, resolvido junto:
"...Brasil de 1988. A Constituição do Estado" tem a FORMA exata de um item
(número, ponto, espaço, maiúscula). O que separa os dois é **abrir
oração** — item vem no começo do bloco ou depois de pontuação; "1988" vem
depois de "de ". Sem essa âncora, o ano viraria tópico.

Resultado medido: PC-BA passou de 0 para 86 tópicos em 13 disciplinas
reais, e o edital da FGV continuou correto (14 disciplinas). Conferido
ponta a ponta contra o acervo: a mesa da PC-BA casa 18 questões de Direito
Penal. Lição de método: **cada edital novo é um caso de teste novo** —
dois bastaram pra achar cinco defeitos distintos, e nenhum deles aparecia
no outro. Fixture antes de regex.

**Terceira banca, quarta rodada de defeitos: o Cesgranrio (TRANSPETRO, 33
ênfases) devolvia ZERO cargo, e o que entrava no lugar era pior que vazio.** A
tela mostrava "4 disciplinas · 67 tópicos", duas delas chamadas `I- Matemática`
e `Dados` — que são SUBSEÇÕES de dentro da ênfase de Ciência de Dados,
oferecidas a quem ia prestar outra coisa. Quatro defeitos independentes, nenhum
visível nos dois editais anteriores:

1. **`ÊNFASE 8: CIÊNCIA DE DADOS` é o marcador de cargo desta banca**, o mesmo
   papel de `PERFIL 3:` (FGV) e `CARGO:` (AOCP). Entra em `RE_CARGO` sem
   hesitação porque é o caso que o parser existe pra atender — o edital DIZ onde
   o cargo começa, com marcador literal e numerado. É o oposto do cabeçalho nu
   que fez `RE_CARGO_NU` ser revertida.
2. **O pypdf QUEBRA O NÚMERO**: `ÊNFASE 1 0 :`, `ÊNFASE 1 4:`, `ÊNFASE 2 2:`.
   Com `\d{0,2}`, 12 das 33 casavam e 21 sumiam — e os tópicos da ênfase que não
   casou caem na ANTERIOR, com o total continuando plausível. Mesma classe da
   mobília de página no FGV: o pior formato de erro é o que nenhuma contagem
   denuncia.
3. **Ênfase escrita em PROSA, sem numeração nenhuma.** `RE_SUBITEM` não acha
   nada, e `extrair_estrutura` só aceita disciplina COM tópico — então
   Administração e Advocacia (as duas maiores em conteúdo) saíam com zero de
   tudo, sem nada denunciar, porque as outras 31 enchiam o número.
   `_topicos_por_pontuacao` corta por ponto-e-vírgula (o separador que a banca
   escolheu de propósito) ou por ponto que fecha oração, e **só roda quando não
   há item numerado** — é essa guarda que a torna incapaz de regredir FGV e
   AOCP, que numeram tudo.
4. **Data da prova errada:** a tela dizia "Prova em 2026-12-01" e a prova é
   29/11/2026. 01/12 é o fim do prazo de RECURSO, e o título da seção "DA
   REVISÃO DA NOTA DA PROVA OBJETIVA" cai na janela de 250 caracteres dela —
   empate em 3 a 3 com a data real, resolvido pela ordem no documento (item 9.1
   na página 32, cronograma na 79). "Aplicação da(s) prova(s)" passou a valer 5,
   e recurso, gabarito e revisão SUBTRAEM: marcam prazo SOBRE a prova, não a
   prova. Penalidade e não descarte — cronograma pode nomear as duas linhas
   juntas, e descartar perderia a certa.

**Uma quinta mudança foi TENTADA E REVERTIDA, e vale registrar porque parecia
obviamente certa:** deixar o nome do cabeçalho atravessar uma quebra de linha. O
pypdf devolve `ADMINISTRAÇÃO\nMERCADOLÓGICA:`, e como as classes de caractere
não cruzam `\n`, casava só o RABO — a disciplina virava "Mercadológica", e nome
truncado nunca casa no `mesa.filtro`. Medido, a permissão fez duas coisas
piores: engoliu a seção no nome (`CONHECIMENTOS BÁSICOS\nLÍNGUA PORTUGUESA:`
virou a disciplina "Conhecimentos Básicos Língua Portuguesa") e MATOU UM CARGO —
o nome esticado passa do começo da linha seguinte, e o desempate de `_marcas`
(que descarta marca iniciada antes do fim da anterior) descartava a marca de
ÊNFASE. Cinco ênfases viraram quatro. Reverter devolveu o quinto.

Medido no PDF real (83 páginas): **33 cargos, 2 comuns (Português 12, Inglês 2,
exatos), 237 disciplinas e 1601 tópicos** no total — e escolhendo UMA ênfase na
curadoria, "Análise de Sistemas – Segurança Cibernética", o edital gravado tem 5
disciplinas e 37 tópicos: Português, Inglês, Segurança Ofensiva, Segurança
Defensiva e Compliance. Sem tocar no LLM (`origem: parser`, zero cota). FGV e
AOCP conferidos byte a byte contra o HEAD antes e depois: **idênticos** (4
cargos/20 disciplinas/104 tópicos e 2/13/86), e há teste travando esses números
justamente porque cada regex nova neste módulo quebrou o edital anterior.

E uma armadilha de MÉTODO, que custou tempo e quase virou medição falsa: o
script que montou o fixture usava `txt.index("ÊNFASE 8: ...")` sem âncora e achou
a ocorrência do **Anexo III** (requisitos e atribuições) em vez do **Anexo IV**
(conteúdos programáticos) — o mesmo texto de cabeçalho existe nos dois. Pior: o
script abortou numa exceção ANTES de gravar, então o arquivo ficou sendo a versão
velha e três medições seguintes mediram outra coisa. Fixture se confere abrindo,
não presumindo.

**O produto NÃO é só para Direito.** O filtro da mesa é por NOME de
disciplina e funciona igual pra TI, bancária, fiscal ou policial — o que
limita é só o que já foi ingerido no acervo. Uma mesa de TI num acervo de
Direito bate zero questão, e isso é verdade, não defeito; mas a tela agora
DIZ ("o acervo ainda não tem questões dessas disciplinas") em vez de
mostrar "0/0" calado, que parece bug.

**Nome do edital: o arquivo TEMPORÁRIO do servidor vazou pro banco.**
`POST /edital` grava o upload num `NamedTemporaryFile` e passava esse
caminho pra `edital.ingerir()`, cujo fallback de título é o nome do
arquivo — então o edital virou "tmpcmrpqinr" no banco e na tela. O
fallback certo na borda HTTP é `UploadFile.filename` (o nome que o usuário
enviou); o `stem` do caminho só faz sentido na CLI, onde o caminho é um
arquivo de verdade. Classe de erro a procurar em qualquer rota que grave
upload: caminho interno do servidor não é dado do usuário.

---

## A questão passou a sair da apostila (026)

**O relato.** "O ideal não seria pegar dos dois lugares? Se você está trazendo a
fonte de um lugar, o certo é trazer questões dali também." O tutor explicava
traumatologia forense pela aula da professora — `socratic.explicar` sempre leu a
biblioteca privada — e, na hora de treinar, gerava questão de Direito Penal.

**A causa era uma linha.** `geracao.FILTRO_UTIL` exigia `c.artigo IS NOT NULL`, e
chunk de apostila é janela de texto: não tem artigo. A apostila era ingerável
por definição, porque a proveniência (`questao.fonte_chunks`) era casada pelo
ARTIGO que o modelo dizia ter usado. Sem artigo, todo candidato caía no descarte
"artigo None não está no lote".

**Por que não bastava tirar a linha.** `questao` era acervo estritamente
compartilhado (008, sem `usuario_id`). Gerar da apostila enfiaria o material
pago de um aluno no banco de questões de todos, com proveniência apontando pra
um chunk que os outros não podem ler. O comentário que dizia isso estava no
código e estava certo — o que ele descrevia não era uma escolha de gosto, era a
consequência de a tabela não ter dono.

**A 026 removeu a causa, não o sintoma:** `questao.usuario_id`, NULL = público
como sempre, preenchido = privado daquele aluno. Duas decisões sustentam o
resto:

1. **O dono sai do CHUNK, nunca de parâmetro** (`geracao.salvar`). É o mesmo
   raciocínio de `documento_id` e `disciplina`, com mais consequência: com
   parâmetro existiria a chamada que grava apostila como pública por
   esquecimento, e o esquecimento aqui é vazamento. Derivado do chunk, a
   chamada errada não existe.
2. **O predicado mora num lugar só** (`questoes.do_aluno()`), como
   `mesa.filtro()`. Aqui divergir entre duas cópias não devolve número errado:
   devolve o material de outra pessoa. Toda consulta que escolhe questão de um
   POOL passa por ele — fila, desafio, simulado, lookup por id, cobertura da
   mesa, cobertura do edital, geração. Consulta que sai de
   `progresso`/`tentativa`/`erro_caderno` não precisa, porque aquelas tabelas
   já são por usuário; `test_questao_da_apostila.py` enumera as rotas em vez de
   checar uma, porque o valor do teste é ser a LISTA.

**Uma brecha latente fechou de lado.** O filtro antigo aceitava qualquer chunk
com artigo, e apostila cujo PDF traz "Art. N" é fatiada por artigo — 543 chunks
assim no banco de desenvolvimento. `_por_disciplina` não olhava dono nenhum:
bastava a apostila cair no recorte da mesa pra virar questão PÚBLICA. Nunca
aconteceu (conferido: zero questões de documento privado antes da mudança),
porque a busca por tema não abria a biblioteca. Era um `AND` de distância.

### Proveniência sem artigo: o número do trecho

`retrieval.formatar_numerado` numera os excertos do lote e o modelo devolve
`trecho: N`. Não é o modelo dizendo onde estava — é escolhendo entre o que nós
mandamos, então número fora da faixa é descarte, igual a artigo fora do lote.
Ficou separado de `formatar_contexto` de propósito: numerar o prompt do tutor
seria ruído, e mexer naquela função mexe na regra de citação
(`limpar_citacoes`), onde este projeto já se queimou.

**A ORDEM das duas chaves é a decisão inteira, e ela foi medida.** Primeira
rodada real com o Gemini, pedidas 3 questões sobre "lesão corporal grave": o
lote veio todo da apostila e o modelo devolveu `artigo: "129"` em duas delas —
porque a aula TRANSCREVE o art. 129. As duas foram descartadas por "artigo não
está no lote", e eram boas. Ali o campo `artigo` não é proveniência, é CONTEÚDO
do material. Então: **trecho apontando chunk sem artigo manda, inclusive sobre
um `artigo` que o modelo tenha preenchido**; nada se perde, porque `salvar` não
guarda `artigo` em coluna alguma. O prompt já manda deixar o campo vazio nesse
caso e o modelo preenche mesmo assim — situação exata em que este projeto decide
no código.

O que a ordem NÃO permite: trecho apontando LEI sem citar o artigo é descarte.
Sem essa trava, o número seria o jeito de gravar questão de dispositivo sem
dizer qual — o afrouxamento que o módulo existe pra não fazer, entrando pela
porta lateral. Depois do conserto: 3 de 3 gravadas, zero descartes.

### "Dos dois lugares" precisou de mais que abrir a porta

Aberta a apostila, o pêndulo foi todo pro outro lado. Medido, tema "lesão
corporal grave: conceito e classificação" com a biblioteca indexada: **os 24
primeiros colocados são todos da apostila e o art. 129 não aparece em nenhuma
posição**. A causa é a 025 — o rótulo do material entrou no tsvector —, e ela
está certa: é o que faz "traumatologia forense" achar a aula. O efeito colateral
é aritmético: um rótulo repetido em 78 chunks produz 78 acertos lexicais, e o
único artigo sobre o assunto não tem como competir.

Duas peças, e a segunda é a que quase deu errado:

**`_misturar` reserva uma vaga pra cada lado** — mínimo, não cota. O primeiro
colocado da busca nunca perde a vaga (é a trava que devolveu "concussão" pra
quem pediu concussão); o lado ausente entra na ÚLTIMA. Pedido de 1 questão não
mistura, e assunto que existe num lugar só sai inteiro dali: reservar vaga pra
lado sem candidato devolveria menos questão do que o aluno pediu. Função pura,
cinco casos em tabela.

**`_lei_do_assunto` é o reforço, e ele precisou de trava.** A mistura não tinha
o que misturar: sem candidato de lei no pool, não há vaga a preencher. Uma
segunda busca, só no acervo público, resolve — mas a busca pública devolve
alguma coisa pra QUALQUER pergunta, porque é ranking, não julgamento. Medido:

| consulta | 1º colocado público | veredito |
|---|---|---|
| `peculato` | CP 312 Peculato | certo |
| `lesão corporal grave` | CP 129 Lesão corporal | certo |
| `lesão corporal grave: conceito e classificação` | CP 131 Perigo de contágio | **errado** (o 129 caiu pra 2º com o sufixo) |
| `asfixiologia forense: mecanismos de asfixia mecânica` | CP 252 Uso de gás asfixiante | **errado**, e não existe artigo do assunto |

Aceitar o 1º colocado teria recriado a reclamação original — "trouxe questões
aleatórias de outro assunto" — agora do lado da lei. A trava é a RUBRICA
compartilhar palavra de conteúdo com o tema, e **por CONTAGEM, não por
booleano**: "Perigo de contágio de moléstia GRAVE" passa o teste de "alguma
palavra" por causa de um adjetivo, e vinha à frente de "LESÃO CORPORAL", que
casa duas. Ordenar pela contagem põe o certo na frente sem que ninguém precise
decidir que "grave" é palavra fraca — a alternativa era mais uma palavra na
lista `VAZIAS`, o remendo que `core/assunto.py` já documenta como o que nunca
acaba.

`por_rubrica`, que existe e é a estratégia precisa, não serve de trava: exige
TODOS os termos da consulta na rubrica (`websearch_to_tsquery` é AND), então
"lesão corporal grave" não casa "Lesão corporal" por causa do "grave" — medido,
devolve vazio. Sobreposição de palavras é o mesmo espírito com o limiar no lugar
certo.

Sete de sete corretos depois disso, e o resultado ponta a ponta:

```
lesão corporal grave      -> 1 da apostila + 2 do CP art. 129   (os dois lugares)
asfixiologia forense      -> 3 da apostila, ZERO de lei         (a lei não trata)
```

O segundo caso é o que prova a trava: sem ela, o aluno receberia questão de
"uso de gás tóxico" estudando asfixiologia forense.

### A assimetria é medida, não estética

Só a LEI leva reforço. O material afoga, nunca falta — se ele não apareceu na
busca é porque não existe material do assunto, e aí não há o que reforçar.
Custo do reforço: uma consulta de busca a mais, e só quando a lei ficou de
fora. Zero chamadas de LLM.

### O que a 026 quebrou nos TESTES, e a lição repetida

Sete testes de `test_mesa_api.py` caíram de uma vez, todos afirmando coisas
certas. A fixture `duas_disciplinas` fazia `SELECT DISTINCT disciplina FROM
questao` sem filtro de dono, e minhas questões privadas de Criminalística
entraram nela — disciplina com dezenas de questões PRIVADAS e zero públicas.

É a MESMA classe já documentada em `test_geracao._disciplina_do_acervo` (o
`LIMIT 1` sem `ORDER BY` nem filtro de dono, que quebrava na segunda execução
no mesmo banco). Fixture que diz "uma questão do acervo" tem de dizer QUAL
acervo. Fechadas todas: `conftest.questao_id`, `duas_questoes`,
`test_intervencao`, `test_desafio_orcamento`, `test_conversa`, `test_mesa_api`,
e `semear_demo.py` — a conta de demonstração pegaria questão da apostila de
outro aluno e mostraria material privado alheio na tela.

### A sincronização leva questão privada como PRIVADA

`sincronizar.py` já exportava material privado com o PDF (decisão anterior). A
questão gerada dele viaja no mesmo pacote, com o email do dono; importar como
pública a publicaria no acervo comum da outra máquina, com trecho de material
pago dentro do enunciado. Questão privada cujo dono não existe no banco de
destino é PULADA e reportada — publicá-la resolveria o número e vazaria o
material. Pacote da era anterior à 026 não tem o campo: entra público, que é o
que ele era. Conferido exportando de verdade: 259 questões, 13 marcadas com
dono, as públicas com `usuario: null`. Sem cobertura de teste automatizado — o
`sincronizar` não tem suíte.

---

## "Jurisprudência não deve ser fragmentada" (027)

**O relato, com a evidência na tela.** O aluno indexou a Constituição pelo link
do Planalto, marcada como jurisprudência, e a tela mostrou:

```
Direito Constitucional
  Princípios fundamentais e direitos e garantias fundamentais
  constituicao.txt · 543 trechos · eu deduzi, confira
```

O argumento dele: "jurisprudência não deve ser fragmentada, é simplesmente um
poço de informações que serve de auxiliar complementar aos PDFs; ele deveria
estar separado ali embaixo para diferenciar do material de aula. Até porque se
fôssemos criar assunto da CF, iríamos ter que criar uma quantidade imensurável
de assuntos, e bem mais do que os 3 que você mapeou."

**Estava certo, e o problema era maior do que arrumação de tela.**
`classificar()` lê só `texto[:MAX_CHARS_CLASSE]` — o COMEÇO do material. O
começo da CF é o Preâmbulo, o Título I (Dos princípios fundamentais) e o Título
II (Dos direitos e garantias fundamentais); daí o rótulo. Plausível, e falso
para 543 artigos.

E `assunto` não é rótulo de tela: ele vai pro texto que virou embedding e,
desde a 025, pro tsvector de CADA trecho (`chunk.rotulo`). Um assunto falso
repetido em mil trechos casa lexicalmente com qualquer consulta constitucional.
Medido, com a biblioteca dele:

| consulta | antes |
|---|---|
| `princípios fundamentais do direito administrativo` | a cópia leva **6 de 6**: art. 88, art. 39, art. 234, art. 18, art. 133, art. 24 |
| `direitos e garantias fundamentais: remédios constitucionais` | art. 196 (saúde), art. 54-A, art. 157, art. 197, art. 55, art. 83 |

Relevância decidida por ruído. **E este é o mecanismo do defeito antigo "as
cópias da CF do aluno passam na frente da CF oficial"**, que estava em
LIMITACOES sem causa identificada: não era ser cópia, era o rótulo mentiroso
repetido mil vezes.

### A regra

`assunto` é rótulo de AULA: o título de uma coisa só ("Traumatologia forense",
"Lesão corporal"), e é o que faz a busca achar a aula 12 quando se pergunta de
asfixiologia (020/025). Poço de consulta não tem um. `material.e_referencia()`
decide por duas evidências, qualquer uma bastando: o TIPO escolhido
(`jurisprudencia`) e o material ter sido fatiado por artigo — corpus de norma
inteira, independentemente do que o aluno marcou no seletor.

Material de referência não perde nada: cada trecho já tem `artigo` e `rubrica`,
rótulos PRECISOS por trecho, melhores que um assunto único.

**O descarte fica no CÓDIGO, não só no prompt.** `classificar(...,
com_assunto=False)` manda o modelo não devolver assunto E o campo é descartado
na volta — o modelo preenche mesmo mandado não preencher, e é a doutrina do
projeto (`limpar_citacoes`, `limpar_questoes`) aplicada de novo.

### A disciplina também sai do rótulo, e isso foi a segunda medição

A primeira versão da 027 mantinha a disciplina em `chunk.rotulo`, com o
argumento de que ela é VERDADE nos 543 trechos (é tudo Direito
Constitucional). É verdade e não bastou: medido depois, a cópia ainda levava 5
de 5 em "direitos e garantias fundamentais: remédios constitucionais" (art. 6
dos direitos sociais, art. 196 da saúde), enquanto a CF oficial, com os MESMOS
artigos, não aparecia. "Direito Constitucional" casa "direitos"/"constitucionais"
em todos os trechos, e o trecho oficial tem `rotulo` NULL.

Num corpus de norma inteira o rótulo não DISTINGUE trecho nenhum — só
multiplica por mil um acerto que não informa nada. `documento.disciplina` fica
(dela saem o recorte da mesa e o agrupamento da tela); o que sai é a injeção
por trecho. **Cópia da CF passa a se comportar como a CF.**

O que a 025 comprou é outra coisa: o rótulo do material de AULA, onde ele
distingue a aula 12 da aula 3. Aquela medição segue de pé — "traumatologia
forense" e "asfixiologia" continuam devolvendo a aula nas cinco primeiras
posições.

### Depois

| consulta | depois |
|---|---|
| `princípios fundamentais do direito administrativo` | **CF oficial em 1º** (art. 5º), oficial também em 3º |
| `habeas corpus` | **4 de 5 oficiais** (CPP 654, 667, 656, 647-A) |
| `traumatologia forense` / `asfixiologia` | a aula em 1º — o ganho da 025 preservado |
| `direitos e garantias fundamentais: remédios constitucionais` | ainda ruim, e agora por outro motivo: a CF nunca escreve "remédios constitucionais" — é o teto de doutrina já medido, não efeito do rótulo |

### Na tela

Duas listas. Material de estudo agrupado por matéria, como antes; material de
consulta numa seção própria, DEPOIS, sem grupo e sem assunto, com uma linha
dizendo o que é. O campo de assunto também não é oferecido na edição inline de
material de referência: ele seria descartado na indexação, e campo que promete
efeito inexistente é pior que campo ausente.

Quem decide é o backend, pelo campo `referencia` de `material.listar()`: o
front não tem como saber que um PDF virou 543 artigos, e reimplementar a regra
lá seria a segunda cópia dela.

---

## Dois indexadores no mesmo documento apagaram a Constituição de um aluno

**Achado ao consertar a 027**, e é independente dela. Reindexei o documento
1495 por um comando de manutenção enquanto o `uvicorn --reload` do aluno estava
de pé. `uvicorn --reload` chama `material.retomar_pendentes()` a cada boot, e o
documento estava `processando`. Os dois trabalhadores rodaram `indexar()` em
paralelo:

```
erro: falhou ao indexar: duplicate key value violates unique constraint
      "chunk_documento_id_ordem_key"
DETAIL: Key (documento_id, ordem)=(1495, 0) already exists.
```

Resultado: `status='falha'` e **ZERO trechos**. A Constituição inteira do aluno,
invisível pra busca, por um comando de manutenção que só queria reindexar.

**Por que as duas defesas que existiam não pegaram:**

- a **idempotência** do `DELETE FROM chunk` antes de inserir é real e cobre duas
  passadas em SEQUÊNCIA. O problema é o paralelo: os dois apagaram, os dois
  começaram a inserir;
- a **fila com um trabalhador** — a que resolveu a queda no upload de 20 PDFs —
  é do PROCESSO. Dois processos têm duas filas e nenhum coordena com o outro.

A coordenação tem de estar no único lugar que os dois compartilham: o banco.
`pg_try_advisory_lock(TRAVA_INDEXACAO, documento_id)`, sem espera — quem perde a
corrida DESISTE, porque quem ganhou vai fazer exatamente o mesmo trabalho. Lock
de sessão, então sai sozinho quando a conexão fecha, inclusive se o processo
morrer no meio.

O teste (`test_dois_indexadores_no_mesmo_documento_nao_se_atropelam`) sobe
material, dispara duas threads chamando `indexar` no mesmo documento e afirma o
número de trechos no fim. Verificado que ele PEGA o defeito: desligando o lock,
falha com o mesmo `duplicate key ... ordem)=(…, 0)`.

**O LOCK NÃO DESFAZ O DANO JÁ FEITO, e havia dano.** Achado depois, olhando a
biblioteca do aluno inteira: TRÊS materiais estavam quebrados pelo mesmo erro,
de antes do lock existir.

```
856  falha        62/62   "duplicate key ... ordem)=(856, 32)"   Medicina Legal
849  processando 224/233  (preso no meio)                        Traumatologia forense
842  falha       192/340  "duplicate key ... ordem)=(842, 0)"    (sem classificar)
```

O 856 estava COMPLETO e marcado como falha — a tela dizia "Falha na leitura"
para material que funcionava (apareceu numa captura de tela do aluno, e foi
assim que dei com os outros dois). Os outros dois estavam pela metade: 224 de
233 e 192 de 340 trechos, calados. O 842 nunca chegou a ser classificado, então
estava no grupo "Outros" sem disciplina nem assunto.

Reparados reindexando um por um. Quem procurar por esta classe de dano depois:

```sql
SELECT d.id, d.status, d.chunks_total,
       (SELECT count(*) FROM chunk c WHERE c.documento_id = d.id) AS reais
  FROM documento d
 WHERE d.usuario_id IS NOT NULL
   AND (d.status <> 'pronto'
        OR (SELECT count(*) FROM chunk c WHERE c.documento_id = d.id) <> d.chunks_total);
```

**E uma coisa a saber ao consertar isto com o servidor de pé:** `uvicorn
--reload` reinicia a cada edição em `core/*.py` e chama `retomar_pendentes()` no
startup. Ou seja, editar `material.py` durante o reparo põe um SEGUNDO indexador
para trabalhar — o que agora é seguro (um pega o lock, o outro desiste e diz
isso no log) mas não é grátis: dois processos calculando embedding numa máquina
de 8 GB derrubaram um `pytest` inteiro por OOM (exit 137). Reparo grande: pare o
servidor, ou faça um documento por vez e espere.

**De passagem, um número que a tela mostrava errado:** `chunks_total` é gravado
em `registrar` e nunca era reescrito. A CF tinha 1074 (janelas genéricas de uma
versão anterior de `_dividir`) e reindexou pra 543 artigos, então a tela dizia
"543 de 1074" pra material completo — que parece indexação travada. O
denominador passa a vir de quem acabou de contar.

### Três ajustes de tela em cima da 027

**A separação virou ABA, não seção no rodapé.** A primeira versão punha a
consulta depois dos grupos, e o relato foi imediato: "não gostei dessa visão,
eu tenho que rolar até lá embaixo pra poder ver; seria melhor separar eles logo
no começo". Certo, e a razão é do tamanho do dado: 18 apostilas em 5 grupos
empurram qualquer coisa que venha depois pra fora da tela. **Separação que só
existe depois de rolar não separa — esconde.** As abas aparecem só quando há
material de consulta (aba solitária não é escolha) e trazem a contagem no
rótulo, pra dizer que existe algo do outro lado antes de alguém clicar pra
descobrir.

**O interruptor "usar meu edital" passou a mandar na sugestão de RENOMEAR.**
Pedido: "o botão de usar meu edital também deve servir pra dar sugestão para a
alteração da matéria". Duas coisas mudaram, e a segunda era a que faltava de
verdade:

- o campo de renomear em lote era um `<input>` pelado, sem sugestão nenhuma. É
  o pior lugar possível pra isso: a renomeação em lote existe justamente pra
  unificar "Criminalística" e "Ciências Forenses", e digitar o nome à mão é o
  convite pra criar uma TERCEIRA grafia — o problema que ela veio resolver.
  Virou `Seletor`;
- o interruptor manda na ORDEM da lista, não no conteúdo. A decisão anterior
  ("no lápis não há toggle") fica de pé na parte que importa: as duas fontes
  continuam entrando juntas, senão renomear pra um nome que você JÁ usa
  exigiria descobrir que existe um interruptor no outro canto da tela. O que
  muda é qual lado vem primeiro, que é o que "dar sugestão" quer dizer numa
  lista. Sem `.sort()` no fim, que desfaria a preferência recém-expressa.

**O clique que "pegava no iconezinho": `<button>` dentro de `<label>`.** O
interruptor era um botão dentro do `<label>` do campo de disciplina. Clicar em
qualquer lugar de um label dispara o comportamento de ativação dele — o foco
vai pro controle rotulado —, então cada clique no interruptor também focava e
abria o campo de disciplina, e o contorno de foco ficava aceso no lugar errado.
Controle interativo dentro de label é sempre isso: dois efeitos num clique, e o
segundo ninguém pediu. O `<label>` virou `<div>`; o campo não perde
acessibilidade porque o `Seletor` já recebe `aria`, que é o nome acessível dele
— o label ali era decoração de layout.

**Classe de erro pra procurar:** qualquer `<label>` que envolva mais que o
próprio campo. Nesta tela havia três, e só o de Disciplina tinha botão dentro.

### As abas passaram a ser por TIPO, e a lição é sobre vocabulário

"Ainda tá faltando o botão de Jurisprudência?"

Cinco palavras desfazendo uma decisão minha. Eu tinha derivado a separação num
conceito PRÓPRIO — "material de estudo × poço de consulta" — e batizado as abas
de "aulas e resumos" e "consulta e apoio". O conceito está certo (é ele que
governa a regra do assunto, no backend, e continua governando), mas ele é MEU.
O aluno pensa nos três tipos que ele mesmo escolhe no seletor ao subir o
arquivo: aula, resumo, jurisprudência. Procurou "Jurisprudência" na tela e não
achou — porque eu tinha traduzido o nome dele para o meu.

As abas agora saem de `TIPOS`, a MESMA constante que alimenta o seletor do
formulário: os dois lugares dizem "Jurisprudência" porque leem o mesmo rótulo,
e não porque alguém lembrou de escrever igual nos dois. Só aparecem os tipos
que têm material (aba vazia é promessa de conteúdo que não existe, e com três
tipos fixos duas ficariam vazias na conta normal), e a aba efetiva cai na
primeira com conteúdo se a selecionada esvaziar — aba selecionada mostrando
lista vazia parece biblioteca vazia.

**A regra de dado NÃO virou "tipo".** Continua sendo `material.e_referencia()`,
que também pega material fatiado por artigo — uma lei subida como "Aula /
apostila" é corpus de norma independentemente do seletor, e é dela que o
assunto tem de sair. Só a NAVEGAÇÃO é por tipo. Isso cria um caso que a tela
tem de explicar: essa lei aparece na aba "Aula / apostila", sem assunto, do
lado de treze aulas que têm um. A linha do material ganhou " · consulta" pra
esse caso — e só pra ele, porque na aba de Jurisprudência o cabeçalho já diz
isso e repetir é ruído.

**Lição:** conceito interno bom não é nome de botão. O nome do botão é a palavra
que o usuário já usou em outro lugar do produto — de preferência lida da mesma
constante, pra não poder divergir.

**E as TRÊS abas aparecem, inclusive a que está em zero.** Escondi a vazia na
primeira versão, argumentando que aba vazia é promessa de conteúdo que não
existe. O relato desfez, com o seletor de Tipo (três opções) e as abas (duas)
lado a lado na mesma captura: "o que eu pedi foi que agrupasse os 3 tópicos
também ali embaixo".

O argumento dele é melhor. As abas ESPELHAM o seletor: se o seletor oferece três
tipos e a lista mostra dois, o terceiro parece não existir — e ele existe, só
está vazio. Aba em zero informa; aba ausente esconde. A contagem em zero fica
mais apagada (`opacity-35`) pra a aba cheia continuar sendo a óbvia, e a aba
vazia diz o que fazer em vez de ficar em branco ("escolha esse tipo lá em cima
antes de arrastar o arquivo") — lista vazia sem explicação parece defeito de
carregamento.

### "Não consigo saber" é um defeito, mesmo quando a resposta é "está limpo"

Relato: "eu apaguei o material de jurisprudência, mas ficou ainda algum rastro
do link da CF que ele mapeou como aula, porém eu não consigo saber, ele não me
dá essa informação."

Conferido no banco: **não havia rastro.** 18 documentos, todos `aula`, nenhum
fatiado por artigo, zero trechos órfãos, nenhuma cópia de norma na conta. A
exclusão tinha funcionado inteira.

E ainda assim o relato é procedente, o que é o ponto: **o defeito era a tela não
saber dizer NEM que estava limpo NEM que não.** A pessoa apaga uma cópia de lei
— que ela sabe ter degradado a busca — e fica sem como verificar, com 18 linhas
espalhadas em três abas pra varrer à mão. Ausência de aviso não é prova de nada.

Duas coisas mudaram:

**Uma linha de resumo do acervo**, sempre visível: "18 materiais · 2.060 trechos
· nenhuma cópia de lei aqui" (verde), ou "1 cópia de lei (constituicao.txt) —
ela compete com a lei oficial na busca" (rubro), nomeando os arquivos. Aparece
nos DOIS casos, e é isso que a torna informação: um aviso que só existe quando
há problema não permite concluir nada quando está ausente.

O sinal é `fatiado_por_artigo` (novo em `material.listar`), e não o tipo que a
pessoa escolheu no seletor — a CF colada pelo link virou "aula" e continuava
sendo lei dividida em 543 artigos. Separado de `referencia` porque responde
outra pergunta: `referencia` é "como a tela deve tratar isto",
`fatiado_por_artigo` é "isto é uma cópia de lei".

**E o TEMPO VERBAL da recusa.** A mensagem de duplicata dizia "subir uma cópia
não acrescenta nada e piora a busca, porque as duas versões competem". Presente.
O aluno tinha ACABADO de apagar a cópia dele, colou o link de novo pra
conferir, leu "as duas versões competem" e entendeu que havia sobrado rastro —
razoavelmente. Recusa fala do que ACONTECERIA; no presente ela afirma um fato
sobre o acervo que não verificou. Agora abre com "não subi:" e termina com "nada
foi gravado e a sua biblioteca continua como estava".

**Classe de erro pra procurar:** mensagem de recusa escrita no presente do
indicativo. Ela descreve um mundo que a recusa acabou de impedir de existir.

**E ainda não era isso.** Reescrita a mensagem, o relato voltou: "o problema
continua e ainda não mostra qual arquivo tá com o link". Duas coisas erradas de
uma vez, e nenhuma era a que eu tinha consertado:

1. **"acervo do app" foi lido como "a minha biblioteca".** A recusa dizia "esta
   lei já está no acervo do app (CF)" e não dizia ONDE — então a pessoa foi
   procurar o arquivo culpado na lista dela. Não havia arquivo dela: o que
   existe é a CF OFICIAL que o app já traz ingerida por artigo, e da qual não há
   nada pra apagar. Mensagem que aponta um conflito sem dizer com QUEM manda
   procurar o culpado na lista errada. Agora abre com "não subi, e não é nada
   que você tenha na biblioteca: esta lei JÁ VEM COM O APP (CF — 276 artigos,
   já ingerida pelo próprio app)... não há arquivo seu envolvido nem nada pra
   apagar."

2. **"qual arquivo tá com o link" era uma informação que o sistema nunca
   guardou** — e essa é a migração 028. `POST /materiais/link` chama
   `material.baixar(url)`, que devolve um NOME derivado do endereço, e é esse
   nome que vai pra `documento.origem`. A URL morria ali: do banco em diante,
   material vindo de link era indistinguível de arquivo arrastado com o mesmo
   nome, e "constituicao.txt" não diz que veio do Planalto.

   Coluna nova e não reuso de `origem`, porque `origem` tem função ativa:
   `indexar` o devolve pro `_extrair`, que escolhe o leitor pela EXTENSÃO.
   Guardar URL ali quebraria a reextração de todo material de link — e
   silenciosamente, no reindex, não no upload. Sem backfill possível: a URL do
   material já existente não foi guardada em lugar nenhum.

   Na tela, a linha do material mostra o HOST como link (`planalto.gov.br`), com
   a URL inteira no `title` e no `href` — a linha é monoespaçada e estreita, e
   60 caracteres de endereço empurrariam o resto pro truncamento.

**De passagem, uma inconsistência achada pelo teste:** a rota de link passava
`titulo=nome`, o que pulava a tira-extensão do `registrar`. Material de link
ficava titulado "constituicao.txt" ao lado de "aula-local" — mesma origem (um
nome de arquivo), dois resultados na tela.

(De passagem: a aba vazia mostrava DUAS mensagens — o estado vazio e a
explicação do que é material de referência. Agora a explicação só sai quando há
algo pra explicar.)

### O interruptor FILTRA, e essa foi a terceira tentativa

Três versões do mesmo campo, cada correção mais direta que a anterior:

1. **as duas fontes juntas, interruptor sem efeito no lápis.** Argumento meu:
   esconder metade das grafias atrás de um botão de modo faria a correção
   depender de um estado no outro canto da tela;
2. **as duas juntas, interruptor mandando na ORDEM.** Resposta: "eu marquei usar
   sugestões daqui e ainda assim ele tá trazendo somente o do edital";
3. **uma fonte por vez, a que o interruptor diz.**

A objeção do item 1 continuou verdadeira e deixou de importar, e é isso que
faltava eu ver: o campo é LIVRE — qualquer nome pode ser digitado, esteja ou não
na lista. Nada fica inalcançável. O que a filtragem tira é a lista misturar
justamente o que o interruptor acabou de dizer para não usar.

**Interruptor que só reordena é interruptor que não obedece.** Ele promete duas
fontes exclusivas ("usar meu edital" × "usar sugestões daqui"), e uma promessa
de exclusividade cumprida como preferência de ordenação é lida como defeito —
corretamente. Se as duas fontes tivessem de aparecer juntas, o controle não
devia ser um interruptor de modo.

Sobrou uma constante só (`opcoesDiscEdicao = opcoesDisc`): dois lugares que
dizem "sugestões daqui" não podem sugerir coisas diferentes.

### E o campo de renomear vinha PREENCHIDO, o que matava a lista

Relatado na mensagem seguinte, em duas frases que pareciam dois defeitos: "já
traga todos os tipos de material ali, tá faltando jurisprudência" e "minha
matéria não tá pegando sugestão de nenhum dos dois".

Uma causa só, e minha: eu pré-preenchia o campo com o nome atual
(`setNomeNovo(disc)`), e o `Seletor` FILTRA a lista pelo que está digitado — o
que é bom e existe por medição (com 11 matérias, digitar três letras é melhor
que rolar). Com "Criminalística" dentro do campo, a lista filtrava até sobrar
"Criminalística": **a única sugestão visível era justamente o nome que a pessoa
quer trocar.** E "Direito Constitucional" — a disciplina do material de
jurisprudência — nunca aparecia, daí a primeira frase.

Conferido antes de mexer, pra não consertar o lugar errado: o backend devolvia
as quatro disciplinas da biblioteca (`Criminalística`, `Direito
Constitucional`, `Direito Penal`, `Direito Processual Penal`) mais as sete do
edital. O dado estava certo; a tela é que o escondia.

O campo passa a nascer VAZIO, com o nome atual no placeholder ("renomear
Criminalística para…") — ele já está no cabeçalho ao lado, e repeti-lo dentro
do campo custava a lista inteira. O botão "Renomear" fica desabilitado enquanto
não há nome novo: com o campo vazio o clique não fazia nada e parecia quebrado.

**Lição geral, que vale pra qualquer combobox com filtro:** pré-preencher com o
valor atual e filtrar pelo que está escrito são duas decisões boas que se
anulam. Escolha uma.

---

## `sincronizar.sh`: onde o hook avisa, o script para

Pergunta que originou: "quando eu der um pull, eu tenho que rodar qual comando
pra atualizar minha máquina?". A resposta era `./setup.sh --subir`, e a resposta
seguinte foi "coloca tudo num sincronizar.sh".

**A automação já existia, e continua sendo o caminho principal.** `.githooks/`
tem `pre-push` (exporta e manda o estado num ref próprio) e `post-merge` (traz o
ref, migra, importa em duas fases, indexa o material em segundo plano). O script
NÃO reimplementa nada disso — ele faz `source` do `_comum.sh` e chama
`estado_enviar` / `estado_receber`, as mesmas funções.

**O que ele acrescenta é um portão onde o hook tem um aviso.** A decisão dos
hooks está certa e é explícita no código deles: "falha aqui NUNCA derruba a
operação do git, porque banco desligado não pode impedir commit". A consequência
é que um `git pull` com migração pendente imprime

```
  [tutor] migracao pendente nao aplicada — rode ./setup.sh --subir
```

no meio da saída do git, e segue. A linha passa batida, o código novo conversa
com o schema velho, e a aplicação SOBE pra quebrar depois — exatamente o modo de
falha que a migração 023 existe pra fechar. No script a mesma falha para o
comando, com a razão e o próximo passo. É a diferença entre um aviso e um
portão, e é a única justificativa dele existir.

Três decisões pequenas dentro:

- **`git pull --ff-only`.** Merge automático nas costas de quem chamou um script
  de conveniência é a última coisa que ele deve fazer. Divergência para, dizendo
  qual comando resolve.
- **O estado vai sozinho; o CÓDIGO pergunta.** `--sair` manda o estado sem
  perguntar (é rotina de dado, e o hook faria igual), mas commit de código não:
  publicar código é decisão de quem escreveu. E a pergunta só acontece com
  terminal (`[ -t 0 ]`) — sem TTY o `read` falha, e com `set -e` isso abortaria
  o script DEPOIS de o estado já ter subido, parando no meio da única parte que
  não se repete de graça.
- **Um relatório de pendências no fim.** Duas coisas terminam em segundo plano
  aqui: o embedding do material que veio no pacote e a reindexação que a 027
  pede. Sem essa linha, "acabou" e "está trabalhando" ficam iguais na tela.

### Dois defeitos no próprio script, achados rodando

**Backtick dentro de aspas duplas EXECUTA.** Duas mensagens de erro tinham
`` `git rebase` `` e `` `docker compose logs` `` entre aspas duplas — a de
divergência rodaria `git rebase` de verdade, dentro da mensagem que explica a
divergência. Trocadas por aspas simples. Vale como classe: crase em mensagem de
shell é código, não tipografia.

**Heredoc de Python rodando da raiz.** A contagem de material pendente saía como
`?` porque `from core import db` só resolve em `apps/api` — e `load_dotenv()`
procura do diretório ATUAL. Mesmo `cd` que o `testar.sh` e o `./tutor`
documentam, pelo mesmo motivo.

### E o livro-razão que eu mesmo desalinhei

`migrar.py --listar` passou a avisar que a 027 "foi EDITADO depois de aplicado".
Verdade: apliquei, medi, descobri que faltava tirar a disciplina do rótulo, e
editei o arquivo em vez de criar uma 028 — aplicando o delta à mão.

O aviso é bom e a mensagem dele é honesta ("o efeito da edição NÃO está neste
banco. Se ela importa, faça uma migração nova"), mas ali ela afirmava o
contrário do que o banco mostrava. Conferido antes de tocar em nada: nenhum
material de referência com assunto ou rótulo — o efeito da versão FINAL está
presente. E a versão antiga nunca saiu desta máquina: a 027 foi commitada uma
vez só, já na forma final, então toda outra máquina roda a certa de primeira.

Com isso o checksum do livro-razão foi atualizado à mão, nesta máquina, porque
registrar o hash novo é dizer a verdade sobre este banco. O que NÃO se faz é
generalizar isso pro `migrar.py`: ele avisa e segue justamente porque, no caso
geral, não dá pra saber se a edição já teve efeito — e adivinhar é o que aquele
script existe pra não fazer. Aqui não houve adivinhação, houve verificação.

**A lição verdadeira é anterior:** eu não devia ter editado migração aplicada.
Custou uma verificação, um UPDATE manual e este parágrafo. A regra do CLAUDE.md
("a PRÓXIMA migração é a N") existe pra isso.

---

## A bateria de 10/09: 5 avisos, 4 falsos positivos, e um defeito de verdade escondido

O `.logs/defeitos.md` dizia **0 erros de regra** nas quatro baterias, só avisos.
Quatro dos cinco eram o mesmo aviso ("não termina com pergunta") em casos que o
próprio texto do aviso chama de aceitáveis. O quinto apontava para outra coisa.

E o defeito que importava **não estava no arquivo**: só apareceu lendo a
transcrição inteira, porque o turno que o continha não gerou apontamento nenhum.

### 1. O tutor repetia a própria pergunta (o defeito de verdade)

```
aluno : oi
tutor : ...por qual destas disciplinas você prefere seguir hoje: Direito
        Administrativo, Direito Constitucional, Direito Penal...?
aluno : tudo bem e você?
tutor : ...você prefere começar por Direito Constitucional, Direito
        Processual Penal ou Direito Administrativo?
```

A regra do prompt manda cumprimentar de volta e perguntar o rumo. "Tudo bem e
você?" TAMBÉM é cumprimento, então a regra dispara outra vez e o cardápio volta
com outras palavras. Dois turnos gastos na mesma pergunta não respondida — o
juiz pontuou 0/4 em "cada turno move a conversa adiante", e estava certo.

Faltava a cláusula "você já perguntou". Professor humano não insiste no
cardápio: escolhe, diz o que escolheu e começa — porque começar devolve o
controle ao aluno (ele corrige em uma palavra), enquanto repetir a pergunta
devolve o silêncio.

### 2. O tutor prometia questões que não existiam

O aviso dizia "não termina com pergunta". A resposta era:

> "Como você quer testar, selecionei questões... **As questões estão logo
> abaixo.**"

Nenhuma questão foi gerada. `pedido.treino("podemos testar eu nao sei se ja
estou bom")` devolvia `None` — o parser não conhecia "testar" como verbo de
pedido. O aluno olha pra baixo e não tem nada lá, e **nada no sistema apontava
isso**: o log só reclamou da falta de pergunta no fim.

Duas correções, porque uma não basta:

- `RE_TREINO` passou a reconhecer "podemos/quero/vamos/bora testar". O verbo vem
  ANCORADO num marcador de intenção de propósito: "testar" solto aparece em
  pergunta de conteúdo ("como testar a validade de uma prova pericial?"), e ali
  gerar questão trocaria a dúvida por um exercício que ninguém pediu;
- checagem NOVA no avaliador, e é ERRO, não aviso: `RE_ANUNCIA_QUESTAO` casando
  com `questoes` vazio. Nenhum prompt garante que o modelo só anuncie questão
  quando ela existe, e este projeto decide no código o que o prompt não garante.
  **12 ocorrências reais** no acervo gravado — defeito que escapava havia meses.

  `questoes is not None` e não `not questoes`: 198 dos 383 turnos gravados são
  anteriores ao campo existir, e ali "não sei" não é "nenhuma". Sem essa
  distinção a checagem nova apontaria erro em metade do histórico — ausência de
  dado virando prova.

### 3. "Prova" sozinha não é pedido de prova (achado de raspão, e o pior dos três)

Testando o item 2 apareceu um falso positivo que **não** era da mudança:
`RE_FORMAL` era `prova\s`. No Processo Penal e nas Ciências Forenses, "prova" é
o substantivo mais comum da matéria. Medido, com frases reais dessas
disciplinas, **seis de oito** viravam pedido de simulado formal:

| fala | antes |
|---|---|
| "me explica prova testemunhal" | `formal=True` |
| "quem tem o ônus da prova no processo penal?" | `formal=True` |
| "o que é prova emprestada" | `formal=True` |
| "quais são os meios de prova admitidos" | `formal=True` |
| "prova ilícita por derivação" | `formal=True` |
| "como testar a validade de uma prova pericial?" | `formal=True` |

E `formal=True` não é rótulo inofensivo: `api.py` NÃO gera questão nesse caminho
(`if p and not p["formal"]`) e ainda acende `simulado_pedido` na tela. O aluno
pedia explicação sobre prova pericial — que é uma disciplina inteira do edital
dele, com apostila subida — e recebia um empurrão pra tela de Simulado.

Agora "prova" só conta com MOLDURA DE EXAME: verbo de intenção colado ("fazer
uma prova", "quero prova") ou qualificador de exame depois ("prova
cronometrada"). "Simulado" e "caderno de erros" seguem valendo sozinhos — não
têm outro sentido. 13 de 13 nos dois sentidos, travados em teste.

### 4. O aviso que gritava em acerto, de novo

Quatro dos cinco avisos eram "não termina com pergunta" em: turno que gerou
questão (as questões SÃO a pergunta), despedida ("nada, só passei pra ver" →
"Até a próxima!") e instrução de tela ("na tela de Simulado do aplicativo", que
a regex só conhecia como "botão").

Já aconteceu com a checagem 3b (7 de 9 falsos positivos, demovida e depois
removida) e a lição é a mesma: **aviso que dispara em acerto ensina a ignorar
avisos, e um log que se ignora não vale o custo de existir.**

O conserto usa o sinal FORTE que o avaliador já recebia e não olhava:
`questoes`. A isenção por `p_treino` já dizia isso, mas keyada no PARSER do
pedido — e o parser não reconhece toda forma de pedir, nem o caso em que o
próprio tutor decide treinar.

**Medido antes de confiar** (é o que `--reprocessar` existe pra fazer): A/B no
mesmo corpus de 366 turnos, com e sem a mudança — 15 → 20 achados removidos, ou
seja, **5 turnos**. E a checagem continua disparando em 24. Afrouxou onde devia,
não virou decoração.

### O resultado

| bateria | antes | depois |
|---|---|---|
| `regressoes` | 0 erros / 1 aviso | 0 erros / 1 aviso (outro) |
| `cumprimento` | 0 erros / 2 avisos | **0 / 0** |
| `pede_treino` | 0 erros / 1 aviso | **0 / 0** |
| `desanimo` | 0 erros / 1 aviso | **0 / 0** |

O aviso que sobrou em `regressoes` é outro e é LEGÍTIMO: 413 caracteres para
"podemos testar eu nao sei se ja estou bom". Lendo a resposta, a frase do meio
repete o que as próprias questões mostram — cabe em ~200. Ficou apontado de
propósito: depois de afrouxar três checagens numa sessão, a quarta tem de ser
consertada no texto, não no medidor.

**E a nota do juiz caiu de 64 para 32.** Não é regressão: é a régua que o
próprio projeto manda ignorar — "36, 93 e 57 na mesma entrada", medido. A
contagem de erros é a medida; a nota é opinião de uma rodada.

## O nome do arquivo entra no classificador — e um contador de artigos decidia três coisas

Dois relatos do dono, no mesmo dia, sobre a mesma tela da biblioteca.

### 1. "Me dei o trabalho de nomear o arquivo e ele ignorou"

A aula de Princípios do Direito Administrativo subiu como
`direito administrativo - Princípios do Direito Administrativo - princípios da
Administração Pública.pdf` e o assunto saiu **"Regime Jurídico Administrativo"**
— o tópico 2 de 7 do índice (p. 5–14 de 151), com princípios ocupando da p. 14 à
58. Plausível e estreito, pelo mesmo mecanismo da CF virando "Princípios
fundamentais" na 027: `classificar()` lê `texto[:6_000]`, e o começo de uma
apostila é a capa do primeiro vídeo.

O nome do arquivo não estava perdido — ele é o `titulo` desde sempre, e a tela o
mostra em cinza. Quem nunca o via era o classificador. Agora ele entra
**rotulado** no payload (`NOME DO ARQUIVO: …`, sem extensão, uma linha, 160
caracteres), e é a única evidência disponível que cobre o documento INTEIRO em
vez dos primeiros 6 mil caracteres.

O exemplo de contradição dentro do prompt é INVENTADO ("Direito Penal - crimes
contra a fé pública" num PDF de licitações), e não o caso que motivou a regra: a
3b já ensinou que exemplo formatado vale mais que regra em prosa, então o caso
real ali dentro entregaria a resposta ao modelo e mataria a única prova de que a
regra funciona sozinha.

**Pista não sobrepuja prova, e isso precisou de uma segunda rodada.** A primeira
versão dizia "INDICADOR FORTE" e parou aí. O dono então renomeou À MÃO uma aula
de Direitos Sociais para "Direitos Humanos - princípios internacionais" e subiu
— nome descritivo, estruturado e ERRADO, que é exatamente o caso que "indicador
forte" não cobre. A regra virou de PRECEDÊNCIA, com o exemplo dele dentro do
prompt: nome que **contradiz** o texto é descartado, nome que concorda orienta,
nome inútil (`scan_001.pdf`, `curso-392722-aula-10-9415-completo`) se ignora. E
o rótulo sai no formato canônico — copiar o nome literal seria o classificador
virando eco.

### 2. E o que estava quebrado nesse segundo material era outra coisa

Antes de mexer no prompt, o registro: doc 789 tinha `assunto = NULL` e **52 de
52 trechos com `artigo`**. O modelo não preferiu o nome do arquivo — ele nunca
foi perguntado. A aula transcreve os arts. 6º a 11 da CF, bateu **57** "Art." em
começo de linha, passou do `MIN_ARTIGOS_LEI = 40` e foi tratada como LEI SECA.
Daí em cascata: `chunk_lei` fatiou por artigo e jogou fora a explicação do
professor entre um dispositivo e outro; `e_referencia` viu chunk com artigo e
chamou de poço de consulta; a 027 suprimiu o assunto; e a tela, sem assunto,
caiu no `titulo` — que era o nome errado que ele mesmo tinha digitado. **Um
limiar de contagem decidindo três comportamentos.**

Subir o limiar não resolve: lei de 60 artigos existe. O que separa não é
quantidade de artigo, é a COMPANHIA. Medido sobre oito leis de verdade (as cinco
do `corpus/` e os três `.html` compilados do Planalto, que são o caso original da
019) e o que o dono subiu de fato:

| arquivo | artigos | banca | marcas de aula |
|---|---|---|---|
| cf.txt | 292 | 0 | 4 |
| cp.txt | 437 | 0 | 0 |
| cpp.txt | 899 | 0 | 1 |
| lei8112.txt | 253 | 0 | 1 |
| adct.txt | 174 | 0 | 0 |
| Constituicao-Compilado.html | 466 | 0 | 0 |
| Del3689Compilado.html | 898 | 0 | 0 |
| L8112consol.html | 362 | 0 | 1 |
| aula 10, Processo Legislativo (738) | 55 | 82 | 155 |
| aula 04, Direitos Sociais (789) | 57 | 38 | 87 |
| **Edital PC-PR 2026** | 72 | 99 | 9 |
| aula 00 (344) | 26 | 56 | 100 |

Nenhuma lei cita banca; nenhuma passa de 7 marcas; nenhuma apostila fica abaixo
de 37 bancas. Os cortes (3 bancas ou 20 marcas) ficam no meio dessa distância.
`_e_apostila` é VETO, não classificador: responder "não" não afirma que o texto
é lei, só que não há prova de apostila — e por isso os cortes são altos, já que
vetar por engano devolve a lei do aluno à janela genérica (o mundo pré-019),
enquanto errar pro outro lado destrói a aula.

**O EDITAL apareceu na medição sem ninguém procurar por ele**: 72 "Art." em
começo de linha, as regras do certame. Estava caindo na mesma armadilha, e o
mesmo veto o tira.

**O que fica ambíguo, dito pra não virar susto:** o livro de emendas
(`CF88_Livro_EC91_2016.pdf`, 1197 artigos, zero marcas de curso) continua
passando por lei seca se alguém o subir pela biblioteca. É o comportamento
anterior, não mudou, e não há medição que diga qual dos dois lados é o certo —
no `corpus/` ele entra como `historico`, por outro caminho.

### 3. E a reindexação promoveu o palpite a resposta do aluno

Material já indexado ficou como estava: a regra nova só age em quem passa por
`indexar()`. Os dois documentos afetados foram reindexados pelo caminho normal
(`material.indexar`, idempotente desde a 019) — sem `DELETE FROM documento`:

| doc | antes | depois |
|---|---|---|
| 738, Processo Legislativo | 54/54 trechos com artigo | **0/202**, assunto intacto (`aluno`) |
| 789, Direitos Sociais | 52/52 com artigo, `assunto = NULL` | **0/164**, assunto **"Direitos Sociais"** |

O 789 é a prova das duas mudanças juntas, e por isso o exemplo do prompt não
podia ser ele: o modelo recebeu o nome "Direitos Humanos - princípios
internacionais" e devolveu "Direitos Sociais", que está no texto.

**Mas ele voltou marcado como "você informou", e ninguém informou nada.**
`_classificar_se_faltar` decidia a procedência por "a disciplina já está
preenchida?" — verdade na primeira passada, MENTIRA na segunda, porque quem
preencheu foi o modelo. Reindexar apagava o aviso "eu deduzi, confira" de todo
material deduzido, e palpite sem aviso é pior que palpite: a tela pede
conferência exatamente onde ela é necessária. A procedência agora sai do
`classificado_por` GRAVADO (`registrar` já o escreve 'aluno' só quando o aluno
digita), e a linha do 789 foi corrigida de volta para `modelo`.

Achado só porque o antes/depois da reindexação foi impresso campo a campo — a
mudança "funcionou" em tudo que se tinha ido conferir.

### 4. "Ele não identificou a matéria" — com a matéria gravada no banco

O dono apagou o material e subiu de novo. A tela mostrou o PDF em **Outros**,
sem disciplina e sem assunto; o banco, no mesmo instante, tinha `Direito
Constitucional` / `Direitos sociais`. Os dois estavam certos, e é isso que
tornava o relato difícil de acreditar.

`indexar()` gravava `status='pronto'` e SÓ ENTÃO classificava. A biblioteca faz
polling apenas enquanto existe material `processando` — senão seria consulta a
cada 3s numa tela parada —, então bastava a lista ser buscada dentro dessa
janela de segundos: a tela desenhava "Outros", ouvia "pronto", parava de
perguntar, e ficava mentindo até alguém dar F5. Um material que está para mudar
de linha não pode ser anunciado como terminado.

O `pronto` passou a ser a ÚLTIMA escrita da função, depois da classificação. Só
o anúncio mudou de lugar: o rótulo continua fora do `try` da indexação e
continua sem poder marcar `falha`, então material sem cota de modelo termina
`pronto` igual. A prova de ordem está no teste — o duplê do LLM consulta o
`status` DE DENTRO da chamada de classificação, porque no fim os dois campos
ficam certos de qualquer jeito e nenhuma asserção sobre o resultado final
distinguiria as duas versões.

## Cinco falhas apontadas no chat, uma existia (e é a terceira leva de `assunto`)

Relato com log longo e diagnóstico pronto, de outra ferramenta. Conferido no
código, item a item, antes de mexer — o mesmo exercício de 10/09, com resultado
parecido.

**1. "Erro de gatilho JSON: pediu peculato culposo e veio 'inserção de dados
falsos'".** Não existe gatilho por JSON neste projeto. O caminho automático é
`core/pedido.treino` (regra sobre a fala) e o manual é o botão, que manda só
`conversa_id`. A questão exibida é a de `id=7`, do acervo PÚBLICO, criada em
04/08 — veio da fila, não de geração. Questões de peculato existem e são de
10/09 (ids 1511-1519).

**2. "Amnésia da saudação: 'boa noite' no meio da sessão reseta o fluxo".** Na
conversa real (525), `boa noite` é a PRIMEIRA mensagem. Abrir perguntando por
onde começar é o comportamento correto — não há o que blindar.

**3. "Alucinação: disse que não estava no material e os chunks eram da
apostila".** A frase é literal do prompt (`socratic.py`), e é decisão registrada
neste arquivo: doutrina sem trecho é PERMITIDA e MARCADA. O que estava errado
era o que a busca trouxe — ver o item 5.

**4. "Botão órfão: remova o botão manual".** Ele é o único caminho manual e não
foi substituído por nada. Removê-lo tiraria função em nome de um mecanismo que
não existe.

**5. ENVENENAMENTO DA BUSCA — este era real, e reproduzido.** `em_foco` é puro,
então a conversa inteira foi reexecutada pelo banco. Para

    "queria um resumão mais detalhado com 2 exemplos de cada"

a consulta que ia ao pgvector era

    "queria um resumão mais detalhado com 2 exemplos de cada agora eu queria que
     trouxesse um resumão com tudo de uma vez ja"

Sem UMA palavra de matéria. "resumao", "detalhado" e "trouxesse" contavam como
conteúdo, então a fala "dizia assunto", virou consulta E puxou as anteriores
(também meta) como reforço. Daí CP art. 150 (violação de domicílio), CP art. 28
(embriaguez) e CF art. 220 (comunicação social) numa aula de Direito
Administrativo.

Depois de entrarem em `VAZIAS`, a mesma fala cai no turno do TUTOR:

    "Vamos ao resumão completo dos princípios implícitos que caem na sua prova:
     Supremacia do interesse público..."

**E o item 3 é consequência deste.** Com a consulta envenenada, o tutor dizia a
verdade ao avisar "isto é doutrina e não está no seu material" — não estava no
que ele recebeu. Estava na apostila.

**O fixture recortado MENTIU, e isso quase virou o teste.** A primeira versão do
caso usava oito turnos escolhidos a dedo, e com eles a consulta caía nas falas
anteriores do ALUNO em vez do turno do tutor — outro resultado, com o mesmo
código. `em_foco` decide olhando a sequência, então recortar a conversa é mudar
a pergunta. O fixture passou a ser o log inteiro, literal, como o cabeçalho do
arquivo já mandava.

**"citar" ficou de fora da lista de propósito:** citação é ato processual no CPP,
e cegar a busca para ela custa mais que a diluição que ela causa. A assimetria é
a mesma de sempre — palavra a mais dilui, palavra de domínio a menos cega.

## Quatro melhorias reais do tutor — fila 20, 58, 65 e 108

Tratadas juntas em 21/09/2026 porque as quatro expunham o mesmo limite: regras
genéricas do prompt perdiam para sinais mais próximos da fala ou para dados sem
hierarquia explícita.

- **#108 — matéria não é assunto.** O diário deixou de entregar
  `Peculato (Direito Penal)` como texto ambíguo e agora agrega as matérias e
  rotula cada linha como `ASSUNTO` e `MATÉRIA`. O tutor respondeu com Direito
  Constitucional, Direito Penal e Direito Administrativo como matérias e
  manteve Processo Legislativo, Peculato etc. como conteúdos vistos.
- **#65 — planejamento não empurra aula.** “Como vamos estudar por dia?” virou
  pedido explícito de planejamento. A resposta medida ficou no plano e terminou
  oferecendo a distribuição dos dias, sem retomar a pergunta de conteúdo nem
  escolher uma matéria para o aluno.
- **#58 — humor precisa de sinal local.** Duas versões só no prompt falharam e
  voltaram a saudar por causa da palavra “tarde”. O `kkk`/`rs` da fala atual
  agora gera uma instrução condicional junto da própria pergunta. Na medição
  final, o tutor entrou na brincadeira com “o prejuízo é só no relógio”, sem
  nova saudação, e retomou uma única ideia.
- **#20 — salto dentro do mesmo item também é posição.** Papiloscopia pertence
  ao próprio item 2.1 de Medicina Legal no edital atual; o tutor medido disse
  “Continuamos no 2.1, em Medicina Legal” antes de explicar, sem inventar uma
  subdivisão.

Validação direcionada após a última alteração: **72 testes passaram**. As quatro
saídas também foram verificadas com o provedor real; não bastou inspecionar o
texto do prompt.

## Auditoria no Chrome: assunto atual, intenção de mapa e vitrine falsa

Em 22/09/2026, o defeito relatado foi reproduzido na conversa 1337. A fala
“certo eu quero questões de ciencias forense quais são os assuntos?” vinha após
Direito Constitucional. `pedido.treino()` reconhecia o pedido, mas
`assunto.em_foco()` excluía a fala atual pela hipótese antiga de que pedido de
treino nunca nomeava assunto. O gerador herdava Constitucional e entregava
Mutação Constitucional e Controle Interno.

A correção separou três intenções que antes estavam misturadas:

- treino explícito com disciplina/tema atual usa a fala atual como foco;
- treino elíptico (“manda cinco”) continua herdando o foco da conversa;
- pergunta de escolha (“quais são os assuntos/temas/tópicos?”) é mapa e não
  gera questões até o aluno escolher.

O fallback de geração também foi recortado pela disciplina explicitamente
nomeada. A primeira repetição real passou a gerar somente Ciências Forenses,
mas revelou o segundo defeito: o aluno ainda estava pedindo o mapa, não a
geração. Depois da separação de intenção, a mesma fala não criou questão e o
tutor apresentou o item de Medicina Legal para escolha.

O uso visível mostrou ainda dois defeitos independentes:

1. questões geradas ficavam no estado React ao trocar de conversa; o estado é
   zerado imediatamente em “abrir” e “nova conversa”;
2. `/tutor` sempre desenhava uma conversa completa de demonstração — números,
   pergunta de peculato, questão e flashcard — antes das mensagens reais. Esse
   conteúdo de Penal podia parecer exatamente uma geração indevida anterior à
   escolha do assunto. A vitrine foi removida da rota real e os exports sem
   consumidor também saíram de `mock/prototipo.ts`.

Na mesma rodada, a tela deixou de decidir “citado” procurando apenas o número do
artigo na prosa. O caso real do art. 312 marcava simultaneamente CP e CPP. Agora
o backend persiste `citada` e a tela respeita esse dado inclusive ao reabrir a
conversa. Um teste com CP 312 citado e CPP 312 apenas consultado trava o
contrato. A atribuição positiva completa continua limitada pelo contrato do
modelo e está descrita em `LIMITACOES.md`.

Evidência final: **132 testes direcionados**, ESLint direcionado e
`git diff --check` aprovados; testes reais no Chrome para Ciências Forenses,
papiloscopia, meta-pergunta, retomada de Penal, troca curta de disciplina e
colisão CP/CPP. Não foi rodada a suíte completa nem declarada bateria 1 inteira
como concluída.

## Resolução pedida, pergunta sobre o tutor e cards que ninguém pediu (28/09/2026)

Conversa real, relatada pelo dono como "erros grotescos", e em seguida uma
bateria pela ROTA com o modelo real numa conta descartável (13 turnos). As
causas, uma por defeito:

1. **Card sem pedido depois de uma questão colada.** O enunciado começava com
   "Um levantamento interno…", logo depois de um turno de treino, e o "Um" casou
   com `RE_CONTINUA` como "manda uma". A forma elíptica agora tem no máximo
   seis palavras (`pedido._eliptica`).
2. **"Resolva pra mim questões de probabilidade" virou treino.** Pela palavra
   "questões". `pedido.resolucao` (imperativo dirigido ao tutor, ou enunciado
   colado com alternativas ou moldura de prova) tira o turno do treino e
   acrescenta `SISTEMA_RESOLUCAO` ao prompt: questão escrita, passo a passo com
   a conta, `\boxed{}`, gabarito, macete. "Quero questões PARA resolver"
   continua sendo treino. Nesse turno `limpar_questoes` não roda: a questão é
   dele, e o gabarito cita a alternativa.
3. **"Do que você é capaz?" e "quais apostilas eu tenho?" buscaram material.**
   Entraram em `RE_SISTEMA` e em `RE_BIBLIOTECA` ("sobre" fica de fora: "o que
   tem no acervo sobre peculato" é matéria). Bateria: fontes = 0 nas quatro.
4. **"Conta não é número de lei".** A regra 0 do prompt ("nunca afirme número
   sem trecho") era lida como proibição de fazer conta. A seção 4 agora separa
   as duas coisas.
5. **Fórmula, mapa mental e tabela.** `SISTEMA_FORMATO`, só em turno de
   resolução ou de pedido visual (`pedido.formato_visual`), ensina a notação que
   `TextoDoTutor.tsx` + `Formula.tsx` desenham: LaTeX entre cifrões (subconjunto
   fechado), árvore em bloco de código, tabela Markdown. Sem biblioteca: a
   decisão de não transformar texto de modelo em HTML continua de pé.
6. **Duas perdas no caminho, achadas só lendo a bateria.**
   - `llm._parse_json` apagava TODA crase, e a árvore chegava sem o bloco.
     Agora só sai a cerca de fora.
   - Dentro do JSON, `\text`, `\frac` e `\boxed` sem a barra dobrada viram TAB,
     form feed e backspace: "105<TAB>ext{ Agentes}". `socratic.latex_de_volta`
     devolve a barra quando o caractere de controle vem colado a uma letra.
7. **"2 questões de conjuntos" → "Conceito de Proposição" e "Furto Noturno".**
   A busca é k-vizinhos sem piso, e `_misturar` reservou a vaga da lei para o
   artigo mais bem colocado (CF 57, CP 155), que não tinha nada de conjuntos.
   `geracao._no_assunto`: fora o 1º colocado, só entra candidato que tenha
   palavra de conteúdo do tema (na rubrica, se é lei; no texto, se é apostila).
   O gerador também passou a pular apresentação ou estrutura do curso.

## Bateria de descoberta: o juiz não pode ter o defeito do código (28/09/2026)

O dono achou numa conversa real o que as baterias não pegavam, e cobrou: "seus
testes são rasos e não simulam um usuário real". A causa foi de desenho:

- `avaliar_chat.py` conferia "card sem pedido" com o próprio `pedido.treino`. Com
  a regra errada, o teste errava junto e aprovava.
- Os roteiros eram só de Direito, numa conta sem apostila.
- Ninguém olhava a tela. As crases apagadas e o `\text` comido aconteciam
  depois do modelo, e a resposta continuava "válida".
- A bateria escrita depois do defeito confirma o conserto, não acha o próximo.

`descobrir.py` (`./testar.sh --descobrir`) muda os quatro pontos:

1. **Oráculo independente.** Um revisor lê a conversa como o aluno a viu: o texto
   desenhado, os cartões e o consultado. Ele não conhece regra do tutor. O código
   compara o veredito com o que o sistema fez.
2. **Falas reais.** As mensagens da conta real são repetidas numa conta
   descartável, e um aluno simulado persegue OBJETIVOS, não matérias.
3. **Tela.** Toda resposta passa pelo `TextoDoTutor` de verdade
   (`apps/web/scripts/texto-na-tela.cjs`).
4. **Contradição.** Cada bloco condicional do prompt é lido contra o base, e cada
   decisão nova desta página contra as antigas mais parecidas.

**Medido na montagem.**
- O revisor precisa ser mais forte que o tutor. Com o modelo do tutor, a leitura
  de contradição respondeu "nenhuma" com um choque injetado.
- Mesmo o revisor oscila a temperatura 0: acha numa rodada e não acha na
  seguinte, e aponta exceção que o texto declara. Por isso são duas leituras
  (união) e uma conferência por suspeita ("o texto já resolve isso?").
- Pega choque direto (colchete proibido × colchete pedido). Não pegou um sutil
  (oferecer questões "mesmo que ele já tenha recusado" × "não ofereça duas vezes
  seguidas"). É rede, não garantia.

**Primeira rodada (falas reais).** A cota acabou no meio: 22 dos 42 achados eram
503, e a bateria agora para no primeiro 503 e marca a rodada INCOMPLETA. Do resto:

- **"Consultado" com sorteio da busca** (CPP 15 e 744 debaixo de conjuntos e de
  português). `socratic._fontes_da_tela`: fica o citado, o lido e o não citado
  da matéria em foco ou com palavra da consulta.
- **Recusa de assunto fora do edital** ("isso não está no seu edital", quatro
  turnos seguidos, para coesão e parônimos). Regra nova na seção 4: ensina e avisa
  uma vez.
- **Promessa sem cartão.** O gerador falhou (cota) depois de o tutor escrever
  "estão logo abaixo". A resposta passa a dizer o que aconteceu, na tela e no
  histórico (`conversa.reescrever`).
- **"Qual aula e página sustentam isso?"** foi à busca e voltou sem página.
  `pedido.pede_fonte` + `conversa.origem_da_ultima_resposta`.
- **Resolução não reconhecida.** Problema colado sem alternativas e "quero que vc
  resolva" (verbo no fim).

### Segunda rodada completa (7 conversas reais + 5 simuladas, 28/09/2026)

Juiz leve (a cota diária do forte acabou), então cada achado foi conferido na
conversa. Três eram engano do juiz:

- "boa noite" para quem disse "bom dia": a fala foi repetida às 23h, e o tutor
  segue o relógio;
- frações "25" no lugar de 2/5: defeito da MINHA extração de texto. O `Formula`
  ganhou separador `sr-only`;
- "cartão sem pedido" num turno em que o aluno exigia a questão certa.

Os reais:

- **Cartão de outra matéria.** Na conversa de lógica, o aluno pediu tabela-verdade
  e recebeu conjuntos, depois 8.112 art. 86. A fala de reclamação é ruído para a
  busca. `geracao._na_materia_da_conversa`: fica na matéria dos trechos citados
  quando o pedido está nela. O pedido vago leva o assunto da conversa ao gerador,
  e o último recurso sorteia dentro dessa matéria.
- **Aceitar a oferta não gerava nada** ("quer que eu monte?" → "sim").
  `pedido.aceitou_oferta_de_questoes`. O treino passou a ser decidido ANTES de o
  tutor escrever e vai ao prompt como fato ("### Questões deste turno"); a seção 9
  deixou de mandar o modelo adivinhar.
- **"Volta pro controle de constitucionalidade" virou leitura** da apostila (três
  telas de direito sindical). `leitura.retoma_um_assunto`: sobrando assunto além
  do nome da matéria, não é retomar leitura.
- **"Volta pro constitucional DEPOIS, foca nisso agora"** trocava de matéria na
  hora. `assunto.sem_o_adiado` tira a oração adiada (com verbo de rumo; "depois da
  posse" fica).
- **Troca de assunto por palavra igual** ("controle interno" no lugar de controle
  de constitucionalidade). Regra na seção 4: assunto sem trecho se ensina pelo
  conceito, sem substituir.
- **Recusa de assunto fora do edital**, mesmo com a regra da seção 4. Subiu para a
  precedência 1.
- **"Consultado":** filtrar por matéria ou por palavra ainda deixava passar (a
  questão colada tem palavra para qualquer artigo). A lista mostra só o que
  sustentou a resposta: citado ou lido.
- **Fórmula quebrada por `limpar_citacoes`**, que apagava `[...]` dentro de
  `$$...$$`: `socratic.fora_da_formula`. Símbolo solto (`\cap` em prosa) passou a
  ser desenhado.

Na bateria: diante de 503, espera um minuto, desfaz o turno sem resposta e repete
(o limite é por minuto; medido). O revisor nunca cai no modelo do tutor
(`llm.Gemini(evitar=...)`), e o relatório diz qual modelo julgou.

### A cota é por DIA e por modelo, e as baterias a gastaram (28/09/2026)

Lido no corpo de cada 429 (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`):

- 500 chamadas por dia no `gemini-3.5-flash-lite`, o modelo do tutor;
- 20 por dia no `gemini-3.5-flash`;
- `gemini-flash-lite-latest` é APELIDO do `3.5-flash-lite` e divide a cota com ele.

Quatro rodadas de bateria no mesmo dia esgotaram o modelo do tutor. As reservas
padrão (`3.5-flash`, `flash-lite-latest`, `3.5-flash-lite`) caíram juntas, e o
app parou para o dono, com o `3.1-flash-lite` respondendo normalmente. O que
mudou:

- **Reservas padrão:** `3.1-flash-lite`, `3.5-flash-lite`, `3.5-flash`. Cada
  reserva tem cota própria, e a de 20 por dia fica por último.
- **`llm.CotaDiaria`:** quando todos os modelos respondem 429 "PerDay", o erro diz
  que é a cota do dia, não "instabilidade que passa em minutos".
- **A bateria tem orçamento** (150 chamadas por padrão), contado pela telemetria.
  Com cota do dia esgotada ela para na hora, e o revisor evita o principal e o
  apelido dele.

## Manutenção noturna de 29/09/2026: a bateria estava cega, e a leitura pulava trecho

**O que a bateria achou.** 195 defeitos grave/médio em 7 conversas reais (a rodada
parou no orçamento antes das simuladas). 188 eram o mesmo: todo turno "com erro
técnico de sistema" e "marcação crua `[[não deu para desenhar`".

**A causa desses 188 era a bateria.** Quem chama de madrugada (`manutencao.sh`,
pelo Agendador) roda shell não interativo; o `node` só entra no PATH pelo
`~/.bashrc`. `descobrir.na_tela` caiu no `FileNotFoundError`, devolveu a mensagem
de erro no lugar de cada resposta, e o juiz julgou a mensagem — com razão. As
respostas de verdade estavam boas na maioria dos turnos. Conserto: `testar.sh
--descobrir` procura o node em `~/.local/node/bin` e no nvm, e recusa rodar sem
ele; `descobrir.main` desenha uma resposta de prova ANTES de montar conta e de
chamar modelo, e sai com 2 se a tela não desenha (nada de cota gasta). O juiz e as
divergências não mudaram.

**Lendo as conversas eu mesmo, três defeitos reais do tutor:**

- **A leitura marcava como lido o que só foi ENVIADO.** "Quero seguir a ordem do
  edital" mandou a apostila de lógica inteira (7 trechos); a resposta ensinou só
  "1. Proposições" e anunciou "A seguir: conectivos", mas o marcador foi para o
  fim. Nos quatro turnos seguintes o material "tinha acabado" e o tutor seguiu de
  memória, sem fonte. O mesmo na Lei 8.112 (arts. 18–20 enviados, resposta sobre
  LIMPE, a leitura seguinte abriu no 21) e na CF (trechos 7, 18–19 e 24–27).
  MEDIDO nas 20 respostas de leitura da noite: cobertura (fração das raízes de
  6 letras das palavras de conteúdo do trecho presentes na resposta) do último
  trecho ensinado de cada turno entre 0,40 e 0,94; trecho enviado e pulado entre
  0,00 e 0,25. `leitura.ensinados` marca do primeiro ao ÚLTIMO trecho com
  cobertura ≥ 0,35; nenhum coberto, nenhum lido. Errar para menos repete um
  trecho, errar para mais o pulava para sempre. Os dublês de três testes
  respondiam "Aula sobre o trecho." — agora a aula falsa ensina o material falso.
- **"Os assuntos foram os tópicos 1, 5, 18, 21".** Apostila com "Tópico N" na
  linha acima de cada artigo: `chunking._eh_rubrica` aceita a linha como rubrica,
  e o diário usa a rubrica como nome do assunto. `diario.rotulo` troca a rubrica
  que só numera (uma palavra + número) pelo assunto do material; sem assunto, a
  numeração fica. O fatiador não mudou (a rubrica entra na busca, e ele tem
  medição própria).
- **Pergunta sobre a biblioteca com o verbo antes do nome** ("quais a gente tem
  material?", "saber sobre o que você tem material") ia à busca e mostrava a Lei
  8.112 art. 5º como CONSULTADO. `pedido.RE_BIBLIOTECA` aceita a ordem falada, e
  "sobre o que"/"sobre quais" deixou de ser assunto.

**Não corrigido:** ver `LIMITACOES.md`, "Manutenção de 29/09/2026".

### Segunda passada (bateria 2, depois dos consertos da primeira)

**O que a bateria achou.** A rodada ficou incompleta (orçamento), com 4 das 12
conversas: 5 achados grave/médio e 5 leves. A tela desenhou em todos os turnos, então
o conserto da bateria segurou. Nenhuma regressão das correções da primeira passada.

**Real: recusa de assunto fora do edital, pela terceira vez.** "você sabe algo sobre
formas de coesão de lp?" recebeu "isso não cai na sua prova" em quatro turnos
seguidos. Reproduzido com o prompt EXATO do turno: conta descartável montada como a
da bateria, turnos anteriores com a resposta gravada num dublê, e o modelo real só
no turno em questão. As hipóteses da primeira passada caíram, uma chamada cada:

- com a frase da seção 8 ("responda pelo que já foi tratado e siga dela")
  restrita a quem continua no assunto: recusou;
- SEM os seis trechos de lógica que a busca mandou: recusou;
- com a mesma regra num bloco "### Assunto desta fala" logo antes da pergunta:
  ensinou coesão referencial e sequencial e avisou uma vez. Também ensinou no turno
  seguinte (homônimos e parônimos), com as recusas gravadas no histórico. Numa
  pergunta do edital sem o nome da disciplina ("o que é estágio probatório?") não
  disse "não cai".

É o mesmo caminho do `_tom_da_fala`: regra geral no sistema perde para o que está
colado à fala. `socratic._assunto_da_fala` aparece quando a fala tem palavra de
conteúdo (5+ letras, fora do vocabulário de estudo e das palavras do nome das
disciplinas) e não nomeia disciplina do edital. Fica fora da leitura e da falta de
material da matéria do edital. Quem decide se o assunto está fora do edital é o
modelo, que já acertava isso: código não sabe que "peculato" é de Direito Penal. A
frase da seção 8 ficou restrita, porque mandava voltar ao assunto anterior.
Teste: `tests/test_fora_do_edital.py`.

**Engano do juiz:** "bom dia" para "boa noite" (a bateria rodou às 5h); "resolveu
em vez de propor exercício" para quem escreveu "quero que vc resolva".

**Não corrigido:** mapa e trilha do edital inteiro saem rasos, e CONSULTADO fica
vazio quando o modelo não lista o trecho que usou (`LIMITACOES.md`).

## Depois da madrugada: revisão do que ela fez e as pendências dela (29/09/2026)

**Revisão.** Li as mudanças da noite comparando com o estado de antes dela
(`antes.patch` sobre o HEAD). Estão certas. Um acerto: na leitura, o CITADO ainda
era a janela inteira, e só o marcador usava `leitura.ensinados`. Por isso o
consultado e o diário diziam "estudou conectivos" de uma aula que parou em
proposições. Agora citado e diário também contam só o que a aula ensinou.

**As três decisões que a noite deixou:**

1. **Trilha ou mapa do edital inteiro.** Pedido de visão geral
   (`socratic.RE_VISAO_GERAL`) sem disciplina nomeada leva o ÍNDICE do edital: os
   cabeçalhos dos itens de cada disciplina, com teto de 80 itens. Não vai a lista
   de subitens. A razão de `_resumo_mesa` (1015 tópicos na Dataprev) continua de pé.
2. **CONSULTADO vazio com trecho usado: medido, e não mexi.** Nas conversas reais,
   fora da leitura:
   - 34 de 47 respostas com trechos não citaram nenhum;
   - trecho citado tem cobertura mediana de 0,17 (10% abaixo de 0,04);
   - trecho não citado tem mediana de 0,03 (só 3 de 225 acima de 0,20).
   Fora da leitura, a cobertura não separa usado de não usado, e uma reserva por
   ela trocaria uma omissão rara por citação errada.
3. **Tabela só a pedido.** Tabela espontânea para "três ou mais coisas" enfileirava
   as espécies que a seção 2 manda ensinar uma por vez.

**Os menores:**
- **Conversa fiada com risada** ("se ta descolado em chat kkk") não busca
  (`pedido.conversa_fiada`).
- **Plano com o tempo do aluno** é da SEMANA e usa o tempo todo.
- **Cifrão desparelhado** (`$$…$`, `$$…$|`) é consertado na tela, só em linha
  desbalanceada.
- **Nota SEM MATERIAL do programa mapeado** contradizia a seção 4 (proibia
  explicar o ponto). Alinhada: o que depende de lei não se afirma de memória;
  conceito, sim.

### Validação de dia (5 conversas simuladas, 29/09/2026)

**A questão de outra matéria voltou em 4 das 5 conversas.** Informática saía de
Direito Administrativo; controle de constitucionalidade e contagem saíam de
"competência municipal". Três causas no gerador, nenhuma no prompt:

1. **A consulta levava o pedido inteiro.** "me manda questões de…" puxava o CPP 482
   ("Do Questionário e sua Votação"). `pedido.sem_o_pedido` tira o vocabulário de
   pedido antes da busca.
2. **"O 1º colocado entra sempre"** é regra de citação precisa. Com assunto nomeado
   e sem trecho dele, o 1º era ruído. Agora todo candidato precisa trazer o TERMO
   RARO do pedido (`geracao.termo_raro`), por palavra exata e tolerando falta de
   acento. Com o radical do `portuguese`, "constitucionalidade" vira
   "constitucional", e o termo raro saía "controle".
3. **O sorteio na mesa quando não há trecho** continua só para pedido VAGO. Assunto
   nomeado sem trecho levanta `SemMaterial`, e a resposta diz que não há material
   dele.

Medido no acervo público: peculato vai ao CP 312; internet e Informática ficam sem
trecho (mensagem honesta); controle de constitucionalidade também fica sem trecho,
porque o art. 102 da CF tem alíneas revogadas e o filtro antigo não o aceita.

**Os outros três:**
- **"Tu já pulou exercício, explica direito"** gerava cartão. Com pedido de
  explicação, só conta como treino o pedido direto (verbo ou quantidade colados à
  palavra de treino).
- **"A tabela exige visualização detalhada"** a quem pediu a tabela. Novo bloco
  "### Formato pedido nesta fala" colado à pergunta, como o do assunto.
- **Tabela com `|---|---|>`** aparecia crua. A tela tolera o lixo no fim da linha.

### Sorteio na mesa só sem assunto; e o tutor sabe antes se há questões (29/09/2026)

**Substitui** a regra "cair pro recorte, declarando a troca, é melhor que devolver
vazio" (a do "trocou_de_assunto"). Ela foi medida contra a troca SILENCIOSA, e
estava certa contra aquilo. Mas a bateria de hoje mostrou a troca declarada
falhando igual: o aluno pede Informática, recebe Tocantins e corrupção ativa, e
reclama turno após turno. O aviso na tela não conserta uma questão errada.

- **Sorteio só sem assunto.** Com assunto na conversa, nomeado agora ou antes, a
  escolha usa a trava dos termos raros. Sem trecho, levanta `SemMaterial`. O
  sorteio na mesa fica para a conversa que ainda não tem assunto nenhum ("me dá
  umas questões" de cara).
- **Dois termos raros, e não um.** "consegue" (gíria que a lei não usa) foi o
  termo "mais raro" de um pedido de controle de constitucionalidade e trouxe o
  CP 177. O trecho precisa trazer os DOIS termos mais raros do pedido.
- **A escolha vem antes de o tutor escrever** (`geracao.escolher`, sem modelo). Sem
  trecho, o prompt diz "NENHUMA vai aparecer", e o tutor responde com as palavras
  dele e oferece o que dá. A frase fixa, que substituía a resposta depois, se
  repetia igual e foi apontada como defeito. Ela só sobra para quando o MODELO
  falha na geração.
- **"Saíram 2 de 3"** é dito quando o gerador entrega menos do que foi pedido.

**Pendência de produto (do dono):** o aluno pede "inventa uma questão de
Informática, não precisa de material". Hoje não há questão sem fonte, pela
invariante de `fonte_chunks`. Uma "questão de treino no chat", sem cartão e sem
fila, só de conceito e marcada como não vinda do material dele, seria uma decisão
nova.

### Validação sem cota e o que ela pegou (29/09/2026, noite)

**O jeito de validar mudou.** A bateria completa (aluno simulado + tutor + juiz)
custa de 3 a 4 chamadas por turno e esbarra no limite por minuto do plano
gratuito. Os defeitos de CARTÃO estão todos no código de escolha, que não usa
modelo. `.logs/validacao/offline.py` repete as conversas gravadas pela rota, com o
tutor dublado pela resposta gravada, e mostra de onde sairia cada questão: sem
nenhuma chamada, em poucos minutos. A bateria completa fica para depois de uma
leva grande de mudanças.

**Ela pegou o que eu achava resolvido:**
- A matéria em foco não valia no pedido com palavra própria ("é a RAM que é
  volátil, bota uma questão disso"). Agora o pedido VAGO tira o assunto da última
  explicação do tutor (`api`, com rede de segurança: sem termo do acervo, fica o
  assunto da conversa).
- "disso", "fácil", "mano" viravam termo raro. Entraram no vocabulário de conversa
  de `pedido.sem_o_pedido`.
- "resolver direito" (advérbio) casava com Direito Constitucional. O pedido SEM
  TERMO FORTE (`geracao.tem_termo_forte`: 6 letras ou mais, em até 150 trechos)
  fica na matéria da conversa. Com termo forte ("peculato"), é troca de assunto e
  fica livre.
- Dois assuntos num pedido ("conjunto e porcentagem") vão cada um por si
  (`geracao._partes`), intercalados.

Resultado da repetição: as 8 falas de pedido de questão das conversas gravadas não
tiram mais cartão de outra matéria. Antes, 3 tiravam.

**Leitura:** o ÚLTIMO trecho só conta como lido se foi coberto de verdade
(`leitura.LIMIAR_COMPLETO` = 0,6). Coberto em parte, o "continua" pulava os tópicos
que ele trazia.

**Limite (não corrigido):** a reclamação que mistura assuntos ("pedi direitos
fundamentais… meu concurso é pra administrativo… procurador") fica sem cartão.
Não sai errado, mas também não sai o certo.

## Conversa real de Português: IDs na prosa, "português" sem disciplina, resumão curto, PDF quebrado (29/09/2026)

- **"(ID 67553)" no meio da explicação.** O prompt identifica cada trecho por "ID
  da fonte: N" para o modelo preencher `fontes_usadas`; o modelo passou a
  escrevê-los na prosa. `socratic.sem_ids` tira em código, fora das fórmulas.
- **"português" não era "Língua Portuguesa".** `assunto.disciplina_citada` exigia
  todas as palavras distintivas. Daí quatro erros seguidos: o tópico 1.1 de
  Constitucional para quem pedia Português, "isso não cai na sua prova", "não
  tenho a numeração" e o programa só na sétima pergunta. Nome de duas palavras
  casa pela SEGUNDA quando ela tem 8 letras ou mais e é única no edital
  ("forenses" também; "geral" e "penal", não).
- **"Resumão completo do assunto"** saía em duas linhas e uma pergunta. "Resumão",
  "resumo completo" ou "geral", "assunto completo", "textão" e "tudo sobre" abrem a
  leitura completa. Com assunto nomeado ("resumão de voz passiva"), a leitura
  começa no trecho do material que trata dele (`leitura._ordem_do_assunto`); "na
  ordem do material" continua do começo.
- **Reclamação de pedido ignorado** era respondida com "o que você precisa que eu
  faça?". Regra na seção 3: faça agora o pedido anterior.
- **Tabela do PDF (separada por tabulação)** aparecia crua. A tela desenha.
- **PDF justificado, uma palavra por linha: 52% dos trechos das apostilas da conta
  real** (2.098 de 4.032; Poder Judiciário 80%, Direitos sociais 90%). O `pypdf`
  separa cada palavra com uma linha de um espaço. `chunking.desquebrar` remonta: 0
  trechos quebrados e o dobro de palavras por trecho. Vale para o que for subido
  daqui em diante; o que já está indexado precisa ser reprocessado.

## O índice de assuntos por trecho (036, `core/indice.py`, 30/09/2026)

**O problema.** O material era uma sequência de trechos soltos, com um rótulo para
o arquivo inteiro. "Resumão de voz passiva", "questões de habeas corpus" e "onde
está X" dependiam de a busca acertar um trecho solto. Assunto retomado mais
adiante, ou cobrado nas questões comentadas do fim, não era juntado.

**Medido antes de construir** (bateria nas 18 apostilas da conta real; precisão
julgada à mão, numa amostra):

| Caminho | Precisão | Lugares espalhados | Assuntos vizinhos |
|---|---|---|---|
| Sumário, títulos e agrupamento por vetor (sem modelo) | 60–75%, instável | perdia as questões | habeas corpus e mandado de segurança num grupo de 82 trechos |
| Modelo leve lendo a apostila | 72–77% | voz passiva em 18 de 24; mandado de segurança em 36 de 44 | 3 trechos com os dois |

O e5 não serve para limiar fixo: as similaridades ficam todas entre 0,82 e 0,87, e
o limiar de 0,88 marcou até 21 assuntos por trecho.

**Como ficou:**
- **Estrutura:** 1 chamada por material, com o começo (capa e sumário) e os títulos
  do corpo. Sai a lista de assuntos com páginas e papel (ensino, questões, outro).
- **Marcação:** lotes de 30 trechos (60 estouraram o limite de tokens por minuto),
  com a SEÇÃO pela página como pista. Papel "outro" fica sem assunto; trecho de
  ensino sem assunto dentro de uma seção fica com o da seção.
- **Reserva sem modelo:** sumário ou títulos, marcados por seção e por expressão.
  O documento fica `reserva` e é refeito com cota (`python -m core.indice`).
- **Cota:** `config.LLM_INDICE` (`3.1-flash-lite`), nunca o modelo do tutor, e
  orçamento diário `INDICE_ORCAMENTO_DIA` (150), contado pela telemetria.
- **Uso:** questões de X saem dos trechos marcados com X (`geracao._pelo_indice`);
  "resumão de X" começa no primeiro trecho de ensino de X; o rótulo da fonte, na
  tela e no prompt, é o assunto do TRECHO ("Vozes verbais, p. 64").

**O que sobra:** o erro do modelo leve é entre assuntos vizinhos da mesma
apostila (impessoalidade marcada como princípio implícito; sanção e veto como
reforma constitucional). Trocar `LLM_INDICE` por um modelo mais forte é a
melhoria direta (`docs/PLANOS.md`).

## Questões de prova: o simulado do aluno vira banco de questões (037, `core/prova.py`, 30/09/2026)

**O pedido.** O aluno sobe simulados comentados de banca (100 questões de
múltipla escolha, gabarito e comentário do professor) e quer que virem questões:
que sirvam para treinar e que, ao pedir questões de um assunto, venham elas.

**Como ficou:**
- **Tipo de material "Simulado / questões".** É indexado como os outros (busca e
  índice de assuntos), e além disso cada questão é extraída para `questao`, com
  `origem='prova'`. Ela é **literal**: o modelo não reescreve nada.
- **Extração pela estrutura, sem modelo.** São três formas de gabarito: junto da
  questão ("Gabarito: C" mais o comentário), em tabela ("1 2 3 … / C E D …", também
  em blocos, todas as linhas de número antes das de letra, como sai do PDF) e
  em arquivo só de respostas, subido à parte, que se liga ao simulado pelo número
  da questão (`documento.gabarito_de`). Não é preciso mesclar arquivos.
- **Número sequencial.** Um "N." só abre questão se for o número seguinte. Em
  prova comentada vale o último "N." antes do gabarito, porque comentário com lista
  numerada ("2. reler o trecho") abriria a questão errada.
- **Texto-base, disciplina e assunto.** O texto antes do número vira o texto-base
  da questão (tabela `contexto`). Os títulos do simulado, casados com o edital da
  mesa, dão a disciplina. O índice (036) do trecho em que a questão está dá o
  assunto.
- **Sem gabarito nenhum, o modelo resolve** (`LLM_INDICE`, dentro do orçamento do
  índice), e fica `gabarito_fonte='tutor'`, que a tela mostra. Gabarito oficial
  que chegue depois substitui. Sem cota, a questão espera
  (`documento.questoes_sem_gabarito`) e `python -m core.prova` refaz.
- **Múltipla escolha existe de verdade**: `gabarito_letra` e `questao_alternativa`,
  corrigida em código (`socratic.avaliar_multipla_escolha`), sem dica e sem
  segunda tentativa, pelo mesmo motivo do item certo/errado. O comentário do
  professor é a explicação.
- **Na conversa**, "questões de X" traz primeiro as questões de prova ainda não
  respondidas que tratam de X (mesma trava de termos raros do gerador), e o
  gerador só completa o que faltar.

**O que fica para depois (o desenho já comporta):** servir a mesma questão em
outro formato (C/E por alternativa, por extenso, híbrido) é um modo de
apresentar, não outra questão. Sai da linha mais as alternativas, sem duplicar o
banco. Por isso a alternativa guarda o texto literal e o gabarito guarda a letra.

## Busca: braço lexical vivo, peso do tipo pela intenção, índice como terceira lista, resposta que escolhe (30/09/2026)

**Medido antes de mexer**, nas 73 falas reais com busca (`.logs/busca/medir.py`,
sem modelo) e no gabarito (`avaliar_retrieval.py`, 34 casos).

**1. O braço lexical estava morto: vazio em 70 de 73 falas (95%).** O
`websearch_to_tsquery` exige TODAS as palavras, e a consulta da conversa tem em
média 13. O peso 1.5 do lexical, medido no gabarito de frases curtas, não
valia na conversa. **Conserto:** quando o E acha menos de 3 trechos, valem
PARES, isto é, duas palavras da consulta no mesmo trecho
(`retrieval._termos_da_consulta`). O OU puro derrubava o gabarito de 32 para
29/34 (top-6). Os pares o levaram a **34/34**, com o top-1 igual (23/34). Vazio
nas conversas: 95% → 7%.

**2. Peso do tipo pela intenção da fala** (`retrieval.PESO_TIPO`, `intencao`).
Desempata, não exclui, e vale para todo tipo:
- **lei** (artigo, "o que diz a lei"): lei seca, depois jurisprudência;
- **jurisprudência** (STF, súmula, "como os tribunais decidem"): jurisprudência,
  depois lei;
- **conceito** (explica, o que é, cálculo, resumo): aula e resumo.

A intenção sai da FALA, não da consulta, que pode ter herdado o turno anterior.
A intenção "questões" foi tirada depois de medir: pegava "sem questões por
enquanto", e pedido de questões já vai ao banco do simulado. No gabarito, o
efeito foi nenhum (nem ganho nem perda). Nas conversas, saíram artigos de CF e
CP que entravam em pedidos de explicação.

**3. Índice de assuntos (036) como terceira lista do RRF.** A fala nomeia um
assunto do material, e os trechos marcados com ele entram, de qualquer parte
da apostila.

**4. A resposta que escolhe manda na consulta** (`assunto.em_foco`, ramo do eco).
O tutor ofereceu um cardápio de disciplinas e o aluno escolheu "ciências
forense?": a busca foi pelo cardápio inteiro e trouxe Direitos políticos. Agora:
- com disciplina citada, a fala é a escolha;
- com assunto próprio, a fala atual vai depois do assunto do tutor, que continua
  primeiro, como pede a decisão do caso Maria da Penha;
- "sim" ou "não" segue herdando.

Resultado: "ciências forense?" passou a trazer Perícias e Provas; "1.1
Interpretação e compreensão de texto" trocou a Lei 8.112 pelo simulado de
Interpretação.

**Julgado à mão** nas 57 falas que mudaram de trecho: 12 melhores, 4 piores
(duas eram a intenção "questões", já tirada), o resto empate entre páginas
vizinhas da mesma apostila.

**Ficou como está, de propósito:**
- pergunta "você tem material de X?" continua buscando: é o que deixa o tutor
  dizer onde está;
- 47% dos top-6 têm trechos vizinhos do mesmo material, por sobreposição de 150
  caracteres. Não é repetição: cada vizinho traz texto novo.

## Resumo, jurisprudência e simulado se organizam por DESCRIÇÃO (01/10/2026)

**Pedido do dono.** Só a aula se organiza pelo edital, com disciplina e assunto.
Resumo, jurisprudência e simulado ganham UMA descrição que agrupa ("Código de
Processo Penal", "Informativos do STF", "Simulados PCPR"), sugerida dos
materiais do mesmo tipo e não do edital.

**Como ficou:**
- A descrição mora em `documento.assunto`, sem migração (`TIPOS_POR_DESCRICAO`).
- A tela de envio mostra só "Descrição", com o indicador fixo "sugestões dos seus
  [tipo]". A biblioteca agrupa essas abas por descrição, e o lápis, o arrasto e o
  renomear de grupo mudam a descrição.
- **De onde sai o nome, em ordem:**
  1. o que o aluno digitou;
  2. o modelo, que lê o conteúdo e recebe o nome do arquivo ou o `<title>` da
     página como pista, além das descrições existentes do tipo para reusar
     igual;
  3. sem modelo, o nome do arquivo quando ele diz algo (`material.nome_util`):
     "del3689compilado", "aula_04" e "curso-392635-…-374d" não dizem.
- **Simulado entrou em `TIPOS_DE_REFERENCIA`.** Cem questões de doze
  disciplinas não têm um assunto, e a descrição no rótulo de busca de cada trecho
  seria o ruído medido na 027. Ela fica só na tela. O assunto de cada questão
  vem do índice (036).
- **Nome corrompido por codificação** ("3Âº Simulado") é consertado ao registrar
  (`material.sem_mojibake`), inclusive na forma decomposta (NFD) em que o
  arquivo real chegou.
- **Link de lei que o app já tem** (o CPP do Planalto) continua recusado: a
  segunda cópia competiria na busca. A mensagem passou a citar a própria lei.

## Simulado real: o texto remontado escondia as questões (`prova.ressegmentar`)

O primeiro simulado real (100 questões comentadas) deu **0 questões**. O
`chunking.desquebrar`, que conserta o PDF justificado com uma palavra por linha,
também juntou as linhas da prova ("…boa ou má. 1. Levando…", "Gabarito: C
COMENTÁRIO DO PROFESSOR: …").

O extrator agora põe cada marca no começo de uma linha: o número da questão
primeiro, depois gabarito, comentário e alternativas. Medido no arquivo:
- número solto antes do gabarito ("A = 5. Gabarito: E") deixava de ser
  reconhecido; resolvido pela ordem das marcas;
- título de seção colado ao fim do comentário anterior, em duas linhas;
- alternativa de mais de 4 linhas;
- "4 – 1 – 3 – 2" de um comentário lido como lista de gabarito, que trocava a
  questão 20;
- "À" fora da classe de maiúsculas, que parava a extração na 88.

Resultado: **100 de 100**, todas com 5 alternativas. O gabarito ao lado de cada
questão bate com a tabela da página 2 nas 100, e a disciplina sai certa nas doze
seções.

O simulado tinha ficado "pronto" sem questões porque a API reiniciou no meio da
indexação. A API agora importa no arranque todo simulado sem extração.

**Apagar simulado (01/10/2026).** As questões de prova saem junto (`material.apagar`).
O FK de `questao.documento_id` é SET NULL, pensado para a questão GERADA, e
deixou 99 questões sem trecho na fila de quem apagou o simulado. Elas foram
removidas, com zero tentativas. A tela recarrega as sugestões depois de apagar:
descrição ou assunto do último material apagado não é mais oferecido.

## Pedido de explicação abre a leitura; pergunta pontual responde pontual (01/10/2026)

**Pedido do dono:** "quando eu fizer pergunta pontual ele responde pontual,
quando eu pedir me explica tal coisa ou traga a explicação do assunto eu quero
trazer o pdf pro chat", e é preciso "insistir pra ele trazer igual na foto".

**Medido na conversa real.** Das 12 falas da conversa, só "continua" e "traga
todo o conceito" abriam a leitura. "traga todo conceito" (sem o "o"), "cadê o
conteúdo de Proposições Simples?", "me explica proposições compostas", "quero
entender…", "vamos começar do zero e seguir na ordem" e "é só isso que tem no
material?" respondiam em duas frases e uma pergunta.

**Como ficou** (`leitura.intencao`):
- **`RE_EXPLICACAO` abre a leitura:** explicar, ensinar, trazer ou mostrar o
  conteúdo, o conceito ou a matéria, querer entender ou aprender, "do zero",
  "seguir a ordem".
- **`RE_PONTUAL` fica fora:** "o que é…?", "qual…", "quando…", "diferença
  entre…". Pergunta sobre o próprio tutor também (`pedido.RE_SISTEMA` ganhou
  "como funciona o sistema/app").
- **`RE_MAIS` continua a leitura:** "é só isso?", "tem mais?", "de tudo".
- **Explicação de assunto nomeado vai ao COMEÇO DA SEÇÃO dele, pela página do
  índice (036),** e não ao primeiro trecho marcado. A introdução cita "proposições
  compostas" de passagem e é marcada com elas, e a leitura começava 30 páginas
  antes.
- **A leitura pula as seções `outro` do índice:** capa, aviso, apresentação. O
  "continua" lia a página da equipe de professores.
- **Continuar a leitura mantém a matéria do MATERIAL lido** (`socratic.explicar`).
  A página da equipe "de Raciocínio Lógico e Estatística" pôs Estatística em
  foco, não havia material dela, e o "certo.." virou "não temos material de
  Estatística".

Simulado na apostila real de Proposições, só leitura:
- "traga todo o conceito" começa na p. 5, depois de capa e apresentação;
- "continua" e "certo.." seguem a sequência;
- "me explica proposições compostas" vai à p. 34;
- "é só isso?" segue dali.

## O simulado contaminava as outras matérias (01/10/2026, conversa real)

Na conversa de Raciocínio Lógico:
- "vamos pros cálculos" citou "Interpretação de texto, p. 16" numa questão de
  juros;
- a resposta seguinte virou "Raciocínio Lógico-Matemático e Estatística", com a
  mediana do simulado;
- "e da questão anterior?" trouxe 2 cartões de Língua Portuguesa.

**Causas e consertos:**
- **O índice de assuntos (036) não lê simulado.** Ele é de apostila, que tem
  seções; num simulado de 12 disciplinas achou 3 "assuntos" e rotulou mal (o
  cartão "Parônimos" era uma questão de pontuação). O assunto da questão de prova
  é a disciplina da seção dela, e a citação de um trecho de simulado diz "questão
  28 · Raciocínio Lógico-Matemático" (`prova.rotulos_dos_trechos`).
- **Com matéria em foco, trecho de simulado de outra matéria sai da resposta**
  (`socratic._sem_prova_de_outra_materia`). Apostila e simulado sem questão
  extraída não são tocados.
- **"e da questão anterior?", "sim já com a resolução" e "resolve a anterior"**
  são resolução, não pedido de questões novas (`pedido.RE_RESOLUCAO`).
- **Sigla de disciplina** ("rlm", "lp") casa pelas iniciais do nome, quando é
  única no edital e não é palavra comum ("da", "do").
- **Só o nome da matéria** ("rlm", "português") retoma a leitura dela de onde
  parou (`leitura.so_escolhe_materia`). Antes pulava para "o próximo ponto do
  edital".
- **Asterisco solto na tela:** o itálico exigia a palavra colada (`*assim*`) mas
  aceitava "`* *`", isto é, o marcador da lista com o começo do negrito. Asterisco
  sem par sai da tela.

A saudação "Boa noite" respondendo a "bom dia" estava CERTA: eram 23h44 locais.

## Mapa de domínio e métrica das questões (02/10/2026)

**Caixas fixas, não SM-2.** O agendamento é Leitner (1, 3, 7, 15, 30, 90 dias),
sem fator de facilidade; o selo "Algoritmo SM-2" na tela era falso e virou
"Revisão espaçada". O dono preferiu manter as caixas: acerto com dica já não
punia (mantém a caixa), e trocar para SM-2 mudaria a fila de todo mundo sem nota
de 0–5 no histórico.

**Meio acerto estaciona.** `parcial` descia uma caixa; agora fica nela, como o
acerto com dica. O tutor é socrático — guia até a resposta —, e punir quem chegou
perto com a ajuda dele contradiz a didática. Continua indo para o caderno de erros.

**Cobertura em camadas.** "Coberto" = caixa ≥ 3 (15 dias): nas primeiras semanas
a tela mostrava 0% para quem estudava todo dia. `em_construcao_pct` (respondida,
abaixo da caixa 3) é a camada amarela ao lado do verde em Panorama, Raio-X e
Meu edital. O limiar do verde não mudou.

**Ligação ao edital pelo índice, decidida pelo modelo.** Medido na conta real
(110 assuntos de edital, 119 nomes do índice): o 035 levava só 1 de 108 questões a
um assunto; palavras em comum erram ("Verbos" -> "Modos de organização
discursiva", por "modo"); os vetores e5 erram com folga grande, pelo texto inteiro
e por subitem ("Princípios fundamentais" -> "Direitos e garantias", folga 0,033).
O modelo do índice (cota própria), uma chamada por material com os nomes do
índice contra os assuntos do edital da disciplina, acertou os casos acima:
"Verbos" -> "Classes de palavras", "Supremo Tribunal Federal" -> "Poderes da
União". 18 chamadas para 160 nomes. Sem cota, as palavras distintivas com folga
1,5× sobre o segundo, gravadas como `texto` e refeitas depois.

"Estudado" = leu o trecho com o tutor (leitura em sequência ou fonte citada) ou
respondeu questão do assunto. O ciclo do assunto é o da questão mais fraca dele.
Questão sem assunto identificado aparece como contagem na disciplina, nunca
forçada num assunto.

**Defeito à parte, não consertado aqui:** o 035 marca 313 subitens do edital real
como "sem material" e 1 como "coberto", inclusive onde há apostila do assunto.

## Bateria de estudo: dois meses simulados sobre a conta real (02/10/2026)

`bateria_estudo.py` copia uma mesa real (edital, material, índice, questões) para
uma conta descartável e simula 60 dias pelas rotas, envelhecendo as datas um dia
por vez. Cota zero. A conta real não é usada: dois meses inventados no histórico
dela misturariam fila, caderno e mapa com o que não aconteceu. O que achou:

- **Fuso.** O Postgres roda em UTC e o Python no horário local: das 20h à
  meia-noite (UTC−4) `CURRENT_DATE` já era amanhã — a questão errada à noite
  voltava à fila na mesma noite, e o estudo da noite contava no dia seguinte.
  A conexão agora usa o fuso do processo (`db.fuso_local`: `TZ`, senão
  /etc/localtime). Na nuvem, processo e banco em UTC continuam iguais.
- **/meta contava questão privada de outra pessoa** no denominador (sem
  `questoes.do_aluno`): 2,3% dominado onde eram 4,7%.
- **Questão de prova não chegava ao edital**: só 3 de 32 pelo trecho. Ligada
  pelo enunciado (039), pelo modelo do índice, lote de 12 (25 estourou 4000
  tokens de resposta): 96 de 103 com assunto, conferidas à mão por amostra.
- Sem defeito nas conferências automáticas depois disso: caixa e próxima revisão
  de cada questão batem com as regras puras; mapa refeito do banco por outro
  caminho bate; fila, meta e caderno coerentes entre si. O domínio latente do
  aluno simulado acompanha o mapa (dominado 0,82 · em dia 0,69).

Duas regras de produto, decididas pelo dono:

- **Superados.** O caderno nunca tirava a questão que já chegou à caixa de 15
  dias (com 95% dominado ainda listava 20 "erros"). Agora ela sai da lista
  principal, do que o tutor (`socratic`, `ritmo`) e o desafio tratam como
  fraqueza, e aparece em "Superados" (`/erros?superados=1`). O histórico fica.
- **Pouca evidência.** 33 dos 53 assuntos ligados têm UMA questão só. O verde
  continua, mas o mapa mostra em quantas questões diferentes ele se apoia
  (`questoes_distintas`) e, abaixo de 3, a gaveta pede mais questões. Exigir 3
  para ficar verde foi recusado: com o banco atual quase nenhum assunto chegaria
  lá sem gerar questão, e isso gasta cota.

## Uma conta só para "estudado", "dominado" e "edital fechado" (02/10/2026)

Relatado pelo dono, com a carga de dois meses na conta: o Meu edital contava 466
subitens onde o mapa contava 110 assuntos; "edital fechado 94%" com 53 assuntos
nunca tocados; e "1 sem contato recente" com quase todo o material sem ler.

- **Estudado = leu a maior parte do material do assunto** (`LIMIAR_LIDO` = 70% dos
  trechos de ensino ligados a ele pelo índice) ou, não havendo material, respondeu
  questões ("só por questões"). Ler um trecho ou responder uma questão é "em
  andamento". Medido: o aluno simulado leu menos de 10% dos 2.522 trechos e todo
  assunto com material saía "estudado".
- **Dominado exige estudado**: questão em dia com a apostila sem ler é acerto de
  questão, não domínio do assunto (`questoes_em_dia` diz isso à parte).
- **Atenção** ganha "material não lido": assunto com material abaixo do limiar.
- **Edital fechado e o Meu edital por disciplina** contam assuntos dominados sobre
  o total do edital (`dominio._contas`), e a probabilidade de fechamento usa o mesmo
  número: na conta carregada caiu de 100% para 9,3% (68 assuntos, 9 dias). Sem
  edital, segue por questões. O Panorama passou a dizer "questões dominadas" onde
  a conta é por questão.
- **"O que do edital está no seu material"** saiu da conferência por subitem (035)
  para o mapa: assunto com material, onde está (apostila, seção, páginas) e quanto
  foi lido. O resumo que o tutor recebe no chat também. O 035 continua no backend
  para a leitura na ordem do edital e o "onde está"; o defeito de "sem material"
  dele segue aberto (ver LIMITACOES).

## Conversa real de 02/10/2026: "ti", "5", "eu pedi de…", recusa e matérias não vistas

Achados na conversa do dono e conferidos pela `bateria_decisoes.py` (124 falas, sem
modelo) e por 4 chamadas numa cópia da conta:

- **Disciplina de nome longo não era reconhecida.** "ti" e "fundamentos de informática,
  sistemas operacionais e segurança da informação" não achavam "Tecnologia e Sistemas
  de Informação e de Comunicação, Segurança Cibernética e Crimes Digitais". Agora:
  sigla pelas iniciais EM ORDEM (nome de 4+ palavras, sigla única; "pra ti" é pronome),
  duas palavras próprias do nome, e as duas primeiras palavras ("direito penal").
- **Pedido vago após explicação SEM fonte** buscava pelas palavras da explicação e
  trouxe Direito Penal ("integridade", "comunicação") para TI. Só explicação com fonte
  vira assunto de busca; e o sorteio sem assunto respeita a matéria em foco (sem
  material dela, não há questão).
- **"5" respondendo à oferta** é aceite com essa quantidade; **"eu não pedi X, eu pedi
  de Y"** é pedido de Y.
- **Recusa** ("não", "também não") não adota a matéria que o tutor ofereceu: vale a
  última que o aluno nomeou.
- **"Quais matérias não vi?"** vem da seção do mapa (assuntos começados por disciplina,
  "Disciplinas sem nenhum assunto começado"), e o tutor não dá razão contra os
  registros nem inventa "o registro falhou".
- Questões geradas com a frase que as oferecia: a frase sai da resposta.
