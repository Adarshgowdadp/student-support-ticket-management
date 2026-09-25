from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import os
from typing import Optional

import jwt
from fastapi import FastAPI, Depends, HTTPException, Query, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, DateTime, ForeignKey, Text, select, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_URL = f"sqlite:///{os.path.join(BASE_DIR, 'edumerge.db')}"
SECRET = os.getenv('JWT_SECRET', 'edumerge-demo-secret-change-me')
ALGORITHM = 'HS256'

engine = create_engine(DB_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(20))
    department: Mapped[str] = mapped_column(String(120), default='Administration')

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    default_sla_hours: Mapped[int] = mapped_column(Integer, default=48)

class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'))
    priority: Mapped[str] = mapped_column(String(20), default='Medium')
    status: Mapped[str] = mapped_column(String(30), default='Open')
    student_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    due_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'))
    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    internal: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Activity(Base):
    __tablename__ = 'activities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey('tickets.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

def pwd(s): return hashlib.sha256(s.encode()).hexdigest()

def seed():
    db=SessionLocal()
    if db.scalar(select(User).limit(1)):
        db.close(); return
    users=[
      User(name='Admin User', email='admin@edumerge.com', password_hash=pwd('admin123'), role='admin', department='Administration'),
      User(name='Support Staff', email='staff@edumerge.com', password_hash=pwd('staff123'), role='staff', department='Student Services'),
      User(name='Adarsh Student', email='student@edumerge.com', password_hash=pwd('student123'), role='student', department='MCA'),
      User(name='Finance Staff', email='finance@edumerge.com', password_hash=pwd('finance123'), role='staff', department='Finance'),
    ]
    db.add_all(users)
    cats=[Category(name='Fees',default_sla_hours=24),Category(name='Attendance',default_sla_hours=24),Category(name='ID Card',default_sla_hours=48),Category(name='Documents',default_sla_hours=72),Category(name='Certificates',default_sla_hours=72),Category(name='Other',default_sla_hours=48)]
    db.add_all(cats); db.commit()
    now=datetime.now(timezone.utc)
    t1=Ticket(ticket_no='EDU-1001',title='Attendance correction request',description='My attendance for DBMS on 18 September is missing. Please review.',category_id=2,priority='High',status='In Progress',student_id=3,assignee_id=2,created_at=now-timedelta(hours=18),updated_at=now-timedelta(hours=2),due_at=now+timedelta(hours=6))
    t2=Ticket(ticket_no='EDU-1002',title='Request duplicate ID card',description='I lost my ID card and need a replacement.',category_id=3,priority='Medium',status='Open',student_id=3,assignee_id=None,created_at=now-timedelta(hours=10),updated_at=now-timedelta(hours=10),due_at=now+timedelta(hours=38))
    t3=Ticket(ticket_no='EDU-1003',title='Semester fee payment issue',description='Payment was debited but the portal still shows outstanding fees.',category_id=1,priority='Critical',status='Pending',student_id=3,assignee_id=4,created_at=now-timedelta(hours=30),updated_at=now-timedelta(hours=8),due_at=now-timedelta(hours=6))
    db.add_all([t1,t2,t3]); db.commit()
    for t,a,msg in [(t1,2,'Ticket assigned to Support Staff'),(t2,3,'Ticket created'),(t3,4,'Finance team reviewing payment state')]:
        db.add(Activity(ticket_id=t.id,actor_id=a,action=msg))
    db.commit(); db.close()
seed()

