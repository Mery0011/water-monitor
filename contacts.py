"""Local owner directory and contact links. This module never sends messages."""
import re
from urllib.parse import urlencode, quote
from storage import connection, utc_now


def validate_contact(apartment,name,phone,email):
    if apartment not in {f'{n:02d}' for n in range(1,16)}:
        raise ValueError('Invalid apartment')
    name,phone,email = name.strip(),phone.strip(),email.strip()
    if not name or len(name)>80 or any(ord(c)<32 for c in name):
        raise ValueError('Invalid owner name')
    if phone:
        phone = re.sub(r'[ ()-]','',phone)
        if not re.fullmatch(r'\+?[0-9]{7,15}',phone):
            raise ValueError('Invalid phone')
    if email and (len(email)>254 or not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',email)):
        raise ValueError('Invalid email')
    return name,phone,email


def get_contact(apartment,path=None):
    validate_contact(apartment,'Demo','','')
    with connection(path) as db:
        row = db.execute('SELECT * FROM contacts WHERE apartment=?',(apartment,)).fetchone()
        if row is not None and row['is_demo'] and row['phone'] == f'+120255501{apartment}' and row['email'] == f'owner{apartment}@example.invalid':
            db.execute('UPDATE contacts SET phone=?,email=?,updated_at=? WHERE apartment=?',
                (f'+82100000{apartment.zfill(4)}',f'water.monitor.demo.owner{apartment}@gmail.com',utc_now(),apartment))
            row = db.execute('SELECT * FROM contacts WHERE apartment=?',(apartment,)).fetchone()
        if row is not None and row['is_demo'] and row['email'] == f'water.monitor.demo.owner{apartment}@gmail.com':
            db.execute('UPDATE contacts SET email=?,updated_at=? WHERE apartment=?',
                (f'owner{apartment}@gmail.com',utc_now(),apartment))
            row = db.execute('SELECT * FROM contacts WHERE apartment=?',(apartment,)).fetchone()
        if row is None:
            # Sample Korean-format phone and Gmail address; demo actions stay disabled.
            db.execute('INSERT OR IGNORE INTO contacts VALUES(?,?,?,?,?,?)',
                (apartment,f'Demo Resident {apartment}',f'+82100000{apartment.zfill(4)}',
                 f'owner{apartment}@gmail.com',1,utc_now()))
            row = db.execute('SELECT * FROM contacts WHERE apartment=?',(apartment,)).fetchone()
    return dict(row)


def save_contact(apartment,name,phone,email,is_demo=True,path=None):
    name,phone,email = validate_contact(apartment,name,phone,email)
    with connection(path) as db:
        db.execute('''INSERT INTO contacts VALUES(?,?,?,?,?,?)
            ON CONFLICT(apartment) DO UPDATE SET name=excluded.name,
            phone=excluded.phone,email=excluded.email,is_demo=excluded.is_demo,
            updated_at=excluded.updated_at''',
            (apartment,name,phone,email,int(is_demo),utc_now()))


def contact_links(contact,subject,body):
    """Fictional demo contacts cannot be called or emailed from the UI."""
    if contact['is_demo']:
        return None,None
    _,phone,email = validate_contact(contact['apartment'],contact['name'],contact['phone'],contact['email'])
    call = 'tel:'+phone if phone else None
    mail = 'mailto:'+quote(email,safe='@')+'?'+urlencode({'subject':subject,'body':body},quote_via=quote) if email else None
    return call,mail
