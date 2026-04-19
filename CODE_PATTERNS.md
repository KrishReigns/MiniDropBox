# MiniDropBox: Code Patterns & Implementation Examples

## Quick Reference: Issue → Solution Patterns

---

## PATTERN 1: Thread-Safe Database Connection Pool

### Current Code (UNSAFE)
```python
# main.py - Lines 19-21, 26-35
conn = pymysql.connect(host=DB_HOST, user=DB_USER, ...)  # Global mutable object
cursor = conn.cursor()

def init_db_connection():  # Called on every request - expensive
    global conn, cursor
    try:
        conn.ping(reconnect=True)
    except Exception:
        conn = pymysql.connect(...)  # Reconnect on ANY error
```

### PROPOSED Pattern
```python
# db_connection.py
from DBUtils.PooledDB import PooledDB
import threading

class DatabasePool:
    """Singleton thread-safe connection pool"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_pool_initialized'):
            return
        
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=10,           # Max pooled connections
            mincached=2,                  # Min idle always available
            maxcached=5,                  # Max idle kept
            maxshared=3,                  # Max concurrent shared
            blocking=True,                # Wait if none available
            maxusage=None,                # Infinite reuse
            ping=1,                       # Health check before use
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            charset='utf8mb4',
            autocommit=True,
            connect_timeout=10
        )
        self._pool_initialized = True
    
    def get_connection(self):
        """Get connection from pool (thread-safe)"""
        return self.pool.connection()
    
    def close_all(self):
        """Close all connections in pool"""
        if hasattr(self, 'pool'):
            self.pool.close()

# Usage in main.py
db_pool = DatabasePool()

@app.before_request
def before_request():
    # Pool manages connections automatically
    # No need to call init_db_connection()
    pass

@app.teardown_appcontext
def shutdown(exception=None):
    # Optional: explicitly close pool on shutdown
    pass
```

### Key Differences
| Aspect | Current | Proposed |
|--------|---------|----------|
| Connection Count | 1 global | 2-10 in pool |
| Thread Safety | ❌ Race conditions | ✅ Internal locking |
| Reuse | Single connection | Connection reuse |
| Health Checks | Manual (`ping()`) | Automatic (pool) |
| Error Recovery | Generic catch-all | Pool handles |
| Overhead | Reconnect on each error | Minimal (pool manages) |

---

## PATTERN 2: Database Error Handling with Retry Logic

### Current Code (NO ERROR HANDLING)
```python
# main.py - Lines 180-182, 251, 277, etc.
@app.route("/user_registration1", methods=['post'])
def user_registration1():
    name = request.form.get("name")
    email = request.form.get("email")
    
    # NO ERROR HANDLING - Exception crashes the route
    count = cursor.execute("select * from users where email = '"+email+"'")
    if count > 0:
        return render_template("user_registration.html", message="Duplicate")
    
    # If execute() fails, route crashes
    cursor.execute("insert into users(...) values(...)")
    conn.commit()  # If this fails, no handling
```

