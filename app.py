from dataclasses import dataclass
from flask import render_template, Flask, request, redirect, url_for, make_response
from hashlib import md5, sha256
import cx_Oracle
from os import urandom
from datetime import datetime as dt

sessions = {}

app = Flask(__name__)

def validate(inp, typ, lmin=-1, lmax=-1):
    if lmin!= -1 and lmax!=-1:
        if len(inp) < lmin or len(inp) > lmax:
            raise Exception('Input length error')
    
    if typ == dt:
        try:
            inp = dt.strptime(inp,'%d %B, %Y')
        except:
            raise Exception('Invalid date format')
    else:
        inp = typ(inp)

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
    overtime_bonus: float = -1

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
    teamid: int = -1

@dataclass()
class Team:
    name: str
    leader: str
    normal_users: list = None
    id : int = -1

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
        res = cur.execute("select * from ptask where assignedTo is not null")
        tasks = [Task(*task) for task in list(res)]
        for task in tasks:
            res = cur.execute(f"select teamid from (SELECT TEAMID, PLOGIN.USERNAME u FROM PLOGIN, PNORMAL WHERE PLOGIN.USERNAME = PNORMAL.USERNAME) where u = '{task.assignedto}'")
            teamid = int(list(res)[0][0])
            task.teamid =teamid
            res = cur.execute(f"select teamname from pteam where teamid={teamid}")
            task.team_name = list(res)[0][0]
            res = cur.execute(f"select u from (SELECT TEAMID, PLOGIN.USERNAME u FROM PLOGIN, PNORMAL WHERE PLOGIN.USERNAME = PNORMAL.USERNAME) where teamid = {teamid}")
            task.normal_users = [user[0] for user in list(res)]
        res = cur.execute("select * from pteam")
        teams = {teamid: teamname for teamid, teamname in list(res)}
        teamsfullinfo = [Team(teams[teamid], getLeader(teamid), getNormal(teamid), teamid) for teamid in teams]
        # print(teamsfullinfo)
        taskstat = {}
        res=cur.execute("select teamid, progress, count(*) from ptask, pnormal where assignedto is not null and ptask.assignedto=pnormal.username group by progress, teamid order by teamid, progress")
        res = list(res)
        for tid in teams.keys():
            taskstat[tid] = [0,0,0]
        for r in res:
            taskstat[r[0]][r[1]]=r[2]
        stats = {"ts": taskstat}
        print(stats)
        maxcompl = [tid for tid,tsk in taskstat.items() if tsk[2] == max(t[2] for t in taskstat.values())][0]
        maxprog = [tid for tid,tsk in taskstat.items() if tsk[1] == max(t[1] for t in taskstat.values())][0]
        maxcomplrat = [tid for tid,tsk in taskstat.items() if sum(tsk) !=0 and tsk[2]/sum(tsk) == max(t[2]/sum(t) for t in taskstat.values() if sum(t) !=0)][0]
        stats["maxcompl"] = maxcompl
        stats["maxprog"] = maxprog
        stats["maxcomplrat"] = maxcomplrat
        print(stats)
        res = cur.execute("select name, username, 'Admin' as type, hiredate, salary from pemployee where username in (select username from plogin where type='admin')")
        admin = [Employee(*a) for a in list(res)]
        res = cur.execute(f"select username,salary+120*overtime as total from pemployee natural join pnormal")
        total_sal = {r[0] : r[1] for r in list(res)}
        res = cur.execute(f"select username,salary+bonus as total from pemployee natural join pteamleader")
        total_sal.update({r[0] : r[1] for r in list(res)})
        res = cur.execute(f"select sum(salary+120*overtime) as total from pemployee natural join pnormal")
        total_sal["total_normal_sal"] = float(list(res)[0][0])
        res = cur.execute(f"select sum(salary+bonus) as total from pemployee natural join pteamleader")
        total_sal["total_leader_sal"] = float(list(res)[0][0])
        return render_template('admin_dashboard.html', user=emp, tasks=tasks, task_teams={t.team_name for t in tasks}, teams=teamsfullinfo, admin=admin, stats=stats, total_sal=total_sal)

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
    try:
        taskID = int(request.json['taskID'])
        deadline = request.json['deadline']
        validate(deadline, dt)
        descr = request.json['description']
        validate(descr, str, 1, 200)
        imp = int(request.json['importance'])
        validate(imp, int)
        assignedto = request.json['assignedto']
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"update ptask set assignedTo = '{assignedto}', deadline = TO_DATE('{deadline}', 'dd MONTH, yyyy'), importance = {imp}, descr = '{descr}'  where taskID = {taskID}")
        connection.commit()
        return 'success'
    except Exception as e:
        return str(e)

@app.route("/addTask", methods = ['POST'])
def addTask():
    try:
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"select max(taskID) from ptask")

        taskID = int(list(res)[0][0]) + 1
        deadline = request.json['deadline']
        validate(deadline, dt)
        descr = request.json['descr']
        validate(descr, str, 1, 200)
        imp = int(request.json['imp'])
        validate(imp, int)
        assignedto = request.json['assignto']
        cur = connection.cursor()
        res = cur.execute(f"insert into ptask values ({taskID}, TO_DATE('{deadline}', 'dd MONTH, yyyy'), {imp}, '{descr}', '{assignedto}', 0)")
        connection.commit()
        return 'success'
    except Exception as e:
        return str(e)


