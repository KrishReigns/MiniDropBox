import datetime

from flask import Flask, request, send_file, render_template, session, redirect
import pymysql as pymysql
import os
import random
conn = pymysql.connect(host="localhost", user="root", password="password", db="MiniDropbox")
cursor = conn.cursor()

app = Flask(__name__)
app.secret_key = "kjjirfg"

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = APP_ROOT+'/static'

video_formats = [".mp4"]
audio_formats = [".mp3"]
image_formats = [".png", ".jpg", ".jpeg"]
pdf_formats = [".pdf"]


import boto3 as boto3
#keys sec and acc removed
User_bucket = "userminidropbox"
User_Email_Source = 'krishna1996sai@gmail.com'
User_S3_Client = boto3.client('s3', aws_access_key_id=User_Access_Key, aws_secret_access_key=User_Secret_Access_Key)
User_SES_Client = boto3.client('ses', aws_access_key_id=User_Access_Key, aws_secret_access_key=User_Secret_Access_Key, region_name='us-east-1')

# conn = pymysql.connect(host="database-1.cd2o0ic6s8pg.us-east-1.rds.amazonaws.com", user="admin", password="adminroot", db="Train_Booking_System")
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/user_login", methods=['post'])
def user_login():
    email = request.form.get("email")
    password = request.form.get("password")
    count = cursor.execute(
        "select * from users where email = '" + str(email) + "' and password = '" + str(password) + "'")
    users = cursor.fetchall()
    if count > 0:
        name = users[0][1]
        try:
            emails = User_SES_Client.list_identities(
                IdentityType='EmailAddress'
            )
            if email in emails['Identities']:
                email_msg = 'Hello ' + name + ' You Have Successfully Logged into Website'
                User_SES_Client.send_email(Source=User_Email_Source,
                                                            Destination={'ToAddresses': [email]},
                                                            Message={
                                                                'Subject': {'Data': email_msg, 'Charset': 'utf-8'},
                                                                'Body': {'Html': {'Data': email_msg,
                                                                                  'Charset': 'utf-8'}}})
            user = users[0]
            session["user_id"] = user[0]
            session["role"] = 'user'
            return render_template("user_home.html", user=user)
        except Exception as e:
            return render_template("index.html", message="Verify yourself click on the link that have recivied on your mail and then login.")
    else:
        return render_template("index.html", message="Login Failed")


@app.route("/user_home")
def user_home():
    user_id = session['user_id']
    cursor.execute("select * from users where user_id='"+str(user_id)+"'")
    users = cursor.fetchall()
    return render_template("user_home.html", user=users[0])


# @app.route("/user_verify")
# def user_verify():
#     return render_template("user_verify.html")
#
#
# @app.route("/user_verify1", methods=['post'])
# def user_verify1():
#     email = request.form.get("email")
#     count = cursor.execute("select * from users where email = '"+str(email)+"'")
#     if count == 0:
#         OTP = random.randint(1000, 10000)
#         return render_template("user_verify1.html", email=email, OTP=OTP)
#     return render_template("user_verify.html", message="Duplicate Email Address")
#
#
#
# @app.route("/user_verify2", methods=['post'])
# def user_verify2():
#     email = request.form.get("email")
#     OTP = request.form.get("OTP")
#     email_otp = request.form.get("email_otp")
#     print(OTP)
#     print(email_otp)
#     if OTP == email_otp:
#         return render_template("user_registration.html", email=email)
#     else:
#         return render_template("user_verify.html", message="Invalid OTP")


@app.route("/user_registration")
def user_registration():
    return render_template("user_registration.html")


@app.route("/user_registration1", methods=['post'])
def user_registration1():
    name = request.form.get("name")
    phone = request.form.get("phone")
    email = request.form.get("email")
    password = request.form.get("password")
    count = cursor.execute("select * from users where email = '"+str(email)+"' or phone = '"+str(phone)+"'")
    if count > 0:
        return render_template("user_registration.html", message="Duplicate Details")
    else:
        User_SES_Client.verify_email_address(
            EmailAddress=email
        )
        cursor.execute(
            "insert into users(name, phone, email, password) values('" + str(
                name) + "','" + str(phone) + "','" + str(email) + "','" + str(password) + "')")
        conn.commit()
        return render_template("user_registration.html", message="User Registered Successfully Verify yourself on mail by clicking on the link")


@app.route("/logout")
def logout():
    session.clear()
    return render_template("index.html")


@app.route("/view_folders")
def view_folders():
    cursor.execute("select * from folders where user_id = '"+str(session['user_id'])+"'")
    folders = cursor.fetchall()
    return render_template("view_folders.html", folders=folders, get_user_by_user_id=get_user_by_user_id)


