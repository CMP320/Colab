from dataclasses import dataclass
from flask import render_template, Flask, request, redirect, url_for, make_response
from hashlib import md5, sha256
import cx_Oracle
from os import urandom
from datetime import datetime as dt

sessions = {}

app = Flask(__name__)

def getType(ck):
    global sessions
    if 'sessionID' not in ck.keys():
        return -1
    if ck['sessionID'] not in sessions.keys():
        return -1
    return sessions[ck['sessionID']].type

@dataclass()
class Employee:
    name : str
    username : str
    type : str

@dataclass()
class Task:
    id : int
    deadline : dt
    importance : int
    description : str
    assignedto : str
    progress : int

@app.route('/',methods=['GET','POST'])
@app.route('/login', methods=['GET','POST'])
def login():
    global sessions
    if request.method == 'GET':
        if 'sessionID' in request.cookies:
            s = request.cookies['sessionID']
            if s in sessions:
                return redirect(url_for('dashboard'))
            else: # invalid sessionID cookie
                resp = make_response(render_template("login.html"))
                resp.set_cookie('sessionID', '', expires=0)
                return resp
        else:
            return render_template("login.html")
    # else: request.method=='POST'
    user = request.form['user']
    pwd = md5(request.form['pass'].encode()).hexdigest()
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"select name, username, type from plogin where username='{user}' and password='{pwd}'")
    res = [row for row in res]
    # print(res)
    if len(res) > 0:
        emp = Employee(*res[0])
        sessID = sha256(emp.username.encode() + urandom(16)).hexdigest()
        sessions[sessID] = emp
        # print(sessions)
        resp = redirect(url_for('dashboard'))
        resp.set_cookie('sessionID', sessID)
        return resp
    else:
        return 'pls no hax'

@app.route("/logout", methods = ['GET'])
def logout():
    global sessions
    if 'sessionID' in request.cookies:
            s = request.cookies['sessionID']
            if s in sessions:
                sessions.pop(s)
    resp = redirect(url_for('login'))
    resp.set_cookie('sessionID', '', expires=0)
    return resp

@app.route('/dashboard')
def dashboard():
    global sessions
    if 'sessionID' in request.cookies:
        s = request.cookies['sessionID']
        if s in sessions:
            emp = sessions[s]
        else: # invalid sessionID cookie
            resp = redirect(url_for('login'))
            resp.set_cookie('sessionID', '', expires=0)
            return resp
    else:
        return redirect(url_for('login'))
    if emp.type == 'admin':
        print('admin')
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"select * from ptask")
        tasks = [Task(*task) for task in list(res)]
        return render_template('admin_dashboard.html', user=emp, tasks=tasks)
    if emp.type == 'teamleader':
        print('team leader')
        return render_template('dashboard.html', user=emp)
    if emp.type == 'normal':
        # print('normal')
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"select taskid, deadline, importance, descr, assignedto, progress from ptask where assignedto = '{emp.username}'")
        tasks = [Task(*r) for r in list(res)]
        assignedTasks = [t for t in tasks if t.progress==0]
        inprogTasks = [t for t in tasks if t.progress==1]
        complTasks = [t for t in tasks if t.progress==2]
        # print(tasks)
        cur = connection.cursor()
        res = cur.execute(f"select name from pemployee where username in (select username from pnormal where teamID = (select teamID from pnormal where username='{emp.username}'))")
        members = [r[0] for r in res]
        cur = connection.cursor()
        res = cur.execute(f"select teamID from pnormal where username = '{emp.username}'")
        teamID = int(list(res)[0][0])
        cur = connection.cursor()
        res = cur.execute(f"select name from pemployee where username = (select username from pteamleader where teamID={teamID})")
        leader= list(res)[0][0]
        return render_template('normal_dashboard.html', user=emp, assignedTasks=assignedTasks, inprogTasks=inprogTasks, complTasks=complTasks, teamID=teamID, members=members, leader=leader)

    else:
        assert False



@app.route("/startCompleteTask", methods = ['POST'])
def startCompleteTask():
    global sessions
    if getType(request.cookies) != "normal":
        return redirect(url_for('index'))
    
    username = sessions[request.cookies['sessionID']].username
    #print(request.json)
    taskID = int(request.json['taskID'])
    currProg = int(request.json['currProg'])
    newProg = 1 if currProg == 0 else 2
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"update ptask set progress = {newProg} where assignedto='{username}' and taskID = {taskID}")
    connection.commit()
    return 'success'
