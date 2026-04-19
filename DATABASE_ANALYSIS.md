# MiniDropBox: Database Connection & Error Handling Analysis

## Executive Summary
Current implementation has **CRITICAL production issues**: global connection object (unsafe for concurrent requests), minimal error handling (generic exceptions), and S3 operations with no retry logic or timeout management.

---

## 1. DATABASE CONNECTION ISSUES

### Issue #1: Global Connection Object (UNSAFE FOR PRODUCTION)

| Property | Details |
|----------|---------|
| **Issue Type** | Thread Safety / Concurrency Violation |
| **Current Pattern** | **Lines 19-21** |
| **Current Code** | `conn = pymysql.connect(...)`<br/>`cursor = conn.cursor()` |
| **Problem** | Global mutable objects shared across all requests<br/>Flask handles multiple concurrent requests<br/>Multiple threads access/modify same connection<br/>Race conditions on cursor operations<br/>Connection state corruption |
| **Risk Level** | CRITICAL |
| **Failure Modes** | - Lost transactions<br/>- Data corruption<br/>- Query timeout cascades<br/>- Connection pool exhaustion<br/>- Thread deadlocks |

### Issue #2: Inadequate Connection Recovery

| Property | Details |
|----------|---------|
| **Issue Type** | Connection Management |
| **Current Pattern** | **Lines 26-35** (`init_db_connection()`) |
| **Current Code** | `conn.ping(reconnect=True)` with catch-all exceptions<br/>Recreates connection on any error<br/>No backoff strategy<br/>Silent recovery |
| **Problems** | - Swallows real errors<br/>- No logging of failures<br/>- Aggressive reconnection spikes database<br/>- Doesn't validate cursor state<br/>- Connection leaks possible |
| **Risk Level** | HIGH |

### Issue #3: No Connection Pooling

| Property | Details |
|----------|---------|
| **Issue Type** | Resource Management |
| **Current Pattern** | One-off connection per app lifecycle |
| **Current Code** | Single `pymysql.connect()` call at startup |
| **Problems** | - No connection reuse optimization<br/>- Network overhead on reconnection<br/>- No idle timeout management<br/>- Connections hang after network partitions<br/>- Cannot handle connection state variations |
| **Risk Level** | HIGH |

### Proposed Solution: Thread-Safe Connection Pool

```python
# Pattern: DBUtils-based connection pooling
from DBUtils.PooledDB import PooledDB

class DatabasePool:
    """Thread-safe, pooled MySQL connections with monitoring"""
    
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
            mincached=2,                  # Min idle connections
            maxcached=5,                  # Max idle connections
            maxshared=3,                  # Max concurrent shared connections
            blocking=True,                # Wait if no connection available
            maxusage=None,                # Reuse connections indefinitely
            setsession=[],                # Auto-execute on connection
            ping=1,                       # Check connection health (0=never, 1=on cursor)
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
        """Returns connection from pool (thread-safe)"""
        try:
            conn = self.pool.connection()
            return conn
        except Exception as e:
            logger.error(f"Pool connection failed: {e}")
            raise
    
    def execute_query(self, query, params=None, fetch_type='all'):
        """Executes query with automatic connection management"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            
            if fetch_type == 'one':
                return cursor.fetchone()
            elif fetch_type == 'all':
                return cursor.fetchall()
            else:
                return cursor.rowcount
        finally:
            if conn:
                conn.close()  # Returns to pool, doesn't close

# Usage in Flask:
db_pool = DatabasePool()

@app.before_request
def before_request():
    # No longer need init_db_connection()
    # Connections are managed by pool
    pass
```

---

## 2. ERROR HANDLING IN DATABASE OPERATIONS

### Issue #4: Inconsistent Query Parameter Handling

