"""Combine an owner-private UI payload with a source-only template. Never publish output."""
import json,pathlib,sys
payload=json.loads(pathlib.Path(sys.argv[1]).read_text())
for sample in payload['samples']:
 for field in ('raw_image','glyph_image'):
  if not sample[field].startswith('data:image/png;base64,'):raise ValueError('Images must be embedded local PNGs')
template=pathlib.Path(__file__).with_name('review-template.html').read_text()
output=template.replace('__PRIVATE_REVIEW_DATA__',json.dumps(payload).replace('</','<\\/'))
pathlib.Path(sys.argv[2]).write_text(output)
