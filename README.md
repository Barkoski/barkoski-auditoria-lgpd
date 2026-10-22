# Barkoski — Auditoria LGPD Brasil

Plugin de Lucas Barkoski para apoiar a revisão técnica e jurídica de projetos de software em relação à Lei Geral de Proteção de Dados brasileira. Examina fluxos, código, infraestrutura e documentos disponibilizados, exige evidências para conclusões e distingue falhas demonstradas de informações não verificadas. Produz inventário de tratamentos, matriz de cobertura de 20 áreas, achados priorizados e plano de correção.

Versão candidata 0.1.0. Ainda não publicada nem aprovada pela Anthropic. O pacote passou por revisão estática; testes comportamentais e validação no portal continuam pendentes. Não constitui certificado, parecer jurídico definitivo ou garantia de segurança/conformidade.

## Uso

Depois de instalar, peça: “Use auditoria-lgpd-br para revisar este projeto sem alterar o código. Apresente evidências, riscos, limites e plano de correção”. No Claude Code, a invocação do plugin é `/barkoski-auditoria-lgpd:auditoria-lgpd-br`.

Forneça apenas projeto e ambientes que você pode autorizar. Prefira dados sintéticos e documentos sanitizados. A skill não concede acesso a bancos, repositórios ou produção e não deve executar testes quando não for possível garantir isolamento adequado.

## Dados e permissões

Este plugin contém somente instruções e referências. Não inclui executáveis, hooks, servidores MCP, telemetria própria ou serviço do autor. Durante o uso, o agente pode ler código e dados pessoais que estejam nos materiais autorizados e criar relatórios locais. O processamento pelo modelo e ferramentas segue as condições da plataforma e da conta: o plugin não garante execução local, ausência de retenção nem exclusão automática do histórico.

Pesquisas de legislação devem usar termos genéricos e fontes oficiais, sem transmitir material privado. Relatórios devem conter evidências mínimas sanitizadas em destino restrito, nunca publicado automaticamente. O autor não recebe dados por um mecanismo deste pacote. Os relatórios permanecem no destino escolhido até que o usuário ou sua política os remova; não há serviço próprio de armazenamento nem prazo universal definido pelo plugin.

Destinado a profissionais e responsáveis por projetos, não a crianças/adolescentes. Pode examinar projetos que tratem dados de menores, com controles específicos e revisão humana.

## Conteúdo e limites

A skill está em `skills/auditoria-lgpd-br/`, com referências jurídicas, matriz e modelo de relatório. Pesquisa-base: 22/10/2026; as fontes precisam ser revalidadas em cada auditoria. Duas publicações orientativas não tiveram conteúdo integral recuperado na pesquisa inicial; a limitação está descrita nas referências.

Segurança por instrução não substitui sandbox, permissões mínimas e supervisão. Um resultado sem achados não comprova conformidade integral. A revisão deve declarar quais ambientes e documentos não foram acessados.

## Licença

Copyright 2026 Lucas Barkoski. Distribuído sob Apache License 2.0, conforme o arquivo LICENSE. Textos normativos não são apresentados como criação exclusiva do autor. Nenhuma afiliação, aprovação ou endosso da ANPD, Anthropic ou OpenAI é alegado.