app=FastAPI(title='Edumerge Student Support & Ticket Management', version='1.0.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
app.mount('/static', StaticFiles(directory=os.path.join(BASE_DIR,'static')), name='static')

class LoginIn(BaseModel): email:str; password:str
class TicketIn(BaseModel): title:str=Field(min_length=3,max_length=200); description:str=Field(min_length=5); category_id:int; priority:str='Medium'
class UpdateTicket(BaseModel): status:Optional[str]=None; priority:Optional[str]=None; assignee_id:Optional[int]=None
class CommentIn(BaseModel): body:str=Field(min_length=1); internal:bool=False

VALID_STATUS={'Open','In Progress','Pending','Resolved','Closed'}
VALID_PRIORITY={'Low','Medium','High','Critical'}

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

def token_for(u):
    return jwt.encode({'sub':str(u.id),'exp':datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm=ALGORITHM)

def current_user(db:Session, authorization:Optional[str]):
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Authentication required')
    try: payload=jwt.decode(authorization.split(' ',1)[1],SECRET,algorithms=[ALGORITHM]); uid=int(payload['sub'])
    except Exception: raise HTTPException(401,'Invalid or expired session')
    u=db.get(User,uid)
    if not u: raise HTTPException(401,'User not found')
    return u

def user_dict(u): return {'id':u.id,'name':u.name,'email':u.email,'role':u.role,'department':u.department}
def ticket_dict(db,t):
    cat=db.get(Category,t.category_id); student=db.get(User,t.student_id); assignee=db.get(User,t.assignee_id) if t.assignee_id else None
    now=datetime.now(timezone.utc); due=t.due_at.replace(tzinfo=timezone.utc) if t.due_at.tzinfo is None else t.due_at
    overdue=t.status not in {'Resolved','Closed'} and now>due
    return {'id':t.id,'ticket_no':t.ticket_no,'title':t.title,'description':t.description,'category':cat.name,'category_id':t.category_id,'priority':t.priority,'status':t.status,'student':user_dict(student),'assignee':user_dict(assignee) if assignee else None,'created_at':t.created_at.isoformat(),'updated_at':t.updated_at.isoformat(),'due_at':t.due_at.isoformat(),'resolved_at':t.resolved_at.isoformat() if t.resolved_at else None,'sla_breached':overdue}

def activity(db,ticket_id):
    rows=db.scalars(select(Activity).where(Activity.ticket_id==ticket_id).order_by(Activity.created_at.desc())).all(); out=[]
    for x in rows:
        u=db.get(User,x.actor_id); out.append({'action':x.action,'actor':u.name if u else 'System','created_at':x.created_at.isoformat()})
    return out

def can_view(u,t): return u.role in {'admin','staff'} or t.student_id==u.id

def log(db,t,u,msg): db.add(Activity(ticket_id=t.id,actor_id=u.id,action=msg))

@app.get('/')
def root(): return FileResponse(os.path.join(BASE_DIR,'static','index.html'))

@app.post('/api/login')
def login(body:LoginIn,db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==body.email.lower().strip()))
    if not u or u.password_hash!=pwd(body.password): raise HTTPException(401,'Incorrect email or password')
    return {'token':token_for(u),'user':user_dict(u)}

@app.get('/api/me')
def me(authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    return user_dict(current_user(db,authorization))

@app.get('/api/users')
def users(authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization)
    if u.role not in {'admin','staff'}: raise HTTPException(403,'Staff access required')
    return [user_dict(x) for x in db.scalars(select(User).where(User.role.in_(['admin','staff']))).all()]

@app.get('/api/categories')
def categories(db:Session=Depends(get_db)): return [{'id':x.id,'name':x.name,'default_sla_hours':x.default_sla_hours} for x in db.scalars(select(Category).order_by(Category.name)).all()]

@app.post('/api/tickets',status_code=201)
def create_ticket(body:TicketIn,authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization)
    if u.role!='student': raise HTTPException(403,'Only students create tickets in this demo')
    cat=db.get(Category,body.category_id)
    if not cat: raise HTTPException(400,'Invalid category')
    if body.priority not in VALID_PRIORITY: raise HTTPException(400,'Invalid priority')
    now=datetime.now(timezone.utc); ticket_no=f'EDU-{1000 + (db.scalar(select(func.count(Ticket.id))) or 0) + 1}'
    t=Ticket(ticket_no=ticket_no,title=body.title,description=body.description,category_id=cat.id,priority=body.priority,status='Open',student_id=u.id,created_at=now,updated_at=now,due_at=now+timedelta(hours=cat.default_sla_hours))
    db.add(t); db.commit(); db.refresh(t); log(db,t,u,'Ticket created'); db.commit(); return ticket_dict(db,t)

@app.get('/api/tickets')
def tickets(status_filter:Optional[str]=Query(None,alias='status'),priority:Optional[str]=None,q:Optional[str]=None,authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization); stmt=select(Ticket).order_by(Ticket.created_at.desc())
    if u.role=='student': stmt=stmt.where(Ticket.student_id==u.id)
    if status_filter: stmt=stmt.where(Ticket.status==status_filter)
    if priority: stmt=stmt.where(Ticket.priority==priority)
    rows=db.scalars(stmt).all()
    if q: rows=[t for t in rows if q.lower() in (t.title+' '+t.description+' '+t.ticket_no).lower()]
    return [ticket_dict(db,t) for t in rows]

@app.get('/api/tickets/{ticket_id}')
def get_ticket(ticket_id:int,authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization); t=db.get(Ticket,ticket_id)
    if not t or not can_view(u,t): raise HTTPException(404,'Ticket not found')
    return {**ticket_dict(db,t),'activities':activity(db,t.id),'comments':[{'body':c.body,'internal':bool(c.internal),'author':db.get(User,c.author_id).name,'created_at':c.created_at.isoformat()} for c in db.scalars(select(Comment).where(Comment.ticket_id==t.id).order_by(Comment.created_at.asc())).all() if not c.internal or u.role in {'admin','staff'}]}

@app.patch('/api/tickets/{ticket_id}')
def update_ticket(ticket_id:int,body:UpdateTicket,authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization)
    if u.role not in {'admin','staff'}: raise HTTPException(403,'Staff access required')
    t=db.get(Ticket,ticket_id)
    if not t: raise HTTPException(404,'Ticket not found')
    changes=[]
    if body.status:
        if body.status not in VALID_STATUS: raise HTTPException(400,'Invalid status')
        if t.status!=body.status: t.status=body.status; changes.append(f'Status changed to {body.status}')
        if body.status=='Resolved': t.resolved_at=datetime.now(timezone.utc)
    if body.priority:
        if body.priority not in VALID_PRIORITY: raise HTTPException(400,'Invalid priority')
        if t.priority!=body.priority: t.priority=body.priority; changes.append(f'Priority changed to {body.priority}')
    if body.assignee_id is not None:
        a=db.get(User,body.assignee_id)
        if not a or a.role not in {'staff','admin'}: raise HTTPException(400,'Invalid assignee')
        t.assignee_id=a.id; changes.append(f'Assigned to {a.name}')
    t.updated_at=datetime.now(timezone.utc)
    for c in changes: log(db,t,u,c)
    db.commit(); return ticket_dict(db,t)

@app.post('/api/tickets/{ticket_id}/comments')
def comment(ticket_id:int,body:CommentIn,authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization); t=db.get(Ticket,ticket_id)
    if not t or not can_view(u,t): raise HTTPException(404,'Ticket not found')
    if body.internal and u.role not in {'admin','staff'}: raise HTTPException(403,'Internal notes are for staff')
    c=Comment(ticket_id=t.id,author_id=u.id,body=body.body,internal=1 if body.internal else 0); db.add(c); log(db,t,u,'Added internal note' if body.internal else 'Added comment'); db.commit(); return {'ok':True}

@app.get('/api/dashboard')
def dashboard(authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization)
    if u.role not in {'admin','staff'}: raise HTTPException(403,'Staff access required')
    rows=db.scalars(select(Ticket)).all(); counts={s:sum(1 for t in rows if t.status==s) for s in VALID_STATUS}
    overdue=sum(1 for t in rows if ticket_dict(db,t)['sla_breached'])
    open_rows=[t for t in rows if t.status not in {'Resolved','Closed'}]
    avg=None
    resolved=[t for t in rows if t.resolved_at]
    if resolved:
        avg=sum(((t.resolved_at.replace(tzinfo=timezone.utc) if t.resolved_at.tzinfo is None else t.resolved_at)-(t.created_at.replace(tzinfo=timezone.utc) if t.created_at.tzinfo is None else t.created_at)).total_seconds()/3600 for t in resolved)/len(resolved)
    return {'total':len(rows),'counts':counts,'sla_breached':overdue,'avg_resolution_hours':round(avg,1) if avg is not None else None,'unassigned':sum(1 for t in open_rows if not t.assignee_id),'high_priority_open':sum(1 for t in open_rows if t.priority in {'High','Critical'})}

@app.post('/api/tickets/{ticket_id}/close')
def close_ticket(ticket_id:int,authorization:Optional[str]=Header(None),db:Session=Depends(get_db)):
    u=current_user(db,authorization)
    if u.role not in {'admin','staff'}: raise HTTPException(403,'Staff access required')
    t=db.get(Ticket,ticket_id)
    if not t: raise HTTPException(404,'Ticket not found')
    t.status='Closed'; t.updated_at=datetime.now(timezone.utc); log(db,t,u,'Ticket closed'); db.commit(); return ticket_dict(db,t)
