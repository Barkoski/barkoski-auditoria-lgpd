# Changelog

## 0.2.0 — 10/11/2026 (candidata)

Motivação: testes em projetos reais mostraram que a skill diagnosticava bem, mas (1) não conduzia o dono até a adequação, (2) falhava na atualização jurídica sempre que a fonte oficial não respondia e (3) dependia de o modelo lembrar o que procurar.

### Adicionado
- **Varredura determinística** (`scripts/varredura.py`): somente leitura, sem rede, só biblioteca padrão; mascara segredos e dados pessoais; recusa gravar a saída dentro do projeto; analisa o que scripts de build/deploy empacotam; agrega `.env*` por arquivo e usa `git` somente leitura para saber se estão versionados; relatório Markdown começa com "Top 10" e agrupa repetições. Validada em dois projetos reais (site PHP: 36 achados, 7/7 itens do gabarito; SaaS Next.js: 939 → 333 achados e 16 → 1 alta após três rodadas de correção de falsos positivos, mantendo o único verdadeiro positivo grave).
- **Redução de falsos positivos:** credenciais de teste reconhecidas também em português (`testar`, `exemplo`, `ficticio`, `sonda`…), com exceção para valor idêntico ao de um `.env` (hash só em memória → alta); CPF/CNPJ só com dígito verificador válido; telefone só em formato brasileiro plausível e nunca dentro de número de processo CNJ; campo de formulário classificado por `name`/`id`/`type`, nunca por placeholder; `.git` na raiz como info; pastas públicas só com imagens como baixa; pasta de documentos em que PDFs são minoria como média; pastas de build/cache (`.next*`, `.cache*`, `coverage`…) ignoradas.
- **Marketplace:** `.claude-plugin/marketplace.json` para instalar com `/plugin marketplace add Barkoski/barkoski-auditoria-lgpd`. Pacote passa em `claude plugin validate --strict`. Fallback manual em `references/padroes-varredura.md`.
- **Projeto-isca e testes** em `evals/` (`fixture-site-isca/`, `test_varredura.py`).
- **Cadeia de fontes jurídicas** no `SKILL.md` (oficial → espelho oficial → base local → dispositivos embutidos → memória sinalizada), com registro do degrau usado no relatório.
- **`references/dispositivos-chave.md`**: texto literal datado (captura de 14/10/2026) dos artigos mais usados da LGPD, do art. 15 do Marco Civil e do art. 1º do ECA Digital.
- **Modo "decisões do dono"** (`references/decisoes-do-dono.md` e seção 5 do `SKILL.md`): 12 perguntas em linguagem simples, registro de decisões e minutas geradas só com as respostas obtidas.

### Alterado
- Regra de segredos estendida a arquivos de configuração fora de `.env` (`config.php`, `wp-config.php` etc.).
- Modelo de relatório passa a informar o degrau de fonte e se a varredura rodou.
- README: o pacote agora inclui um script; badge e seção de dados/permissões atualizados.

### Registrado para verificação
- Lei 15.352/2026 aparece como origem da redação dos incisos VIII e XIX do art. 5º da LGPD na captura de 14/10/2026. Alcance não verificado.

## 0.1.0 — 22/10/2026

Versão inicial.