### PROPOSED Pattern with Decorator
```python
# error_handlers.py
import pymysql
from functools import wraps
import logging
import time

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Base database exception"""
    pass

class DatabaseConnectionError(DatabaseError):
    pass

class DatabaseIntegrityError(DatabaseError):
    pass

def handle_db_errors(max_retries=2, backoff_multiplier=1.5):
    """
    Decorator for database operations
    Implements retry logic with exponential backoff
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            wait_time = 0.5  # Start with 500ms
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                
                except pymysql.err.OperationalError as e:
                    # Connection lost, lock timeout, etc. - RETRYABLE
                    logger.warning(f"[Attempt {attempt+1}/{max_retries+1}] "
                                 f"OperationalError: {e}")
                    if attempt < max_retries:
                        time.sleep(wait_time)
                        wait_time *= backoff_multiplier
                    else:
                        raise DatabaseConnectionError(
                            f"DB connection failed after {max_retries} retries"
                        ) from e
                
                except pymysql.err.IntegrityError as e:
                    # Duplicate key, FK violation - DON'T RETRY
                    logger.error(f"IntegrityError (duplicate/FK): {e}")
                    raise DatabaseIntegrityError(str(e)) from e
                
                except pymysql.err.ProgrammingError as e:
                    # SQL syntax error - DON'T RETRY
                    logger.error(f"ProgrammingError (SQL syntax): {e}")
                    raise DatabaseError(f"Query error: {e}") from e
                
                except pymysql.err.DatabaseError as e:
                    # Other DB errors
                    logger.error(f"DatabaseError: {e}")
                    raise DatabaseError(str(e)) from e
                
                except Exception as e:
                    # Unexpected
                    logger.critical(f"Unexpected error: {type(e).__name__}: {e}")
                    raise
        
        return wrapper
    return decorator

# Usage in main.py
@handle_db_errors(max_retries=2)
@app.route("/user_registration1", methods=['post'])
def user_registration1():
    name = request.form.get("name")
    email = request.form.get("email")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # Query with parameterized values
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            return render_template("user_registration.html", 
                                 message="Duplicate email")
        
        # Insert with parameters
        cursor.execute(
            "INSERT INTO users(name, email) VALUES(%s, %s)",
            (name, email)
        )
        conn.commit()
        
        return render_template("user_registration.html",
                             message="Registered successfully")
    
    except DatabaseIntegrityError:
        # Duplicate detected - handled above
        return render_template("user_registration.html",
                             message="User already exists")
    
    except DatabaseConnectionError:
        # Connection lost - user should retry
        return render_template("index.html",
                             message="Database unavailable. Please try again.",
                             error_id="DB-001")
    
    except DatabaseError as e:
        # Other DB errors
        logger.error(f"Database error: {e}")
        return render_template("index.html",
                             message="An error occurred. Please try again.")
```

### Retry Logic Example
```
Attempt 1: Fails with OperationalError
  → Wait 0.5s
  
Attempt 2: Fails with OperationalError
  → Wait 0.75s (0.5 * 1.5)
  
Attempt 3: Fails with OperationalError
  → Raise DatabaseConnectionError (max retries exhausted)
  
If ANY attempt succeeds → Return result immediately
If IntegrityError → Don't retry, raise immediately
```

---

## PATTERN 3: SQL Injection Prevention (Parameterized Queries)

### Current Code (VULNERABLE)
```python
# main.py - Lines 162-164
email = request.form.get("email")
password = request.form.get("password")

# SQL INJECTION VULNERABLE
count = cursor.execute(
    "select * from users where email = '" + str(email) + "' and password = '" + str(password) + "'"
)

# Attack: email = "' OR '1'='1"
# Becomes: SELECT * FROM users WHERE email = '' OR '1'='1' AND password = ...
# Returns ALL users!
```

### PROPOSED Pattern
```python
# main.py - Fixed
@app.route("/user_login", methods=['post'])
def user_login():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    
    # Validate input format
    if not email or len(email) > 255:
        return render_template("index.html", message="Invalid email")
    if not password or len(password) > 128:
        return render_template("index.html", message="Invalid password")
    
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        
        # SAFE: Parameterized query with %s placeholders
        cursor.execute(
            "SELECT * FROM users WHERE email=%s AND password=%s",
            (email, password)  # Values passed separately
        )
        
        user = cursor.fetchone()
        if not user:
            return render_template("index.html", message="Login failed")
        
        session['user_id'] = user[0]
        return render_template("user_home.html", user=user)
    
    finally:
        if conn:
            conn.close()  # Returns to pool
```

### Key Rules for Parameterized Queries
```
❌ WRONG:  cursor.execute("SELECT * FROM users WHERE id = " + str(user_id))
✅ RIGHT:  cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

❌ WRONG:  cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
✅ RIGHT:  cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

❌ WRONG:  cursor.execute("SELECT * FROM users WHERE email = '" + email + "'")
✅ RIGHT:  cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

Note: Tuple must have comma even for single value: (value,) not (value)
```

---

## PATTERN 4: S3 Operations with Retry Logic

### Current Code (NO RETRIES)
```python
# main.py - Lines 59-73
def s3_upload_file(path, bucket, key):
    try:
        User_S3_Client.upload_file(path, bucket, key)
        return True
    except Exception as e:
        print("S3 upload_file failed:", repr(e))  # Lost when process exits
        return False  # Caller doesn't know WHY it failed

# Usage in upload_file1() - Line 388
upload_ok = s3_upload_file(path, User_bucket, floder_name+'/'+file.filename)
if upload_ok:
    message = "File Upload Successfully"
else:
    message = "Folder Created Successfully (local storage only)"
    # Transient network error treated same as permanent permission error!
```

