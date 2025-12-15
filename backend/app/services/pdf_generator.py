"""PDF generation service for evaluation reports."""

from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_evaluation_pdf(evaluation: Dict[str, Any]) -> BytesIO:
    """
    Generate a one-page PDF report for an evaluation.

    Args:
        evaluation: Dictionary containing evaluation data with criterion_scores

    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = BytesIO()

    # Create PDF document
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    # Container for PDF elements
    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=12,
    )

    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8,
    )

    # Header Section
    story.append(Paragraph(evaluation.get('rubric_title', 'Evaluation Report'), title_style))

    date_str = datetime.fromisoformat(evaluation['created_at'].replace('Z', '+00:00')).strftime('%B %d, %Y at %I:%M %p')
    story.append(Paragraph(f"Evaluated on {date_str}", subtitle_style))

    # Performance Summary Box
    performance_band = evaluation.get('performance_band', 'N/A')
    total_score = evaluation.get('total_score', 0)
    max_total_score = evaluation.get('max_total_score', 0)
    percent = (total_score / max_total_score * 100) if max_total_score > 0 else 0

    summary_data = [
        ['Overall Performance', 'Total Score', 'Percentage'],
        [performance_band, f"{total_score}/{max_total_score}", f"{percent:.1f}%"]
    ]

    summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#e2e8f0')),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))

    # Criteria Checklist Table
    story.append(Paragraph("Evaluation Criteria", header_style))

    criterion_scores = evaluation.get('criterion_scores', [])

    # Build table data
    table_data = [['✓', 'Criterion', 'Score', 'Feedback']]

    for criterion in criterion_scores:
        # Determine if criterion is "passed" (>= 70% of max score)
        score = criterion.get('score', 0)
        max_score = criterion.get('max_score', 1)
        is_passed = (score / max_score) >= 0.7 if max_score > 0 else False

        checkbox = '☑' if is_passed else '☐'
        name = criterion.get('name', 'Unnamed')
        score_text = f"{score}/{max_score}"
        feedback = criterion.get('feedback', '')[:200]  # Truncate long feedback

        # Wrap feedback in Paragraph for better text wrapping
        feedback_para = Paragraph(feedback, styles['Normal'])

        table_data.append([checkbox, name, score_text, feedback_para])

    # Create table with appropriate column widths
    criteria_table = Table(
        table_data,
        colWidths=[0.4*inch, 1.8*inch, 0.7*inch, 3.6*inch],
        repeatRows=1
    )

    criteria_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),

        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),  # Checkbox column
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),    # Criterion name
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # Score
        ('ALIGN', (3, 1), (3, -1), 'LEFT'),    # Feedback
        ('VALIGN', (0, 1), (-1, -1), 'TOP'),

        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),

        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, colors.HexColor('#cbd5e1')),
    ]))

    story.append(criteria_table)
    story.append(Spacer(1, 0.2 * inch))

    # Summary Section
    story.append(Paragraph("Summary", header_style))

    summary_text = evaluation.get('feedback_summary', 'No summary available.')
    story.append(Paragraph(summary_text, styles['Normal']))
    story.append(Spacer(1, 0.15 * inch))

    # Key Strengths
    key_strengths = evaluation.get('key_strengths', [])
    if key_strengths:
        story.append(Paragraph("<b>Key Strengths:</b>", styles['Normal']))
        for strength in key_strengths[:3]:
            story.append(Paragraph(f"• {strength}", styles['Normal']))
        story.append(Spacer(1, 0.1 * inch))

    # Areas for Development
    areas = evaluation.get('areas_for_development', [])
    if areas:
        story.append(Paragraph("<b>Areas for Development:</b>", styles['Normal']))
        for area in areas[:3]:
            story.append(Paragraph(f"• {area}", styles['Normal']))

    # Build PDF
    doc.build(story)

    # Reset buffer position to beginning
    buffer.seek(0)

    return buffer
