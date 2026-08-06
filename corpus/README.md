# corpus/

Leis do Planalto, em texto puro (`.txt`). Vai para o git de propósito: texto
de lei não tem direito autoral no Brasil (art. 8º, IV da Lei 9.610), e isso
resolve o bloqueio de rede corporativa — reingerir numa máquina nova não
depende de baixar de novo.

Diferente de `acervo/` (PDF de cursinho, material pago), que continua fora
do git.

## Como chega aqui

1. Baixe o texto compilado no Planalto — ex., Código Penal:
   `https://www.planalto.gov.br/ccivil_03/decreto-lei/del2848compilado.htm`
   (salve como `.txt`; se vier HTML, extraia o texto antes).
2. Salve em `corpus/<norma-em-minúsculas>.txt` — ex. `corpus/cp.txt`.
3. Ingira:
   ```bash
   python ingest.py corpus/cp.txt --disciplina "Direito Penal" --tipo lei --norma CP
   ```

> Nota: este arquivo ainda não tem `cp.txt` porque a máquina que gerou este
> commit não teve acesso à rede do Planalto (bloqueio de ambiente, o mesmo
> tipo de bloqueio que o corporativo). Baixe pelo navegador e adicione — é
> exatamente o passo manual que este diretório existe para evitar repetir.