| Property | Details |
|----------|---------|
| **Issue Type** | Security / Code Quality |
| **Current Pattern** | Mixed approaches across codebase |
| **Examples** | **Lines 162-164** (SQL injection):<br/>`"select * from users where email = '" + str(email) + "'"`<br/><br/>**Line 510** (parameterized):<br/>`cursor.execute("select * from files where file_id = %s", (file_id,))` |
| **Problems** | - SQL injection vulnerabilities<br/>- Inconsistent error handling<br/>- No input validation<br/>- String parsing errors<br/>- Null pointer exceptions |
| **Risk Level** | CRITICAL |

### Issue #5: Missing Error Handling in Database Operations

| Property | Details |
|----------|---------|
| **Issue Type** | Exception Handling |
| **Lines with Gap** | Multiple: 162-164, 180, 251, 277, 284, 313, 349, 393, 422, 457, etc. |
| **Current Pattern** | Most operations have **ZERO error handling** |
| **Example** | **Lines 180-182**: No try-catch<br/>`cursor.execute(...)`<br/>`conn.commit()` |
| **Specific Gaps** | - No `pymysql.IntegrityError` for duplicates<br/>- No `pymysql.OperationalError` for connection loss<br/>- No `pymysql.DatabaseError` for syntax errors<br/>- No timeout exceptions<br/>- No constraint violations<br/>- No transaction rollback |
| **Risk Level** | CRITICAL |

### Issue #6: Inconsistent Error Recovery

| Property | Details |
|----------|---------|
| **Issue Type** | Error Recovery Pattern |
| **Inconsistent Use** | **Lines 510-512**: Only ONE function has recovery<br/>`except pymysql.err.OperationalError:`<br/>`    init_db_connection()` |
| **Problem** | Only `download_file()` recovers from connection loss<br/>Other functions fail silently or crash<br/>No standard error recovery pattern<br/>User sees raw error pages |
| **Risk Level** | HIGH |

### Proposed Solution: Standardized Error Handling Pattern

```python
from functools import wraps
import pymysql
from pymysql import err as pymysql_errors
import logging

logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom DB exception for application logic"""
    pass

class DatabaseConnectionError(DatabaseError):
    pass

class DatabaseIntegrityError(DatabaseError):
    pass

def handle_db_errors(max_retries=2, backoff_multiplier=1.0):
    """
    Decorator for database operation error handling
    Implements exponential backoff + retry logic
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            retry_count = 0
            wait_time = 0.5  # Start with 500ms
            
            while retry_count <= max_retries:
                try:
                    return func(*args, **kwargs)
                
                except pymysql_errors.OperationalError as e:
                    # Connection lost, lock wait timeout, etc.
                    last_exception = e
                    logger.warning(f"OperationalError (retry {retry_count+1}): {e}")
                    
                    if retry_count < max_retries:
                        time.sleep(wait_time)
                        wait_time *= backoff_multiplier
                        retry_count += 1
                    else:
                        raise DatabaseConnectionError(
                            f"Connection failed after {max_retries} retries"
                        ) from e
                
                except pymysql_errors.IntegrityError as e:
                    # Duplicate key, foreign key violation, etc.
                    logger.error(f"Integrity violation: {e}")
                    raise DatabaseIntegrityError(str(e)) from e
                
                except pymysql_errors.DatabaseError as e:
                    # General database errors
                    logger.error(f"Database error: {e}")
                    raise DatabaseError(str(e)) from e
                
                except pymysql_errors.ProgrammingError as e:
                    # SQL syntax errors - don't retry
                    logger.error(f"Programming error (SQL syntax?): {e}")
                    raise DatabaseError(f"Query syntax error: {e}") from e
                
                except Exception as e:
                    # Unexpected errors
                    logger.error(f"Unexpected error: {type(e).__name__}: {e}")
                    raise
            
            raise last_exception
        
        return wrapper
    return decorator

# Usage:
@handle_db_errors(max_retries=2, backoff_multiplier=1.5)
def safe_query_user(user_id):
    """Example: safely query user with error handling & retry"""
    query = "SELECT * FROM users WHERE user_id = %s"
    try:
        conn = db_pool.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        return result
    except DatabaseIntegrityError:
        return None  # User doesn't exist
    except DatabaseConnectionError:
        logger.critical("Database connection failed after retries")
        raise  # Re-raise for route handler
```

