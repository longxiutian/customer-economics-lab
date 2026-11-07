"""A compact, two-page example; full redacted evidence remains in companion HTML."""
from pathlib import Path
import json
import os
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab import rl_config

ROOT=Path(__file__).resolve().parent
rl_config.invariant=1
font_dir=Path(os.environ.get('STUDIO_NORTH_FONT_DIR',r'C:\Windows\Fonts'))
pdfmetrics.registerFont(TTFont('Arial',str(font_dir/'arial.ttf')))
pdfmetrics.registerFont(TTFont('Arial-Bold',str(font_dir/'arialbd.ttf')))
pdfmetrics.registerFontFamily('Arial',normal='Arial',bold='Arial-Bold')
snapshot=json.loads((ROOT/'debrief-example/evidence-packet.json').read_text(encoding='utf-8'))
feedback=json.loads((ROOT/'debrief-example/validated-response.json').read_text(encoding='utf-8'))
validation=json.loads((ROOT/'reviews/debrief-validation.json').read_text(encoding='utf-8'))
m=snapshot['metrics']
navy=colors.HexColor('#13294B');blue=colors.HexColor('#155B88');slate=colors.HexColor('#627488')
styles={
 'kicker':ParagraphStyle('k',fontName='Arial-Bold',fontSize=9,leading=12,textColor=blue,spaceAfter=8),
 'title':ParagraphStyle('t',fontName='Arial-Bold',fontSize=25,leading=29,textColor=navy,spaceAfter=10),
 'head':ParagraphStyle('h',fontName='Arial-Bold',fontSize=13,leading=17,textColor=blue,spaceBefore=13,spaceAfter=6),
 'body':ParagraphStyle('b',fontName='Arial',fontSize=10.4,leading=14,textColor=navy,spaceAfter=7),
 'small':ParagraphStyle('s',fontName='Arial',fontSize=8.8,leading=12,textColor=slate,spaceAfter=7),
 'prompt':ParagraphStyle('p',fontName='Arial',fontSize=10.4,leading=14,textColor=navy,leftIndent=11,borderColor=colors.HexColor('#4B9CD3'),borderWidth=1,borderPadding=9,spaceBefore=14,spaceAfter=15),
}
def p(text,style='body'):
 return Paragraph(text,styles[style])
def refs(row):
 return ', '.join(x.split('/ev:')[-1] for x in row['evidence_ids'])
story=[p('INSTRUCTOR REHEARSAL EXAMPLE · 7 NOVEMBER 2026','kicker'),p('Your Studio North lab debrief','title'),p('An example of the personal feedback format. These records come from instructor testing, not a student assessment.','small'),p('Recorded activity','head'),p(f"<b>{m['lab_requests']} lab requests</b> · {m['saved_judgments']} saved judgments · {len(m['checkpoints_observed'])} checkpoints · {m['fresh_fits']} fresh fit"),p(f"<b>{m['nemotron_attempts']} Nemotron responses · {m['nemotron_total_tokens']:,} reported tokens</b><br/>{m['nemotron_known_input_tokens']:,} input + {m['nemotron_known_output_tokens']:,} output; {m['nemotron_attempts_with_unknown_usage']} missing usage receipts."),p('Input includes system instructions and supplied checkpoint evidence. Native BlueChip chat tokens are unavailable. Token volume does not measure learning.','small'),p('What these records show','head')]
for row in feedback['observations']:
 story.append(p(escape(row['text'])+f" <font color='#627488'>[Evidence {refs(row)}]</font>"))
story.append(p('Take Studio North further','head'))
for row in feedback['studio_north_next_steps']:
 story.append(p(escape(row['text'])+f" <font color='#627488'>[Evidence {refs(row)}]</font>"))
story += [PageBreak(),p('PERSONAL NEXT STEPS','kicker'),p('Prompts you can try next','title')]
for key,heading in [('studio_north_next_steps','Studio North analysis'),('ai_learning_next_steps','Working with AI')]:
 story.append(p(heading,'head'))
 for row in feedback[key]:
  content=[]
  if key=='ai_learning_next_steps':content.append(p(escape(row['text'])))
  content.append(p(escape(row['prompt']),'prompt'))
  content.append(p('Evidence '+refs(row),'small'))
  story.append(KeepTogether(content))
story.append(p('About the evidence','head'))
story.append(p('Evidence 1: measured activity; 2: cohort/segment question; 3–7: instructor-supplied saved judgments; 8: fresh-fit receipt; 9: report manifest; 10: Nemotron interpretation. The companion HTML contains the full redacted excerpts and coverage notes.','small'))
story.append(p('Drafted with Opus 5.5 (high), checked and clarified by Codex against snapshot '+snapshot['snapshot_id']+f". Debrief generation used {validation['usage']['total_tokens']:,} separate operator tokens; these are excluded from the lab usage above.",'small'))
def footer(canvas,doc):
 canvas.setStrokeColor(colors.HexColor('#C7D8E6'));canvas.line(44,37,568,37)
 canvas.setFont('Arial',8);canvas.setFillColor(slate);canvas.drawString(44,24,'Studio North · Personal debrief example');canvas.drawRightString(568,24,str(doc.page))
out=ROOT/'output/Studio-North-Personal-Debrief-Example.pdf'
SimpleDocTemplate(str(out),pagesize=(612,792),leftMargin=44,rightMargin=44,topMargin=40,bottomMargin=49,title='Studio North — Personal Debrief Example',author='Kenan-Flagler Business School').build(story,onFirstPage=footer,onLaterPages=footer)
print(out)
