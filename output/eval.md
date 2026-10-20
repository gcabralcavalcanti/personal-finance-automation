# Eval: LLM classifier on the golden set

The golden set holds every description in the synthetic statements that the seed rules do not catch, with the expected category (`tests/golden/labels.csv`).

```
Golden set: 31 descriptions, answered 31
Accuracy (all answers): 96.8%
Auto-applied (confidence >= 0.8): 28, accuracy 96.4%
Sent to review: 3 (of which wrong: 0)
Confusion (expected -> predicted, errors only):
  Education -> Subscriptions: 1
```

| Description | Expected | Predicted | Confidence | Result |
|---|---|---|---:|---|
| BORRACHARIA DO ZE | Transport | Transport | 0.90 | ok |
| CAFETERIA GRAO NOBRE | Restaurants & Delivery | Restaurants & Delivery | 0.90 | ok |
| CALCADOS PASSO FIRME | Shopping | Shopping | 0.92 | ok |
| CARLA M SOUZA | Income | Income | 0.60 | ok |
| CARTORIO 2 OFICIO DE NOTAS | Fees & Taxes | Fees & Taxes | 0.90 | ok |
| CHAVEIRO SEGURO 24H | Housing | Housing | 0.90 | ok |
| CHURRASCARIA BRASA VIVA | Restaurants & Delivery | Restaurants & Delivery | 0.95 | ok |
| CLINICA ODONTO SORRISO | Health | Health | 0.95 | ok |
| CURSO ONLINE APRENDA MAIS | Education | Education | 0.90 | ok |
| ESTACIONAMENTO CENTRAL PARK | Transport | Transport | 0.92 | ok |
| EXPRESSO SUL RODOVIARIA | Travel | Travel | 0.85 | ok |
| FLORICULTURA JARDIM SECRETO | Shopping | Shopping | 0.90 | ok |
| GUIA IPVA 2026 COTA 3 | Fees & Taxes | Fees & Taxes | 0.97 | ok |
| INSTITUTO ESPERANCA DOACAO | Other | Other | 0.85 | ok |
| JOSE ELETRICISTA REPAROS | Housing | Housing | 0.80 | ok |
| JUROS CHEQUE ESPECIAL | Fees & Taxes | Fees & Taxes | 0.97 | ok |
| LABORATORIO ANALISES VIDA | Health | Health | 0.93 | ok |
| LANCHONETE DA ESQUINA | Restaurants & Delivery | Restaurants & Delivery | 0.90 | ok |
| MAGAZINE ELETRO LAR | Shopping | Shopping | 0.92 | ok |
| MARCOS A ROCHA | Income | Income | 0.55 | ok |
| MATERIAL DE CONSTRUCAO TIJOLAO | Housing | Housing | 0.95 | ok |
| OTICA VISAO CLARA | Health | Health | 0.95 | ok |
| PAG*GAMEPLAY STORE | Shopping | Shopping | 0.85 | ok |
| PAPELARIA MATERIAL ESCOLAR | Education | Education | 0.90 | ok |
| PEDAGIO RODOVIA DAS FLORES | Transport | Transport | 0.95 | ok |
| PEDRO H LIMA | Other | Other | 0.50 | ok |
| PET SHOP AMIGO FIEL | Shopping | Shopping | 0.90 | ok |
| POUSADA MAR AZUL | Travel | Travel | 0.90 | ok |
| RENDIMENTO CONTA REMUNERADA | Income | Income | 0.95 | ok |
| VIDEOAULAS PREMIUM MENSAL | Education | Subscriptions | 0.90 | wrong, auto-applied |
| VOEBEM LINHAS AEREAS | Travel | Travel | 0.95 | ok |
