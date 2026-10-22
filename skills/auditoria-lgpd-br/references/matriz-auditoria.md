# Matriz de auditoria e provas

IDs estáveis para cobertura e plano de ação. Referências L/P/I/E/T/U/C/D estão em fontes-e-criterios.md. Todos os itens devem receber estado e evidência ou motivo de não aplicação. Controles técnicos abaixo são meios de verificação, não tecnologias literalmente impostas pela LGPD.

| ID | Verificar | Evidência técnica e documental esperada | Fundamento |
|---|---|---|---|
| LG01 | Incidência e papéis por operação | Público/território, decisões sobre finalidade, contratos, controlador/operador/suboperador; divergência entre contrato e prática | L arts. 3–5, 39 |
| LG02 | Inventário e minimização | Formulários, schemas, APIs, SDKs, telemetria, texto livre; finalidade e necessidade por campo; dados recebidos sem formulário | L arts. 6, 37 |
| LG03 | Base legal específica | Registro por finalidade, dados comuns/sensíveis, fundamento e comprovação; necessidade contratual e avaliação de legítimo interesse quando invocados | L arts. 7–11 |
| LG04 | Consentimento quando utilizado | Escolha livre e granular, versão/instante/finalidade, prova sem excesso, retirada efetiva e efeitos; não usar aceite de termos como autorização genérica | L arts. 8–9, 18 |
| LG05 | Transparência coerente | Aviso acessível antes/na coleta, controlador/contato, finalidade/duração, compartilhamento, responsabilidades e direitos; comparação com SDKs e fluxos reais | L arts. 6, 9 |
| LG06 | Cookies e rastreamento | Rede/storage antes e depois de aceitar/recusar/revogar; consentimento não antecipado quando essa for a base; distinguir necessários, analytics, ads e server-side tracking | L arts. 6–10; GC após consulta |
| LG07 | Direitos e identidade | Canal funcional, responsável, autenticação proporcional, protocolo e resposta; acesso/exportação sem vazar terceiros; correção propagada | L arts. 18–19 |
| LG08 | Retenção e descarte | Regras por categoria, jobs, soft-delete, caches, índices vetoriais, filas, objetos, fornecedores, backups e restauração; obrigação de guarda comprovada | L arts. 15–16, 18 |
| LG09 | Autenticação e autorização | Verificação no servidor por objeto e organização; perfis/admin, sessão/revogação, reset, regras SQL/storage e credenciais privilegiadas | L arts. 6, 46–49 |
| LG10 | Infraestrutura e segredos | Bundles frontend, variáveis públicas, repositório, buckets/CDN, URLs assinadas, TLS, acesso administrativo, exposição de banco e backups; confirmar ambiente efetivo | L arts. 46–49 |
| LG11 | Logs e observabilidade | Redação de payloads/tokens, cookies de sessão, session replay, erros, suporte e métricas; acesso/retenção e terceiros receptores | L arts. 6, 46–49 |
| LG12 | Fornecedores e instruções | Contratos, finalidade própria ou em nome do controlador, instruções, subprocessadores, assistência a direitos/incidentes, devolução/descarte; contratos não substituem teste | L arts. 37, 39, 46; T se aplicável |
| LG13 | Transferência internacional | Países reais, suporte remoto, logs/backups/IA; base de tratamento e mecanismo do art. 33 comprovados; alcance da adequação e transferências posteriores | L arts. 33–36; T, U |
| LG14 | Dados sensíveis | Fluxos de saúde/biometria etc., base do art. 11, minimização, acesso restrito e compartilhamento específico; inferências sensíveis | L arts. 5 II, 11, 46 |
| LG15 | Crianças e adolescentes | Público real/provável, melhor interesse, hipótese legal, verificação proporcional quando necessária, linguagem acessível e proteção por padrão | L art. 14; C; D em trilha separada |
| LG16 | IA, RAG e decisões | Prompts, anexos, embeddings, provedores, retenção/treino configurados e contratados; segregação na recuperação, exclusão, decisões exclusivamente automatizadas e revisão/explicação | L arts. 6–11, 18–20, 33, 46 |
| LG17 | Incidentes | Responsáveis, detecção/triagem, conhecimento, avaliação de risco relevante, decisão motivada sobre comunicação, modelos e registros; evidência de exercício sintético | L art. 48; I arts. 5–10 |
| LG18 | Encarregado e canal | Enquadramento, ato formal/substituto quando exigidos, contato público funcional, recursos e conflitos; fundamento de dispensa se alegada | L art. 41; E; P art. 11 |
| LG19 | Governança e impacto | Registro das operações, responsáveis, treinamento, revisão de mudanças, risco, RIPD quando exigido ou recomendado; distinguir documento de implementação | L arts. 6 X, 37–38, 46, 50 |
| LG20 | Regimes específicos e cobertura | Pequeno porte comprovado, critérios cumulativos de alto risco, poder público, leis setoriais; exclusões de escopo documentadas | P arts. 2–4; L arts. 23–30 |

## Roteiros de teste com dados sintéticos

Use apenas ambiente local/de teste autorizado, com dependências externas simuladas quando necessário. Não executar exclusão real nem enviar mensagens a titulares.

- **Isolamento:** criar A e B em organizações distintas; tentar ler, alterar, exportar e baixar objeto de B com sessão de A. Incluir rotas alternativas, funções serverless, realtime, buscas e RAG. Esperado: negar acesso sem revelar conteúdo/metadados pessoais. Conferir também operações legítimas de A.
- **Consentimento:** sessão limpa → recusar → aceitar categoria → revogar → nova visita. Registrar eventos e destinos de rede e persistência. Verificar a base aplicável antes de concluir que tráfego pré-consentimento é irregular.
- **Direitos/exclusão:** titular fictício com registros em banco, objeto, índice e fila; simular pedido autenticado; confirmar escopo, segregação, propagação e retenções justificadas. Se backup não puder ser exercitado, registrar pendência do procedimento e prazo, sem declarar remoção completa.
- **Exportação:** validar conteúdo e autorização; arquivo temporário com validade, acesso controlado e descarte; ausência de dados de outros titulares, tokens ou campos internos desnecessários.
- **Observabilidade/IA:** introduzir marcador sintético em campo livre; acompanhar destino até logs/provedor simulado. Verificar minimização, redação e evidência de configuração do provedor. Um SDK instalado não prova envio ou uso em treinamento.
- **Incidente:** exercício de mesa com cenário fictício; identificar responsável, gatilho de conhecimento, avaliação, evidências necessárias e comunicação; não comunicar efetivamente ANPD/titulares durante teste.

Sem ferramentas ou acesso, descrever teste pendente e responsável sugerido, sem inventar resultados. Não presumir vulnerabilidade explorável a partir de chave pública de cliente: distinguir chave pública legítima de segredo privilegiado e conferir controles efetivos.
