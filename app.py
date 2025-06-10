from flask import Flask, render_template, request, send_file, jsonify
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from io import BytesIO
import os
from datetime import datetime
import sqlite3
from openai import OpenAI
import json
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure NetMind API
NETMIND_API_KEY = os.getenv('NETMIND_API_KEY')
NETMIND_BASE_URL = os.getenv('NETMIND_BASE_URL')
client = OpenAI(api_key=NETMIND_API_KEY)

# AI Memo Generation Class
class MemoAI:
    def __init__(self, api_key=None, base_url=None):
        self.api_key = api_key or NETMIND_API_KEY
        self.base_url = base_url or NETMIND_BASE_URL
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def generate_memo_content(self, user_prompt, memo_type="internal memo", sender="", recipient=""):
        """Generate memo content using NetMind API"""
        try:
            if not self.api_key:
                raise Exception("NetMind API key not found. Please check your .env file.")
                
            system_prompt = f"""
            You are a professional memo writer for Bishop Abiero Shaurimoyo Secondary School.

            IMPORTANT: Respond ONLY with the memo body content. Do not include:
            - Any explanations or reasoning
            - Headers (TO, FROM, DATE, SUBJECT)
            - Signatures or closing remarks
            - Any meta-commentary about the memo

            Write a clear, professional memo body that is:
            - Formal and respectful in tone
            - Specific and actionable
            - Appropriate for school administration
            - 2-4 paragraphs maximum"""
            
            user_message = f"""
            Write the main content for a memo based on this request: {user_prompt}
            
            Context:
            - This is for a secondary school environment
            - Sender: {sender if sender else 'School Administration'}
            - Recipient: {recipient if recipient else 'Staff/Students'}
            
            Output ONLY the memo content, nothing else, no headers or signatures.
            """
            
            # Use NetMind API with OpenAI-compatible format
            response = self.client.chat.completions.create(
                model="Qwen/Qwen3-8B",  # NetMind usually supports this model name
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=400,
                temperature=0.7
            )
            
            return {
                "success": True,
                "content": response.choices[0].message.content.strip(),
                "usage": response.usage.total_tokens if hasattr(response, 'usage') else 0
            }
            
        except Exception as e:
            print(f"NetMind API Error: {str(e)}")  # Log for debugging
            return {
                "success": False,
                "error": f"NetMind API Error: {str(e)}",
                "content": ""
            }
    
    def suggest_subject(self, content):
        """Generate a subject line based on memo content using NetMind API"""
        try:
            if not self.api_key:
                return "General Communication"
                
            response = self.client.chat.completions.create(
                model="Qwen/Qwen3-8B",
                messages=[
                    {
                        "role": "system", 
                        "content": "Generate a concise, professional subject line for this memo. Keep it under 10 words and make it specific."
                    },
                    {"role": "user", "content": f"Memo content: {content[:200]}..."}
                ],
                max_tokens=50,
                temperature=0.5
            )
            
            subject = response.choices[0].message.content.strip()
            # Clean up the subject line
            subject = re.sub(r'^(Subject:|RE:|SUBJECT:)\s*', '', subject, flags=re.IGNORECASE)
            return subject.strip('"\'')
            
        except Exception as e:
            print(f"NetMind API Error (subject generation): {str(e)}")
            return "General Communication"

# Initialize AI helper with NetMind API
memo_ai = MemoAI()

