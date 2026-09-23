# Schema — o que cada migração trouxe

Livro-razão legível. O estado REAL do banco sai de `python migrar.py --listar`,
e o porquê de cada decisão está em `docs/DECISOES.md`. `db/schema.dbml` é a
visualização; a fonte de verdade são os arquivos `db/*.sql`.

```
db/001_schema.sql          documento, chunk, questao, tentativa, erro_caderno
db/002_rubrica_secao.sql   colunas rubrica e secao
db/003_embedding_cache.sql cache de vetores por hash de conteúdo
db/004_simulado.sql        tabela simulado, tentativa.simulado_id
db/005_desempenho_json.sql v_desempenho_disciplina em float8 (JSON-pronta) + cobertura_pct
db/006_tipo_historico.sql  documento.tipo aceita 'historico' (material com múltiplas versões do artigo)
db/007_edital.sql          tabelas edital e topico
db/008_usuario.sql         usuario, progresso (caixa/prox_revisao saem de questao), usuario_id em tudo pessoal
db/009_cascade_usuario.sql ON DELETE CASCADE consistente em toda FK pra usuario
db/010_mesa.sql            mesa de estudo: edital passa a ser da mesa, simulado ganha etiqueta
db/011_edital_rascunho.sql rascunho de edital: curadoria (escolher cargo) antes de virar oficial
db/012_questao_tipo.sql    questao.tipo + gabarito_ce: item CERTO/ERRADO (Cebraspe), CHECK casada
db/013_contexto.sql        "Texto associado": texto-base compartilhado por vários itens
db/014_conversa.sql        conversa + mensagem: o chat do tutor passa a ter memória
db/015_perfil.sql          usuario.perfil (JSONB): horas/nível/turno declarados no onboarding
db/016_mensagem_evento.sql mensagem de EVENTO: o que o aluno FEZ (errou a questão), não só o que disse
db/017_mesa_disciplinas.sql mesa declara disciplinas SEM edital — cartão de mesa nova para de nascer cheio
db/018_edital_cargo.sql    edital.cargo: o plano diz PARA QUEM ele é (17 cargos no da PF)
db/018_simulado_resumavel.sql simulado.questao_ids: a prova sobrevive a queda de conexão no meio
db/019_simulado_nome.sql   simulado.nome: três provas no mesmo dia deixam de ser indistinguíveis
db/019_material_do_aluno.sql documento.usuario_id + status/erro/chunks_total: biblioteca privada
db/020_material_classificado.sql disciplina virou NULLABLE + assunto + classificado_por
db/021_biblioteca_por_mesa.sql documento.mesa_id + mesa.biblioteca_compartilhada
db/022_conceito_faltante.sql tentativa.conceito_faltante: o que o aluno CONFUNDE
db/023_migracao.sql        livro-razão: quais migrações já rodaram NESTE banco
db/024_arquivo_do_material.sql documento.arquivo (bytea): o PDF original fica guardado, e dá pra baixar de volta
db/025_rotulo_no_lexical.sql chunk.rotulo entra no tsvector: a disciplina/assunto que o ALUNO corrige passa a valer na BUSCA
db/026_questao_do_aluno.sql questao.usuario_id: questão gerada da APOSTILA dele, privada — NULL segue sendo o acervo de todos
db/027_referencia_sem_assunto.sql material de REFERÊNCIA (jurisprudência, corpus de norma) não tem assunto — um rótulo único num corpus mentia E afogava a busca
db/028_url_do_material.sql documento.url: de onde o material veio, quando veio de link — `origem` guarda só o nome derivado
db/029_fila_melhoria.sql feedback `/erro`/`/feedback` preso à conversa e à resposta do tutor comentada
db/030_telemetria_llm.sql provedor/modelo, tokens, status e origem de cada chamada de LLM
db/031_estudo_teoria.sql diário por usuário/dia/assunto para teoria conversada atravessar sessões
db/032_desempenho_sem_questao_alheia.sql o denominador do desempenho deixa de contar questão privada de outro aluno
```

Próximo número livre: **033**. Confirme no diretório e com
`python migrar.py --listar` antes de criar.
