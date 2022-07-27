from flask import Flask, render_template, session, request, url_for, redirect, Response,g
from proj_constants import MONGO_HOST_URL, MONGO_USER_PWD, MONGO_USER_NAME, MONGO_DATABASE_NAME, salt
from mailer import send_email_verification_mail
from flask.helpers import make_response
from flask.json import jsonify
from bson import ObjectId
import pymongo
import hashlib
import json


client = pymongo.MongoClient(MONGO_HOST_URL, username=MONGO_USER_NAME, password=MONGO_USER_PWD)     
db = client[MONGO_DATABASE_NAME]
users = db["users"]
tasks = db["tasks"]
auth_users_col = db['auth_user']
verify_usr_eml_col = db['verify_usr_eml']
app = Flask(__name__)
app.secret_key = "usadassdsds"


def string_hash(text):
    return hashlib.sha256(salt.encode() + text.encode()).hexdigest() + ':' + salt

def register_auth_user(user_name, user_firstname, user_lastname, user_password, user_email):

    

    auth_users_col = db['auth_user']
    if auth_users_col.count_documents({'email': user_email}):
        print(f'User with email {user_email} is already created.')
        return False


    new_user_data = {'username': user_name,'firstname': user_firstname, 'lastname': user_lastname, 'email': user_email, 'password': user_password,
                    'is_activated': 'False'}
    ins = auth_users_col.insert_one(new_user_data)

    key, pkey = string_hash(user_email).split(':')

    verification_data = {
        'email': user_email,
        'key': key
    }
    verify_usr_eml_col = db['verify_usr_eml']
    ins = verify_usr_eml_col.insert_one(verification_data)
    client.close()
    link = request.host_url + f'verify/{key}'
    send_email_verification_mail(user_email, user_firstname, link)
    return ins.acknowledged


def check_auth_login(user_email, user_password):
    
    

    auth_users_col = db['auth_user']
    search_data = {'email': user_email, 'password': user_password}

    res = auth_users_col.count_documents(search_data)
    is_activated = auth_users_col.find_one({'email': user_email}, {'is_activated': 1, '_id': 0})

    if is_activated is None:
        return False
    is_activated = is_activated.get('is_activated')
    client.close()

    if res == 1 and is_activated == 'True':
        return True
    else:
        return False



def verify_usr_eml(key):
  
    search_data = {
        'key': key,
    }
    

    verify_usr_eml_col = db['verify_usr_eml']
    auth_user_col = db['auth_user']
    res = verify_usr_eml_col.count_documents(search_data)
    if res == 1:
        user_email = verify_usr_eml_col.find_one(search_data, {'_id': 0, 'email': 1}).get('email')
        user_search_data = {
            'email': user_email
        }
        new_data = {
            'is_activated': 'True'
        }
        auth_user_col.update_one(user_search_data, {"$set": new_data})

        verify_usr_eml_col.delete_one(search_data)
        return f'User verification for {user_email} successful!!'
    else:
        return f'User verification failed!!'


def getUserStats():
    active_tasks = tasks.count_documents(
        {'user': session['email'], 'status': 1})
    completed_tasks = tasks.count_documents(
        {'user': session['email'], 'status': 0})
    try:
        percent = int((completed_tasks/(active_tasks + completed_tasks))*100)
    except ZeroDivisionError:
        percent = 0

    user_stats = {
        'email': session['email'],
        'name': auth_users_col.find_one({'email': session['email']})['username'],
        'completed': completed_tasks,
        'rem_tasks': active_tasks,
        'percent': percent
    }
    return user_stats


class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return json.JSONEncoder.default(self, o)




@app. route("/signup", methods=["POST", "GET"])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')
    elif request.method == "POST":
        if register_auth_user (user_name = request.form["usrname"],
            user_email = request.form["email"],
            user_firstname = request.form["firstnme"],
            user_lastname = request.form["lastnme"],
            user_password = request.form["passwd"]):

        
            return render_template("login.html", title="Sign in", message="Register Successfull, Check Your email to verify your account ")
        else:
            return render_template("signup.html", title="Sign up", message="Account Already Exist, Please Try with different Email ")




@app. route("/login", methods=["POST", "GET"])
def login():
 
    if request.method == "POST":
        user_email = request.form["email"]
        user_password = request.form["passwd"]
        x = auth_users_col.find_one({'email': user_email})
        if x is not None:
            if x ['password'] == user_password:
                session["email"] = user_email
                return redirect(url_for("home"))
            else:
                return render_template("login.html", title="Sign in", message="Wrong Password")
        else:
            return render_template("login.html", title="Sign in", message="Invalid email id")

    else:
        return render_template("login.html", title="Sign in", message="")




