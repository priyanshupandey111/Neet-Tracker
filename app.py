from flask import Flask,render_template,request,redirect,session,url_for,flash
from werkzeug.security import generate_password_hash,check_password_hash
from functools import wraps
from datetime import date,datetime,timedelta
import sqlite3,os,calendar,json,random

app=Flask(__name__); app.secret_key=os.environ.get("SECRET_KEY","change-me")
DB=os.environ.get("DB_PATH","neet_hub.db")
SUBJECTS=["Biology","Physics","Chemistry"]; TYPES=["Study","Revision","MCQ","Test"]
with open(os.path.join(os.path.dirname(__file__),"pyq_data.json"),encoding="utf-8") as f: PYQS=json.load(f)

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
    c=db(); c.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'student',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS studies(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,topic TEXT NOT NULL,subject TEXT NOT NULL,study_type TEXT NOT NULL,study_date TEXT NOT NULL,notes TEXT DEFAULT '',done INTEGER DEFAULT 0,completed_at TEXT,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS pyq_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,test_key TEXT NOT NULL,score INTEGER NOT NULL,total INTEGER NOT NULL,correct INTEGER NOT NULL,wrong INTEGER NOT NULL,answers_json TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS calendar_completions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,completion_date TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(user_id,completion_date),FOREIGN KEY(user_id) REFERENCES users(id));""")
    if not c.execute("SELECT id FROM users WHERE email='teacher@neet.local'").fetchone():
        c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",("Teacher","teacher@neet.local",generate_password_hash("teacher123"),"teacher",datetime.now().isoformat()))
    c.commit(); c.close()
def req(role=None):
    def deco(f):
        @wraps(f)
        def w(*a,**k):
            if "user_id" not in session:return redirect(url_for("login"))
            if role and session["role"]!=role:return redirect(url_for("dashboard"))
            return f(*a,**k)
        return w
    return deco
def streak(rows):
    ds={r["study_date"] for r in rows if r["done"]}; d=date.today()
    if d.isoformat() not in ds:d-=timedelta(days=1)
    n=0
    while d.isoformat() in ds:n+=1; d-=timedelta(days=1)
    return n
def stats(rows):
    return {s:{"total":sum(r["subject"]==s for r in rows),"done":sum(r["subject"]==s and r["done"] for r in rows),"percent":round(sum(r["subject"]==s and r["done"] for r in rows)*100/sum(r["subject"]==s for r in rows)) if sum(r["subject"]==s for r in rows) else 0} for s in SUBJECTS}

def split_pyq_question(text):
    """Split the source question into stem + four numbered options when present."""
    import re
    parts=re.split(r'\s*\((1|2|3|4)\)\s*', text)
    if len(parts) >= 10:
        stem=parts[0].strip()
        opts={}
        for i in range(1, len(parts)-1, 2):
            n=parts[i]
            if n in {"1","2","3","4"}: opts[n]=parts[i+1].strip()
        if len(opts)==4:
            return stem, opts
    return text.strip(), {}

def pyq_filters():
    subject=request.args.get('subject','All'); chapter=request.args.get('chapter','All'); year=request.args.get('year','All'); phase=request.args.get('phase','All')
    rows=PYQS
    if subject!='All': rows=[x for x in rows if x['subject']==subject]
    if chapter!='All': rows=[x for x in rows if x['chapter']==chapter]
    if year!='All': rows=[x for x in rows if str(x['year'])==str(year)]
    if phase!='All': rows=[x for x in rows if x['phase']==phase]
    return rows,subject,chapter,year,phase

@app.route("/")
def home(): return redirect(url_for("dashboard"))
@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower(); pw=request.form["password"]
        if not name or len(pw)<6: flash("Name aur minimum 6 character password required."); return render_template("register.html")
        c=db()
        try:
            x=c.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",(name,email,generate_password_hash(pw),"student",datetime.now().isoformat())); c.commit(); session.update(user_id=x.lastrowid,name=name,role="student"); return redirect(url_for("dashboard"))
        except sqlite3.IntegrityError: flash("Email already registered.")
        finally:c.close()
    return render_template("register.html")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=db(); u=c.execute("SELECT * FROM users WHERE email=?",(request.form["email"].strip().lower(),)).fetchone(); c.close()
        if u and check_password_hash(u["password_hash"],request.form["password"]): session.update(user_id=u["id"],name=u["name"],role=u["role"]); return redirect(url_for("dashboard"))
        flash("Email ya password galat hai.")
    return render_template("login.html")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@req()
def dashboard():
    if session["role"]=="teacher": return redirect(url_for("teacher"))
    c=db(); rows=c.execute("SELECT * FROM studies WHERE user_id=? ORDER BY study_date DESC,id DESC",(session["user_id"],)).fetchall(); c.close(); total=len(rows); done=sum(r["done"] for r in rows); today=date.today().isoformat()
    return render_template("student.html",rows=rows,total=total,done=done,pending=total-done,progress=round(done*100/total) if total else 0,stats=stats(rows),streak=streak(rows),today=today,today_done=sum(r["study_date"]==today and r["done"] for r in rows),today_total=sum(r["study_date"]==today for r in rows))
@app.route("/add",methods=["POST"])
@req("student")
def add():
    c=db(); c.execute("INSERT INTO studies(user_id,topic,subject,study_type,study_date,notes,created_at) VALUES(?,?,?,?,?,?,?)",(session["user_id"],request.form["topic"].strip(),request.form["subject"],request.form["study_type"],request.form["study_date"],request.form.get("notes","").strip(),datetime.now().isoformat())); c.commit(); c.close(); return redirect(url_for("dashboard"))
@app.route("/toggle/<int:i>",methods=["POST"])
@req("student")
def toggle(i):
    c=db(); r=c.execute("SELECT done FROM studies WHERE id=? AND user_id=?",(i,session["user_id"])).fetchone()
    if r:c.execute("UPDATE studies SET done=?,completed_at=? WHERE id=? AND user_id=?",(0 if r["done"] else 1,datetime.now().isoformat() if not r["done"] else None,i,session["user_id"])); c.commit()
    c.close(); return redirect(request.referrer or url_for("dashboard"))
@app.route("/delete/<int:i>",methods=["POST"])
@req("student")
def delete(i):
    c=db(); c.execute("DELETE FROM studies WHERE id=? AND user_id=?",(i,session["user_id"])); c.commit(); c.close(); return redirect(url_for("dashboard"))
@app.route("/calendar")
@req("student")
def cal():
    try:
        y=int(request.args.get("year",date.today().year)); m=int(request.args.get("month",date.today().month))
        if m<1 or m>12: raise ValueError
    except ValueError:
        y,m=date.today().year,date.today().month
    c=db()
    rows=c.execute("SELECT * FROM studies WHERE user_id=? AND substr(study_date,1,7)=? ORDER BY study_date,id",(session["user_id"],f"{y:04d}-{m:02d}")).fetchall()
    done_rows=c.execute("SELECT completion_date FROM calendar_completions WHERE user_id=?",(session["user_id"],)).fetchall()
    c.close()
    by={}
    for r in rows: by.setdefault(int(r["study_date"][8:10]),[]).append(r)
    completed_dates={r["completion_date"] for r in done_rows}
    pm,py=(12,y-1) if m==1 else (m-1,y); nm,ny=(1,y+1) if m==12 else (m+1,y)
    day_labels={d:f"{d} {calendar.month_abbr[m]} {y}" for d in range(1,calendar.monthrange(y,m)[1]+1)}
    quotes=[
        "Bas aaj ka din jeet lo. 🔥","1% better every day.","Consistency > motivation.",
        "NCERT kholo, concept pakdo, question lagao.","Future you will thank you.",
        "Ek aur chapter. Ek aur step. 🚀","Phone kam, focus zyada.","Aaj ka effort kal ka rank hai.",
        "Slow progress bhi progress hai.","Discipline se dream reality banta hai.",
        "Revision karo, confidence badhao.","NEET ko daily chhote steps se crack karo."
    ]
    return render_template("calendar.html",weeks=calendar.monthcalendar(y,m),by=by,completed_dates=completed_dates,quotes=quotes,day_labels=day_labels,month=calendar.month_name[m],month_num=m,year=y,pm=pm,py=py,nm=nm,ny=ny,today=date.today().isoformat(),today_label=date.today().strftime("%d %B %Y"))

@app.route("/calendar/toggle",methods=["POST"])
@req("student")
def toggle_calendar_date():
    target=request.form.get("date","").strip()
    try:
        datetime.strptime(target,"%Y-%m-%d")
    except ValueError:
        return redirect(url_for("cal"))
    c=db(); exists=c.execute("SELECT id FROM calendar_completions WHERE user_id=? AND completion_date=?",(session["user_id"],target)).fetchone()
    if exists:
        c.execute("DELETE FROM calendar_completions WHERE id=?",(exists["id"],))
    else:
        c.execute("INSERT INTO calendar_completions(user_id,completion_date,created_at) VALUES(?,?,?)",(session["user_id"],target,datetime.now().isoformat()))
    c.commit(); c.close()
    return redirect(url_for("cal",year=request.form.get("year",date.today().year),month=request.form.get("month",date.today().month)))

@app.route('/pyq')
@req()
def pyq():
    rows,subject,chapter,year,phase=pyq_filters(); subjects=['All']+SUBJECTS
    chapters=sorted({x['chapter'] for x in PYQS if subject=='All' or x['subject']==subject})
    years=sorted({x['year'] for x in PYQS},reverse=True); phases=sorted({x['phase'] for x in PYQS})
    return render_template('pyq.html',rows=rows,subject=subject,chapter=chapter,year=year,phase=phase,subjects=subjects,chapters=chapters,years=years,phases=phases,total=len(rows))

@app.route('/pyq/test')
@req()
def pyq_test():
    rows,subject,chapter,year,phase=pyq_filters(); count=min(max(int(request.args.get('count',10)),5),50)
    if not rows: return redirect(url_for('pyq'))
    seed=request.args.get('seed')
    if seed is None: seed=str(datetime.now().timestamp())
    rnd=random.Random(seed); chosen=rows if len(rows)<=count else rnd.sample(rows,count)
    key='|'.join(str(x['id']) for x in chosen)
    
    prepared=[]
    for q in chosen:
        item=dict(q)
        item['stem'], item['options']=split_pyq_question(q.get('question',''))
        prepared.append(item)
    return render_template('pyq_test.html',questions=prepared,test_key=key,filters=dict(subject=subject,chapter=chapter,year=year,phase=phase),count=len(prepared))

@app.route('/pyq/submit',methods=['POST'])
@req()
def pyq_submit():
    ids=request.form.get('ids','').split('|'); questions={x['id']:x for x in PYQS}; answers={}; correct=wrong=0
    for qid in ids:
        q=questions.get(qid)
        if not q: continue
        a=request.form.get('q_'+qid,'')
        answers[qid]=a
        if a:
            if a==q['answer']: correct+=1
            else: wrong+=1
    total=len(ids); score=correct*4-wrong
    c=db(); c.execute('INSERT INTO pyq_attempts(user_id,test_key,score,total,correct,wrong,answers_json,created_at) VALUES(?,?,?,?,?,?,?,?)',(session['user_id'],request.form.get('test_key',''),score,total,correct,wrong,json.dumps(answers),datetime.now().isoformat())); c.commit(); c.close()
    result=[dict(q,selected=answers.get(q['id'],''),is_correct=answers.get(q['id'])==q['answer']) for qid in ids if (q:=questions.get(qid))]
    return render_template('pyq_result.html',questions=result,score=score,total=total,correct=correct,wrong=wrong,unattempted=total-correct-wrong)

@app.route('/teacher')
@req('teacher')
def teacher():
    c=db(); ss=c.execute("SELECT * FROM users WHERE role='student' ORDER BY name").fetchall(); data=[]
    for s in ss:
        r=c.execute("SELECT * FROM studies WHERE user_id=?",(s["id"],)).fetchall(); t=len(r); d=sum(x["done"] for x in r); data.append({"id":s["id"],"name":s["name"],"email":s["email"],"total":t,"done":d,"percent":round(d*100/t) if t else 0,"streak":streak(r)})
    c.close(); T=sum(x["total"] for x in data); D=sum(x["done"] for x in data); return render_template("teacher.html",students=data,total_students=len(data),total=T,done=D,overall=round(D*100/T) if T else 0)
@app.route("/teacher/student/<int:i>")
@req("teacher")
def student(i):
    c=db(); s=c.execute("SELECT * FROM users WHERE id=? AND role='student'",(i,)).fetchone(); r=c.execute("SELECT * FROM studies WHERE user_id=? ORDER BY study_date DESC,id DESC",(i,)).fetchall(); c.close()
    if not s:return redirect(url_for("teacher"))
    d=sum(x["done"] for x in r); return render_template("student_detail.html",student=s,rows=r,total=len(r),done=d,progress=round(d*100/len(r)) if r else 0,streak=streak(r),stats=stats(r))

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=True)
