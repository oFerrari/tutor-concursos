# corpus/

Leis do Planalto, em texto puro (`.txt`). Vai para o git de propósito: texto
de lei não tem direito autoral no Brasil (art. 8º, IV da Lei 9.610), e isso
resolve o bloqueio de rede corporativa — reingerir numa máquina nova não
depende de baixar de novo.

Diferente de `acervo/` (PDF de cursinho, material pago), que continua fora
do git.

## Como chega aqui

1. Baixe o HTML compilado no Planalto — ex., Código Penal:
   `https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm`.
   Salve o `.html` também (ele fica no git ao lado do `.txt` derivado — ver
   `Del3689Compilado.html`/`L8112consol.html`): reproduzir a conversão sem
   baixar de novo é o mesmo motivo de manter o `.txt`.
2. Extraia o texto puro com `html_para_texto.py` (cp1252, não utf-8 — é o
   que o `<meta charset>` do Planalto declara):
   ```bash
   python corpus/html_para_texto.py corpus/SeuArquivo.html corpus/norma.txt \
       --cortar-em "MARCADOR — ver armadilhas abaixo"
   ```
   `--cortar-em` é obrigatório: cada lei tem uma assinatura/aviso/eventual
   anexo diferente depois do último artigo de verdade, e adivinhar por
   posição no arquivo já causou bug real (ver armadilhas abaixo).
3. Salve em `corpus/<norma-em-minúsculas>.txt` — ex. `corpus/cp.txt`.
4. **Sempre valide antes de ingerir**: `python diagnostico.py corpus/cp.txt --norma CP`
   — segundos, sem banco. Confira "artigos sem rubrica: N, destes com
   candidata ACEITA que não foi atribuída: **0**" (o "único número que
   indica bug" do próprio diagnóstico) e a taxa de colisão de artigo
   (`from core import chunking; chunking.taxa_colisao_artigo(chunks)` —
   `ingest.py`/`reingest.py` abortam sozinhos acima de 5%, mas vale checar
   antes, não só confiar no abort).
5. Ingira:
   ```bash
   python ingest.py corpus/cp.txt --disciplina "Direito Penal" --tipo lei --norma CP
   ```

## Armadilhas reais encontradas nestas extrações

- **Assinatura e aviso de rodapé colados no último artigo.** O HTML
  compilado tem assinatura ("Rio de Janeiro, 7 de dezembro de 1940...",
  "GETÚLIO VARGAS") e aviso ("Este texto não substitui o publicado no
  DOU...") logo depois do último artigo. `cp.txt` tinha isso colado no
  corpo do Art. 361 — `_cortar_cauda` não descarta porque o trecho termina
  em pontuação e não parece rubrica nem nota. `diagnostico.py` NÃO detecta:
  a métrica é contagem de artigo/rubrica, não conteúdo do corpo, então o
  arquivo passava limpo com o defeito dentro. Só apareceu ao inspecionar
  `chunk_lei(...)[-1]` na mão. Corrigido cortando a partir do marcador
  ("Rio de Janeiro, 7 de") — corte pelo MARCADOR, não por posição no arquivo
  — e é exatamente pra isso que `--cortar-em` existe em `html_para_texto.py`.
- **Anexo de "partes vetadas mantidas pelo Congresso" depois da assinatura
  real (Lei 8.112).** Depois da assinatura de verdade (Brasília, 11/12/1990,
  Fernando Collor), o HTML compilado inclui um SEGUNDO bloco de cabeçalho +
  promulgação do Presidente do Senado reintroduzindo "Art. 87", "Art. 250"
  etc. dentro de um `<blockquote>`. Sem cortar antes disso, esses números
  eram lidos como artigos NOVOS, colidindo com os originais (23,9% de
  colisão medida antes do corte). `--cortar-em` na assinatura real resolve.
- **Redação revogada tachada, com o MESMO número de artigo (Lei 8.112,
  ~250 ocorrências).** Diferente de artigo TOTALMENTE revogado (que deve
  ser preservado — é matéria de prova), aqui é a redação ANTIGA de um
  artigo emendado, mostrada ao lado da vigente, tachada — via tag
  `<strike>` OU via `<span style="text-decoration:line-through">` (dois
  mecanismos diferentes no mesmo documento). Sem descartar as duas formas,
  `RE_ARTIGO` casava a redação revogada como se fosse outro artigo com o
  MESMO número — 23,9% de colisão medida. `html_para_texto.py` descarta o
  conteúdo de ambas as formas (`TAGS_IGNORAR_CONTEUDO` + `_tem_tachado()`).
- **Citação de artigo de OUTRA lei no meio de um parágrafo, quebrada em
  nova linha, casa com `RE_ARTIGO` como se fosse um artigo novo** (mesma
  classe de "chunk fantasma" já documentada pro ADCT em CLAUDE.md). Achado
  no CPP: "art. 159 do Decreto-Lei nº 2.848... (Código Penal)" e "Art. 101,
  I, g, da Constituição" geram 2 falsos positivos (0,24% de colisão) — baixo
  volume, mesma decisão já tomada pro ADCT: não vale regex mais esperto
  pra uma fração tão pequena enquanto não aparecer caso real de citação
  errada num gabarito de avaliação.