@app.route('/verify/<string:key>', methods=['GET'])
def verify(key):
    resp = verify_usr_eml(key)
    return Response(f'<script type="text/javascript"> alert("{resp}") </script>')



@app. route("/logout", methods=["GET"])
def logout():
    session.pop('email', None)
    return redirect(url_for("home"))



@app.route("/updatePassword", methods=["POST"])
def updatePassword():
    msg = ""
    x = auth_users_col.find_one({'email': session['email']})
    user_password = request.form["oldpasswd"]
    if x['password'] == user_password:
        new_password = request.form["newpasswd"]
        auth_users_col.update_one({'email': session['email']}, {
                         '$set': {'password': new_password}})
        msg = "Updated password successfully"
    else:
        msg = "Wrong password"

    return render_template("profile.html", title="User profile", message=msg, user=getUserStats())



@app.route("/deleteAccount", methods=["POST"])
def deleteUser():
    user_password = request.form["passwd"]
    x = auth_users_col.find_one({'email': session['email']})
    if x['password'] == user_password:
        auth_users_col.delete_one({'email': session['email']})
        tasks.delete_many({'email': session['email']})
        return redirect(url_for("logout"))
    else:
        msg = "Wrong password. Account deletion failed."
        return render_template("profile.html", title="User profile", message=msg, user=getUserStats())



@app.route("/markCompleted", methods=['POST'])
def markCompleted():
    t = request.get_json()
    print(t)
    tasks.update_one({'_id': ObjectId(t['id'])}, {'$set': {'status': 0}})
    return '200'



@app.route("/markAllCompleted", methods=['POST'])
def markAllCompleted():
    tasks.update_many({'user': session['email']}, {'$set': {'status': 0}})
    return '200'


@app.route("/markIncomplete")
def markAllIncomplete():
    tasks.update_many({'user': session['email']}, {'$set': {'status': 1}})
    return '200'



@app.route("/addTask", methods=['POST'])
def addTask():
    t = request.get_json()
    new_task = {
        'content': t['task'],
        'status': 1,
        'user': session['email']
    }
    x = tasks.insert_one(new_task)
    res = make_response(jsonify({'id': str(x.inserted_id)}), 200)
    return res



@app.route("/completed")
def getCompletedTasks():
    usr_inactive_tasks = tasks.find({'user': session['email'], 'status': 0})
    return render_template("finished.html", title="Compeleted tasks", tasks=usr_inactive_tasks)



@app.route("/deleteCompleted")
def deleteCompletedTasks():
    tasks.delete_many({'user': session['email'], 'status': 0})
    return '200'



@app.route("/about")
def about():
    return render_template("about.html", title="About")



@app.route("/profile")
def displayProfile():
    return render_template("profile.html", title="User profile", message="", user=getUserStats())



@app.route('/')
def home():
    if "email" in session:
        usrname = auth_users_col.find_one({'email': session['email']})['username']
        usr_tasks = tasks.find({'user': session['email']})
        usr_active_tasks = []
        for x in usr_tasks:
            if x['status'] == 1:
                usr_active_tasks.append(x)
        return render_template("index.html", title="My home", user=usrname, tasks=usr_active_tasks)
    else:
        return redirect(url_for("login"))



@app.route('/forgotPassword')
def forgotPassword():
    return render_template('forgotPassword.html')




@app.route('/forgotPasswordAction',methods=['post'])
def forgotPasswordAction():
    msg=""
    user_email = request.form["email"]
    x = auth_users_col.find_one({'email': user_email})
    if x is not None:
        if x['email'] == user_email:
            return render_template('forgotp.html')
    else:
        msg = "Wrong Email Address "
        return render_template("forgotPassword.html", title="User profile", message=msg)
    


@app.route('/forgotpAction',methods=['post'])
def forgotpAction():
    msg = ""
    user_username = request.form["usrname"]
    x = auth_users_col.find_one({'username': user_username})
    if x is not None:
        if x['username'] == user_username:
            new_password = request.form["newpasswd"]
            auth_users_col.update_one({'username': user_username}, {
                            '$set': {'password': new_password}})
            
            msg = "Updated password successfully"
            return render_template("login.html", title="User profile", message=msg)

    else:
        msg = "Wrong username"
        return render_template("forgotp.html", title="User profile", message=msg)



@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404




if __name__ == '__main__':
    app.run(debug=True)