### PROPOSED Pattern with Tenacity
```python
# s3_operations.py
from tenacity import retry, stop_after_attempt, wait_exponential
from botocore.exceptions import ClientError, ConnectionError as BotoConnectionError
from botocore.config import Config
from botocore.session import get_session
import boto3
import logging

logger = logging.getLogger(__name__)

class S3Error(Exception):
    pass

class S3RetryableError(S3Error):
    """Transient error - safe to retry"""
    pass

class S3PermanentError(S3Error):
    """Permanent error - don't retry"""
    pass

class S3OperationWrapper:
    
    RETRYABLE_ERROR_CODES = {
        'RequestTimeout',
        'ServiceUnavailable',
        'ThrottlingException',
        'SlowDown',
    }
    
    def __init__(self, bucket, region, max_retries=3):
        self.bucket = bucket
        self.region = region
        self.max_retries = max_retries
        
        # Enhanced config with timeouts
        config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'virtual'},
            retries={'max_attempts': max_retries},
            connect_timeout=30,
            read_timeout=30,
            max_pool_connections=20
        )
        
        self.client = boto3.client(
            's3',
            region_name=region,
            config=config
        )
    
    @staticmethod
    def _is_retryable(error):
        """Classify error as retryable or permanent"""
        if isinstance(error, BotoConnectionError):
            return True  # Network errors always retryable
        
        if isinstance(error, TimeoutError):
            return True
        
        if isinstance(error, ClientError):
            error_code = error.response.get('Error', {}).get('Code', '')
            return error_code in S3OperationWrapper.RETRYABLE_ERROR_CODES
        
        return False
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    def upload_file(self, local_path, s3_key):
        """Upload with automatic retry"""
        try:
            logger.info(f"Uploading {local_path} to s3://{self.bucket}/{s3_key}")
            
            self.client.upload_file(
                local_path,
                self.bucket,
                s3_key,
                ExtraArgs={
                    'ContentType': self._guess_content_type(local_path)
                }
            )
            
            logger.info(f"Upload successful: {s3_key}")
            return True
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if self._is_retryable(e):
                logger.warning(f"Retryable S3 error [{error_code}]: {error_msg}")
                raise S3RetryableError(error_msg) from e
            else:
                logger.error(f"Permanent S3 error [{error_code}]: {error_msg}")
                raise S3PermanentError(error_msg) from e
        
        except (BotoConnectionError, TimeoutError) as e:
            logger.warning(f"Retryable network error: {e}")
            raise S3RetryableError(str(e)) from e
        
        except Exception as e:
            logger.error(f"Unexpected S3 error: {type(e).__name__}: {e}")
            raise S3PermanentError(str(e)) from e
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    def delete_object(self, s3_key):
        """Delete with automatic retry (idempotent)"""
        try:
            logger.info(f"Deleting s3://{self.bucket}/{s3_key}")
            self.client.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info(f"Delete successful: {s3_key}")
            return True
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'NoSuchKey':
                logger.info(f"Object already deleted (idempotent): {s3_key}")
                return True  # Already gone - success
            
            if self._is_retryable(e):
                raise S3RetryableError(str(e)) from e
            else:
                raise S3PermanentError(str(e)) from e
        
        except Exception as e:
            raise S3PermanentError(str(e)) from e
    
    @staticmethod
    def _guess_content_type(file_path):
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'

# Usage in main.py
s3_wrapper = S3OperationWrapper(User_bucket, AWS_BUCKET_REGION, max_retries=3)

@app.route("/upload_file1", methods=['post'])
@handle_db_errors()
def upload_file1():
    file = request.files.get("files_name")
    folder_id = request.form.get("folder_id")
    
    try:
        # Database operation
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT folder_name FROM folders WHERE folder_id=%s", (folder_id,))
        folder = cursor.fetchone()
        
        if not folder:
            return render_template("user_msg.html", message="Folder not found")
        
        folder_name = folder[0]
        
        # File operations
        local_path = os.path.join(APP_ROOT, folder_id, file.filename)
        file.save(local_path)
        
        # S3 upload with automatic retries
        s3_key = f"{folder_name}/{file.filename}"
        try:
            s3_wrapper.upload_file(local_path, s3_key)
            file_reference = s3_key
            message = "File uploaded to cloud"
        except S3RetryableError as e:
            logger.error(f"Cloud upload failed (transient): {e}")
            file_reference = f"/static/{folder_id}/{file.filename}"
            message = "File uploaded locally (cloud temporarily unavailable)"
        except S3PermanentError as e:
            logger.error(f"Cloud upload failed (permanent): {e}")
            file_reference = f"/static/{folder_id}/{file.filename}"
            message = "File uploaded locally"
        
        # Database insert
        cursor.execute(
            "INSERT INTO files(file, folder_id, status, file_type, file_name) "
            "VALUES(%s, %s, %s, %s, %s)",
            (file_reference, folder_id, 'Uploaded', os.path.splitext(file.filename)[1], file.filename)
        )
        conn.commit()
        
        return render_template("user_msg.html", message=message)
    
    except S3PermanentError as e:
        return render_template("user_msg.html", message=f"Upload failed: {str(e)[:100]}")
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        return render_template("user_msg.html", message="Database error")
```

