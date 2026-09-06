from pathlib import Path
p=Path('static/beta_features_v2.js')
s=p.read_text(encoding='utf-8')
s=s.replace('class="beta-fit-select-v2"','class="beta-fit-select beta-fit-select-v2"')
p.write_text(s,encoding='utf-8')
print('Beta v2 selector compatibility applied.')
