import os
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable, KeepTogether
from reportlab.lib.units import inch

def generate_emi_schedule_pdf(loan, employee, schedule_items, output_path, company_name="AJIT ZONE PVT. LTD."):
    """
    Generates a dynamic, professional, company-branded EMI Schedule PDF document.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0f172a'),
        alignment=1 # Center
    )
    
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#2563eb'),
        alignment=1
    )

    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155')
    )

    bold_label = ParagraphStyle(
        'BoldLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#0f172a')
    )

    notice_style = ParagraphStyle(
        'NoticeText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#1e3a8a'),
        alignment=1
    )

    elements = []

    # Company Header
    elements.append(Paragraph(company_name, title_style))
    elements.append(Paragraph("EMPLOYEE LOAN & EMI RECOVERY SCHEDULE", subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2563eb'), spaceAfter=15))

    # Employee & Loan Information Table
    tenure_from_str = loan.tenure_from.strftime('%d-%b-%Y') if loan.tenure_from else '-'
    tenure_to_str = loan.tenure_to.strftime('%d-%b-%Y') if loan.tenure_to else '-'
    app_date_str = loan.application_date.strftime('%d-%b-%Y') if loan.application_date else '-'

    info_data = [
        [
            Paragraph("<b>Employee ID:</b>", bold_label), Paragraph(employee.emp_id, normal_style),
            Paragraph("<b>Loan ID:</b>", bold_label), Paragraph(loan.loan_id, normal_style)
        ],
        [
            Paragraph("<b>Employee Name:</b>", bold_label), Paragraph(employee.name, normal_style),
            Paragraph("<b>Loan Type:</b>", bold_label), Paragraph(loan.loan_type, normal_style)
        ],
        [
            Paragraph("<b>Department:</b>", bold_label), Paragraph(employee.department, normal_style),
            Paragraph("<b>Loan Amount:</b>", bold_label), Paragraph(f"₹{loan.loan_amount:,.2f}", normal_style)
        ],
        [
            Paragraph("<b>Designation:</b>", bold_label), Paragraph(employee.designation, normal_style),
            Paragraph("<b>Monthly EMI:</b>", bold_label), Paragraph(f"₹{loan.monthly_emi:,.2f}", normal_style)
        ],
        [
            Paragraph("<b>Current Salary:</b>", bold_label), Paragraph(f"₹{employee.current_salary:,.2f}", normal_style),
            Paragraph("<b>Tenure:</b>", bold_label), Paragraph(f"{loan.tenure_months} Months", normal_style)
        ],
        [
            Paragraph("<b>Tenure From:</b>", bold_label), Paragraph(tenure_from_str, normal_style),
            Paragraph("<b>Tenure To:</b>", bold_label), Paragraph(tenure_to_str, normal_style)
        ],
        [
            Paragraph("<b>Deduction Day:</b>", bold_label), Paragraph(f"{loan.emi_deduction_day}th of every month", normal_style),
            Paragraph("<b>Approval Date:</b>", bold_label), Paragraph(app_date_str, normal_style)
        ]
    ]

    info_table = Table(info_data, colWidths=[1.3*inch, 2.2*inch, 1.3*inch, 2.2*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#f1f5f9')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))

    # Dynamic Prominent Notice Box
    deduction_suffix = "th"
    if loan.emi_deduction_day in [1, 21, 31]: deduction_suffix = "st"
    elif loan.emi_deduction_day in [2, 22]: deduction_suffix = "nd"
    elif loan.emi_deduction_day in [3, 23]: deduction_suffix = "rd"

    notice_html = f"“Your EMI of <b>₹{loan.monthly_emi:,.2f}</b> will be deducted on the <b>{loan.emi_deduction_day}{deduction_suffix}</b> of every month from <b>{tenure_from_str}</b> to <b>{tenure_to_str}</b>.”"
    
    notice_data = [[Paragraph(notice_html, notice_style)]]
    notice_table = Table(notice_data, colWidths=[7.0*inch])
    notice_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#dbeafe')),
        ('BOX', (0,0), (-1,-1), 1.5, colors.HexColor('#2563eb')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    elements.append(notice_table)
    elements.append(Spacer(1, 15))

    # EMI Schedule Table
    header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.white, alignment=1)
    
    schedule_data = [[
        Paragraph("EMI No.", header_style),
        Paragraph("Due Date", header_style),
        Paragraph("Scheduled EMI (₹)", header_style),
        Paragraph("Actual Deduction (₹)", header_style),
        Paragraph("Outstanding (₹)", header_style),
        Paragraph("Status", header_style)
    ]]

    for item in schedule_items:
        due_str = item.due_date.strftime('%d-%b-%Y') if item.due_date else '-'
        act_ded = f"₹{item.actual_deduction:,.2f}" if item.actual_deduction else "₹0.00"
        out_bal = f"₹{item.outstanding_after:,.2f}"
        
        status_color = colors.HexColor('#475569')
        if item.status == 'Deducted': status_color = colors.HexColor('#16a34a')
        elif item.status in ['Overdue', 'Pending']: status_color = colors.HexColor('#dc2626')
        elif item.status == 'Partial': status_color = colors.HexColor('#d97706')

        item_status_style = ParagraphStyle('ItemStatus', parent=normal_style, fontName='Helvetica-Bold', textColor=status_color, alignment=1)

        schedule_data.append([
            Paragraph(str(item.emi_no), ParagraphStyle('Center', parent=normal_style, alignment=1)),
            Paragraph(due_str, ParagraphStyle('Center', parent=normal_style, alignment=1)),
            Paragraph(f"₹{item.scheduled_emi:,.2f}", ParagraphStyle('Right', parent=normal_style, alignment=2)),
            Paragraph(act_ded, ParagraphStyle('Right', parent=normal_style, alignment=2)),
            Paragraph(out_bal, ParagraphStyle('Right', parent=normal_style, alignment=2)),
            Paragraph(item.status, item_status_style)
        ])

    sched_table = Table(schedule_data, colWidths=[0.8*inch, 1.2*inch, 1.4*inch, 1.4*inch, 1.4*inch, 0.8*inch])
    sched_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')])
    ]))
    elements.append(sched_table)
    elements.append(Spacer(1, 25))

    # Signatures & Footer
    sig_data = [
        [
            Paragraph("<b>Prepared & Verified By:</b><br/><br/><br/>_______________________<br/><b>HR Manager</b><br/>AJIT ZONE PVT. LTD.", normal_style),
            Paragraph("<b>Employee Acknowledgement:</b><br/><br/><br/>_______________________<br/><b>Signature:</b> " + employee.name + "<br/><b>Date:</b> ____/____/20__", normal_style)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[3.5*inch, 3.5*inch])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT')
    ]))
    elements.append(KeepTogether(sig_table))

    # Build Document
    doc.build(elements)
    return output_path

def generate_noc_pdf(noc_record, loan, employee, output_path, company_name="AJIT ZONE PVT. LTD."):
    """
    Generates an official No Objection Certificate (NOC) PDF document for loan closure.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'NocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#0f172a'),
        alignment=1
    )

    noc_header_style = ParagraphStyle(
        'NocHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#16a34a'),
        alignment=1
    )

    body_style = ParagraphStyle(
        'NocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=16,
        textColor=colors.HexColor('#1e293b')
    )

    elements = []

    elements.append(Paragraph(company_name, title_style))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph("NO OBJECTION CERTIFICATE (NOC)", noc_header_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#16a34a'), spaceAfter=15))

    # NOC Metadata Table
    meta_data = [
        [Paragraph(f"<b>NOC Reference No:</b> {noc_record.noc_number}", body_style), Paragraph(f"<b>Date:</b> {noc_record.generated_date.strftime('%d-%b-%Y')}", body_style)]
    ]
    meta_table = Table(meta_data, colWidths=[4.0*inch, 2.8*inch])
    elements.append(meta_table)
    elements.append(Spacer(1, 15))

    # Declaration Paragraph
    declaration_text = f"""
    This is to certify that Mr./Ms. <b>{employee.name}</b> (Employee ID: <b>{employee.emp_id}</b>), 
    working as <b>{employee.designation}</b> in the <b>{employee.department}</b> Department at 
    <b>{company_name}</b>, had availed a <b>{loan.loan_type}</b> (Loan ID: <b>{loan.loan_id}</b>) 
    amounting to <b>₹{loan.loan_amount:,.2f}</b>.
    <br/><br/>
    We hereby confirm that the employee has successfully repaid the full loan amount along with all applicable EMIs. 
    As of <b>{noc_record.generated_date.strftime('%d-%b-%Y')}</b>, the outstanding loan balance is <b>₹0.00 (Zero Rupees)</b>, 
    and all financial obligations related to this loan have been fully satisfied.
    <br/><br/>
    <b>AJIT ZONE PVT. LTD.</b> has <b>NO OBJECTION</b> or further monetary claim against the employee regarding this loan account, 
    and the loan status is officially marked as <b>CLOSED</b> in our company records.
    """
    elements.append(Paragraph(declaration_text, body_style))
    elements.append(Spacer(1, 20))

    # Loan Summary Box
    summary_data = [
        [Paragraph("<b>Loan Summary</b>", ParagraphStyle('BHeader', parent=body_style, fontName='Helvetica-Bold', fontSize=11, textColor=colors.HexColor('#0f172a'))), ""],
        [Paragraph("Original Loan Amount:", body_style), Paragraph(f"₹{loan.loan_amount:,.2f}", body_style)],
        [Paragraph("Total Amount Recovered:", body_style), Paragraph(f"₹{loan.total_recovered:,.2f}", body_style)],
        [Paragraph("Closure Date:", body_style), Paragraph(noc_record.generated_date.strftime('%d-%b-%Y'), body_style)],
        [Paragraph("<b>Outstanding Balance:</b>", body_style), Paragraph("<b>₹0.00 (NIL)</b>", ParagraphStyle('ZeroBal', parent=body_style, fontName='Helvetica-Bold', textColor=colors.HexColor('#16a34a')))]
    ]
    sum_table = Table(summary_data, colWidths=[3.0*inch, 3.8*inch])
    sum_table.setStyle(TableStyle([
        ('SPAN', (0,0), (1,0)),
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(sum_table)
    elements.append(Spacer(1, 30))

    # HR Authorization Box
    sig_data = [
        [
            Paragraph("<b>Authorized Signatory</b><br/><br/><br/>______________________________<br/><b>HR Manager / Authorized Officer</b><br/>" + company_name + "<br/><i>Official Company Seal & Stamp</i>", body_style)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[6.8*inch])
    elements.append(KeepTogether(sig_table))

    doc.build(elements)
    return output_path
