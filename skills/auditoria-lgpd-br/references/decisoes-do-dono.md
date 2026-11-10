# Decisões do dono (modo de adequação)

Este modo serve para depois da auditoria. Muitos controles (base legal, retenção, encarregado, transferência, incidente) não se resolvem com código: dependem de uma **decisão do responsável pelo projeto**. A skill não pode inventar essa decisão, mas pode fazer a pergunta certa, mostrar as opções e consequências e, com a resposta, gerar o texto.

## Como conduzir

1. **Só pergunte o que a auditoria não respondeu.** Antes de cada pergunta, confira o inventário: se o código ou um documento já responde, mostre a resposta encontrada e peça só a confirmação.
2. **Faça as perguntas em blocos de no máximo 4**, na ordem abaixo. Use a ferramenta de perguntas da plataforma quando houver; senão, numere as perguntas e as opções.
3. **Linguagem simples.** Cada pergunta traz: por que importa (uma frase), opções concretas, o que muda em cada opção e "não sei — o que fazer para descobrir".
4. **"Não sei" é resposta válida.** Registre como pendência com o próximo passo (quem perguntar, onde olhar). Nunca escolha pelo dono.
5. **Base legal é decisão jurídica.** Mostre as hipóteses plausíveis do art. 7 (ou art. 11 para dados sensíveis) com prós e riscos, recomende revisão do advogado e registre a escolha como "proposta do dono, pendente de validação jurídica" até que ele confirme que a validou.
6. **Ao final:** gere o registro de decisões (tabela abaixo), atualize os estados LG que dependiam dessas respostas e, só então, gere as minutas pedidas. Toda minuta sai marcada como **minuta para revisão jurídica**. Campo sem resposta continua visível como `[PENDENTE: …]`; nunca preencha com texto plausível.

## Perguntas