---

## 3. AWS S3 ERROR HANDLING

### Issue #7: No Retry Logic or Timeout Management

| Property | Details |
|----------|---------|
| **Issue Type** | Resilience / Error Handling |
| **Current Pattern** | **Lines 59-94** (all S3 functions) |
| **Current Code** | Simple try-except with print statements<br/>No retry on transient errors<br/>No timeout configuration<br/>Returns boolean instead of error details |
| **Problems** | - Network timeouts fail instantly<br/>- Rate limiting (HTTP 503) not handled<br/>- Transient errors not retried<br/>- No exponential backoff<br/>- CloudFront cache issues ignored<br/>- Multipart upload failures silent |
| **Risk Level** | CRITICAL |

### Issue #8: S3 Operations Lack Specific Error Handling

| Property | Details |
|----------|---------|
| **Issue Type** | Specific Exception Handling |
| **Current Pattern** | `except Exception as e:` (catch-all) |
| **Lines** | 65, 73, 85, 95 |
| **Missing Handlers** | - `botocore.exceptions.ClientError` (S3 API errors)<br/>- `botocore.exceptions.ConnectionError` (network)<br/>- `botocore.exceptions.Waiter.WaiterError` (retry exhausted)<br/>- `botocore.exceptions.HTTPClientError` (HTTP 500/503)<br/>- `concurrent.futures.TimeoutError`<br/>- `socket.timeout`<br/>- Invalid bucket/key scenarios |
| **Risk Level** | HIGH |

### Issue #9: No Timeout Configuration for Boto3

| Property | Details |
|----------|---------|
| **Issue Type** | Resource Management |
| **Current Pattern** | **Lines 149-171**: S3 client initialization |
| **Missing** | No timeout configuration in boto3 config<br/>Default timeouts may be too long (60s)<br/>Connection pool limits not set<br/>Retry mode not configured |
| **Risk Level** | HIGH |

### Proposed Solution: S3 Operations with Retry Logic