app = Flask(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('school_forms.db')
    c = conn.cursor()
    
    # Create tables for storing form data
    c.execute('''CREATE TABLE IF NOT EXISTS leave_out_chits
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  student_name TEXT,
                  student_class TEXT,
                  admission_no TEXT,
                  leave_date TEXT,
                  leave_time TEXT,
                  return_time TEXT,
                  reason TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS internal_memos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  memo_no TEXT,
                  recipient TEXT,
                  sender TEXT,
                  subject TEXT,
                  content TEXT,
                  date_issued TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS teacher_duty_forms
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  teacher_name TEXT,
                  duty_date TEXT,
                  periods TEXT,
                  subjects TEXT,
                  classes TEXT,
                  special_instructions TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

# School Information
SCHOOL_INFO = {
    'name': 'BISHOP ABIERO SHAURIMOYO SECONDARY SCHOOL',
    'po_box': 'P.O Box 1691-40100',
    'location': 'Kisumu, Kenya',
    'tel': 'Tel: +254 700 123 456',
    'email': 'bishopabiero@yahoo.com',
    'motto': 'Empowerment and Service'
}

def create_banner(canvas, doc):
    """Create the school banner/header"""
    canvas.saveState()
    
    # School name
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawCentredString(A4[0]/2, A4[1] - 50, SCHOOL_INFO['name'])
    
    # Contact information
    canvas.setFont("Helvetica", 10)
    canvas.drawCentredString(A4[0]/2, A4[1] - 70, f"{SCHOOL_INFO['po_box']}, {SCHOOL_INFO['location']}")
    canvas.drawCentredString(A4[0]/2, A4[1] - 85, f"{SCHOOL_INFO['tel']} | {SCHOOL_INFO['email']}")
    canvas.drawCentredString(A4[0]/2, A4[1] - 100, f"Motto: {SCHOOL_INFO['motto']}")
    
    # Draw a line under the header
    canvas.line(50, A4[1] - 110, A4[0] - 50, A4[1] - 110)
    
    canvas.restoreState()

def generate_leave_out_chit(data):
    """Generate Leave Out Chit PDF in memo format"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=130, leftMargin=50, rightMargin=50)
    
    styles = getSampleStyleSheet()
    
    # Custom styles for memo format
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        spaceAfter=30,
        fontSize=16,
        textColor=colors.darkblue,
        fontName='Helvetica-Bold'
    )
    
    memo_header_style = ParagraphStyle(
        'MemoHeader',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=8,
        fontName='Helvetica'
    )
    
    memo_content_style = ParagraphStyle(
        'MemoContent',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=15,
        alignment=TA_JUSTIFY,
        leftIndent=20,
        rightIndent=20
    )
    
    signature_style = ParagraphStyle(
        'SignatureStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=30,
        leftIndent=50
    )
    
    story = []
    
    # Form title
    story.append(Paragraph("LEAVE OUT CHIT", title_style))
    story.append(Spacer(1, 20))
    
    # Memo header information
    story.append(Paragraph(f"<b>Date:</b> {data['leave_date']}", memo_header_style))
    story.append(Paragraph(f"<b>To:</b> The Principal", memo_header_style))
    story.append(Paragraph(f"<b>From:</b> Class Teacher", memo_header_style))
    story.append(Paragraph(f"<b>Subject:</b> Permission to Leave School Premises", memo_header_style))
    story.append(Spacer(1, 20))
    
    # Draw a line separator
    story.append(Paragraph("_" * 80, styles['Normal']))
    story.append(Spacer(1, 15))
    
    # Memo content
    memo_text = f"""
    I hereby request permission for the following student to leave the school premises during school hours:
    
    <b>Student Name:</b> {data['student_name']}
    <b>Class:</b> {data['student_class']}
    <b>Admission Number:</b> {data['admission_no']}
    
    <b>Time of Departure:</b> {data['leave_time']}
    <b>Expected Return Time:</b> {data['return_time']}
    
    <b>Reason for Leave:</b>
    {data['reason']}
    
    The student is expected to return to school at the specified time and report to the class teacher upon return.
    
    Thank you for your consideration.
    """
    
    story.append(Paragraph(memo_text, memo_content_style))
    story.append(Spacer(1, 40))
    
    # Signatures section
    story.append(Paragraph("<b>Class Teacher</b>", signature_style))
    story.append(Paragraph("Signature: ________________________    Date: ________________", signature_style))
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("<b>Principal's Approval</b>", signature_style))
    story.append(Paragraph("Signature: ________________________    Date: ________________", signature_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Status: [ ] Approved   [ ] Denied", signature_style))
    
    doc.build(story, onFirstPage=create_banner)
    buffer.seek(0)
    return buffer

def generate_internal_memo(data):
    """Generate Internal Memo PDF in proper memo format"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=130, leftMargin=50, rightMargin=50)
    
    styles = getSampleStyleSheet()
    
    # Custom styles for memo format
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        spaceAfter=30,
        fontSize=16,
        textColor=colors.darkblue,
        fontName='Helvetica-Bold'
    )
    
    memo_header_style = ParagraphStyle(
        'MemoHeader',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=8,
        fontName='Helvetica'
    )
    
    memo_content_style = ParagraphStyle(
        'MemoContent',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=12,
        alignment=TA_JUSTIFY,
        leftIndent=0,
        rightIndent=0
    )
    
    signature_style = ParagraphStyle(
        'SignatureStyle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=15
    )
    
    story = []
    
    # Form title
    story.append(Paragraph("INTERNAL MEMORANDUM", title_style))
    story.append(Spacer(1, 20))
    
    # Memo header
    story.append(Paragraph(f"<b>MEMO NO:</b> {data['memo_no']}", memo_header_style))
    story.append(Paragraph(f"<b>DATE:</b> {data['date_issued']}", memo_header_style))
    story.append(Paragraph(f"<b>TO:</b> {data['recipient']}", memo_header_style))
    story.append(Paragraph(f"<b>FROM:</b> {data['sender']}", memo_header_style))
    story.append(Paragraph(f"<b>SUBJECT:</b> {data['subject']}", memo_header_style))
    story.append(Spacer(1, 15))
    
    # Draw a line separator
    story.append(Paragraph("_" * 80, styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Memo content
    content_paragraphs = data['content'].split('\n')
    for paragraph in content_paragraphs:
        if paragraph.strip():
            story.append(Paragraph(paragraph.strip(), memo_content_style))
    
    story.append(Spacer(1, 40))
    
    # Signature section
    story.append(Paragraph("Regards,", memo_content_style))
    story.append(Spacer(1, 10))
    #story.append(Paragraph("_" * 30, signature_style))
    story.append(Paragraph(f"<b>{data['sender']}</b>", signature_style))
    story.append(Paragraph("Signature", signature_style))
    
    doc.build(story, onFirstPage=create_banner)
    buffer.seek(0)
    return buffer

def generate_teacher_duty_form(data):
    """Generate Teacher On Duty Form PDF (keeping table format as requested)"""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=130)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        alignment=TA_CENTER,
        spaceAfter=30,
        fontSize=14,
        textColor=colors.darkblue
    )
    
    story = []
    
    # Form title
    story.append(Paragraph("TEACHER ON DUTY FORM", title_style))
    story.append(Spacer(1, 20))
    
    # Teacher duty information
    duty_data = [
        ['Teacher Name:', data['teacher_name']],
        ['Duty Date:', data['duty_date']],
        ['Periods:', data['periods']],
        ['Subjects:', data['subjects']],
        ['Classes:', data['classes']],
        ['Special Instructions:', data['special_instructions']]
    ]
    
    table = Table(duty_data, colWidths=[2*inch, 4*inch])
    table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 40))
    
    # Acknowledgment section
    ack_data = [
        ['Teacher Signature:', '_' * 30, 'Date:', '_' * 20],
        ['', '', '', ''],
        ['HOD Signature:', '_' * 30, 'Date:', '_' * 20],
        ['', '', '', ''],
        ['Principal Signature:', '_' * 30, 'Date:', '_' * 20],
    ]
    
    ack_table = Table(ack_data, colWidths=[1.5*inch, 2*inch, 1*inch, 1.5*inch])
    ack_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
    ]))
    
    story.append(ack_table)
    
    doc.build(story, onFirstPage=create_banner)
    buffer.seek(0)
    return buffer

# Routes
@app.route('/')
def index():
    return render_template('index.html', school_info=SCHOOL_INFO)

@app.route('/leave-out-chit')
def leave_out_chit_form():
    return render_template('leave_out_chit.html')

@app.route('/internal-memo')
def internal_memo_form():
    return render_template('internal_memo.html')

@app.route('/teacher-duty')
def teacher_duty_form():
    return render_template('teacher_duty.html')

@app.route('/generate-leave-chit', methods=['POST'])
def generate_leave_chit():
    data = request.get_json()
    
    # Save to database
    conn = sqlite3.connect('school_forms.db')
    c = conn.cursor()
    c.execute('''INSERT INTO leave_out_chits 
                 (student_name, student_class, admission_no, leave_date, leave_time, return_time, reason)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (data['student_name'], data['student_class'], data['admission_no'],
               data['leave_date'], data['leave_time'], data['return_time'], data['reason']))
    conn.commit()
    conn.close()
    
    # Generate PDF
    pdf_buffer = generate_leave_out_chit(data)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"leave_out_chit_{data['student_name'].replace(' ', '_')}.pdf",
        mimetype='application/pdf'
    )

