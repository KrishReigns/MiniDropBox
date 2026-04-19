import datetime
import os
from functools import wraps
from flask import Flask, request, render_template, session, redirect

# Import new modules
from config import (
    FLASK_SECRET_KEY, FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    VIDEO_FORMATS, AUDIO_FORMATS, IMAGE_FORMATS, PDF_FORMATS,
    RECYCLE_BIN_RETENTION_DAYS, S3_PRESIGNED_URL_EXPIRY_SECONDS
)
from db_operations import DatabasePool, DatabaseOperation
from s3_operations import get_s3_operations, S3OperationError
from error_handlers import (
    setup_logging, safe_route, log_user_action_detail, log_login,
    log_file_operation, AuthenticationError, ValidationError as ValidatorError,
    DatabaseError, S3Error, ResourceNotFoundError
)
from validators import (
    validate_email, validate_password, validate_phone, validate_name,
    validate_filename, validate_foldername, validate_file_size,
    ValidationError, sanitize_input, hash_password, verify_password
)

# Setup logging
logger = setup_logging()

# Initialize database pool
db_pool = DatabasePool()

# Initialize S3 operations
s3_ops = get_s3_operations()

# Create Flask app
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return render_template("index.html", message="Please log in to continue.")
        return f(*args, **kwargs)
    return decorated_function


def delete_local_file(folder_id, file_name):
    local_path = os.path.join(APP_ROOT, str(folder_id), file_name)
    try:
        if os.path.exists(local_path):
            os.remove(local_path)
            return True
    except Exception as e:
        logger.error(f"Local file delete failed for {local_path}: {repr(e)}")
    return False