```python
from botocore.exceptions import ClientError, ConnectionError as BotoConnectionError
from botocore.client import BaseClient
import boto3
from botocore.config import Config
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time

class S3Error(Exception):
    """Custom S3 exception"""
    pass

class S3RetryableError(S3Error):
    """Transient error that can be retried"""
    pass

class S3PermanentError(S3Error):
    """Permanent error that shouldn't be retried"""
    pass

class S3OperationWrapper:
    """Wraps S3 operations with retry logic, timeouts, and error handling"""
    
    def __init__(self, bucket_name, region, max_retries=3, timeout_seconds=30):
        self.bucket = bucket_name
        self.region = region
        self.max_retries = max_retries
        self.timeout = timeout_seconds
        
        # Enhanced config with timeouts & retries
        config = Config(
            signature_version='s3v4',
            s3={'addressing_style': 'virtual'},
            retries={'max_attempts': max_retries},
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            max_pool_connections=20,
            region_name=region
        )
        
        self.client = boto3.client(
            's3',
            region_name=region,
            config=config
        )
    
    @staticmethod
    def _classify_s3_error(error):
        """Classify S3 errors as retryable or permanent"""
        
        # Transient errors (retryable)
        retryable_codes = {
            'RequestTimeout',      # Timeout
            'ServiceUnavailable',  # HTTP 503
            'ThrottlingException', # Rate limited
            'SlowDown',           # Rate limited (upload)
            'ProviderError',      # Provider error
            'RequestLimitExceeded' # Too many requests
        }
        
        # Permanent errors (don't retry)
        permanent_codes = {
            'InvalidBucket',
            'NoSuchBucket',
            'NoSuchKey',
            'AccessDenied',
            'InvalidAccessKeyId',
            'SignatureDoesNotMatch',
            'NotImplemented'
        }
        
        error_code = error.response.get('Error', {}).get('Code', '')
        
        if error_code in retryable_codes:
            return 'retryable'
        elif error_code in permanent_codes:
            return 'permanent'
        else:
            return 'unknown'
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(S3RetryableError),
        reraise=True
    )
    def upload_file(self, local_path, s3_key):
        """
        Upload file with retry logic
        
        Raises:
            S3RetryableError: Transient error (will retry)
            S3PermanentError: Permanent error (won't retry)
        """
        try:
            logger.info(f"Uploading {local_path} to s3://{self.bucket}/{s3_key}")
            
            self.client.upload_file(
                local_path,
                self.bucket,
                s3_key,
                Config=TransferConfig(
                    max_concurrency=5,
                    max_io_queue_size=100,
                    max_in_memory_upload_chunks=10,
                    multipart_threshold=32*1024*1024,  # 32MB
                    multipart_chunksize=16*1024*1024,  # 16MB chunks
                ),
                ExtraArgs={
                    'ContentType': self._guess_content_type(local_path)
                }
            )
            
            logger.info(f"Successfully uploaded to {s3_key}")
            return True
            
        except ClientError as e:
            error_type = self._classify_s3_error(e)
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if error_type == 'retryable':
                logger.warning(f"Retryable S3 error [{error_code}]: {error_msg}")
                raise S3RetryableError(f"{error_code}: {error_msg}") from e
            else:
                logger.error(f"Permanent S3 error [{error_code}]: {error_msg}")
                raise S3PermanentError(f"{error_code}: {error_msg}") from e
        
        except BotoConnectionError as e:
            logger.warning(f"S3 connection error (retryable): {e}")
            raise S3RetryableError(f"Connection failed: {e}") from e
        
        except TimeoutError as e:
            logger.warning(f"S3 timeout (retryable): {e}")
            raise S3RetryableError(f"Operation timeout: {e}") from e
        
        except Exception as e:
            logger.error(f"Unexpected S3 error: {type(e).__name__}: {e}")
            raise S3PermanentError(f"Unexpected error: {e}") from e
    
    def delete_object(self, s3_key):
        """Delete S3 object with error handling"""
        try:
            logger.info(f"Deleting s3://{self.bucket}/{s3_key}")
            self.client.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info(f"Successfully deleted {s3_key}")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.warning(f"Object already deleted: {s3_key}")
                return True  # Idempotent
            raise S3PermanentError(str(e)) from e
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            raise S3PermanentError(str(e)) from e
    
    def generate_presigned_url(self, s3_key, expiry_seconds=3600):
        """Generate presigned URL with validation"""
        try:
            if not s3_key:
                raise S3PermanentError("Empty S3 key provided")
            
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_key},
                ExpiresIn=expiry_seconds,
                HttpMethod='GET'
            )
            logger.info(f"Generated presigned URL for {s3_key}")
            return url
        except ClientError as e:
            logger.error(f"Presigned URL generation failed: {e}")
            raise S3PermanentError(str(e)) from e
    
    @staticmethod
    def _guess_content_type(file_path):
        """Guess MIME type from file extension"""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'


# Usage in Flask routes:
s3_wrapper = S3OperationWrapper(User_bucket, AWS_BUCKET_REGION)

@app.route("/upload_file1", methods=['post'])
@login_required
@handle_db_errors()
def upload_file1():
    file = request.files.get("files_name")
    folder_id = request.form.get("folder_id")
    
    try:
        # DB operation
        cursor.execute(
            "SELECT * FROM folders WHERE folder_id = %s AND user_id = %s",
            (folder_id, session['user_id'])
        )
        folder = cursor.fetchone()
        if not folder:
            return render_template("user_msg.html", message="Folder not found")
        
        # File upload
        local_path = os.path.join(APP_ROOT, folder_id, file.filename)
        file.save(local_path)
        
        # S3 upload with retries
        s3_key = f"{folder[1]}/{file.filename}"
        try:
            s3_wrapper.upload_file(local_path, s3_key)
            file_reference = s3_key
        except S3RetryableError as e:
            logger.error(f"S3 upload failed after retries: {e}")
            file_reference = f"/static/{folder_id}/{file.filename}"
        except S3PermanentError as e:
            logger.error(f"S3 upload permanent failure: {e}")
            file_reference = f"/static/{folder_id}/{file.filename}"
        
        # DB insert
        cursor.execute(
            "INSERT INTO files(file, folder_id, status, file_type, file_name) "
            "VALUES(%s, %s, %s, %s, %s)",
            (file_reference, folder_id, 'Uploaded', os.path.splitext(file.filename)[1], file.filename)
        )
        conn.commit()
        
        return render_template("user_msg.html", message="File uploaded successfully")
    
    except S3PermanentError as e:
        return render_template("user_msg.html", message=f"Upload failed: {str(e)[:100]}")
    except DatabaseError as e:
        logger.error(f"Database error: {e}")
        return render_template("user_msg.html", message="Database error during upload")
```