### Retry Backoff Example
```
Retry Attempt 1:
  Upload fails with ThrottlingException
  Wait 1 second
  
Retry Attempt 2:
  Upload fails with ServiceUnavailable
  Wait 2 seconds (exponential)
  
Retry Attempt 3:
  Upload fails with ServiceUnavailable
  Wait up to 10 seconds (capped)
  
Retry Attempt 4:
  Upload fails with RequestTimeout
  Max retries (3) exhausted
  Raise S3RetryableError
  
Caller catches S3RetryableError and:
  - Falls back to local storage
  - Shows user message: "cloud unavailable"
  - Stores file locally
```

---

## PATTERN 5: Route Protection with Safe Route Decorator

### Current Code (FRAGILE)
```python
# main.py - Each route handles errors differently (or not at all)
@app.route("/user_home")
@login_required
def user_home():
    user_id = session['user_id']
    # If this fails, user sees 500 error with traceback
    cursor.execute("select * from users where user_id='"+str(user_id)+"'")
    users = cursor.fetchall()
    return render_template("user_home.html", user=users[0])
```

### PROPOSED Pattern
```python
# error_handlers.py
from flask import render_template
import uuid

def safe_route(on_error_render='index.html', status_code=500):
    """
    Decorator for Flask routes - comprehensive error handling
    Catches all exceptions, logs them, renders error template
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            
            except DatabaseConnectionError as e:
                logger.error(f"DB Connection error in {func.__name__}: {e}", exc_info=True)
                error_id = generate_error_id()
                return render_template(
                    on_error_render,
                    message="Database connection error. Please try again.",
                    error_id=error_id
                ), 503
            
            except DatabaseIntegrityError as e:
                logger.warning(f"Integrity error in {func.__name__}: {e}")
                return render_template(
                    on_error_render,
                    message="Operation failed - duplicate or invalid data.",
                    error_id=generate_error_id()
                ), 400
            
            except S3RetryableError as e:
                logger.warning(f"S3 transient error in {func.__name__}: {e}")
                return render_template(
                    on_error_render,
                    message="Cloud storage temporarily unavailable. Please try again.",
                    error_id=generate_error_id()
                ), 503
            
            except S3PermanentError as e:
                logger.error(f"S3 permanent error in {func.__name__}: {e}")
                return render_template(
                    on_error_render,
                    message="Cloud storage operation failed.",
                    error_id=generate_error_id()
                ), 400
            
            except DatabaseError as e:
                logger.error(f"Database error in {func.__name__}: {e}", exc_info=True)
                return render_template(
                    on_error_render,
                    message="Database error. Please contact support.",
                    error_id=generate_error_id()
                ), 500
            
            except ValueError as e:
                logger.warning(f"Validation error in {func.__name__}: {e}")
                return render_template(
                    on_error_render,
                    message=f"Invalid input: {str(e)[:100]}",
                    error_id=generate_error_id()
                ), 400
            
            except Exception as e:
                logger.critical(f"Unexpected error in {func.__name__}: {type(e).__name__}: {e}",
                               exc_info=True)
                return render_template(
                    on_error_render,
                    message="An unexpected error occurred. Support has been notified.",
                    error_id=generate_error_id()
                ), 500
        
        return wrapper
    return decorator

def generate_error_id():
    """Generate unique error ID for support reference"""
    return str(uuid.uuid4())[:8].upper()

# Usage in main.py
@app.route("/user_home")
@login_required
@safe_route(on_error_render='index.html')
def user_home():
    user_id = session['user_id']
    
    conn = db_pool.get_connection()
    cursor = conn.cursor()
    
    # If this fails, @safe_route catches it and renders friendly error
    cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        raise ValueError("User not found")
    
    return render_template("user_home.html", user=user)
```