def get_user_by_user_id(user_id):
    cursor.execute("select * from users where user_id = '"+str(user_id)+"'")
    users = cursor.fetchall()
    return users[0]


def get_folder_by_folder_id(folder_id):
    cursor.execute("select * from folders where folder_id = '"+str(folder_id)+"'")
    folders = cursor.fetchall()
    return folders[0]


def get_file_by_file_id(file_id):
    cursor.execute("select * from files where file_id = '"+str(file_id)+"'")
    files = cursor.fetchall()
    return files[0]


def get_shared_to_by_user_id(user_id):
    cursor.execute("select * from users where user_id = '"+str(user_id)+"'")
    users = cursor.fetchall()
    return users[0]


def get_shared_by_by_user_id(user_id):
    cursor.execute("select * from users where user_id = '"+str(user_id)+"'")
    users = cursor.fetchall()
    return users[0]


@app.route("/add_folder")
def add_folder():
    return render_template("add_folder.html")


@app.route("/add_folder1")
def add_folder1():
    folder_name = request.args.get("folder_name")
    count = cursor.execute("select * from folders where folder_name = '"+str(folder_name)+"'")
    if count > 0:
        return render_template("user_msg.html", message='Duplicate Folder Name')
    else:
        cursor.execute("insert into folders(folder_name, user_id) values('" + str(folder_name) + "','" + str(session['user_id']) + "')")
        conn.commit()
        folder_id = cursor.lastrowid
        print(folder_id)
        final_directory = os.path.join(APP_ROOT, str(folder_id))
        if not os.path.exists(final_directory):
            os.makedirs(final_directory)
        folder_name = folder_name+'/'
        User_S3_Client.put_object(Bucket=User_bucket, Key=folder_name)
        return render_template("user_msg.html", message="Folder Created Successfully")


@app.route("/delete_folder")
def delete_folder():
    folder_id = request.args.get("folder_id")
    cursor.execute(" delete from folders where folder_id='" + str(folder_id) + "' ")
    conn.commit()
    return redirect("/view_folders")


@app.route("/delete_file")
def delete_file():
    file_id = request.args.get("file_id")
    today = datetime.datetime.now()
    end_date = today+datetime.timedelta(days=30)
    print(end_date)
    end_date = str(end_date).split(" ",)[0]
    print(end_date)
    cursor.execute("update files set status = 'Recycle Bin' where file_id='" + str(file_id) + "' ")
    cursor.execute("insert into recycle_bin(delete_date, date, file_id) values(now(), '"+str(end_date)+"', '"+str(file_id)+"')")
    conn.commit()
    return redirect("/view_files")


@app.route("/recover_file")
def recover_file():
    file_id = request.args.get("file_id")
    cursor.execute("update files set status = 'Uploaded' where file_id='" + str(file_id) + "' ")
    conn.commit()
    return redirect("/view_recycle_bin")


@app.route("/view_files")
def view_files():
    view_type = request.args.get("view_type")
    if view_type == None:
        view_type = 'list_view'
    elif view_type == 'on':
        view_type = 'grid_view'

    cursor.execute("select * from files where folder_id in(select folder_id from folders where user_id = '" + str(session['user_id']) + "') and status = 'Uploaded'")
    files = cursor.fetchall()
    status = 'Uploaded'
    return render_template("view_files.html", message="Files", view_type=view_type , status=status, files=files, get_user_by_user_id=get_user_by_user_id, get_folder_by_folder_id=get_folder_by_folder_id, video_formats=video_formats, audio_formats=audio_formats, image_formats=image_formats, pdf_formats=pdf_formats)


@app.route("/upload_file")
def upload_file():
    cursor.execute("select * from folders where user_id = '"+str(session['user_id'])+"'")
    folders = cursor.fetchall()
    return render_template("upload_file.html", folders=folders, str=str)


@app.route("/upload_file1", methods=['post'])
def upload_file1():
    file = request.files.get("files_name")
    folder_id = request.form.get("folder_id")
    path = APP_ROOT+"/"+folder_id+"/"+file.filename
    print(path)
    file.save(path)
    file_type = os.path.splitext(file.filename)[-1]
    cursor.execute("select * from folders where folder_id = '"+str(folder_id)+"'")
    floders = cursor.fetchall()
    floder_name = floders[0][1]
    print(floder_name)
    count = cursor.execute("select * from files where file_name = '" + str(file.filename) + "'")
    if count == 0:
        try:
            User_S3_Client.upload_file(path, User_bucket, floder_name+'/'+file.filename)
            url = User_S3_Client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': User_bucket,
                    'Key': floder_name+'/'+file.filename
                }
            )
            cursor.execute("insert into files(file, folder_id, status, file_type, file_name) values('" + str(url) + "','" + str(folder_id) + "', 'Uploaded', '"+str(file_type)+"', '"+str(file.filename)+"')")
            conn.commit()
            return render_template("user_msg.html", message="File Upload Successfully")
        except Exception as e:
            return render_template("user_msg.html", message="Somthing Went Wrong")
    else:
        return redirect("/upload_file_exist")