---

## 4. ERROR HANDLING DECORATOR PATTERN

### Proposed Solution: Comprehensive Error Handler

```python
from flask import jsonify
import traceback
from typing import Callable, Any

def safe_route(on_error_render='index.html', on_error_message=None):
    """
    Decorator for Flask routes - comprehensive error handling
    
    Args:
        on_error_render: Template to render on error
        on_error_message: Default error message
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            
            except DatabaseConnectionError as e:
                logger.error(f"DB Connection error in {func.__name__}: {e}")
                logger.error(traceback.format_exc())
                return render_template(
                    on_error_render,
                    message="Database connection error. Please try again.",
                    error_id=generate_error_id()
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
                logger.error(f"Database error in {func.__name__}: {e}")
                return render_template(
                    on_error_render,
                    message=on_error_message or "Database operation failed.",
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
                logger.critical(f"Unexpected error in {func.__name__}: {e}")
                logger.critical(traceback.format_exc())
                return render_template(
                    on_error_render,
                    message="An unexpected error occurred. Please contact support.",
                    error_id=generate_error_id()
                ), 500
        
        return wrapper
    return decorator

def generate_error_id():
    """Generate unique error ID for user support reference"""
    import uuid
    return str(uuid.uuid4())[:8].upper()
```

---

## 5. CONNECTION MONITORING & HEALTH CHECKS

### Proposed Solution: Connection Health Monitor

```python
import threading
import time
from datetime import datetime

class ConnectionMonitor:
    """Monitors database connection pool health"""
    
    def __init__(self, pool: DatabasePool, check_interval=60):
        self.pool = pool
        self.check_interval = check_interval
        self.running = False
        self.thread = None
        self.last_check = None
        self.connection_failures = 0
        self.total_checks = 0
    
    def start(self):
        """Start background health check thread"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self.thread.start()
        logger.info("Connection monitor started")
    
    def stop(self):
        """Stop health check thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Connection monitor stopped")
    
    def _health_check_loop(self):
        """Periodic health check loop"""
        while self.running:
            try:
                self._check_connection_health()
            except Exception as e:
                logger.error(f"Health check failed: {e}")
            
            time.sleep(self.check_interval)
    
    def _check_connection_health(self):
        """Test pool connection health"""
        self.total_checks += 1
        
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            
            if result:
                self.last_check = datetime.now()
                logger.debug(f"Connection health OK ({self.total_checks} total checks)")
            else:
                raise Exception("Health check query returned no result")
        
        except Exception as e:
            self.connection_failures += 1
            logger.error(
                f"Connection health check FAILED: {e} "
                f"({self.connection_failures} failures / {self.total_checks} total)"
            )
            
            # Alert if failure rate > 50%
            if self.total_checks >= 5 and (self.connection_failures / self.total_checks) > 0.5:
                logger.critical("High database connection failure rate detected!")
                # Could send alert notification here
    
    def get_status(self):
        """Get connection pool status"""
        return {
            'last_check': self.last_check,
            'total_checks': self.total_checks,
            'failures': self.connection_failures,
            'failure_rate': (
                self.connection_failures / self.total_checks
                if self.total_checks > 0 else 0
            )
        }

# Usage:
monitor = ConnectionMonitor(db_pool, check_interval=60)

@app.before_first_request
def startup():
    monitor.start()

@app.teardown_appcontext
def shutdown(exception):
    monitor.stop()

@app.route("/health")
def health_check():
    """API endpoint for monitoring"""
    status = monitor.get_status()
    return jsonify(status)
```

