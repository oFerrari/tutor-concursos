# corpus/

Leis do Planalto, em texto puro (`.txt`). Vai para o git de propósito: texto
de lei não tem direito autoral no Brasil (art. 8º, IV da Lei 9.610), e isso
resolve o bloqueio de rede corporativa — reingerir numa máquina nova não
depende de baixar de novo.

Diferente de `acervo/` (PDF de cursinho, material pago), que continua fora
do git.

## Como chega aqui

1. Baixe o HTML compilado no Planalto — ex., Código Penal:
   `https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm`
2. Extraia o texto puro e **corte manualmente** a assinatura/aviso de rodapé
   do final (ver armadilha abaixo — nenhuma ferramenta de extração tira isso
   de graça).
3. Salve em `corpus/<norma-em-minúsculas>.txt` — ex. `corpus/cp.txt`.
4. **Sempre valide antes de ingerir**: `python diagnostico.py corpus/cp.txt --norma CP`
   — segundos, sem banco. `cp.txt` bate 434/434 artigos, 0 rubrica aceita
   perdida (o "único número que indica bug" do próprio diagnóstico). Isso
   NÃO garante que o final do arquivo está limpo — ver armadilha abaixo.
5. Ingira:
   ```bash
   python ingest.py corpus/cp.txt --disciplina "Direito Penal" --tipo lei --norma CP
   ```

## Armadilha real encontrada nesta extração

O HTML compilado tem assinatura e aviso de rodapé ("Rio de Janeiro, 7 de
dezembro de 1940...", "GETÚLIO VARGAS", "Este texto não substitui o
publicado no DOU...") logo depois do último artigo (Art. 361). `cp.txt`
tinha isso colado no corpo do Art. 361 — `_cortar_cauda` não descarta porque
o trecho termina em pontuação e não parece rubrica nem nota. `diagnostico.py`
NÃO detecta: a métrica é contagem de artigo/rubrica, não conteúdo do corpo,
então o arquivo passava limpo com o defeito dentro. Só apareceu ao inspecionar
`chunk_lei(...)[-1]` na mão. Corrigido cortando a partir de "Rio de Janeiro,
7 de" — corte pelo MARCADOR (varia por lei), não por posição no arquivo.