### Error Response Examples
```
DatabaseConnectionError:
  Status: 503 Service Unavailable
  Message: "Database connection error. Please try again."
  Error ID: "A7F3B2E1" (for support reference)

DatabaseIntegrityError (duplicate):
  Status: 400 Bad Request
  Message: "Operation failed - duplicate or invalid data."
  Error ID: "X9K2M5L7"

S3RetryableError:
  Status: 503 Service Unavailable
  Message: "Cloud storage temporarily unavailable. Please try again."
  Error ID: "Q6W1E8R3"

Unexpected Exception:
  Status: 500 Internal Server Error
  Message: "An unexpected error occurred. Support has been notified."
  Error ID: "Z2X5C9V4"
```

---

## PATTERN 6: Connection Monitoring

### PROPOSED Pattern
```python
# connection_monitor.py
import threading
import time
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionMonitor:
    """Background thread monitoring database connection pool health"""
    
    def __init__(self, db_pool, check_interval=60):
        self.pool = db_pool
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.last_check = None
        self.failures = 0
        self.total_checks = 0
    
    def start(self):
        """Start background health check"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(
            target=self._health_loop,
            daemon=True,
            name="DBHealthCheck"
        )
        self.thread.start()
        logger.info("Connection monitor started (interval=%ds)", self.check_interval)
    
    def stop(self):
        """Stop health check"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Connection monitor stopped")
    
    def _health_loop(self):
        """Continuous health check loop"""
        while self.running:
            try:
                self._check_health()
            except Exception as e:
                logger.error(f"Health check exception: {e}", exc_info=True)
            
            time.sleep(self.check_interval)
    
    def _check_health(self):
        """Execute single health check"""
        self.total_checks += 1
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            
            self.last_check = datetime.now()
            logger.debug(f"Health check OK (total: {self.total_checks})")
        
        except Exception as e:
            self.failures += 1
            logger.error(
                f"Health check failed: {e} "
                f"(failures: {self.failures}/{self.total_checks})"
            )
            
            failure_rate = self.failures / self.total_checks
            if failure_rate > 0.5:
                logger.critical(
                    f"ALERT: High failure rate {failure_rate:.1%} "
                    f"({self.failures}/{self.total_checks})"
                )
    
    def get_status(self):
        """Return monitoring status"""
        return {
            'last_check': self.last_check.isoformat() if self.last_check else None,
            'total_checks': self.total_checks,
            'failures': self.failures,
            'failure_rate': self.failures / self.total_checks if self.total_checks > 0 else 0,
            'is_healthy': (self.failures / self.total_checks < 0.1) if self.total_checks > 5 else True
        }

# Usage in main.py
monitor = ConnectionMonitor(db_pool, check_interval=60)

@app.before_first_request
def startup():
    monitor.start()

@app.teardown_appcontext
def shutdown(exception=None):
    monitor.stop()

@app.route("/health")
def health_check():
    """Monitoring endpoint"""
    return jsonify(monitor.get_status())
```

---

## Implementation Order

1. **Install dependencies**
   ```bash
   pip install DBUtils tenacity pymysql boto3 botocore python-dotenv
   ```

2. **Create files in order:**
   - `db_connection.py` (DatabasePool)
   - `error_handlers.py` (Custom exceptions, decorators)
   - `s3_operations.py` (S3OperationWrapper)
   - `connection_monitor.py` (ConnectionMonitor)
   - Update `main.py` (Use new patterns)

3. **Test incrementally:**
   - Test pool with concurrent requests
   - Test error handling with network failures
   - Test S3 retries
   - Load test entire application

---

## Key Takeaways

| Pattern | Problem | Solution | Impact |
|---------|---------|----------|--------|
| Pool | Global mutable connection | DBUtils + singleton | Thread-safe, scalable |
| Retry | Network failures are permanent | Exponential backoff decorator | Resilient, user-friendly |
| Parameterize | SQL injection vulnerability | Use %s placeholders | Security |
| Classify | Wrong error recovery | Retryable vs permanent | Efficient, correct |
| Monitor | Blind to issues | Background health check | Proactive alerting |
| Protect | Inconsistent error handling | Universal @safe_route decorator | Consistent UX |

