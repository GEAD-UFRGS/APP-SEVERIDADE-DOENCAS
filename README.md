# Quantificador de Severidade

Aplicativo mobile em Python com Flet para quantificar severidade em folhas a partir de imagens de parcelas. O sistema usa um modelo ONNX para segmentar a folha, classifica areas saudaveis e afetadas e apresenta mapas visuais e percentuais por imagem e media por parcela.

## Como funciona

O fluxo principal do software e:

1. Criar um experimento informando nome, cultura, data inicial e descricao.
2. Organizar o experimento em tratamentos, parcelas e leituras.
3. Definir a data, a quantidade alvo de imagens e o tipo de dano de cada leitura.
4. Adicionar fotos da galeria, camera ou imagens de teste no desktop.
5. Processar pelo experimento todas as leituras completas ainda pendentes.
6. Segmentar a folha com o modelo ATTUNet em ONNX e classificar os pixels por cor com o perfil de pontos necroticos ou de pontos necroticos e cloroticos.
7. Exibir resultados por imagem, leitura, parcela e tratamento, salvando os valores em JSON.

## Estrutura

- `attunet_mobile/`: codigo principal da aplicacao.
- `attunet_mobile/assets/models/`: modelo ONNX e metadados.
- `attunet_mobile/services/`: servicos de segmentacao, classificacao e analise.
- `attunet_mobile/views/`: telas de amostragem e configuracoes.
- `attunet_mobile/state/`: configuracoes e experimentos salvos localmente.

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
