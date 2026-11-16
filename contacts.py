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
        if row is None:
            # Reserved example email domain and fictional NANP 555-01xx number.
            db.execute('INSERT OR IGNORE INTO contacts VALUES(?,?,?,?,?,?)',
                (apartment,f'Demo Resident {apartment}',f'+120255501{apartment}',
                 f'owner{apartment}@example.invalid',1,utc_now()))
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
