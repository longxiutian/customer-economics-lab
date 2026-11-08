"""Render the same validated personal feedback as a portable PDF."""
from pathlib import Path
from xml.sax.saxutils import escape


def render_pdf(snapshot, response, path, *, model):
    import matplotlib
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, KeepTogether
    from hosting.student_debrief import validate_response
    validate_response(snapshot,response)
    fonts=Path(matplotlib.get_data_path())/'fonts/ttf'
    pdfmetrics.registerFont(TTFont('Debrief',str(fonts/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DebriefBold',str(fonts/'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('Debrief',normal='Debrief',bold='DebriefBold')
    styles={
        'body':ParagraphStyle('body',fontName='Debrief',fontSize=10,leading=14,spaceAfter=8,textColor=HexColor('#13294b')),
        'title':ParagraphStyle('title',fontName='DebriefBold',fontSize=25,leading=30,spaceAfter=16,textColor=HexColor('#13294b')),
        'head':ParagraphStyle('head',fontName='DebriefBold',fontSize=13,leading=17,spaceBefore=13,spaceAfter=7,textColor=HexColor('#155b88')),
        'small':ParagraphStyle('small',fontName='Debrief',fontSize=8,leading=11,spaceAfter=7,textColor=HexColor('#526579')),
        'prompt':ParagraphStyle('prompt',fontName='Debrief',fontSize=9,leading=13,leftIndent=12,spaceAfter=12,textColor=HexColor('#155b88'))}
    def p(text,style='body'):return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
    m=snapshot['metrics']
    total=f"{m['nemotron_total_tokens']:,}" if m['nemotron_total_tokens'] is not None else 'unknown total'
    story=[p('STUDIO NORTH'+(' · INSTRUCTOR REHEARSAL' if snapshot['fixture'] else ''),'small'),p('Your personal lab debrief','title'),
           p(f"{m['lab_requests']} lab requests · {m['saved_judgments']} saved judgments · {m['fresh_fits']} fresh statistical fit(s)"),
           p(f"Nemotron: {total} recorded tokens; {m['nemotron_known_input_tokens']:,} known input and {m['nemotron_known_output_tokens']:,} known output."),
           p('Input includes instructions and checkpoint evidence. Native BlueChip chat tokens are unavailable. Activity counts are not a measure of learning.','small')]
    for key,title in [('observations','Your recorded approach'),('studio_north_next_steps','Take Studio North further'),('ai_learning_next_steps','Build your AI practice')]:
        for index,row in enumerate(response[key]):
            refs=', '.join(x.split('/ev:')[-1] for x in row['evidence_ids'])
            block=([p(title,'head')] if index==0 else [])+[p(row['text']+f' [Evidence {refs}]')]
            if row.get('prompt'):block.append(p('Try this: '+row['prompt'],'prompt'))
            story.append(KeepTogether(block))
    story.extend([PageBreak(),p('Evidence and coverage','title'),p('Feedback is grounded in this workspace’s recorded activity. Missing records do not describe what you did elsewhere.','small')])
    for e in snapshot['evidence']:
        story.extend([p(f"Evidence {e['id'].split('/ev:')[-1]} · {e['kind'].replace('_',' ')}",'head'),p(e['text'],'small')])
    story.extend([p('Review provenance','head'),p(f"Reviewed by {model}, high effort, from snapshot {snapshot['snapshot_id']}. Debrief-generation usage is instructor use and is separate from your recorded lab usage.",'small')])
    def footer(canvas,doc):
        canvas.setFont('Debrief',8);canvas.setFillColor(HexColor('#526579'))
        canvas.drawString(44,24,'Studio North · Personal feedback');canvas.drawRightString(568,24,str(doc.page))
    SimpleDocTemplate(str(path),pagesize=(612,792),leftMargin=44,rightMargin=44,topMargin=40,bottomMargin=46,
                      title='Studio North — Personal Lab Debrief',author='Kenan-Flagler Business School').build(story,onFirstPage=footer,onLaterPages=footer)