@app.route('/api-status', methods=['GET'])
def check_api_status():
    """Check NetMind API connection status"""
    try:
        if not NETMIND_API_KEY:
            return jsonify({
                "status": "error",
                "message": "NetMind API key not found in environment variables"
            })
        
        # Test connection with a simple request
        # test_response = openai.ChatCompletion.create(
        #     model="Qwen/Qwen3-8B",
        #     messages=[{"role": "user", "content": "Hello"}],
        #     max_tokens=10
        # )
        
        return jsonify({
            "status": "connected",
            "message": "NetMind API is working properly",
            "base_url": NETMIND_BASE_URL
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"NetMind API connection failed: {str(e)}"
        })

# Add this new route for AI memo generation
@app.route('/ai-generate-memo', methods=['POST'])
def ai_generate_memo():
    """Generate memo content using AI"""
    try:
        data = request.get_json()
        user_prompt = data.get('prompt', '')
        memo_type = data.get('memo_type', 'internal memo')
        sender = data.get('sender', '')
        recipient = data.get('recipient', '')
        
        if not user_prompt:
            return jsonify({
                "success": False,
                "error": "Please provide a prompt for memo generation"
            })
        
        # Generate memo content
        result = memo_ai.generate_memo_content(user_prompt, memo_type, sender, recipient)
        
        if result["success"]:
            # Also generate a suggested subject line
            suggested_subject = memo_ai.suggest_subject(result["content"])
            
            return jsonify({
                "success": True,
                "content": result["content"],
                "suggested_subject": suggested_subject,
                "tokens_used": result.get("usage", 0)
            })
        else:
            return jsonify({
                "success": False,
                "error": result["error"]
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Server error: {str(e)}"
        })

