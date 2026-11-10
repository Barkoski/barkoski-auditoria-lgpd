# Padrões da varredura determinística

A varredura procura **pistas** de risco LGPD no código e nos arquivos de um projeto. O resultado é pista, não prova: zero achados não prova ausência de problema, e cada achado precisa de confirmação humana (o trecho pode ser exemplo, código morto ou dado falso).

## Como rodar

PowerShell no Windows (o relatório precisa ficar FORA da pasta do projeto):

```powershell
py -I scripts\varredura.py "C:\caminho\do\projeto" --saida "$env:TEMP\varredura.md"
```

Opções: `--formato json` (ou saída com extensão `.json`) para leitura por máquina; `--max-bytes N` (padrão 1048576) para o tamanho máximo de arquivo lido.

Pastas ignoradas (e reportadas em "limites"): node_modules, .git, vendor, .venv, venv, __pycache__, dist, build, out, coverage, .turbo, .cache, .svelte-kit, .nuxt, target, qualquer pasta que comece com `.next`, `.vercel/output`, .claude, .agents. Arquivos `*.min.js`, `*.min.css` e chunks compilados também são pulados.

Único subprocesso: `git` somente leitura (`rev-parse`, `ls-files`, `check-ignore`; lista de argumentos, sem shell, timeout curto), usado só para saber se arquivos `.env*` estão versionados ou fora do `.gitignore`. Sem git ou fora de repositório, isso é pulado e o achado informa que não foi possível verificar. Cada `.env*` real vira UM achado ("arquivo de ambiente com K valores secretos", só os nomes): alta se versionado ou fora do .gitignore; info se ignorado e só local.

Arquivos `.sql` de migration/schema saem como info; dump (`.dump`, `.sql.gz`, `.sql` com nome dump/backup, maior que 1 MB, `COPY ... FROM stdin` ou 50+ `INSERT INTO`) sai como alta. O relatório md agrupa achados repetidos por pasta e começa com "Top 10 para olhar primeiro"; o JSON traz a lista completa. Qualquer sequência longa com cara de token no trecho é mascarada.

Regras de redução de ruído (rodada 3):
- Credencial de teste: caminho ou nome com test, spec, e2e, mock, fixture, testar, teste, exemplo, ficticio, sonda, ouro, seed, demo, sample etc. vira baixa ("credencial de teste? confirme que não é real"). Exceção: o script calcula SHA-256 só em memória dos valores secretos dos `.env*` reais e, se o mesmo valor aparecer em qualquer outro arquivo (mesmo de teste), o achado vira ALTA ("valor idêntico ao de <env> (chave X)", e "versionado no git" quando for o caso). Valor e hash nunca são gravados nem impressos.
- CPF e CNPJ: só com dígitos verificadores válidos e sem sequência repetida. CPF válido em teste/exemplo/.md ou exemplo clássico de documentação é baixa; fora disso, média. CNPJ (pessoa jurídica) é sempre baixa.
- Telefone: formato brasileiro plausível (DDD 11 a 99; celular 9xxxx ou fixo 2xxx a 5xxx; com parênteses, +55 ou separador) e nunca colado a outros dígitos, número de processo CNJ ou UUID.
- Campos de formulário: classificados só por name, id, type e autocomplete (nunca placeholder, value ou texto).
- `.git` na raiz é info; alta só dentro de pasta servida (public, public_html, www, htdocs, dist, build, out, static) ou se o script de empacotamento a incluir.
- Pasta só com imagens sob public/static/assets/img é baixa ("conteúdo público por desenho"); PDF/DOCX, tmp/, docs/, uploads/, pdfs/ e ocr* seguem como alta.
- Empacotamento: a lista de "não excluído" traz só itens que seguem alta/média (segredos reais, `.env` não ignorado, dumps, pastas de documentos, .git, setup/install).

Garantias do script: só biblioteca padrão do Python 3.9+, sem rede, sem executar nada do projeto (exceto o `git` somente leitura acima), somente leitura, não segue links simbólicos/junctions, recusa gravar a saída dentro do projeto, mascara segredos e dados pessoais (no máximo 2 caracteres + comprimento) e não lista nomes de arquivos dentro de pastas de documentos (só contagem por extensão). Termina com código 0 quando rodou; código 2 só para erro de uso.