@app.route("/upload_file_exist")
def upload_file_exist():
    cursor.execute("select * from folders where user_id = '" + str(session['user_id']) + "'")
    folders = cursor.fetchall()
    return render_template("upload_file.html", folders=folders, str=str, message="This File Name is Already Exist, Re-Upload with New Name.")


@app.route("/download_file")
def download_file():
    file_id = request.args.get("file_id")
    cursor.execute("select * from files where file_id = '" + str(file_id) + "'")
    files = cursor.fetchall()
    file = files[0][5]
    folder_id = files[0][2]
    url = files[0][1]
    print(file)
    print(folder_id)
    cursor.execute("insert into downloads(date, user_id, file_id) values(now(),'" + str(
        session['user_id']) + "', '" + str(file_id) + "')")
    conn.commit()
    return redirect("/view_files")


@app.route("/view_recycle_bin")
def view_recycle_bin():
    view_type = request.args.get("view_type")
    if view_type == None:
        view_type = 'list_view'
    elif view_type == 'on':
        view_type = 'grid_view'
    cursor.execute("select * from files where folder_id in(select folder_id from folders where user_id = '" + str(session['user_id']) + "') and status = 'Recycle Bin'")
    files = cursor.fetchall()
    status = 'Recycle Bin'
    return render_template("view_files.html", view_type=view_type, get_recycle_bin_by_file_id=get_recycle_bin_by_file_id, status=status, message="Recycle Bin", files=files, get_user_by_user_id=get_user_by_user_id, get_folder_by_folder_id=get_folder_by_folder_id, video_formats=video_formats, audio_formats=audio_formats, image_formats=image_formats, pdf_formats=pdf_formats)


@app.route("/delete_file_from_bin")
def delete_file_from_bin():
    file_id = request.args.get("file_id")
    cursor.execute("delete from recycle_bin where file_id='" + str(file_id) + "' ")
    cursor.execute("delete from files where file_id='" + str(file_id) + "' ")
    conn.commit()
    return redirect("/view_recycle_bin")


def get_recycle_bin_by_file_id(file_id):
    cursor.execute("select * from recycle_bin where file_id = '"+str(file_id)+"'")
    recycle_bin = cursor.fetchall()
    return recycle_bin[0]


@app.route("/share")
def share():
    file_id = request.args.get("file_id")
    return render_template("share.html", file_id=file_id)


@app.route("/share1")
def share1():
    file_id = request.args.get("file_id")
    email = request.args.get("email")
    user_id = session['user_id']
    count = cursor.execute("select * from users where email = '"+str(email)+"'")
    if count == 0:
        return render_template("user_msg.html", message="This email is not registered on this website")
    else:
        user = cursor.fetchall()
        shared_to_user_id = user[0][0]
        cursor.execute("insert into shares(date, shared_by_user_id, shared_to_user_id, file_id) values(now(),'" + str(
            user_id) + "', '"+str(shared_to_user_id)+"', '"+str(file_id)+"')")
        conn.commit()
        return render_template("user_msg.html", message="Shared Successfully")


@app.route("/shared_by_you")
def shared_by_you():
    user_id = session['user_id']
    cursor.execute("select * from shares where shared_by_user_id = '"+str(user_id)+"'")
    shares = cursor.fetchall()
    return render_template("shared_files.html", shares=shares, get_folder_by_folder_id=get_folder_by_folder_id, get_file_by_file_id=get_file_by_file_id, get_shared_by_by_user_id=get_shared_by_by_user_id, get_shared_to_by_user_id=get_shared_to_by_user_id, video_formats=video_formats, audio_formats=audio_formats, image_formats=image_formats, pdf_formats=pdf_formats)


@app.route("/shared_to_you")
def shared_to_you():
    user_id = session['user_id']
    cursor.execute("select * from shares where shared_to_user_id = '"+str(user_id)+"'")
    shares = cursor.fetchall()
    return render_template("shared_files.html", shares=shares, get_folder_by_folder_id=get_folder_by_folder_id, get_file_by_file_id=get_file_by_file_id, get_shared_by_by_user_id=get_shared_by_by_user_id, get_shared_to_by_user_id=get_shared_to_by_user_id, video_formats=video_formats, audio_formats=audio_formats, image_formats=image_formats, pdf_formats=pdf_formats)


app.run(debug=True)