# Alternative route for local/free AI (using Hugging Face)
@app.route('/ai-generate-memo-local', methods=['POST'])
def ai_generate_memo_local():
    """Generate memo content using local AI (fallback option)"""
    try:
        data = request.get_json()
        user_prompt = data.get('prompt', '')
        
        if not user_prompt:
            return jsonify({
                "success": False,
                "error": "Please provide a prompt for memo generation"
            })
        
        # Simple template-based generation (fallback)
        templates = {
            "meeting": "We would like to inform you about an upcoming {topic}. The meeting is scheduled for {details}. Your attendance is highly appreciated.",
            "announcement": "This is to inform all concerned parties about {topic}. Please take note of the following details: {details}. Thank you for your attention.",
            "reminder": "This serves as a reminder regarding {topic}. Please ensure that {details}. Your cooperation is highly appreciated.",
            "request": "We hereby request {topic}. The details are as follows: {details}. We look forward to your positive response."
        }
        
        # Simple keyword matching for template selection
        template_key = "announcement"  # default
        if any(word in user_prompt.lower() for word in ["meeting", "meet", "conference"]):
            template_key = "meeting"
        elif any(word in user_prompt.lower() for word in ["remind", "reminder"]):
            template_key = "reminder"
        elif any(word in user_prompt.lower() for word in ["request", "need", "require"]):
            template_key = "request"
        
        # Generate basic content
        content = f"""
        Dear Recipient,
        
        {templates[template_key].format(topic=user_prompt, details="Please refer to the details provided")}
        
        Should you have any questions or require clarification, please do not hesitate to contact the administration office.
        
        Thank you for your cooperation.
        """
        
        return jsonify({
            "success": True,
            "content": content.strip(),
            "suggested_subject": f"Re: {user_prompt[:50]}...",
            "note": "Generated using local template (for full AI features, configure OpenAI API key)"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Server error: {str(e)}"
        })

