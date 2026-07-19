# Quantificador de Severidade

Aplicativo mobile em Python com Flet para quantificar severidade em folhas a partir de imagens de parcelas. O sistema usa um modelo ONNX para segmentar a folha, classifica areas saudaveis e afetadas e apresenta mapas visuais e percentuais por imagem e media por parcela.

## Como funciona

O fluxo principal do software e:

1. Criar uma parcela informando nome, cultura, data e quantidade alvo de imagens.
2. Adicionar fotos da galeria, camera ou imagens de teste no desktop.
3. Processar cada parcela quando o total de imagens esperado estiver completo.
4. Segmentar a folha com o modelo ATTUNet em ONNX.
5. Classificar os pixels em area saudavel e area com severidade.
6. Exibir visualizacao original, sobreposicao e mapa, alem dos percentuais por imagem e media da parcela.
7. Salvar os resultados resumidos em JSON.

## Estrutura

- `attunet_mobile/`: codigo principal da aplicacao.
- `attunet_mobile/assets/models/`: modelo ONNX e metadados.
- `attunet_mobile/services/`: servicos de segmentacao, classificacao e analise.
- `attunet_mobile/views/`: telas de amostragem e configuracoes.
- `attunet_mobile/state/`: configuracoes e parcelas salvas localmente.

## Executando

Requisitos:

- Python 3.10+
- Dependencias listadas em `attunet_mobile/pyproject.toml`

Exemplo de execucao local:

```bash
cd attunet_mobile
pip install -e .
python main.py
```

## Observacoes

- As visualizacoes das imagens sao temporarias e podem ser perdidas ao fechar o aplicativo.
- O projeto contem artefatos gerados de build; o `.gitignore` da raiz ajuda a evitar novos arquivos locais desnecessarios no versionamento.