---

## 6. SUMMARY TABLE: Issues & Solutions

| # | Issue Type | Current Pattern | Priority | Severity | Solution Pattern |
|---|---|---|---|---|---|
| 1 | Global Connection | Single global `conn` object | CRITICAL | CRITICAL | Use `DBUtils.PooledDB` with singleton |
| 2 | Connection Recovery | Catch-all in `init_db_connection()` | CRITICAL | HIGH | Implement exponential backoff retry |
| 3 | No Connection Pool | Reconnect on each failure | HIGH | HIGH | Implement pooling with min/max connections |
| 4 | SQL Injection | String concatenation queries | CRITICAL | CRITICAL | Parameterized queries with %s placeholders |
| 5 | No DB Error Handling | Zero error handling on most queries | CRITICAL | CRITICAL | Use `@handle_db_errors()` decorator |
| 6 | Inconsistent Recovery | Only 1 function recovers errors | HIGH | HIGH | Standardize with decorator pattern |
| 7 | S3 No Retries | Simple try-catch, no retry logic | CRITICAL | HIGH | Use `tenacity.retry()` with backoff |
| 8 | S3 Generic Errors | Catch-all exception handling | HIGH | HIGH | Classify errors (retryable vs permanent) |
| 9 | No S3 Timeouts | No timeout configuration | HIGH | HIGH | Set connect/read timeout in boto3 config |
| 10 | No Monitoring | Zero connection/operation monitoring | MEDIUM | MEDIUM | Implement `ConnectionMonitor` thread |

---

## 7. IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Week 1-2)
- [ ] Install `DBUtils`, `tenacity` packages
- [ ] Create `DatabasePool` singleton class
- [ ] Create `S3OperationWrapper` with retry logic
- [ ] Create error decorator functions
- [ ] Create logging configuration

### Phase 2: Integration (Week 2-3)
- [ ] Replace global `conn`/`cursor` with pool
- [ ] Apply `@handle_db_errors()` to all database routes
- [ ] Replace all S3 functions with wrapper
- [ ] Add `@safe_route()` decorator to all routes
- [ ] Test with concurrent load

### Phase 3: Monitoring (Week 3-4)
- [ ] Implement `ConnectionMonitor`
- [ ] Add health check endpoint
- [ ] Set up error logging/alerting
- [ ] Add metrics collection

### Phase 4: Validation (Week 4)
- [ ] Load testing with concurrent users
- [ ] Chaos testing (network failures, timeouts)
- [ ] Security audit (SQL injection tests)
- [ ] Production readiness checklist

---

## Dependencies Required

```
DBUtils==1.3.2
tenacity==8.2.3
pymysql==1.1.0
boto3==1.28.0
botocore==1.31.0
python-dotenv==1.0.0
```

---

## Key Metrics to Monitor

1. **Connection Pool**
   - Active connections
   - Idle connections
   - Connection failures/retries
   - Average wait time

2. **Database Operations**
   - Query execution time
   - Failed queries (by type)
   - Retry attempts (success rate)
   - Transaction rollback rate

3. **S3 Operations**
   - Upload/download success rate
   - Retry rate
   - Average latency
   - Timeout incidents

4. **Application Health**
   - Error rate by type
   - Request latency
   - Database availability %
   - S3 availability %