APP_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = APP_ROOT + '/static'
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/user_login", methods=['post'])
@safe_route(render_on_error='index.html')
def user_login():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    
    # Validate inputs
    try:
        email = validate_email(email)
        # Password is validated against stored hash in production
        if not password:
            raise ValidationError("Password is required")
    except ValidationError as e:
        log_login(None, False, email=email, error=str(e))
        raise AuthenticationError(str(e))
    
    try:
        # Use parameterized query to prevent SQL injection
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, name, email, password FROM users WHERE email = %s",
            (email,)
        )
        users = cursor.fetchall()
        cursor.close()
        
        if len(users) > 0:
            user = users[0]
            user_id, name, email_addr, hashed_password = user
            
            # Verify password against hash
            if not verify_password(password, hashed_password):
                log_login(None, False, email=email, error="Invalid password")
                raise AuthenticationError("Invalid email or password")
            
            # Log successful login
            log_login(user_id, True, email=email)
            
            # Set session
            session["user_id"] = user_id
            session["role"] = 'user'
            
            # Try to send login notification email (non-critical)
            try:
                import boto3
                ses_client = boto3.client('ses', region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
                ses_client.send_email(
                    Source=os.getenv("AWS_EMAIL_SOURCE", "krishna1996sai@gmail.com"),
                    Destination={'ToAddresses': [email]},
                    Message={
                        'Subject': {'Data': f'Hello {name}, You Have Successfully Logged into Website', 'Charset': 'utf-8'},
                        'Body': {'Html': {'Data': f'Hello {name}, You Have Successfully Logged into Website', 'Charset': 'utf-8'}}
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send login email for user {user_id}: {repr(e)}")
            
            return render_template("user_home.html", user=user)
        else:
            log_login(None, False, email=email, error="Invalid credentials")
            raise AuthenticationError("Invalid email or password")
    
    except DatabaseError:
        raise
    except Exception as e:
        logger.error(f"Login error: {repr(e)}")
        raise DatabaseError("Login operation failed")


@app.route("/user_home")
@login_required
def user_home():
    user_id = session['user_id']
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        users = cursor.fetchall()
        cursor.close()
        
        if users:
            return render_template("user_home.html", user=users[0])
        else:
            raise ResourceNotFoundError("User")
    except Exception as e:
        logger.error(f"Error in user_home: {repr(e)}")
        raise DatabaseError("Failed to load user profile")


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
    """Show user registration form"""
    return render_template("user_registration.html")


@app.route("/user_registration1", methods=['post'])
@safe_route(render_on_error='user_registration.html')
def user_registration1():
    """Handle user registration"""
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    
    # Validate inputs
    try:
        name = validate_name(name)
        phone = validate_phone(phone)
        email = validate_email(email)
        password = validate_password(password)
    except ValidationError as e:
        log_user_action_detail(None, 'registration_failed', {
            'email': email,
            'reason': str(e)
        })
        raise
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Check for duplicate email or phone
        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s OR phone = %s",
            (email, phone)
        )
        if cursor.fetchone():
            cursor.close()
            log_user_action_detail(None, 'registration_duplicate', {
                'email': email,
                'phone': phone
            })
            raise ValidationError("Email or phone already registered")
        
        # Create user
        hashed_password = hash_password(password)
        cursor.execute(
            "INSERT INTO users(name, phone, email, password) VALUES(%s, %s, %s, %s)",
            (name, phone, email, hashed_password)
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor.close()
        
        log_user_action_detail(user_id, 'user_registration', {
            'email': email,
            'name': name
        })
        logger.info(f"New user registered: {email} (ID: {user_id})")
        
        # Try to send verification email (non-critical)
        try:
            import boto3
            ses_client = boto3.client('ses', region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
            ses_client.verify_email_address(EmailAddress=email)
            ses_client.send_email(
                Source=os.getenv("AWS_EMAIL_SOURCE", "krishna1996sai@gmail.com"),
                Destination={'ToAddresses': [email]},
                Message={
                    'Subject': {'Data': 'Welcome to MiniDropBox', 'Charset': 'utf-8'},
                    'Body': {'Html': {'Data': f'Welcome {name}! Your account has been created successfully.', 'Charset': 'utf-8'}}
                }
            )
        except Exception as e:
            logger.warning(f"Failed to send registration email for {email}: {repr(e)}")
        
        return render_template(
            "user_registration.html",
            message="User registered successfully! You can now log in."
        )
        
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error during registration: {repr(e)}")
        raise DatabaseError("Registration failed")


@app.route("/logout")
def logout():
    session.clear()
    return render_template("index.html")


@app.route("/view_folders")
@login_required
def view_folders():
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM folders WHERE user_id = %s", (session['user_id'],))
        folders = cursor.fetchall()
        cursor.close()
        
        log_file_operation(session['user_id'], 'view_folders', None, None)
        return render_template("view_folders.html", folders=folders, get_user_by_user_id=get_user_by_user_id)
    except Exception as e:
        logger.error(f"Error viewing folders: {repr(e)}")
        raise DatabaseError("Failed to load folders")



def get_user_by_user_id(user_id):
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        users = cursor.fetchall()
        cursor.close()
        return users[0] if users else None
    except Exception as e:
        logger.error(f"Error getting user {user_id}: {repr(e)}")
        return None


def get_folder_by_folder_id(folder_id):
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM folders WHERE folder_id = %s", (folder_id,))
        folders = cursor.fetchall()
        cursor.close()
        return folders[0] if folders else None
    except Exception as e:
        logger.error(f"Error getting folder {folder_id}: {repr(e)}")
        return None


def get_file_by_file_id(file_id):
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM files WHERE file_id = %s", (file_id,))
        files = cursor.fetchall()
        cursor.close()
        return files[0] if files else None
    except Exception as e:
        logger.error(f"Error getting file {file_id}: {repr(e)}")
        return None


def get_file_url(file):
    """Resolve file URL and generate presigned URL if needed"""
    stored_value = file[1].strip() if file[1] else ''
    
    # Already a local URL
    if stored_value.startswith('/static/'):
        return stored_value
    
    # External URL - verify it's S3
    if stored_value.startswith('http'):
        from urllib.parse import urlparse
        parsed = urlparse(stored_value)
        s3_bucket = os.getenv("AWS_BUCKET_NAME", "userminidropbox")
        if s3_bucket in parsed.netloc or parsed.netloc.endswith(f'.s3.{os.getenv("AWS_BUCKET_REGION", "us-east-1")}.amazonaws.com'):
            s3_key = parsed.path.lstrip('/')
            # Generate presigned URL for S3
            content_type = _get_content_type(file[4]) if file[4] else None
            try:
                return s3_ops.generate_presigned_url(
                    s3_key,
                    S3_PRESIGNED_URL_EXPIRY_SECONDS,
                    response_content_disposition='inline',
                    response_content_type=content_type
                ) or stored_value
            except Exception as e:
                logger.error(f"Failed to generate presigned URL for {s3_key}: {repr(e)}")
                return stored_value
        return stored_value
    
    # S3 key without URL - generate presigned URL
    content_type = _get_content_type(file[4]) if file[4] else None
    try:
        return s3_ops.generate_presigned_url(
            stored_value,
            S3_PRESIGNED_URL_EXPIRY_SECONDS,
            response_content_disposition='inline',
            response_content_type=content_type
        ) or stored_value
    except Exception as e:
        logger.error(f"Failed to generate presigned URL for {stored_value}: {repr(e)}")
        return stored_value


def _get_content_type(file_ext):
    """Get MIME type for file extension"""
    from config import FILE_TYPE_MAP
    if file_ext in FILE_TYPE_MAP:
        return FILE_TYPE_MAP[file_ext]['mime']
    return None


@app.route("/add_folder")
@login_required
def add_folder():
    return render_template("add_folder.html")


@app.route("/add_folder1")
@login_required
@safe_route(render_on_error='add_folder.html')
def add_folder1():
    folder_name = request.args.get("folder_name", "").strip()
    
    # Validate folder name
    try:
        folder_name = validate_foldername(folder_name)
    except ValidationError as e:
        raise ValidatorError(str(e))
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Check for duplicates - per user
        cursor.execute(
            "SELECT * FROM folders WHERE folder_name = %s AND user_id = %s",
            (folder_name, session['user_id'])
        )
        if cursor.fetchall():
            cursor.close()
            raise ValidatorError("Duplicate Folder Name")
        
        # Create folder
        cursor.execute(
            "INSERT INTO folders(folder_name, user_id) VALUES(%s, %s)",
            (folder_name, session['user_id'])
        )
        conn.commit()
        folder_id = cursor.lastrowid
        cursor.close()
        
        logger.info(f"Folder created: {folder_name} (ID: {folder_id})")
        
        # Create local directory
        final_directory = os.path.join(APP_ROOT, str(folder_id))
        if not os.path.exists(final_directory):
            os.makedirs(final_directory)
        
        # Try to create S3 folder
        folder_key = f"{folder_name}/"
        try:
            s3_ops.put_object(folder_key)
            message = "Folder Created Successfully"
        except S3OperationError:
            logger.warning(f"S3 folder creation failed for {folder_key}, using local storage only")
            message = "Folder Created Successfully (local storage only; S3 not available)"
        
        log_file_operation(session['user_id'], 'folder_create', folder_id, folder_name)
        return render_template("user_msg.html", message=message)
    
    except (ValidatorError, DatabaseError) as e:
        raise
    except Exception as e:
        logger.error(f"Error creating folder: {repr(e)}")
        raise DatabaseError("Failed to create folder")


@app.route("/delete_folder")
@login_required
@safe_route(render_on_error='view_folders.html')
def delete_folder():
    """Delete folder and all contained files"""
    folder_id = request.args.get("folder_id")
    user_id = session['user_id']
    
    if not folder_id:
        raise ValidationError("Folder ID is required")
    
    try:
        folder_id = int(folder_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid folder ID")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify folder belongs to user
        cursor.execute(
            "SELECT folder_name FROM folders WHERE folder_id = %s AND user_id = %s",
            (folder_id, user_id)
        )
        folder_row = cursor.fetchone()
        if not folder_row:
            cursor.close()
            raise ResourceNotFoundError("Folder")
        
        folder_name = folder_row[0]
        
        # Get all files in folder
        cursor.execute(
            "SELECT file_id, file, file_name FROM files WHERE folder_id = %s",
            (folder_id,)
        )
        files = cursor.fetchall()
        
        # Delete each file
        for file in files:
            file_id = file[0]
            file_url = file[1].strip() if file[1] else ''
            file_name = file[2]
            
            # Clean up related records
            cursor.execute("DELETE FROM downloads WHERE file_id = %s", (file_id,))
            cursor.execute("DELETE FROM shares WHERE file_id = %s", (file_id,))
            cursor.execute("DELETE FROM recycle_bin WHERE file_id = %s", (file_id,))
            
            # Delete from storage
            if file_url and not file_url.startswith('/static/'):
                try:
                    # Parse S3 URL
                    if file_url.startswith('http'):
                        from urllib.parse import urlparse
                        parsed = urlparse(file_url)
                        s3_key = parsed.path.lstrip('/')
                    else:
                        s3_key = file_url.lstrip('/')
                    
                    if not s3_key and folder_name:
                        s3_key = f"{folder_name.rstrip('/')}/{file_name}"
                    
                    if s3_key:
                        s3_ops.delete_object(s3_key)
                        log_file_operation(user_id, 'delete_s3_file', file_id, file_name)
                except S3OperationError as e:
                    logger.warning(f"S3 deletion failed for {file_url}, but continuing: {e}")
                except Exception as e:
                    logger.warning(f"Failed to delete S3 object: {repr(e)}")
            else:
                # Delete local file
                delete_local_file(folder_id, file_name)
                log_file_operation(user_id, 'delete_local_file', file_id, file_name)
        
        # Delete S3 folder marker
        if folder_name:
            folder_object_key = folder_name.rstrip('/') + '/'
            try:
                s3_ops.delete_object(folder_object_key)
            except Exception as e:
                logger.warning(f"S3 folder deletion failed: {repr(e)}")
        
        # Delete database records
        cursor.execute("DELETE FROM files WHERE folder_id = %s", (folder_id,))
        cursor.execute("DELETE FROM folders WHERE folder_id = %s AND user_id = %s", (folder_id, user_id))
        conn.commit()
        
        # Clean up local folder
        local_folder_path = os.path.join(APP_ROOT, str(folder_id))
        try:
            if os.path.isdir(local_folder_path) and not os.listdir(local_folder_path):
                os.rmdir(local_folder_path)
        except Exception as e:
            logger.debug(f"Could not remove local folder {local_folder_path}: {repr(e)}")
        
        log_file_operation(user_id, 'folder_delete', folder_id, folder_name)
        logger.info(f"Folder deleted: {folder_name} (ID: {folder_id})")
        
        cursor.close()
        return redirect("/view_folders")
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error deleting folder {folder_id}: {repr(e)}")
        raise DatabaseError("Failed to delete folder")


@app.route("/delete_file")
@login_required
@safe_route(render_on_error='view_files.html')
def delete_file():
    """Move file to recycle bin"""
    file_id = request.args.get("file_id")
    user_id = session['user_id']
    
    if not file_id:
        raise ValidationError("File ID is required")
    
    try:
        file_id = int(file_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid file ID")
    
    try:
        # Calculate expiry date
        today = datetime.datetime.now()
        end_date = today + datetime.timedelta(days=RECYCLE_BIN_RETENTION_DAYS)
        end_date_str = str(end_date).split(" ")[0]
        
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify file belongs to user's folder
        cursor.execute(
            "SELECT files.file_id FROM files "
            "JOIN folders ON files.folder_id = folders.folder_id "
            "WHERE files.file_id = %s AND folders.user_id = %s",
            (file_id, user_id)
        )
        if not cursor.fetchone():
            cursor.close()
            raise ResourceNotFoundError("File")
        
        # Move to recycle bin
        cursor.execute(
            "UPDATE files SET status = %s WHERE file_id = %s",
            ("Recycle Bin", file_id)
        )
        cursor.execute(
            "INSERT INTO recycle_bin(delete_date, date, file_id) VALUES(NOW(), %s, %s)",
            (end_date_str, file_id)
        )
        conn.commit()
        cursor.close()
        
        log_file_operation(user_id, 'file_delete_to_bin', file_id, None)
        logger.info(f"File moved to recycle bin: file_id={file_id}, expiry={end_date_str}")
        
        return redirect("/view_files")
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error deleting file {file_id}: {repr(e)}")
        raise DatabaseError("Failed to delete file")


@app.route("/recover_file")
@login_required
@safe_route(render_on_error='view_recycle_bin.html')
def recover_file():
    """Recover file from recycle bin"""
    file_id = request.args.get("file_id")
    user_id = session['user_id']
    
    if not file_id:
        raise ValidationError("File ID is required")
    
    try:
        file_id = int(file_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid file ID")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify file belongs to user's folder
        cursor.execute(
            "SELECT files.file_id FROM files "
            "JOIN folders ON files.folder_id = folders.folder_id "
            "WHERE files.file_id = %s AND folders.user_id = %s",
            (file_id, user_id)
        )
        if not cursor.fetchone():
            cursor.close()
            raise ResourceNotFoundError("File")
        
        # Recover file
        cursor.execute(
            "UPDATE files SET status = %s WHERE file_id = %s",
            ("Uploaded", file_id)
        )
        conn.commit()
        cursor.close()
        
        log_file_operation(user_id, 'file_recover', file_id, None)
        logger.info(f"File recovered from recycle bin: file_id={file_id}")
        
        return redirect("/view_recycle_bin")
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error recovering file {file_id}: {repr(e)}")
        raise DatabaseError("Failed to recover file")


@app.route("/view_files")
@login_required
@safe_route(render_on_error='user_home.html')
def view_files():
    """View uploaded files in user's folders"""
    user_id = session['user_id']
    view_type = request.args.get("view_type", 'list_view')
    
    if view_type == 'on':
        view_type = 'grid_view'
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Get all uploaded files in user's folders
        cursor.execute(
            "SELECT * FROM files WHERE folder_id IN "
            "(SELECT folder_id FROM folders WHERE user_id = %s) AND status = %s",
            (user_id, "Uploaded")
        )
        files = cursor.fetchall()
        cursor.close()
        
        log_file_operation(user_id, 'view_files', None, None)
        logger.info(f"User viewed files: {len(files)} files found")
        
        return render_template(
            "view_files.html",
            message="Files",
            view_type=view_type,
            status="Uploaded",
            files=files,
            get_user_by_user_id=get_user_by_user_id,
            get_folder_by_folder_id=get_folder_by_folder_id,
            get_file_url=get_file_url,
            file_url=get_file_url,
            video_formats=VIDEO_FORMATS,
            audio_formats=AUDIO_FORMATS,
            image_formats=IMAGE_FORMATS,
            pdf_formats=PDF_FORMATS
        )
    except Exception as e:
        logger.error(f"Error viewing files: {repr(e)}")
        raise DatabaseError("Failed to load files")


@app.route("/upload_file")
@login_required
@safe_route(render_on_error='user_home.html')
def upload_file():
    """Show upload file form"""
    user_id = session['user_id']
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM folders WHERE user_id = %s",
            (user_id,)
        )
        folders = cursor.fetchall()
        cursor.close()
        
        return render_template("upload_file.html", folders=folders, str=str)
    except Exception as e:
        logger.error(f"Error in upload_file view: {repr(e)}")
        raise DatabaseError("Failed to load upload form")


@app.route("/upload_file1", methods=['post'])
@login_required
@safe_route(render_on_error='upload_file.html')
def upload_file1():
    """Handle file upload"""
    user_id = session['user_id']
    file = request.files.get("files_name")
    folder_id = request.form.get("folder_id")
    
    # Validate inputs
    try:
        if not file or file.filename == '':
            raise ValidationError("No file selected")
        if not folder_id:
            raise ValidationError("Folder ID is required")
        
        folder_id = int(folder_id)
        filename = sanitize_input(file.filename)
        validate_filename(filename)
    except (ValueError, TypeError) as e:
        raise ValidationError(f"Invalid input: {str(e)}")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify folder belongs to user
        cursor.execute(
            "SELECT folder_name FROM folders WHERE folder_id = %s AND user_id = %s",
            (folder_id, user_id)
        )
        folder_row = cursor.fetchone()
        if not folder_row:
            cursor.close()
            raise ResourceNotFoundError("Folder")
        
        folder_name = folder_row[0]
        
        # Check for duplicate files
        cursor.execute(
            "SELECT file_id FROM files WHERE file_name = %s AND folder_id = %s AND status = %s",
            (filename, folder_id, "Uploaded")
        )
        if cursor.fetchone():
            cursor.close()
            return redirect(f"/upload_file_exist?folder_id={folder_id}")
        
        # Save file locally
        local_path = os.path.join(APP_ROOT, str(folder_id), filename)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        file.save(local_path)
        
        file_size = os.path.getsize(local_path)
        
        # Check storage quota
        cursor.execute(
            "SELECT quota_bytes, used_bytes FROM storage_quotas WHERE user_id = %s",
            (user_id,)
        )
        quota_row = cursor.fetchone()
        if quota_row:
            quota_bytes, used_bytes = quota_row
            if used_bytes + file_size > quota_bytes:
                os.remove(local_path)  # Clean up uploaded file
                cursor.close()
                raise ValidationError(f"Storage quota exceeded. Available: {(quota_bytes - used_bytes) / (1024**3):.2f}GB")
        
        file_type = os.path.splitext(filename)[-1].lower()
        local_url = f"/static/{folder_id}/{filename}"
        file_reference = local_url
        
        # Try S3 upload
        s3_upload_ok = False
        try:
            s3_key = f"{folder_name.rstrip('/')}/{filename}"
            if s3_ops.upload_file(local_path, s3_key):
                file_reference = s3_key
                s3_upload_ok = True
                logger.info(f"File uploaded to S3: {s3_key}")
        except S3OperationError as e:
            logger.warning(f"S3 upload failed, using local storage: {e}")
        except Exception as e:
            logger.warning(f"S3 upload error: {repr(e)}")
        
        # Insert into database
        cursor.execute(
            "INSERT INTO files(file, folder_id, status, file_type, file_name, file_size) VALUES(%s, %s, %s, %s, %s, %s)",
            (file_reference, folder_id, "Uploaded", file_type, filename, file_size)
        )
        conn.commit()
        file_id = cursor.lastrowid
        
        # Update storage quota
        cursor.execute(
            "INSERT INTO storage_quotas (user_id, used_bytes) VALUES (%s, %s) ON DUPLICATE KEY UPDATE used_bytes = used_bytes + %s",
            (user_id, file_size, file_size)
        )
        conn.commit()
        cursor.close()
        
        log_file_operation(user_id, 'file_upload', file_id, filename, os.path.getsize(local_path))
        
        if s3_upload_ok:
            message = "File uploaded successfully"
        else:
            message = "File uploaded to local storage (S3 not available)"
        
        logger.info(f"File uploaded: {filename} (ID: {file_id}) - {message}")
        return render_template("user_msg.html", message=message)
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {repr(e)}")
        raise DatabaseError("Failed to upload file")


@app.route("/upload_file_exist")
@login_required
@safe_route(render_on_error='user_home.html')
def upload_file_exist():
    """Show message that file already exists"""
    user_id = session['user_id']
    folder_id = request.args.get("folder_id", "")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM folders WHERE user_id = %s",
            (user_id,)
        )
        folders = cursor.fetchall()
        cursor.close()
        
        return render_template(
            "upload_file.html",
            folders=folders,
            str=str,
            message="This file name already exists. Please upload with a different name."
        )
    except Exception as e:
        logger.error(f"Error in upload_file_exist: {repr(e)}")
        raise DatabaseError("Failed to load upload form")


@app.route("/download_file")
@login_required
@safe_route(render_on_error='view_files.html')
def download_file():
    """Download or access file"""
    file_id = request.args.get("file_id")
    user_id = session['user_id']
    
    if not file_id:
        raise ValidationError("File ID is required")
    
    try:
        file_id = int(file_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid file ID")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Get file details
        cursor.execute(
            "SELECT files.file_id, files.file, files.folder_id, files.file_name, files.file_type "
            "FROM files "
            "JOIN folders ON files.folder_id = folders.folder_id "
            "WHERE files.file_id = %s AND folders.user_id = %s",
            (file_id, user_id)
        )
        file_row = cursor.fetchone()
        if not file_row:
            cursor.close()
            raise ResourceNotFoundError("File")
        
        file_id, file_url, folder_id, file_name, file_type = file_row
        file_url = file_url.strip() if file_url else ''
        
        # Get folder info
        cursor.execute(
            "SELECT folder_name FROM folders WHERE folder_id = %s",
            (folder_id,)
        )
        folder_row = cursor.fetchone()
        folder_name = folder_row[0] if folder_row else None
        
        # Generate URL for access
        url = file_url
        if folder_name and not url.startswith('/static/'):
            try:
                # Parse S3 URL
                if url.startswith('http'):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    s3_key = parsed.path.lstrip('/')
                else:
                    s3_key = url.lstrip('/')
                
                if not s3_key:
                    s3_key = f"{folder_name.rstrip('/')}/{file_name}"
                
                # Generate presigned URL
                presigned_url = s3_ops.generate_presigned_url(
                    s3_key,
                    S3_PRESIGNED_URL_EXPIRY_SECONDS,
                    response_content_disposition=f'attachment; filename="{file_name}"',
                    response_content_type=_get_content_type(file_type)
                )
                if presigned_url:
                    url = presigned_url
            except Exception as e:
                logger.warning(f"Failed to generate presigned URL: {repr(e)}")
        
        # Log download
        cursor.execute(
            "INSERT INTO downloads(date, user_id, file_id) VALUES(NOW(), %s, %s)",
            (user_id, file_id)
        )
        conn.commit()
        cursor.close()
        
        log_file_operation(user_id, 'file_download', file_id, file_name)
        logger.info(f"File download logged: {file_name} (ID: {file_id})")
        
        return redirect(url)
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {repr(e)}")
        raise DatabaseError("Failed to download file")


@app.route("/view_recycle_bin")
@login_required
@safe_route(render_on_error='user_home.html')
def view_recycle_bin():
    """View files in recycle bin"""
    user_id = session['user_id']
    view_type = request.args.get("view_type", 'list_view')
    
    if view_type == 'on':
        view_type = 'grid_view'
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Get all deleted files in user's folders
        cursor.execute(
            "SELECT * FROM files WHERE folder_id IN "
            "(SELECT folder_id FROM folders WHERE user_id = %s) AND status = %s",
            (user_id, "Recycle Bin")
        )
        files = cursor.fetchall()
        cursor.close()
        
        log_file_operation(user_id, 'view_recycle_bin', None, None)
        logger.info(f"User viewed recycle bin: {len(files)} files found")
        
        return render_template(
            "view_files.html",
            view_type=view_type,
            get_recycle_bin_by_file_id=get_recycle_bin_by_file_id,
            status="Recycle Bin",
            message="Recycle Bin",
            files=files,
            get_user_by_user_id=get_user_by_user_id,
            get_folder_by_folder_id=get_folder_by_folder_id,
            get_file_url=get_file_url,
            file_url=get_file_url,
            video_formats=VIDEO_FORMATS,
            audio_formats=AUDIO_FORMATS,
            image_formats=IMAGE_FORMATS,
            pdf_formats=PDF_FORMATS
        )
    except Exception as e:
        logger.error(f"Error viewing recycle bin: {repr(e)}")
        raise DatabaseError("Failed to load recycle bin")


@app.route("/delete_file_from_bin")
@login_required
@safe_route(render_on_error='view_recycle_bin.html')
def delete_file_from_bin():
    """Permanently delete file from recycle bin"""
    file_id = request.args.get("file_id")
    user_id = session['user_id']
    
    if not file_id:
        raise ValidationError("File ID is required")
    
    try:
        file_id = int(file_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid file ID")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify file belongs to user's folder and is in recycle bin
        cursor.execute(
            "SELECT files.file_id, files.file, files.folder_id, files.file_name FROM files "
            "JOIN folders ON files.folder_id = folders.folder_id "
            "WHERE files.file_id = %s AND folders.user_id = %s AND files.status = %s",
            (file_id, user_id, "Recycle Bin")
        )
        file_row = cursor.fetchone()
        if not file_row:
            cursor.close()
            raise ResourceNotFoundError("File")
        
        file_id, file_url, folder_id, file_name = file_row
        file_url = file_url.strip() if file_url else ''
        
        # Get file size for quota update
        cursor.execute("SELECT file_size FROM files WHERE file_id = %s", (file_id,))
        size_row = cursor.fetchone()
        file_size = size_row[0] if size_row and size_row[0] else 0
        
        # Get folder name
        cursor.execute(
            "SELECT folder_name FROM folders WHERE folder_id = %s",
            (folder_id,)
        )
        folder_row = cursor.fetchone()
        folder_name = folder_row[0] if folder_row else None
        
        # Delete from storage
        if folder_name:
            if file_url.startswith('/static/'):
                # Delete local file
                delete_local_file(folder_id, file_name)
                log_file_operation(user_id, 'permanent_delete_local', file_id, file_name)
            else:
                # Delete from S3
                try:
                    if file_url.startswith('http'):
                        from urllib.parse import urlparse
                        parsed = urlparse(file_url)
                        s3_key = parsed.path.lstrip('/')
                    else:
                        s3_key = file_url.lstrip('/')
                    
                    if not s3_key:
                        s3_key = f"{folder_name.rstrip('/')}/{file_name}"
                    
                    if s3_key:
                        s3_ops.delete_object(s3_key)
                        log_file_operation(user_id, 'permanent_delete_s3', file_id, file_name)
                except Exception as e:
                    logger.warning(f"S3 deletion failed: {repr(e)}")
        
        # Delete database records
        cursor.execute("DELETE FROM downloads WHERE file_id = %s", (file_id,))
        cursor.execute("DELETE FROM shares WHERE file_id = %s", (file_id,))
        cursor.execute("DELETE FROM recycle_bin WHERE file_id = %s", (file_id,))
        cursor.execute("DELETE FROM files WHERE file_id = %s", (file_id,))
        
        # Update storage quota
        if file_size > 0:
            cursor.execute(
                "UPDATE storage_quotas SET used_bytes = GREATEST(0, used_bytes - %s) WHERE user_id = %s",
                (file_size, user_id)
            )
        
        conn.commit()
        cursor.close()
        
        log_file_operation(user_id, 'file_permanent_delete', file_id, file_name)
        logger.info(f"File permanently deleted: {file_name} (ID: {file_id})")
        
        return redirect("/view_recycle_bin")
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error permanently deleting file {file_id}: {repr(e)}")
        raise DatabaseError("Failed to delete file")


def get_recycle_bin_by_file_id(file_id):
    """Get recycle bin info for a file"""
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM recycle_bin WHERE file_id = %s", (file_id,))
        recycle_bin = cursor.fetchone()
        cursor.close()
        return recycle_bin if recycle_bin else (None, None, None, None)
    except Exception as e:
        logger.error(f"Error getting recycle bin info for file {file_id}: {repr(e)}")
        return (None, None, None, None)


@app.route("/share")
@login_required
@safe_route(render_on_error='view_files.html')
def share():
    """Show share file form"""
    file_id = request.args.get("file_id")
    user_id = session['user_id']
    
    if not file_id:
        raise ValidationError("File ID is required")
    
    try:
        file_id = int(file_id)
    except (ValueError, TypeError):
        raise ValidationError("Invalid file ID")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify file belongs to user
        cursor.execute(
            "SELECT files.file_id FROM files "
            "JOIN folders ON files.folder_id = folders.folder_id "
            "WHERE files.file_id = %s AND folders.user_id = %s",
            (file_id, user_id)
        )
        if not cursor.fetchone():
            cursor.close()
            raise ResourceNotFoundError("File")
        
        cursor.close()
        return render_template("share.html", file_id=file_id)
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error in share view: {repr(e)}")
        raise DatabaseError("Failed to load share form")


@app.route("/share1")
@login_required
@safe_route(render_on_error='view_files.html')
def share1():
    """Share file with another user"""
    file_id = request.args.get("file_id")
    email = request.args.get("email", "").strip()
    user_id = session['user_id']
    
    if not file_id:
        raise ValidationError("File ID is required")
    if not email:
        raise ValidationError("Email is required")
    
    try:
        file_id = int(file_id)
        email = validate_email(email)
    except (ValueError, TypeError):
        raise ValidationError("Invalid file ID")
    except ValidationError:
        raise
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Verify file belongs to user
        cursor.execute(
            "SELECT files.file_id, files.file_name FROM files "
            "JOIN folders ON files.folder_id = folders.folder_id "
            "WHERE files.file_id = %s AND folders.user_id = %s",
            (file_id, user_id)
        )
        file_row = cursor.fetchone()
        if not file_row:
            cursor.close()
            raise ResourceNotFoundError("File")
        
        file_name = file_row[1]
        
        # Find user by email
        cursor.execute(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )
        shared_user = cursor.fetchone()
        if not shared_user:
            cursor.close()
            raise ValidationError("Email not registered on this platform")
        
        shared_to_user_id = shared_user[0]
        
        # Prevent sharing with self
        if shared_to_user_id == user_id:
            cursor.close()
            raise ValidationError("Cannot share files with yourself")
        
        # Check if already shared
        cursor.execute(
            "SELECT share_id FROM shares WHERE file_id = %s AND shared_by_user_id = %s AND shared_to_user_id = %s",
            (file_id, user_id, shared_to_user_id)
        )
        if cursor.fetchone():
            cursor.close()
            raise ValidationError("File already shared with this user")
        
        # Create share record
        cursor.execute(
            "INSERT INTO shares(date, shared_by_user_id, shared_to_user_id, file_id) "
            "VALUES(NOW(), %s, %s, %s)",
            (user_id, shared_to_user_id, file_id)
        )
        conn.commit()
        cursor.close()
        
        log_file_operation(user_id, 'file_share', file_id, file_name)
        log_user_action_detail(user_id, 'file_share', {
            'file_id': file_id,
            'shared_to_email': email
        })
        logger.info(f"File shared: {file_name} (ID: {file_id}) shared with {email}")
        
        return render_template("user_msg.html", message="File shared successfully")
        
    except (ValidationError, ResourceNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Error sharing file: {repr(e)}")
        raise DatabaseError("Failed to share file")


@app.route("/shared_by_you")
@login_required
@safe_route(render_on_error='user_home.html')
def shared_by_you():
    """View files shared by current user"""
    user_id = session['user_id']
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM shares WHERE shared_by_user_id = %s",
            (user_id,)
        )
        shares = cursor.fetchall()
        cursor.close()
        
        log_user_action_detail(user_id, 'view_shared_by_you', {
            'count': len(shares)
        })
        logger.info(f"User viewed files shared by them: {len(shares)} shares found")
        
        return render_template(
            "shared_files.html",
            shares=shares,
            get_folder_by_folder_id=get_folder_by_folder_id,
            get_file_by_file_id=get_file_by_file_id,
            get_shared_by_by_user_id=get_user_by_user_id,
            get_shared_to_by_user_id=get_user_by_user_id,
            video_formats=VIDEO_FORMATS,
            audio_formats=AUDIO_FORMATS,
            image_formats=IMAGE_FORMATS,
            pdf_formats=PDF_FORMATS
        )
    except Exception as e:
        logger.error(f"Error viewing shared_by_you: {repr(e)}")
        raise DatabaseError("Failed to load shared files")


@app.route("/shared_to_you")
@login_required
@safe_route(render_on_error='user_home.html')
def shared_to_you():
    """View files shared with current user"""
    user_id = session['user_id']
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM shares WHERE shared_to_user_id = %s",
            (user_id,)
        )
        shares = cursor.fetchall()
        cursor.close()
        
        log_user_action_detail(user_id, 'view_shared_to_you', {
            'count': len(shares)
        })
        logger.info(f"User viewed files shared with them: {len(shares)} shares found")
        
        return render_template(
            "shared_files.html",
            shares=shares,
            get_folder_by_folder_id=get_folder_by_folder_id,
            get_file_by_file_id=get_file_by_file_id,
            get_shared_by_by_user_id=get_user_by_user_id,
            get_shared_to_by_user_id=get_user_by_user_id,
            video_formats=VIDEO_FORMATS,
            audio_formats=AUDIO_FORMATS,
            image_formats=IMAGE_FORMATS,
            pdf_formats=PDF_FORMATS
        )
    except Exception as e:
        logger.error(f"Error viewing shared_to_you: {repr(e)}")
        raise DatabaseError("Failed to load shared files")



if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, host=FLASK_HOST, port=FLASK_PORT)


