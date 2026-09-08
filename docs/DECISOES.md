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
metade de um booleano não é nada, e `parcial` DESCE uma caixa em
`scheduler_regras`, punindo por um estado que o formato não pode ocupar.

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
possível por causa da 024 — antes dela os bytes não existiam e reindexar exigia
o upload de novo, que era exatamente o atrito que fazia a correção não valer
nada. Material anterior à 024 não reindexa (`reindexar: false` na resposta) e
fica com o vetor antigo: a lista continua certa, a busca é que não melhora, e
isso é melhor que apagar os trechos que existem.

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