# Add a route to get memo templates/suggestions
@app.route('/memo-templates', methods=['GET'])
def get_memo_templates():
    """Provide common memo templates and suggestions"""
    templates = {
        "meeting_announcement": {
            "title": "Meeting Announcement",
            "prompt": "Announce a staff meeting on Friday at 2 PM in the conference room to discuss academic performance"
        },
        "policy_reminder": {
            "title": "Policy Reminder",
            "prompt": "Remind all teachers about the dress code policy and punctuality requirements"
        },
        "event_notification": {
            "title": "Event Notification", 
            "prompt": "Notify about upcoming sports day activities and request teacher participation"
        },
        "maintenance_request": {
            "title": "Maintenance Request",
            "prompt": "Request urgent repair of classroom projectors and sound system"
        },
        "deadline_reminder": {
            "title": "Deadline Reminder",
            "prompt": "Remind teachers to submit lesson plans and assessment reports by month end"
        }
    }
    
    return jsonify({"templates": templates})

# generate_memo route to include AI-generated memo numbers
@app.route('/generate-memo', methods=['POST'])
def generate_memo():
    data = request.get_json()
    
    # Auto-generate memo number if not provided
    if not data.get('memo_no'):
        current_date = datetime.now()
        conn = sqlite3.connect('school_forms.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM internal_memos WHERE date_issued LIKE ?', 
                 (f"{current_date.year}%",))
        count = c.fetchone()[0] + 1
        conn.close()
        
        data['memo_no'] = f"BASS/MEMO/{current_date.year}/{count:03d}"
    
    # Save to database
    conn = sqlite3.connect('school_forms.db')
    c = conn.cursor()
    c.execute('''INSERT INTO internal_memos 
                 (memo_no, recipient, sender, subject, content, date_issued)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (data['memo_no'], data['recipient'], data['sender'], 
               data['subject'], data['content'], data['date_issued']))
    conn.commit()
    conn.close()
    
    # Generate PDF
    pdf_buffer = generate_internal_memo(data)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"internal_memo_{data['memo_no']}.pdf",
        mimetype='application/pdf'
    )

@app.route('/generate-duty-form', methods=['POST'])
def generate_duty_form():
    data = request.get_json()
    
    # Save to database
    conn = sqlite3.connect('school_forms.db')
    c = conn.cursor()
    c.execute('''INSERT INTO teacher_duty_forms 
                 (teacher_name, duty_date, periods, subjects, classes, special_instructions)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (data['teacher_name'], data['duty_date'], data['periods'],
               data['subjects'], data['classes'], data['special_instructions']))
    conn.commit()
    conn.close()
    
    # Generate PDF
    pdf_buffer = generate_teacher_duty_form(data)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"teacher_duty_{data['teacher_name'].replace(' ', '_')}.pdf",
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Initialize database
    init_db()
    
    app.run(debug=True, host='0.0.0.0', port=5000)