| # | Pergunta (para o dono) | Por que importa | Opções e consequência | Controles |
|---|---|---|---|---|
| D1 | Quem é o responsável pelo projeto perante os usuários: você como pessoa física, uma empresa (qual CNPJ) ou um cliente seu para quem você desenvolveu? | Define o **controlador** (art. 5º, VI), quem assina a política e quem responde por pedidos e incidentes. | Pessoa física → nome e contato aparecem na política. Empresa → razão social e CNPJ. Desenvolvi para um cliente → o cliente é o controlador e você tende a ser **operador** (art. 5º, VII); a política é dele. | LG01, LG05 |
| D2 | Qual e-mail ou canal vai atender pedidos de usuários sobre os dados deles? Alguém lê esse canal toda semana? | O titular precisa de contato do controlador (art. 9º, IV) e de um canal para exercer direitos (art. 18). | Canal dedicado (ex.: privacidade@) → melhor rastreio. E-mail pessoal → funciona, mas mistura assuntos. Formulário no site → exige proteção contra spam e guarda dos pedidos. | LG07, LG18 |
| D3 | Haverá um encarregado (DPO)? Se não, você se enquadra como agente de pequeno porte? | O art. 41 manda o controlador indicar encarregado; regulamento da ANPD prevê dispensa para pequeno porte, mantendo um canal de contato. | Indicar alguém (pode ser você) → nome e contato públicos (art. 41, § 1º). Alegar dispensa → registrar o fundamento e conferir os critérios de pequeno porte e de alto risco (fontes P e E). Não sei → pendência: conferir faturamento, natureza jurídica e se o tratamento é de alto risco. | LG18, LG20 |
| D4 | Para que serve cada dado que o projeto coleta? (lista gerada da auditoria: campo → finalidade) Algum campo pode sair? | Finalidade e necessidade (art. 6º, I e III). Campo sem finalidade é candidato a remoção, que é a correção mais barata. | Manter com finalidade declarada. Remover (a skill indica onde no código). Tornar opcional. | LG02, LG03 |
| D5 | Para cada finalidade, qual a justificativa legal pretendida? (a skill sugere hipóteses do art. 7 ou 11) | Sem base por finalidade (LG03), a política fica incompleta e o consentimento costuma ser usado de forma errada. | Execução de contrato (o usuário pediu o serviço). Obrigação legal (qual lei). Legítimo interesse (exige avaliação; art. 10; não vale para dado sensível). Consentimento (exige registro, revogação fácil e finalidade específica; arts. 8º e 9º). Não sei → pendência para o advogado. | LG03, LG04, LG14 |
| D6 | O projeto usa ou vai usar analytics, pixel de anúncios, gravação de sessão ou fontes/scripts de terceiros? Você precisa deles? | Determina se precisa de banner de cookies e quais fornecedores entram na política. | Não usar / remover → sem banner, política mais simples. Usar só o essencial e hospedar localmente (fontes, scripts) → sem envio a terceiros. Usar analytics/ads → banner com recusa tão fácil quanto aceite, nada carregado antes da escolha quando a base for consentimento, fornecedor listado na política. | LG06, LG05, LG13 |
| D7 | Quais serviços externos recebem dados? (lista pré-preenchida pela varredura: hospedagem, banco, e-mail, IA, pagamento, WhatsApp…) Em que país ficam? Você aceitou contrato/termos de tratamento de dados (DPA) deles? | Fornecedores e transferência internacional (arts. 33 a 36). | Fornecedor no Brasil → sem transferência. Fora do Brasil → identificar o mecanismo do art. 33 (adequação, cláusulas-padrão, consentimento específico etc.); DPA genérico de GDPR não comprova mecanismo brasileiro. Não sei → pendência: buscar a página de "data processing" do fornecedor. | LG12, LG13, LG16 |
| D8 | Por quanto tempo cada tipo de dado fica guardado? E quando o usuário apaga a conta? | Término e eliminação (arts. 15 e 16). Sem prazo, o padrão vira "para sempre". | Prazo fixo por categoria (ex.: logs X meses, conta até exclusão). Guarda por obrigação legal (qual). Exclusão imediata na remoção da conta. Lembrete: backups precisam de regra própria. Se o projeto for de pessoa jurídica com fins econômicos, considerar a guarda de registros de acesso do Marco Civil (art. 15, 6 meses; ver normas adjacentes). | LG08, LG11 |
| D9 | O projeto é voltado a menores de 18 anos ou é provável que menores usem? | Ativa art. 14 da LGPD e a trilha do ECA Digital (Lei 15.211/2025, art. 1º: "acesso provável"). | Não, e há razão objetiva (público profissional, B2B) → registrar o motivo. Sim ou provável → revisão específica antes de publicar; a skill não cobre o ECA Digital inteiro. | LG15 |
| D10 | Há dados sensíveis (saúde, biometria, religião, origem racial, vida sexual, dados genéticos, filiação sindical ou política) — inclusive em anexos, textos livres ou documentos enviados? | Art. 11: hipóteses mais restritas; impacto maior em vazamento. | Não há → registrar. Há → base do art. 11, acesso restrito, minimização e recomendação de revisão especializada. | LG14 |
| D11 | Se houver um vazamento, quem fica sabendo primeiro e quem decide o que fazer? | Art. 48 e regulamento de incidentes (fonte I): comunicação quando houver risco ou dano relevante, registro do incidente. | Definir responsável e substituto. Usar o roteiro de incidente gerado pela skill. Não sei → pendência com prazo interno para definir. | LG17 |
| D12 | O projeto toma decisões automáticas sobre pessoas (aprovar, negar, pontuar) ou usa IA com dados de usuários? | Art. 20 (revisão de decisões automatizadas) e destino dos dados em provedores de IA. | Não → registrar. Sim → descrever critério, canal de revisão e configuração de retenção/treino do provedor. | LG16 |

## Registro de decisões (saída)

| # | Pergunta | Resposta do dono | Data | Fonte (resposta em conversa, documento, código) | Validação jurídica | Controles atualizados | Pendência |
|---|---|---|---|---|---|---|---|

- Data: a data real da resposta; nunca estimar.
- Validação jurídica: "pendente", ou nome e data **fornecidos pelo dono**.
- Grave o registro junto com o relatório (fora do repositório ou ignorado pelo Git; ver "Entregar e encerrar" no `SKILL.md`).

## Minutas que este modo pode gerar

Gere apenas as pedidas e apenas com as respostas obtidas:

1. **Aviso/política de privacidade** com as seções do art. 9º: finalidade, forma e duração, controlador e contato, compartilhamento, responsabilidades, direitos do art. 18 e como exercê-los.
2. **Texto do banner de cookies**, apenas se D6 indicar rastreamento não necessário.
3. **Registro das operações de tratamento** (art. 37), em tabela: operação, dados, finalidade, base, destinatários, país, retenção.
4. **Roteiro de incidente** de uma página: quem, como avaliar risco, o que registrar, quando comunicar. Sem prazo concreto calculado sem termo inicial.
5. **Resposta-modelo a pedido de titular** (confirmação/acesso no formato do art. 19).

Cada minuta começa com: "Minuta gerada a partir das respostas do responsável em [data]. Não revisada juridicamente. Campos [PENDENTE] devem ser preenchidos antes de publicar."