Cada achado traz: regra, categoria, severidade sugerida (alta, média, baixa, info), arquivo, linha, trecho mascarado e dica. O relatório inclui "limites": pastas ignoradas que existem (node_modules, .git, vendor, .venv, venv, __pycache__, dist, .next, build, .claude, .agents), binários e arquivos grandes pulados.

## O que cada categoria significa

| Categoria | Em linguagem simples |
|---|---|
| segredos | Senhas, chaves e tokens escritos dentro de arquivos. Chaves feitas para o navegador (NEXT_PUBLIC_*, anon do Supabase, apiKey web do Firebase) saem como info: são públicas por desenho, mas dependem de regras/RLS bem configuradas. |
| rastreadores_terceiros | Scripts e recursos de terceiros que recebem dados do visitante (analytics, pixels, gravação de sessão, Google Fonts, mapas, vídeos, CDNs). Pedem aviso de privacidade e, em geral, consentimento. |
| coleta_dados_pessoais | Formulários, campos, colunas de banco e uploads que coletam nome, e-mail, telefone, CPF, saúde etc. Mostra onde a coleta acontece e se há aviso e base legal. Inclui CPF/e-mail/telefone soltos em arquivos de dados (mascarados). |
| sessao_cookies | Como o login e os cookies são guardados (session_start sem cookie_secure, cookies sem Secure/HttpOnly/SameSite, localStorage). |
| logs | Registros (console.log, error_log, print) que gravam dados pessoais ou a requisição inteira. Logs costumam ficar sem controle de acesso e sem prazo de retenção. |
| artefatos_deploy | Arquivos que não deveriam estar no projeto publicado: dumps .sql, backups, .zip, .env, install.php/setup.php/phpinfo.php, pasta .git, e ausência de .gitignore quando há segredos. |
| empacotamento | O que o script de deploy/zip leva junto. Aponta itens sensíveis que o script NÃO exclui (ex.: lista $exclude comparada só com o primeiro segmento do caminho, que deixa passar config.php e tmp). Se não conseguir concluir: "revisar manualmente o que o script empacota". |
| pastas_documentos | Pastas com muitos PDFs, imagens digitalizadas ou DOCX (5 ou mais), como tmp/, uploads/, docs/. Só caminho da pasta e contagem por extensão; nomes de arquivo não são listados. Verifica se há regra de bloqueio. |
| protecao_web | Heurística para PHP/Apache: o que o .htaccess da raiz bloqueia e o que fica de fora; ausência de redirecionamento HTTPS e de cabeçalhos de segurança (info; a hospedagem pode fazer isso fora do projeto). |
| ia_externa | Chamadas a provedores de IA (OpenAI, Anthropic, Gemini, Groq, OpenRouter, Replicate, Hugging Face). Info: dados podem ir ao provedor; confira finalidade, retenção e transferência internacional. |

## Limites conhecidos

- Heurística por texto: pode haver falso positivo (exemplo, documentação) e falso negativo (valor montado em tempo de execução, segredo em arquivo binário ou acima do limite, regra definida no painel da hospedagem ou no nginx).
- A análise do .htaccess e dos scripts de empacotamento é aproximada (FilesMatch, RedirectMatch, RewriteRule com [F], Require all denied; listas $exclude, --exclude, -x). Teste a URL direta do arquivo e abra o pacote gerado para confirmar.
- Conteúdo de pastas de documentos não é lido. Arquivos binários não são analisados.

## Fallback sem Python (busca por padrão com Grep)

Quando não for possível rodar o script, use a ferramenta de busca (Grep) do agente com os padrões abaixo, na raiz do projeto, ignorando `node_modules`, `.git`, `vendor`, `.venv`, `dist`, `build`. Ao relatar, **mascare** os valores (2 caracteres + comprimento) e não cole segredo nem dado pessoal na resposta. Padrões em regex estilo ripgrep (adapte as barras e aspas conforme a ferramenta).

