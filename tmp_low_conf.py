import json
from pathlib import Path
root = Path('output_v3')
low = []
for path in sorted(root.rglob('*.json')):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        continue
    if isinstance(data.get('confidence'), str) and data['confidence'].lower() == 'low':
        low.append((path.parent.name, path.stem))
print('LOW_COUNT', len(low))
for lang, pid in low:
    print(f'{lang}/{pid}')
