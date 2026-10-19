from flask import Flask, render_template, request, jsonify, g, session
import os
import re
import sqlite3
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    print("WARNING: resend package not installed. Install with: pip install resend")
from datetime import datetime, timedelta, date
import schedule
import threading
import time
import pytz
import queue
from html import escape as html_escape
from functools import wraps
from dotenv import load_dotenv
from migrate_db import pending_changes

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-only-change-me')

LIBRARIAN_NAME = os.getenv('LIBRARIAN_NAME', 'Librarian')
BORROWER_GROUPS = ['Y1', 'Y2', 'Faculty']
BORROWER_ROLES = ['borrower', 'staff']
BOOK_CATEGORIES = ['Unclassified', 'African Fiction', 'Other Fiction', 'Non-fiction',
                   'art and culture', 'Math and science', 'popular fun/games', 'Olympiad']

_db_initialized = False
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.getenv('DATABASE_FILE', os.path.join(BASE_DIR, 'library.db'))

email_queue = queue.Queue()
email_worker_thread = None

def _connect_sqlite():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    try:
        sqlite3.register_adapter(date, lambda d: d.isoformat())
        sqlite3.register_converter("DATE", lambda b: date.fromisoformat(b.decode()))
    except Exception:
        pass

    conn = sqlite3.connect(
        DATABASE_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.create_collation('UNICASE', lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    return conn

def _get_db_connection():
    return _connect_sqlite(), 'sqlite'

def get_db():
    global _db_initialized

    if 'db' not in g:
        g.db = _connect_sqlite()
        g.db_type = 'sqlite'

        if not _db_initialized:
            new_tables, new_columns = pending_changes(g.db.cursor())
            if new_tables or new_columns:
                missing = new_tables + [f'{table}.{column}' for table, column, *_ in new_columns]
                print(f"WARNING: database schema is out of date (missing: {', '.join(missing)}). "
                      f"Run `python migrate_db.py` and restart the app.")
            _db_initialized = True

    return g.db

class CursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor
    
    def execute(self, query, params=None):
        if params is not None:
            return self.cursor.execute(query, params)
        else:
            return self.cursor.execute(query)

    def executemany(self, query, seq_of_params):
        return self.cursor.executemany(query, seq_of_params)

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self.cursor.fetchall()]
    
    def __getattr__(self, name):
        return getattr(self.cursor, name)

def get_cursor():
    db = get_db()
    cur = db.cursor()
    return CursorWrapper(cur)

@app.teardown_appcontext
def close_db(error):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def next_book_id(cur):
    cur.execute("SELECT book_id FROM Book WHERE book_id IS NOT NULL AND book_id != ''")
    used_book_ids = {str(row['book_id']).strip() for row in cur.fetchall() if str(row['book_id']).strip()}
    candidate = 1
    while str(candidate) in used_book_ids:
        candidate += 1
    return str(candidate)

def load_email_config():
    if not os.getenv('RESEND_API_KEY'):
        return None
    return {
        'enabled': os.getenv('EMAIL_ENABLED', 'true').lower() == 'true',
        'provider': 'resend',
        'resend_api_key': os.getenv('RESEND_API_KEY'),
        'email_address': os.getenv('EMAIL_ADDRESS', 'tech@africanolympiadfoundation.org'),
        'library_name': os.getenv('LIBRARY_NAME', 'AOA Library')
    }

def sanitize_email(email):
    if not email:
        return ""
    email = email.strip()
    if '@' not in email or '.' not in email:
        return ""
    email = ''.join(char for char in email if char.isprintable())
    dangerous_chars = ['\n', '\r', '\\', ';', ',', '<', '>']
    for char in dangerous_chars:
        if char in email:
            return ""
    if len(email) > 254:
        return ""
    return email

def send_email_direct(to_email, subject, body):
    config = load_email_config()
    
    if not config:
        print("Email is off: RESEND_API_KEY is not set")
        return False
    
    if not config.get('enabled', False):
        print("Email sending is disabled in config")
        return False
    
    if not config.get('email_address'):
        print("ERROR: email_address not set in config")
        return False
    
    to_email = sanitize_email(to_email)
    if not to_email:
        print("Invalid or dangerous email address provided")
        return False
    
    if not RESEND_AVAILABLE:
        print("ERROR: resend package not installed. Install with: pip install resend")
        return False
    
    if not config.get('resend_api_key'):
        print("ERROR: resend_api_key not set in config")
        return False
    
    try:
        resend.api_key = config['resend_api_key']
        
        print(f"Attempting to send email to {to_email} via Resend API")
        params = {
            "from": config['email_address'],
            "to": [to_email],
            "subject": subject,
            "html": body
        }
        
        email = resend.Emails.send(params)
        print(f"Email sent successfully to {to_email} via Resend (ID: {email.get('id', 'N/A')})")
        return True
    except Exception as e:
        print(f"ERROR sending email via Resend: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_email(to_email, subject, body, background=True):
    if not load_email_config():
        return False
    if background:
        global email_worker_thread
        if email_worker_thread is None or not email_worker_thread.is_alive():
            print("WARNING: Email worker thread not running! Starting it now...")
            start_email_worker()
        
        email_queue.put({
            'to': to_email,
            'subject': subject,
            'body': body
        })
        print(f"Email queued for background sending to {to_email} (queue size now: {email_queue.qsize()})")
        return True
    else:
        return send_email_direct(to_email, subject, body)

def email_worker():
    print("Email worker thread started")
    import time
    last_heartbeat = time.time()
    heartbeat_interval = 30
    
    while True:
        try:
            email_data = email_queue.get(timeout=1)
            print(f"Email worker: Processing email to {email_data['to']}")
            result = send_email_direct(
                email_data['to'],
                email_data['subject'],
                email_data['body']
            )
            if result:
                print(f"Email worker: Successfully sent email to {email_data['to']}")
            else:
                print(f"Email worker: Failed to send email to {email_data['to']} - check logs above for details")
            email_queue.task_done()
        except queue.Empty:
            current_time = time.time()
            if current_time - last_heartbeat >= heartbeat_interval:
                print(f"Email worker: Alive and waiting for emails (queue size: {email_queue.qsize()})")
                last_heartbeat = current_time
            continue
        except Exception as e:
            print(f"ERROR in email worker: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            try:
                email_queue.task_done()
            except:
                pass

def start_email_worker():
    global email_worker_thread
    
    if email_worker_thread is None or not email_worker_thread.is_alive():
        email_worker_thread = threading.Thread(target=email_worker, daemon=True)
        email_worker_thread.start()
        print("Email worker thread initialized")
        import time
        time.sleep(0.1)
        if email_worker_thread.is_alive():
            print("Email worker thread confirmed running")
        else:
            print("WARNING: Email worker thread started but is not alive!")

def check_and_send_due_tomorrow_reminders():
    try:
        db = _connect_sqlite()
        cur = CursorWrapper(db.cursor())
        config = load_email_config()
        library_name = config.get('library_name', 'AOA Library') if config else 'AOA Library'
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        cur.execute("""
            SELECT l.name, l.email, b.title, i.book_id, i.exp, i.issue
            FROM BookIssue i
            JOIN Login l ON l.userid = i.stdid
            JOIN Book b ON b.serial = CAST(i.serial AS INTEGER)
            WHERE i.exp = ?
        """, (tomorrow,))
        
        results = cur.fetchall()
        
        for row in results:
            student_name = row['name']
            student_email = row['email']
            book_title = row['title']
            book_id = row['book_id']
            return_date = row['exp']
            issue_date = row['issue']
            
            if not student_email:
                continue
            
            email_subject = f'{library_name} - Friendly Return Reminder'
            email_body = f'''
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                    <h2 style="color: #E8A71D; border-bottom: 3px solid #E8A71D; padding-bottom: 10px;">Friendly Return Reminder</h2>
                    
                    <p>Dear <strong>{student_name}</strong>,</p>
                    
                    <p>Thank you for borrowing from the {library_name}. This is a friendly reminder that the following book is <strong style="color: #E8A71D;">due tomorrow</strong>:</p>
                    
                    <div style="background-color: #fff; padding: 15px; border-left: 4px solid #E8A71D; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>Book Title:</strong> {book_title}</p>
                        <p style="margin: 5px 0;"><strong>Date Borrowed:</strong> {format_date_for_display(issue_date)}</p>
                        <p style="margin: 5px 0;"><strong>Due Date:</strong> <span style="color: #E8A71D; font-weight: bold;">{format_date_for_display(return_date)}</span></p>
                    </div>
                    
                    <p style="background-color: #FFF3CD; padding: 12px; border-radius: 5px; border-left: 4px solid #E8A71D;">
                        <strong>Please return this book tomorrow</strong> so other readers can continue to enjoy it.
                    </p>
                    
                    <p>If you need any clarification, please reply to this email and the library staff will assist you.</p>

                    <p>If you need to extend your borrowing period, please consult the library staff as soon as possible. We appreciate your cooperation.</p>

                    
                    <p>Thank you for your attention and for supporting the library.</p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    
                    <p style="font-size: 12px; color: #666;">
                        This is an automated reminder from {library_name}. Please do not reply to this email.
                    </p>
                </div>
            </body>
            </html>
            '''
            
            send_email(student_email, email_subject, email_body, background=False)
            print(f"Sent due tomorrow reminder to {student_name} ({student_email})")
        
        if results:
            print(f"Sent {len(results)} due tomorrow reminder(s)")
    except Exception as e:
        print(f"Error checking due tomorrow reminders: {e}")
    finally:
        if 'db' in locals():
            db.close()

def check_and_send_overdue_reminders():
    try:
        db = _connect_sqlite()
        cur = CursorWrapper(db.cursor())
        config = load_email_config()
        library_name = config.get('library_name', 'AOA Library') if config else 'AOA Library'
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cur.execute("""
            SELECT l.name, l.email, b.title, i.book_id, i.exp, i.issue
            FROM BookIssue i
            JOIN Login l ON l.userid = i.stdid
            JOIN Book b ON b.serial = CAST(i.serial AS INTEGER)
            WHERE i.exp < ?
        """, (today,))
        
        results = cur.fetchall()
        
        for row in results:
            student_name = row['name']
            student_email = row['email']
            book_title = row['title']
            book_id = row['book_id']
            return_date = row['exp']
            issue_date = row['issue']
            
            if not student_email:
                continue
            
            if isinstance(return_date, datetime):
                due_date = return_date
            elif isinstance(return_date, date):
                due_date = datetime.combine(return_date, datetime.min.time())
            else:
                due_date = datetime.strptime(str(return_date), '%Y-%m-%d')
            today_date = datetime.strptime(today, '%Y-%m-%d')
            days_overdue = (today_date - due_date).days
            
            email_subject = f'{library_name} - Overdue Return Reminder'
            email_body = f'''
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                    <h2 style="color: #C0392B; border-bottom: 3px solid #C0392B; padding-bottom: 10px;">Overdue Return Reminder</h2>
                    
                    <p>Dear <strong>{student_name}</strong>,</p>
                    
                    <p style="color: #C0392B; font-weight: bold;">Thank you for borrowing from the {library_name}. This is a reminder that the following book is now overdue:</p>
                    
                    <div style="background-color: #fff; padding: 15px; border-left: 4px solid #C0392B; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>Book Title:</strong> {book_title}</p>
                        <p style="margin: 5px 0;"><strong>Date Borrowed:</strong> {format_date_for_display(issue_date)}</p>
                        <p style="margin: 5px 0;"><strong>Was Due:</strong> <span style="color: #C0392B; font-weight: bold;">{format_date_for_display(return_date)}</span></p>
                        <p style="margin: 5px 0;"><strong>Days Overdue:</strong> <span style="color: #C0392B; font-weight: bold; font-size: 18px;">{days_overdue} day(s)</span></p>
                    </div>
                    
                    <div style="background-color: #F8D7DA; padding: 15px; border-radius: 5px; border-left: 4px solid #C0392B; margin: 20px 0;">
                        <p style="margin: 5px 0; color: #721C24; font-weight: bold;">
                             IMMEDIATE ACTION REQUIRED
                        </p>
                        <p style="margin: 5px 0; color: #721C24;">
                            Please return this book to the library as soon as possible so we can keep the collection moving for everyone.
                        </p>
                    </div>
                    
                    <p>If you have already returned this book, please disregard this message. Otherwise, please return it as soon as you can or contact the library staff if you need assistance.</p>

                    <p>If you need any clarification, please reply to this email and the library staff will assist you.</p>

                    
                    <p>Thank you for your understanding and cooperation.</p>
                    
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                    
                    <p style="font-size: 12px; color: #666;">
                        This is an automated reminder from {library_name}. Please do not reply to this email.
                    </p>
                </div>
            </body>
            </html>
            '''
            
            send_email(student_email, email_subject, email_body, background=False)
            print(f"Sent overdue reminder to {student_name} ({student_email}) - {days_overdue} day(s) overdue")
        
        if results:
            print(f"Sent {len(results)} overdue reminder(s)")
    except Exception as e:
        print(f"Error checking overdue reminders: {e}")
    finally:
        if 'db' in locals():
            db.close()

def run_daily_reminder_checks():
    print(f"\n{'='*60}")
    print(f"Running daily reminder checks at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    check_and_send_due_tomorrow_reminders()
    check_and_send_overdue_reminders()
    
    print(f"{'='*60}")
    print(f"Reminder checks completed")
    print(f"{'='*60}\n")

def setup_reminder_scheduler():
    eat_tz = pytz.timezone('Africa/Nairobi')
    schedule.every().day.at("18:00").do(run_daily_reminder_checks)
    print(f"Reminder scheduler initialized - checks will run daily at 6:00 PM EAT")

def run_scheduler_in_background():
    while True:
        schedule.run_pending()
        time.sleep(60)

def start_reminder_system():
    setup_reminder_scheduler()
    scheduler_thread = threading.Thread(target=run_scheduler_in_background, daemon=True)
    scheduler_thread.start()
    print("Reminder system started in background thread")


def format_date_for_display(date_value):
    if date_value is None:
        return ''
    
    if isinstance(date_value, datetime):
        return date_value.strftime('%B %d, %Y')
    if isinstance(date_value, date):
        return date_value.strftime('%B %d, %Y')
    
    if isinstance(date_value, str):
        try:
            dt = datetime.strptime(date_value, '%Y-%m-%d')
            return dt.strftime('%B %d, %Y')
        except:
            return date_value
    
    return str(date_value)


@app.route('/')
def index():
    return render_template('app.html')


class LibraryError(Exception):
    pass


VIEW_ROLES = ['admin', 'staff', 'borrower']


def current_viewer():
    if 'viewer' in g:
        return g.viewer
    viewer = {'role': 'admin', 'userid': None, 'name': LIBRARIAN_NAME, 'email': ''}
    role = session.get('view_role', 'admin')
    if role in ('staff', 'borrower'):
        cur = get_cursor()
        cur.execute("SELECT userid, name, email, role FROM Login WHERE userid=?", (session.get('view_userid'),))
        person = cur.fetchone()
        if person:
            is_staff = (person['role'] or '').lower() == 'staff'
            viewer = {'role': 'staff' if role == 'staff' and is_staff else 'borrower',
                      'userid': str(person['userid']), 'name': person['name'] or '', 'email': person['email'] or ''}
    g.viewer = viewer
    return viewer


def allowed_roles(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if current_viewer()['role'] not in roles:
                names = ' or '.join(roles)
                return jsonify(success=False, message=f'Switch to the {names} view to do this'), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def iso_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, (date, datetime)):
        return value.strftime('%Y-%m-%d')
    return str(value)


def parse_date(value, field_name):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        raise LibraryError(f'{field_name} must be a date (YYYY-MM-DD)')


def assign_copies(cur, student_id, title, copies, due_date, assigned_by, author=None, issue_date=None):
    cur.execute("SELECT name, email FROM Login WHERE userid=?", (student_id,))
    student = cur.fetchone()
    if not student:
        raise LibraryError('Borrower not found')
    if not student['email']:
        raise LibraryError('No email found for student. Please update student email first.')

    query = "SELECT b.book_id, b.serial, b.title FROM Book b WHERE b.title=? COLLATE UNICASE"
    params = [title]
    if author:
        query += " AND b.author=? COLLATE UNICASE"
        params.append(author)
    query += (" AND NOT EXISTS (SELECT 1 FROM BookIssue i WHERE i.book_id=b.book_id)"
              " ORDER BY CAST(b.book_id AS INTEGER)")
    cur.execute(query, tuple(params))
    available = cur.fetchall()
    if len(available) < copies:
        raise LibraryError(f"Only {len(available)} copy(ies) of '{title}' available")

    issue = (issue_date or date.today()).isoformat()
    chosen = available[:copies]
    for row in chosen:
        cur.execute("INSERT INTO BookIssue(stdid, serial, issue, exp, book_id, assigned_by) "
                    "VALUES(?, ?, ?, ?, ?, ?)",
                    (student_id, row['serial'], issue, due_date.isoformat(), row['book_id'], assigned_by))
    return student, chosen[0]['title'], [row['book_id'] for row in chosen]


def send_assignment_email(student, books, issue_date, due_date, assigned_by):
    config = load_email_config()
    library_name = config.get('library_name', 'AOA Library') if config else 'AOA Library'

    book_list_html = '<ul>' + ''.join(
        f'<li><strong>{html_escape(title)}</strong>{f" ({len(book_ids)} copies)" if len(book_ids) > 1 else ""}</li>'
        for title, book_ids in books) + '</ul>'

    email_subject = f'{library_name} - Thank You for Borrowing'
    email_body = f'''
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
        <h2 style="color: #265530; border-bottom: 3px solid #64A772; padding-bottom: 10px;">Thank You for Borrowing</h2>

            <p>Dear <strong>{html_escape(student['name'])}</strong>,</p>

        <p>Thank you for borrowing from the {library_name}. We appreciate your use of the library and have recorded the following book(s) as assigned to you:</p>

            {book_list_html}

            <div style="background-color: #fff; padding: 15px; border-left: 4px solid #E8A71D; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Date Borrowed:</strong> {format_date_for_display(issue_date)}</p>
                <p style="margin: 5px 0;"><strong>Return Date:</strong> <span style="color: #C87140; font-weight: bold;">{format_date_for_display(due_date)}</span></p>
                <p style="margin: 5px 0;"><strong>Assigned By:</strong> {html_escape(assigned_by)}</p>
            </div>

            <p style="color: #C0392B; font-weight: bold;">Please return the book(s) by the date mentioned above to help us keep the collection available for everyone.</p>

            <p>If you need any clarification, please reply to this email and the library staff will assist you.</p>


            <p>We are glad to support your reading and learning.</p>

            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">

            <p style="font-size: 12px; color: #666;">
                This is an automated message from {library_name}. Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    '''
    return send_email(student['email'], email_subject, email_body, background=True)


def return_copies(cur, student_id, book_ids, return_date, returned_by):
    cur.execute("SELECT name, email FROM Login WHERE userid=?", (student_id,))
    student = cur.fetchone()
    if not student:
        raise LibraryError('Student not found')

    book_ids = [str(bid) for bid in book_ids if str(bid).strip()]
    if not book_ids:
        raise LibraryError('Select at least one book to return')

    placeholders = ','.join('?' * len(book_ids))
    cur.execute(f"""
        SELECT i.book_id, i.issue, b.title
        FROM BookIssue i
        JOIN Book b ON b.serial = CAST(i.serial AS INTEGER)
        WHERE i.stdid=? AND i.book_id IN ({placeholders})
        ORDER BY b.title, i.book_id
    """, (student_id, *book_ids))
    loans = cur.fetchall()
    if not loans:
        raise LibraryError('None of the selected books are on loan to this borrower')

    returned_on = return_date.isoformat()
    by_title = {}
    for loan in loans:
        by_title.setdefault(loan['title'], []).append(loan)

    returned = []
    for title, title_loans in by_title.items():
        first_issue = min(iso_date(loan['issue']) or returned_on for loan in title_loans)
        cur.execute("INSERT INTO BookReturn(stdid, title, copies, issue, returned) VALUES(?, ?, ?, ?, ?)",
                    (student_id, title, len(title_loans), first_issue, returned_on))
        for loan in title_loans:
            cur.execute("INSERT INTO BookReturnDetail(stdid, title, book_id, issue, returned, returned_by) "
                        "VALUES(?, ?, ?, ?, ?, ?)",
                        (student_id, title, loan['book_id'], iso_date(loan['issue']) or returned_on, returned_on, returned_by))
            cur.execute("DELETE FROM BookIssue WHERE stdid=? AND book_id=?", (student_id, loan['book_id']))
            returned.append({'title': title, 'book_id': loan['book_id']})
    return student, returned


def send_return_email(student, returned, return_date, returned_by):
    if not student['email']:
        return False
    config = load_email_config()
    library_name = config.get('library_name', 'AOA Library') if config else 'AOA Library'

    counts = {}
    for book in returned:
        counts[book['title']] = counts.get(book['title'], 0) + 1
    book_list_html = '<ul>' + ''.join(
        f'<li><strong>{html_escape(title)}</strong>{f" ({n} copies)" if n > 1 else ""}</li>'
        for title, n in counts.items()) + '</ul>'

    email_subject = f'{library_name} - Thank You for Returning the Book(s)'
    email_body = f'''
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
            <h2 style="color: #265530; border-bottom: 3px solid #64A772; padding-bottom: 10px;">Thank You for Returning the Book(s)</h2>

            <p>Dear <strong>{html_escape(student['name'])}</strong>,</p>

            <p style="color: #27ae60; font-weight: bold;">Thank you for returning the following book(s) to the {library_name}. We appreciate your prompt return and support:</p>

            {book_list_html}

            <div style="background-color: #fff; padding: 15px; border-left: 4px solid #64A772; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Date Returned:</strong> {format_date_for_display(return_date)}</p>
                <p style="margin: 5px 0;"><strong>Processed By:</strong> {html_escape(returned_by)}</p>
            </div>

            <p>Your return has been recorded in our system. You are always welcome to borrow more books anytime.</p>

            <p>If you have already returned the book but it has not been ticked off by a staff member, please look for the book in the library and ask a staff member to update it in the system so it can be removed from your record.</p>

            <p>If you need any clarification, please reply to this email and the library staff will assist you.</p>


            <p>Thank you for using the {library_name} and helping us keep the library resources in good circulation.</p>

            <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">

            <p style="font-size: 12px; color: #666;">
                This is an automated message from {library_name}. Please do not reply to this email.
            </p>
        </div>
    </body>
    </html>
    '''
    return send_email(student['email'], email_subject, email_body, background=True)


def staff_members():
    cur = get_cursor()
    names = [LIBRARIAN_NAME]
    cur.execute("SELECT name FROM Login WHERE LOWER(role)='staff' AND TRIM(COALESCE(name, ''))!='' ORDER BY LOWER(name)")
    for row in cur.fetchall():
        name = row['name'].strip()
        if name not in names:
            names.append(name)
    return names


@app.errorhandler(LibraryError)
def handle_library_error(error):
    return jsonify(success=False, message=str(error)), 400


def api_ok(message=None, **data):
    return jsonify(success=True, message=message, **data)


def request_data():
    return request.get_json(silent=True) or {}


def clean_category(value):
    text = (value or '').replace('\u2060', '').strip().lstrip('.').strip()
    base = text.split('(')[0].strip().lower()
    for category in BOOK_CATEGORIES:
        if base == category.lower():
            return category
    return text or 'Unclassified'


def require_category(value):
    category = clean_category(value) if (value or '').strip() else ''
    if category not in BOOK_CATEGORIES:
        raise LibraryError(f"Category must be one of: {', '.join(BOOK_CATEGORIES)}")
    return category


def clean_dewey(value):
    dewey = (value or '').strip()
    if not dewey:
        return None
    if not re.fullmatch(r'\d{3}(\.\d+)?', dewey):
        raise LibraryError('Dewey number must look like 823 or 823.914')
    return dewey


def days_overdue(due_value):
    due = iso_date(due_value)
    if not due:
        return 0
    try:
        return max(0, (date.today() - datetime.strptime(due, '%Y-%m-%d').date()).days)
    except ValueError:
        return 0


def clean_group(value, required=False):
    group = (value or '').strip()
    if not group and not required:
        return None
    for known in BORROWER_GROUPS:
        if group.lower() == known.lower():
            return known
    raise LibraryError(f"Group must be one of: {', '.join(BORROWER_GROUPS)}")


def clean_role(value):
    role = (value or 'borrower').strip().lower()
    if role not in BORROWER_ROLES:
        raise LibraryError(f"Role must be one of: {', '.join(BORROWER_ROLES)}")
    return role


def clean_borrower_email(value, cur, exclude_userid=None):
    email = sanitize_email(value or '')
    if not email:
        raise LibraryError('Please enter a valid email address')
    cur.execute("SELECT userid, name FROM Login WHERE LOWER(TRIM(email))=LOWER(?)", (email,))
    for row in cur.fetchall():
        if str(row['userid']) != str(exclude_userid):
            raise LibraryError(f"{email} is already used by {row['name']}")
    return email


@app.route('/api/me')
def api_me():
    viewer = current_viewer()
    cur = get_cursor()
    cur.execute("SELECT userid, name, role FROM Login ORDER BY LOWER(name)")
    people = [{'userid': str(row['userid']), 'name': row['name'] or '',
               'role': 'staff' if (row['role'] or '').lower() == 'staff' else 'borrower'}
              for row in cur.fetchall()]
    return api_ok(role=viewer['role'], userid=viewer['userid'], name=viewer['name'], email=viewer['email'],
                  people=people, staff=staff_members(), groups=BORROWER_GROUPS, categories=BOOK_CATEGORIES,
                  roles=BORROWER_ROLES, today=date.today().isoformat())


@app.route('/api/view-as', methods=['POST'])
def api_view_as():
    data = request_data()
    role = (data.get('role') or '').strip().lower()
    if role not in VIEW_ROLES:
        raise LibraryError(f"Role must be one of: {', '.join(VIEW_ROLES)}")
    userid = str(data.get('userid') or '').strip()
    if role == 'admin':
        session.pop('view_userid', None)
    else:
        cur = get_cursor()
        cur.execute("SELECT name, role FROM Login WHERE userid=?", (userid,))
        person = cur.fetchone()
        if not person:
            raise LibraryError('Choose a borrower to view the app as')
        if role == 'staff' and (person['role'] or '').lower() != 'staff':
            raise LibraryError(f"{person['name']} is not staff. Set their role to Staff on the Borrowers page first.")
        session['view_userid'] = userid
    session['view_role'] = role
    g.pop('viewer', None)
    viewer = current_viewer()
    return api_ok(f"Now viewing as {viewer['name']} ({viewer['role']})")


@app.route('/api/titles')
def api_titles():
    cur = get_cursor()
    cur.execute("""
        SELECT MIN(b.serial) AS key, MIN(b.title) AS title, MIN(b.author) AS author,
               MIN(b.subject) AS subject, MIN(b.dewey) AS dewey, COUNT(*) AS total,
               SUM(CASE WHEN NOT EXISTS (
                   SELECT 1 FROM BookIssue i WHERE i.book_id = b.book_id
               ) THEN 1 ELSE 0 END) AS available
        FROM Book b
        GROUP BY b.title COLLATE UNICASE, b.author COLLATE UNICASE
        ORDER BY MIN(b.title) COLLATE UNICASE
    """)
    titles = [{
        'key': str(row['key']),
        'title': row['title'],
        'author': row['author'] or '',
        'category': clean_category(row['subject']),
        'subject': row['subject'] or '',
        'dewey': row['dewey'] or '',
        'total': row['total'],
        'available': row['available'],
    } for row in cur.fetchall()]
    return api_ok(titles=titles)


@app.route('/api/titles', methods=['POST'])
@allowed_roles('admin')
def api_add_title():
    data = request_data()
    title = (data.get('title') or '').strip()
    author = (data.get('author') or '').strip()
    if not (title and author):
        raise LibraryError('Title and author are required')
    subject = require_category(data.get('category'))
    dewey = clean_dewey(data.get('dewey'))
    try:
        copies = int(data.get('copies') or 1)
    except (TypeError, ValueError):
        raise LibraryError('Copies must be a whole number')
    if not 1 <= copies <= 100:
        raise LibraryError('Copies must be between 1 and 100')

    cur = get_cursor()
    cur.execute("""SELECT title, author, dewey FROM Book
                   WHERE title=? COLLATE UNICASE AND author=? COLLATE UNICASE LIMIT 1""", (title, author))
    existing = cur.fetchone()
    if existing:
        title, author = existing['title'], existing['author']
        dewey = dewey or existing['dewey']

    book_ids = []
    for _ in range(copies):
        book_id = next_book_id(cur)
        cur.execute("INSERT INTO Book(subject,title,author,book_id,dewey) VALUES(?,?,?,?,?)",
                    (subject, title, author, book_id, dewey))
        book_ids.append(book_id)
    get_db().commit()
    verb = 'Added' if not existing else 'Added more copies to'
    return api_ok(f"{verb} '{title}' ({len(book_ids)} {'copy' if len(book_ids) == 1 else 'copies'})", book_ids=book_ids)


@app.route('/api/titles', methods=['PUT'])
@allowed_roles('admin')
def api_edit_title():
    data = request_data()
    title = (data.get('title') or '').strip()
    author = (data.get('author') or '').strip()
    new_title = (data.get('new_title') or '').strip()
    new_author = (data.get('new_author') or '').strip()
    if not (new_title and new_author):
        raise LibraryError('Title and author are required')
    new_subject = require_category(data.get('new_category'))
    new_dewey = clean_dewey(data.get('new_dewey'))

    cur = get_cursor()
    cur.execute("""UPDATE Book SET title=?, author=?, subject=?, dewey=?
                   WHERE title=? COLLATE UNICASE AND author=? COLLATE UNICASE""",
                (new_title, new_author, new_subject, new_dewey, title, author))
    if cur.rowcount == 0:
        raise LibraryError('Title not found')
    get_db().commit()
    return api_ok(f"Updated '{new_title}' ({cur.rowcount} copies)")


@app.route('/api/titles', methods=['DELETE'])
@allowed_roles('admin')
def api_archive_title():
    data = request_data()
    title = (data.get('title') or '').strip()
    author = (data.get('author') or '').strip()
    cur = get_cursor()
    where = "title=? COLLATE UNICASE AND author=? COLLATE UNICASE"
    cur.execute(f"SELECT COUNT(*) AS n FROM Book WHERE {where}", (title, author))
    if not cur.fetchone()['n']:
        raise LibraryError('Title not found')
    cur.execute("""SELECT 1 FROM BookIssue i JOIN Book b ON b.book_id=i.book_id
                   WHERE b.title=? COLLATE UNICASE AND b.author=? COLLATE UNICASE LIMIT 1""", (title, author))
    if cur.fetchone():
        raise LibraryError('Cannot delete: at least one copy is currently on loan')
    cur.execute(f"INSERT INTO DeletedBook(subject, title, author, book_id, deleted, dewey) "
                f"SELECT subject, title, author, book_id, ?, dewey FROM Book WHERE {where}",
                (date.today().isoformat(), title, author))
    cur.execute(f"DELETE FROM Book WHERE {where}", (title, author))
    get_db().commit()
    return api_ok(f"Deleted all copies of '{title}'")


@app.route('/api/copies')
@allowed_roles('admin')
def api_copies():
    title = request.args.get('title', '').strip()
    author = request.args.get('author', '').strip()
    cur = get_cursor()
    cur.execute("""
        SELECT b.book_id, i.stdid, l.name AS borrower, i.issue, i.exp
        FROM Book b
        LEFT JOIN BookIssue i ON i.book_id = b.book_id
        LEFT JOIN Login l ON l.userid = i.stdid
        WHERE b.title=? COLLATE UNICASE AND b.author=? COLLATE UNICASE
        ORDER BY CAST(b.book_id AS INTEGER), b.book_id
    """, (title, author))
    copies = [{
        'book_id': row['book_id'],
        'available': row['stdid'] is None,
        'userid': row['stdid'],
        'borrower': row['borrower'],
        'issued': iso_date(row['issue']),
        'due': iso_date(row['exp']),
        'days_overdue': days_overdue(row['exp']) if row['stdid'] is not None else 0,
    } for row in cur.fetchall()]
    return api_ok(copies=copies)


@app.route('/api/copies', methods=['POST'])
@allowed_roles('admin')
def api_add_copy():
    data = request_data()
    cur = get_cursor()
    cur.execute("""SELECT subject, title, author, dewey FROM Book
                   WHERE title=? COLLATE UNICASE AND author=? COLLATE UNICASE LIMIT 1""",
                ((data.get('title') or '').strip(), (data.get('author') or '').strip()))
    existing = cur.fetchone()
    if not existing:
        raise LibraryError('Title not found')
    new_id = next_book_id(cur)
    cur.execute("INSERT INTO Book(subject,title,author,book_id,dewey) VALUES(?,?,?,?,?)",
                (existing['subject'], existing['title'], existing['author'], new_id, existing['dewey']))
    get_db().commit()
    return api_ok(f"Added a copy of '{existing['title']}'", book_id=new_id)


@app.route('/api/copies/<book_id>', methods=['DELETE'])
@allowed_roles('admin')
def api_delete_copy(book_id):
    cur = get_cursor()
    cur.execute("SELECT 1 FROM Book WHERE book_id=?", (book_id,))
    if not cur.fetchone():
        raise LibraryError('Book not found')
    cur.execute("SELECT 1 FROM BookIssue WHERE book_id=?", (book_id,))
    if cur.fetchone():
        raise LibraryError('Cannot delete: this copy is currently on loan')
    cur.execute("INSERT INTO DeletedBook(subject, title, author, book_id, deleted, dewey) "
                "SELECT subject, title, author, book_id, ?, dewey FROM Book WHERE book_id=?",
                (date.today().isoformat(), book_id))
    cur.execute("DELETE FROM Book WHERE book_id=?", (book_id,))
    get_db().commit()
    return api_ok("Copy deleted")


@app.route('/api/borrowers')
@allowed_roles('admin', 'staff')
def api_borrowers():
    cur = get_cursor()
    cur.execute("""
        SELECT l.userid, l.name, l.email, l.borrower_group, l.role,
               (SELECT COUNT(*) FROM BookIssue i WHERE i.stdid = l.userid) AS active,
               (SELECT COUNT(*) FROM BookIssue i WHERE i.stdid = l.userid AND i.exp < ?) AS overdue
        FROM Login l
        ORDER BY LOWER(l.name), CAST(l.userid AS INTEGER)
    """, (date.today().isoformat(),))
    borrowers = [{
        'userid': str(row['userid']),
        'name': row['name'] or '',
        'email': row['email'] or '',
        'group': row['borrower_group'],
        'role': 'staff' if (row['role'] or '').lower() == 'staff' else 'borrower',
        'active': row['active'],
        'overdue': row['overdue'],
    } for row in cur.fetchall()]
    return api_ok(borrowers=borrowers)


@app.route('/api/borrowers', methods=['POST'])
@allowed_roles('admin')
def api_add_borrower():
    data = request_data()
    cur = get_cursor()
    name = ' '.join((data.get('name') or '').split())
    if not name:
        raise LibraryError('Name is required')
    email = clean_borrower_email(data.get('email'), cur)
    group = clean_group(data.get('group'), required=True)
    role = clean_role(data.get('role'))

    cur.execute("SELECT COALESCE(MAX(CAST(userid AS INTEGER)),0) AS max_id FROM Login")
    new_id = str((cur.fetchone()['max_id'] or 0) + 1)
    cur.execute("INSERT INTO Login(name, userid, email, borrower_group, role) VALUES(?, ?, ?, ?, ?)",
                (name, new_id, email, group, role))
    get_db().commit()
    return api_ok(f"{name} added as {'staff' if role == 'staff' else f'a {group} borrower'}", userid=new_id)


@app.route('/api/borrowers/<userid>', methods=['PUT'])
@allowed_roles('admin')
def api_edit_borrower(userid):
    data = request_data()
    cur = get_cursor()
    cur.execute("SELECT 1 FROM Login WHERE userid=?", (userid,))
    if not cur.fetchone():
        raise LibraryError('Borrower not found')
    name = ' '.join((data.get('name') or '').split())
    if not name:
        raise LibraryError('Name is required')
    email = clean_borrower_email(data.get('email'), cur, exclude_userid=userid)
    group = clean_group(data.get('group'))
    role = clean_role(data.get('role'))
    cur.execute("UPDATE Login SET name=?, email=?, borrower_group=?, role=? WHERE userid=?",
                (name, email, group, role, userid))
    get_db().commit()
    return api_ok(f"{name} updated")


@app.route('/api/borrowers/<userid>', methods=['DELETE'])
@allowed_roles('admin')
def api_delete_borrower(userid):
    cur = get_cursor()
    cur.execute("SELECT name FROM Login WHERE userid=?", (userid,))
    row = cur.fetchone()
    if not row:
        raise LibraryError('Borrower not found')
    cur.execute("SELECT 1 FROM BookIssue WHERE stdid=? LIMIT 1", (userid,))
    if cur.fetchone():
        raise LibraryError('Cannot delete: this borrower still has books on loan')
    cur.execute("INSERT INTO DeletedLogin(name, userid, deleted) SELECT name, userid, ? FROM Login WHERE userid=?",
                (date.today().isoformat(), userid))
    cur.execute("DELETE FROM Login WHERE userid=?", (userid,))
    get_db().commit()
    return api_ok(f"{row['name']} deleted")


def _loan_json(row):
    return {
        'userid': str(row['stdid']),
        'borrower': row['name'],
        'group': row['borrower_group'],
        'title': row['title'],
        'author': row['author'] or '',
        'book_id': row['book_id'],
        'issued': iso_date(row['issue']),
        'due': iso_date(row['exp']),
        'assigned_by': row['assigned_by'] or '',
        'days_overdue': days_overdue(row['exp']),
    }


@app.route('/api/loans')
@allowed_roles('admin', 'staff')
def api_loans():
    cur = get_cursor()
    cur.execute("""
        SELECT i.stdid, l.name, l.borrower_group, b.title, b.author, i.book_id, i.issue, i.exp, i.assigned_by
        FROM BookIssue i
        JOIN Login l ON l.userid = i.stdid
        JOIN Book b ON b.serial = CAST(i.serial AS INTEGER)
        ORDER BY i.exp, l.name, b.title
    """)
    return api_ok(loans=[_loan_json(row) for row in cur.fetchall()])


@app.route('/api/loans', methods=['POST'])
@allowed_roles('admin', 'staff')
def api_assign():
    data = request_data()
    userid = str(data.get('userid') or '').strip()
    assigned_by = (data.get('assigned_by') or '').strip()
    if current_viewer()['role'] == 'staff':
        assigned_by = current_viewer()['name']
    items = data.get('items')
    if items is None:
        items = [{'title': data.get('title'), 'author': data.get('author'), 'copies': data.get('copies')}]
    if not isinstance(items, list):
        raise LibraryError('items must be a list')

    requested = {}
    for item in items:
        if not isinstance(item, dict):
            raise LibraryError('Each item needs a title')
        title = (item.get('title') or '').strip()
        author = (item.get('author') or '').strip() or None
        if not title:
            continue
        try:
            copies = int(item.get('copies') or 1)
        except (TypeError, ValueError):
            raise LibraryError('Copies must be a whole number')
        if copies < 1:
            raise LibraryError('Copies must be at least 1')
        key = (title.lower(), (author or '').lower())
        if key in requested:
            requested[key][2] += copies
        else:
            requested[key] = [title, author, copies]
    if not (userid and requested and assigned_by):
        raise LibraryError('Choose a borrower, at least one book and the staff member assigning it')
    issued = parse_date(data.get('issued') or date.today().isoformat(), 'Assigned date')
    due = parse_date(data.get('due'), 'Due date')
    if due < issued:
        raise LibraryError('Due date cannot be before the assigned date')

    cur = get_cursor()
    books = []
    for title, author, copies in requested.values():
        student, title, book_ids = assign_copies(cur, userid, title, copies, due, assigned_by,
                                                 author=author, issue_date=issued)
        books.append((title, book_ids))
    get_db().commit()
    emailed = send_assignment_email(student, books, issued, due, assigned_by)
    all_ids = [bid for _, ids in books for bid in ids]
    what = f"'{books[0][0]}'" if len(books) == 1 else f"{len(books)} titles"
    return api_ok(f"Assigned {len(all_ids)} book(s) ({what}) to {student['name']}" + (' - email queued' if emailed else ''),
                  book_ids=all_ids)


@app.route('/api/loans/return', methods=['POST'])
@allowed_roles('admin', 'staff')
def api_return():
    data = request_data()
    userid = str(data.get('userid') or '').strip()
    returned_by = (data.get('returned_by') or '').strip()
    if current_viewer()['role'] == 'staff':
        returned_by = current_viewer()['name']
    if not (userid and returned_by):
        raise LibraryError('Choose the borrower and who processed the return')
    returned_on = parse_date(data.get('returned') or date.today().isoformat(), 'Return date')
    book_ids = data.get('book_ids') or []
    if not isinstance(book_ids, list):
        raise LibraryError('book_ids must be a list')

    cur = get_cursor()
    student, returned = return_copies(cur, userid, book_ids, returned_on, returned_by)
    get_db().commit()
    emailed = send_return_email(student, returned, returned_on, returned_by)
    return api_ok(f"Returned {len(returned)} book(s) from {student['name']}" + (' - email queued' if emailed else ''))


@app.route('/api/loans/extend', methods=['POST'])
@allowed_roles('admin')
def api_extend():
    data = request_data()
    userid = str(data.get('userid') or '').strip()
    book_id = str(data.get('book_id') or '').strip()
    due = parse_date(data.get('due'), 'Due date')
    cur = get_cursor()
    cur.execute("UPDATE BookIssue SET exp=? WHERE stdid=? AND book_id=?", (due.isoformat(), userid, book_id))
    if cur.rowcount == 0:
        raise LibraryError('Loan not found')
    get_db().commit()
    return api_ok(f"Due date moved to {format_date_for_display(due)}")


@app.route('/api/returns')
@allowed_roles('admin')
def api_returns():
    userid = request.args.get('userid', '').strip()
    limit = min(max(request.args.get('limit', 300, type=int), 1), 2000)
    cur = get_cursor()
    query = """
        SELECT d.stdid, l.name, d.title, d.book_id, d.issue, d.returned, d.returned_by
        FROM BookReturnDetail d
        LEFT JOIN Login l ON l.userid = d.stdid
    """
    params = []
    if userid:
        query += " WHERE d.stdid=?"
        params.append(userid)
    query += " ORDER BY d.returned DESC, d.rowid DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, tuple(params))
    returns = [{
        'userid': str(row['stdid']),
        'borrower': row['name'] or '(deleted borrower)',
        'title': row['title'],
        'book_id': row['book_id'],
        'issued': iso_date(row['issue']),
        'returned': iso_date(row['returned']),
        'returned_by': row['returned_by'] or '',
    } for row in cur.fetchall()]
    return api_ok(returns=returns)


@app.route('/api/my-books')
@allowed_roles('staff', 'borrower')
def api_my_books():
    userid = current_viewer()['userid']
    cur = get_cursor()
    cur.execute("""
        SELECT b.title, b.author, i.book_id, i.issue, i.exp
        FROM BookIssue i
        JOIN Book b ON b.serial = CAST(i.serial AS INTEGER)
        WHERE i.stdid = ?
        ORDER BY i.exp, b.title
    """, (userid,))
    current = [{
        'title': row['title'], 'author': row['author'] or '', 'book_id': row['book_id'],
        'issued': iso_date(row['issue']), 'due': iso_date(row['exp']),
        'days_overdue': days_overdue(row['exp']),
    } for row in cur.fetchall()]
    cur.execute("""
        SELECT title, book_id, issue, returned
        FROM BookReturnDetail
        WHERE stdid = ?
        ORDER BY returned DESC, title
    """, (userid,))
    history = [{
        'title': row['title'], 'book_id': row['book_id'],
        'issued': iso_date(row['issue']), 'returned': iso_date(row['returned']),
    } for row in cur.fetchall()]
    return api_ok(current=current, history=history)


try:
    with app.app_context():
        get_db()
        start_email_worker()
        start_reminder_system()
        print("App initialized: Email worker and reminder system started")
except Exception as e:
    print(f"Warning: Could not initialize app components: {e}")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

 