@app.route("/addTeam", methods = ['POST'])
def addTeam():
    try:
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"select max(teamID) from pteam")

        teamID = int(list(res)[0][0]) + 1
        teamname = request.json['tname']
        validate(teamname, str, 1, 50)
        cur = connection.cursor()
        res = cur.execute(f"insert into pteam values ({teamID}, '{teamname}')")
        connection.commit()
        return 'success'
    except Exception as e:
        return str(e)

@app.route("/startCompleteTask", methods = ['POST'])
def startCompleteTask():
    global sessions
    if getType(request.cookies) != "normal":
        return redirect(url_for('login'))
    
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

@app.route("/updateTeamName", methods = ['POST'])
def updateTeamName():
    try:
        global sessions
        if getType(request.cookies) != "admin":
            return redirect(url_for('login'))
        teamid = request.json['teamid']
        teamname = request.json['teamname']
        validate(teamname, str, 1, 50)
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        res = cur.execute(f"update pteam set teamname='{teamname}' where teamid={teamid}")
        connection.commit()
        return 'success'
    except Exception as e:
        return str(e)

@app.route("/updateEmployee", methods = ['POST'])
def updateEmployee():
    try:
        global sessions
        if getType(request.cookies) != "admin":
            return redirect(url_for('login'))
        username = request.json['username']
        validate(username, str, 1, 50)
        name = request.json['name']
        validate(name, str, 1, 50)
        password = md5(request.json['password'].encode()).hexdigest()
        hiredate = request.json['hiredate']
        validate(hiredate, dt)
        salary = float(request.json['salary'])
        validate(salary, float)
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        if request.json['password'] != '':
            res = cur.execute(f"update pemployee set name='{name}', password='{password}', hiredate=TO_DATE('{hiredate}','dd MONTH, yyyy'), salary={salary} where username='{username}'")
        else:
            res = cur.execute(f"update pemployee set name='{name}', hiredate=TO_DATE('{hiredate}','dd MONTH, yyyy'), salary={salary} where username='{username}'")
        connection.commit()
        return 'success'
    except Exception as e:
        return str(e)

@app.route("/deleteEmployee", methods = ['POST'])
def deleteEmployee():
    global sessions
    if getType(request.cookies) != "admin":
        return redirect(url_for('login'))
    username = request.json['username']
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    tp = request.json["type"].lstrip().rstrip()
    if tp == "Normal":
        res = cur.execute(f"update ptask set assignedto = null where assignedto='{username}'")
        res = cur.execute(f"delete from pnormal where username='{username}'")
    elif tp == "Team Leader":
        res = cur.execute(f"delete from pteamleader where username='{username}'")
    res = cur.execute(f"delete from pemployee where username = '{username}'")
    connection.commit()
    return 'success'

@app.route("/addEmployee", methods = ['POST'])
def addEmployee():
    try:
        global sessions
        if getType(request.cookies) != "admin":
            return redirect(url_for('login'))
    # bonus: ""
    # hiredate: "bzdf"
    # name: "svz"
    # overtime: ""
    # password: "bxzb"
    # salary: "bzf"
    # team: "0"
    # type: "admin"
    # username: "bhzfhzd"
        username = request.json['username']
        validate(username, str, 1, 50)
        name = request.json['name']
        validate(name, str, 1, 50)
        password = md5(request.json['password'].encode()).hexdigest()
        hiredate = request.json['hiredate']
        validate(hiredate, dt)
        salary = float(request.json['salary'])
        validate(salary, float)
        tp = request.json['type']
        connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
        cur = connection.cursor()
        if request.json['password'] != '':
            res = cur.execute(f"insert into pemployee values('{name}', '{username}', '{password}', TO_DATE('{hiredate}','dd MONTH, yyyy'), {salary})")
        else:
            return "failure", 406
        if tp == "normal":
            teamid = request.json['team']
            overtime = float(request.json['overtime'])
            validate(overtime, float)
            res = cur.execute(f"insert into pnormal values('{username}', {overtime}, {teamid})")
        elif tp == "teamleader":
            teamid = request.json['team']
            bonus = int(request.json['bonus'])
            validate(bonus, int)
            res = cur.execute(f"insert into pteamleader values('{username}', {bonus}, {teamid})")
        connection.commit()
        return 'success'
    except Exception as e:
        return str(e)


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
    res = cur.execute(f"select name, pemployee.username, 'Team Leader' as type, hiredate, salary, bonus from pemployee, pteamleader where pemployee.username = pteamleader.username and pteamleader.teamid={teamid}")
    res = list(res)
    return Employee(*(res)[0]) if res else None

def getNormal(teamid):
    connection = cx_Oracle.connect("b00080205/b00080205@coeoracle.aus.edu:1521/orcl")
    cur = connection.cursor()
    res = cur.execute(f"select name, pemployee.username, 'Normal' as type, hiredate, salary, overtime from pemployee, pnormal where pemployee.username = pnormal.username and pnormal.teamid={teamid}")
    return [Employee(*emp) for emp in list(res)]
