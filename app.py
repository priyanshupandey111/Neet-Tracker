from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3, os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
DB = os.path.join(os.path.dirname(__file__), "neet.db")

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'student'
    );
    CREATE TABLE IF NOT EXISTS studies(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      topic TEXT NOT NULL,
      subject TEXT NOT NULL,
      study_type TEXT NOT NULL,
      study_date TEXT NOT NULL,
      done INTEGER DEFAULT 0,
      FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)
    if not c.execute("SELECT 1 FROM users WHERE email=?", ("teacher@neet.local",)).fetchone():
        c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)",
                  ("Teacher","teacher@neet.local","teacher123","teacher"))
    c.commit(); c.close()

def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapped(*a,**kw):
            if "user_id" not in session: return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("dashboard"))
            return fn(*a,**kw)
        return wrapped
    return deco

@app.route("/")
def home():
    return redirect(url_for("dashboard")) if "user_id" in session else redirect(url_for("login"))

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form["name"].strip(); email=request.form["email"].strip().lower(); password=request.form["password"]
        if not name or not email or len(password)<4:
            flash("Name, email aur 4+ character password required.")
        else:
            c=db()
            try:
                cur=c.execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",(name,email,password))
                c.commit(); uid=cur.lastrowid
                session.update(user_id=uid,name=name,role="student")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError: flash("Ye email already registered hai.")
            finally: c.close()
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form["email"].strip().lower(); password=request.form["password"]
        c=db(); u=c.execute("SELECT * FROM users WHERE email=? AND password=?",(email,password)).fetchone(); c.close()
        if u:
            session.update(user_id=u["id"],name=u["name"],role=u["role"])
            return redirect(url_for("dashboard"))
        flash("Email ya password galat hai.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@login_required()
def dashboard():
    c=db()
    if session["role"]=="teacher":
        students=c.execute("SELECT * FROM users WHERE role='student' ORDER BY name").fetchall()
        rows=[]
        for s in students:
            total=c.execute("SELECT COUNT(*) n FROM studies WHERE user_id=?",(s["id"],)).fetchone()["n"]
            done=c.execute("SELECT COUNT(*) n FROM studies WHERE user_id=? AND done=1",(s["id"],)).fetchone()["n"]
            rows.append({"id":s["id"],"name":s["name"],"email":s["email"],"total":total,"done":done,
                         "percent":round(done*100/total) if total else 0})
        c.close(); return render_template("teacher.html",students=rows)
    studies=c.execute("SELECT * FROM studies WHERE user_id=? ORDER BY study_date,id",(session["user_id"],)).fetchall()
    total=len(studies); done=sum(x["done"] for x in studies)
    c.close()
    return render_template("student.html",studies=studies,total=total,done=done,percent=round(done*100/total) if total else 0)

@app.route("/add", methods=["POST"])
@login_required("student")
def add():
    c=db()
    c.execute("INSERT INTO studies(user_id,topic,subject,study_type,study_date) VALUES(?,?,?,?,?)",
              (session["user_id"],request.form["topic"],request.form["subject"],request.form["study_type"],request.form["study_date"]))
    c.commit(); c.close(); return redirect(url_for("dashboard"))

@app.route("/toggle/<int:sid>", methods=["POST"])
@login_required("student")
def toggle(sid):
    c=db()
    c.execute("UPDATE studies SET done=1-done WHERE id=? AND user_id=?",(sid,session["user_id"]))
    c.commit(); c.close(); return redirect(url_for("dashboard"))

@app.route("/delete/<int:sid>", methods=["POST"])
@login_required("student")
def delete(sid):
    c=db(); c.execute("DELETE FROM studies WHERE id=? AND user_id=?",(sid,session["user_id"])); c.commit(); c.close()
    return redirect(url_for("dashboard"))

@app.route("/student/<int:uid>")
@login_required("teacher")
def student_detail(uid):
    c=db()
    s=c.execute("SELECT * FROM users WHERE id=? AND role='student'",(uid,)).fetchone()
    studies=c.execute("SELECT * FROM studies WHERE user_id=? ORDER BY study_date,id",(uid,)).fetchall()
    c.close()
    if not s: return redirect(url_for("dashboard"))
    total=len(studies); done=sum(x["done"] for x in studies)
    return render_template("student_detail.html",student=s,studies=studies,percent=round(done*100/total) if total else 0)

init_db()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
