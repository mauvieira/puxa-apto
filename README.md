# Puxa Apto

```bash
cd puxa-apto
pip install -r requirements.txt
```

### Development Installation

```bash
pip install -e .
```

## Usage

### Basic Usage

```bash
python main.py scrape
```

### Custom URLs

```bash
puxa-apto scrape \
  --vivareal-url "https://www.vivareal.com.br/..." \
  --chaves-url "https://www.chavesnamao.com.br/..." \
  --imovelweb-url "https://www.imovelweb.com.br/..." \
  --zap-url "https://www.zapimoveis.com.br/..."
```

### Options

- `--vivareal-url`, `-v`
- `--chaves-url`, `-c`
- `--imovelweb-url`, `-i`
- `--zap-url`, `-z`
- `--json`, `-j`(default: `apartamentos.json`)
- `--csv`: (default: timestamped filename)
- `--max-pages`, `-m`
- `--verbose`, `-V`:
- `--skip-vivareal`:
- `--skip-chaves`:
- `--skip-imovelweb`:
- `--skip-zap`:

## Duplicate Detection

1. **Link-based detection**: Exact URL matches
2. **Fingerprint-based detection**: Based on street, neighborhood, area, bedrooms, and price