| Categoria | Padrões principais |
|---|---|
| segredos | `define\(\s*['"][A-Z_]*(PASS\|PASSWORD\|SECRET\|TOKEN\|KEY\|SALT)[A-Z_]*['"]\s*,\s*['"][^'"]+['"]`; `(?i)(password\|passwd\|pwd\|senha\|secret\|api[_-]?key\|token)['"\]]*\s*(=>\|=\|:)\s*['"][^'"\s]{4,}['"]`; `sk-[A-Za-z0-9_-]{20,}`; `AKIA[0-9A-Z]{16}`; `ghp_[A-Za-z0-9]{36}`; `-----BEGIN [A-Z ]*PRIVATE KEY-----`; `(postgres\|mysql\|mongodb)(\+srv)?://[^:/@\s]+:[^@\s]+@`; `service_role`; arquivos `.env*` |
| segredos (públicos, info) | `NEXT_PUBLIC_`; `VITE_`; `anon`; `apiKey\s*:` junto de `authDomain` |
| rastreadores_terceiros | `google-analytics\.com\|gtag\s*\(\|googletagmanager\.com`; `fbq\s*\(\|connect\.facebook\.net`; `hotjar\|clarity\.ms\|ttq\.\|snap\.licdn\.com`; `fonts\.(googleapis\|gstatic)\.com`; `recaptcha`; `youtube(-nocookie)?\.com/embed\|google\.com/maps/embed`; `cdnjs\.cloudflare\.com\|cdn\.jsdelivr\.net\|unpkg\.com`; `sentry\|logrocket\|fullstory\|rrweb\|posthog\|mixpanel\|segment\.com` |
| coleta_dados_pessoais | `<form\b`; `<input[^>]*(name\|id)=['"][^'"]*(nome\|email\|e-mail\|tel\|fone\|cpf\|cnpj\|rg\|nasc\|endere\|cep\|senha\|password\|saude)`; `type=['"](email\|tel\|password\|file)['"]`; colunas em `.sql`/`.prisma`: `^\s*\W?(nome\|email\|cpf\|rg\|telefone\|nascimento\|endereco\|cep)\W?\s+(varchar\|text\|int\|date\|String)`; `\d{3}\.\d{3}\.\d{3}-\d{2}` |
| sessao_cookies | `session_start\s*\(` (e a ausência de `cookie_secure` no projeto); `setcookie\s*\(`; `document\.cookie\s*=`; `(localStorage\|sessionStorage)\.setItem` |
| logs | `(console\.(log\|error\|warn)\|error_log\|var_dump\|print_r\|print\|logger\.\w+)\s*\(.*(cpf\|email\|senha\|password\|telefone\|nome\|req\.body\|\$_POST\|\$_REQUEST)` |
| artefatos_deploy | nomes: `*.zip`, `*.sql`, `*.sql.gz`, `*.bak`, `*.dump`, `*.db`, `*.sqlite`, `*.tar.gz`, `.env`, `install.php`, `setup.php`, `phpinfo.php`, `adminer.php`, pasta `.git`; conferir se existe `.gitignore` |
| empacotamento | ler `*.ps1`, `*.sh`, `deploy*`, `Makefile`, `package.json` (scripts), `vercel.json`, `.vercelignore`, `.gitignore`; procurar `\$exclude`, `--exclude`, `zip .* -x`, `Compress-Archive`, `Split\(.*\)\[0\]` (comparação só do primeiro segmento) |
| pastas_documentos | listar (Glob) `**/*.pdf`, `**/*.{jpg,jpeg,png,tif,tiff,docx}` e contar por pasta; 5 ou mais fora de `assets/`, `img/`, `static/`, ou em `tmp/`, `uploads/`, `docs/`, `pdfs/`, `ocr*`. Reportar só pasta e contagem |
| protecao_web | ler `.htaccess`: `FilesMatch\|Require all denied\|Deny from all\|RedirectMatch\|RewriteRule .* \[F`; `%\{HTTPS\}\|Strict-Transport-Security\|X-Frame-Options\|Content-Security-Policy\|Options -Indexes` |
| ia_externa | `api\.openai\.com\|api\.anthropic\.com\|generativelanguage\.googleapis\.com\|api\.groq\.com\|openrouter\.ai\|api\.replicate\.com\|huggingface`; `import openai\|from anthropic\|@anthropic-ai/sdk\|google-generativeai` |

Os `\|` acima são barras verticais escapadas só por causa da tabela em Markdown: no Grep, use `|` simples.

Lembrete final: os padrões acima são pistas. Confirme cada achado no arquivo de origem, registre o caminho e a linha, e não conclua "sem problema" por ausência de resultado.
