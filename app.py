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
    hiredate : str = ''
    sal : float = 0.0

@dataclass()
class Task:
    id : int
    deadline : dt
    importance : int
    description : str
    assignedto : str
    progress : int
    normal_users : list = None
    team_name : str = ""

@dataclass()
class Team:
    name: str
    leader: str
    normal_users: list = None

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
        # print('admin')
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute("select * from ptask")
        tasks = [Task(*task) for task in list(res)]
        for task in tasks:
            res = cur.execute(f"select teamid from (SELECT TEAMID, PLOGIN.USERNAME u FROM PLOGIN, PNORMAL WHERE PLOGIN.USERNAME = PNORMAL.USERNAME) where u = '{task.assignedto}'")
            teamid = list(res)[0][0]
            res = cur.execute(f"select teamname from pteam where teamid={teamid}")
            task.team_name = list(res)[0][0]
            res = cur.execute(f"select u from (SELECT TEAMID, PLOGIN.USERNAME u FROM PLOGIN, PNORMAL WHERE PLOGIN.USERNAME = PNORMAL.USERNAME) where teamid = {teamid}")
            task.normal_users = [user[0] for user in list(res)]
        res = cur.execute("select * from pteam")
        teams = {teamid: teamname for teamid, teamname in list(res)}
        teamsfullinfo = [Team(teams[teamid], getLeader(teamid), getNormal(teamid)) for teamid in teams]
        # print(teamsfullinfo)
        res = cur.execute("select name, username, 'Admin' as type, hiredate, salary from pemployee where username in (select username from plogin where type='admin')")
        admin = [Employee(*a) for a in list(res)]
        return render_template('admin_dashboard.html', user=emp, tasks=tasks, task_teams={t.team_name for t in tasks}, teams=teamsfullinfo, admin=admin)

    if emp.type == 'teamleader':
        # print('team leader')
        team = []
        for re in list(leader_team_dashboard(emp)):
            team.append(Employee(*re))
        print(team)
        
        task = []
        for re in list(leader_task_dashboard(emp)):
            task.append(Task(*re))

        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"select teamname from pteam where teamID = (select teamID from pteamleader where username = '{emp.username}')")
        teamName = list(res)[0][0]

        return render_template('leader_dashboard.html', res=team, tasks=task, user=emp, teamName = teamName)
        
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

        cur = connection.cursor()
        res = cur.execute(f"select teamname from pteam where teamID = {teamID}")
        teamName = list(res)[0][0]

        return render_template('normal_dashboard.html', user=emp, assignedTasks=assignedTasks, inprogTasks=inprogTasks, complTasks=complTasks, teamID=teamID, members=members, leader=leader, teamName=teamName)

    else:
        assert False

@app.route("/updateTask", methods = ['POST'])
def updateTask():
    taskID = int(request.json['taskID'])
    deadline = request.json['deadline']
    descr = request.json['description']
    imp = int(request.json['importance'])
    assignedto = request.json['assignedto']
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"update ptask set assignedTo = '{assignedto}', deadline = TO_DATE('{deadline}', 'dd MONTH, yyyy'), importance = {imp}, descr = '{descr}'  where taskID = {taskID}")
    connection.commit()
    return 'success'


@app.route("/addTask", methods = ['POST'])
def addTask():
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"select max(taskID) from ptask")

    taskID = int(list(res)[0][0]) + 1
    deadline = request.json['deadline']
    descr = request.json['descr']
    imp = int(request.json['imp'])
    assignedto = request.json['assignto']
    cur = connection.cursor()
    res = cur.execute(f"insert into ptask values ({taskID}, TO_DATE('{deadline}', 'dd MONTH, yyyy'), {imp}, '{descr}', '{assignedto}', 0)")
    connection.commit()
    return 'success'


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

def leader_team_dashboard(emp):
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()

    return cur.execute(f"SELECT * FROM PEMPLOYEE WHERE PEMPLOYEE.USERNAME IN (SELECT PNORMAL.USERNAME FROM PNORMAL WHERE PNORMAL.TEAMID = (SELECT PTEAMLEADER.TEAMID FROM PTEAMLEADER WHERE PTEAMLEADER.USERNAME = '{emp.username}'))")

def leader_task_dashboard(emp):
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()

    return cur.execute(f"SELECT TASKID, DEADLINE, IMPORTANCE, DESCR, USERNAME, PROGRESS FROM PTASK, PNORMAL WHERE PTASK.ASSIGNEDTO = PNORMAL.USERNAME AND PNORMAL.TEAMID = (SELECT PTEAMLEADER.TEAMID FROM PTEAMLEADER WHERE PTEAMLEADER.USERNAME = '{emp.username}')")
    
def getLeader(teamid):
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"select name, username, 'Team Leader' as type, hiredate, salary from pemployee where username = (select username from pteamleader where teamid={teamid})")
    return Employee(*list(res)[0])

def getNormal(teamid):
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"select name, username, 'Normal' as type, hiredate, salary from pemployee where username in (select username from pnormal where teamid={teamid})")
    return [Employee(*emp) for emp in list(res)]
