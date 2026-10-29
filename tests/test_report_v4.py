"""Semantic visual checks: colors and report order carry economic meaning."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cohort_lab import report


def test_triangle_numeral_color_is_economic_not_background_contrast():
    rates=pd.DataFrame([[1.,.63,.01,np.nan]])
    fig,ax=plt.subplots()
    report._triangle(ax,rates,"Retention","rate",list(range(4)),["2024-01"])
    assert {t.get_color() for t in ax.texts}=={report.COLORS["ink"]}
    assert len(ax.texts)==3  # No number invented for an unobserved cell.
    plt.close(fig)
    values=[-100.,-.001,0.,.001,100.]
    fig,ax=plt.subplots()
    report._triangle(ax,pd.DataFrame([values]),"Cash","cash",list(range(5)),["2024-01"])
    labels=ax.texts[:5]
    assert [t.get_color() for t in labels]==["#A3332D","#A3332D","#185A46","#185A46","#185A46"]
    assert labels[1].get_text()=="<0" and labels[3].get_text()==">0"
    assert labels[2].get_text()=="0"
    assert len(ax.patches)==1 and ax.patches[0].get_x()==1.5
    plt.close(fig)


def test_extrapolation_is_early_and_each_major_section_has_a_divider():
    text=(report.ROOT/"templates/customer-economics-report.tex.j2").read_text(encoding="utf-8")
    assert text.index("What the model contributes")<text.index("{retention-forecast}")
    assert text.index("{retention-forecast}")<text.index("{retention-triangle}")<text.index("ltv-and-cac.pdf")
    assert text.count(r"\ReportFigure{retention-forecast}")==1
    assert text.count(r"\SectionDivider{")==9
    assert r"\SectionDivider{APPENDIX}" in text
    assert "journey-save-time" not in text and "journey-build-skill" not in text
    for bad in ["Read the whole sequence", "Check whether progress", "Show the unobserved", "Require the next campaign"]:
        assert bad not in text


def test_heatmap_text_contrast_and_near_zero_sign():
    from matplotlib.colors import to_rgb
    def luminance(c):
        channels=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in to_rgb(c)]
        return sum(x*w for x,w in zip(channels,[.2126,.7152,.0722]))
    for ink,backgrounds in [(report.COLORS["ink"],["#FFFFFF","#BEDFD2"]),("#A3332D",["#F8E7E3","#FFFFFF"]),("#185A46",["#FFFFFF","#DCEDE5"])]:
        assert all((luminance(bg)+.05)/(luminance(ink)+.05)>=4.5 for bg in backgrounds)
    fig,ax=plt.subplots()
    report._triangle(ax,pd.DataFrame([[-.49,-.005,-.001,0.,.001,.49]]),"cash","cash",range(6),["2024-01"])
    assert [t.get_text() for t in ax.texts[:6]]==["−0.49","−0.01","<0","0",">0","0.49"]
    assert len(ax.patches)==1 and ax.patches[0].get_x()==2.5
    plt.close(fig)


def test_retention_ties_share_one_report_and_slide_formatter():
    from cohort_lab.display import retention_label
    assert retention_label(.625)=="63"
    assert retention_label(.1249)=="12"
    assert retention_label(.125)=="13"
    fig,ax=plt.subplots()
    report._triangle(ax,pd.DataFrame([[.625]]),"Retention","rate",[0],["2024-12"])
    assert ax.texts[0].get_text()==retention_label(.625)
    plt.close(fig)


def test_management_report_separates_observation_forecast_and_classroom_protocol():
    template=(report.ROOT/'templates/customer-economics-report.tex.j2').read_text(encoding='utf-8')
    for bad in ['student workflow','future competition','challenge model','private data-generation skill']:
        assert bad not in template
    assert 'Differences use unrounded values' in template
    assert 'controls remained protected' in template
    assert 'A3 / CONTRIBUTION FORECASTS' in template
