# MiniDropBox - Secure File Management Application

**Production-ready secure file sharing platform** with enterprise-grade security, connection pooling, comprehensive error handling, and audit logging.

MiniDropBox is a feature-rich file sharing application that facilitates secure file upload, download, sharing, deletion, recovery, and remote access. Built with Python Flask 3.0.0 and MySQL with production-grade security hardening, connection pooling, and comprehensive audit logging.

<img width="1536" height="1024" alt="CloudArchitecture" src="https://github.com/user-attachments/assets/a6390873-6d4b-48a0-a2a2-5dcf5dcadc14" />

## Key Features

### Core Functionality
- ✅ **User Management**: Secure registration, login, and profile management
- ✅ **File Management**: Upload, download, delete, recover (recycle bin), and bulk operations
- ✅ **Folder Organization**: Create, manage, and organize files in folders
- ✅ **File Sharing**: Share files/folders with other users with access controls
- ✅ **User Messaging**: Built-in messaging system for user communication
- ✅ **Storage Quotas**: Per-user 1GB storage limit with usage tracking

### Security & Reliability
- 🔒 **SQL Injection Prevention**: All 26+ database queries use parameterized statements with %s placeholders
- 🔐 **Password Hashing**: werkzeug pbkdf2:sha256 with 600,000 iterations
- ✅ **Input Validation**: 8 comprehensive validators for email, password, filename, phone, name validation
- 🛡️ **Connection Pooling**: Thread-safe PooledDB with configurable min/max connections
- 📊 **Error Handling**: 6 custom exception types with consistent error responses via @safe_route decorator
- 📝 **Audit Logging**: Comprehensive audit trail with rotating log files (minidropbox.log)
- 🔄 **AWS S3 Retry Logic**: Exponential backoff with max 3 attempts for transient failures

### Supported File Types (40+ formats)
**Video**: .mp4, .avi, .mov, .mkv
**Audio**: .mp3, .wav, .aac, .flac
**Images**: .png, .jpg, .jpeg, .gif, .bmp, .webp
**Documents**: .pdf, .txt, .doc, .docx, .xls, .xlsx, .csv, .ppt, .pptx
**Archives**: .zip, .rar, .7z, .tar, .gz
**Code**: .py, .js, .html, .css, .json, .xml, .sql


## Quick Start (Local Development)

### Prerequisites
- Python 3.8+ ([Download](https://www.python.org/downloads/))
- MySQL 8.0+ ([Download](https://dev.mysql.com/downloads/mysql/))

### Installation

Clone the repository:
```bash
git clone https://github.com/KrishReigns/MiniDropBox.git
cd MiniDropBox
```

### Set Up Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Database Setup

1. **Create MySQL database**:
```bash
mysql -u root -p
```

```sql
CREATE DATABASE MiniDropbox;
```

2. **Initialize schema**:
```bash
mysql -u root -p MiniDropbox < schema.sql
```

3. **Set MySQL root password** (if needed):
```bash
ALTER USER 'root'@'localhost' IDENTIFIED BY 'password';
FLUSH PRIVILEGES;
```

### Configure Environment Variables

Create a `.env` file in the project root:

```env
# Flask Configuration
FLASK_ENV=development
FLASK_APP=main.py
SECRET_KEY=your_secret_key_here_change_this

# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_NAME=MiniDropbox
DB_USER=root
DB_PASSWORD=password
DB_CONNECTION_TIMEOUT=30
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

# AWS S3 Configuration (Optional - if using S3)
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
AWS_DEFAULT_REGION=us-east-1
AWS_BUCKET_NAME=your_s3_bucket_name
AWS_BUCKET_REGION=us-east-1

# AWS SES Configuration (Optional - if using email)
AWS_SES_REGION=us-east-1
```

### Run the Application

```bash
python main.py
```

Open your browser and visit: **http://localhost:5001**

## Architecture & Components

### Project Structure
```
MiniDropBox/
├── main.py                 # Flask application (26 routes)
├── config.py               # Configuration & constants (40+ settings)
├── db_operations.py        # Database connection pool management
├── s3_operations.py        # AWS S3 operations with retry logic
├── error_handlers.py       # Error handling & audit logging
├── validators.py           # Input validation & password hashing
├── schema.sql              # Database schema initialization
├── requirements.txt        # Python dependencies
├── templates/              # HTML templates
├── static/                 # CSS & JavaScript assets
└── minidropbox.log         # Application logs (rotating)
```

### Core Dependencies
- **Flask 3.0.0**: Web framework
- **PyMySQL 1.1.0**: MySQL database driver with parameterized queries
- **DBUtils 1.3**: Connection pooling (PooledDB)
- **werkzeug 3.0.0**: Password hashing (pbkdf2:sha256:600000 iterations)
- **tenacity 8.2.3**: Retry logic for S3 operations
- **boto3 1.28.0**: AWS S3 & SES integration
- **python-dotenv 1.0.0**: Environment configuration

### Database Schema

**users** - User authentication & profile
- user_id, name, email, phone, password (hashed), registration_date

**files** - File metadata
- file_id, user_id, folder_id, file_name, file_type, file_size, storage_location, status (Uploaded/Recycle Bin/Permanent Delete), created_at, updated_at

**folders** - Folder hierarchy
- folder_id, user_id, folder_name, parent_folder_id, created_at

**storage_quotas** - Per-user quota tracking
- quota_id, user_id, quota_bytes (1GB default), used_bytes, created_at

**activity_logs** - Audit trail
- log_id, user_id, action, resource_type, resource_id, details (JSON), ip_address, user_agent, timestamp

**file_shares** - File sharing permissions
- share_id, file_id, shared_by_user_id, shared_to_user_id, permission_level, created_at

## Security Features

### SQL Injection Prevention
All database queries use parameterized statements:
```python
# ✅ Secure - uses parameterized query
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))

# ❌ Insecure - DO NOT USE
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")
```

### Password Security
```python
# Password hashing with pbkdf2:sha256:600000 iterations
from validators import hash_password, verify_password

hashed = hash_password("MyPassword123!")
# Output: pbkdf2:sha256:600000$salt$hash...

is_valid = verify_password("MyPassword123!", hashed)  # True
```

### Input Validation
All user inputs validated before database operations:
```python
- validate_email()      # RFC 5322 compliant, 5-254 chars
- validate_password()   # Min 6 chars
- validate_phone()      # 10-15 digits
- validate_name()       # Alphanumeric + spaces, 2-100 chars
- validate_filename()   # No null/slashes/pipes/brackets, max 255 chars
- validate_foldername() # Same as filename, max 100 chars
- validate_file_size()  # Max 5GB
- sanitize_input()      # Remove/escape dangerous characters
```

### Error Handling
6 custom exception types with consistent HTTP responses:
```python
- AuthenticationError    (401) - Login failures
- ValidationError        (400) - Input validation failures
- DatabaseError          (500) - Database operation failures
- S3Error                (503) - S3 operation failures
- ResourceNotFoundError  (404) - File/folder not found
- AuthorizationError     (403) - Permission denied
```

### Audit Logging
All operations logged with timestamp, user_id, IP address, and details:
```
2026-04-19 17:11:20,196 - root - INFO - User viewed recycle bin: 2 files found
2026-04-19 17:11:19,334 - root - ERROR - Email or phone already registered (duplicate user)
2026-04-19 17:11:20,204 - root - WARNING - User login failed - email=invalid@test.com
```

## Infrastructure Features

### Thread-Safe Connection Pooling
```python
# Automatic connection pooling with PooledDB
# Min 2 cached connections, max 5 cached, 10 overflow connections
# Automatic cleanup and reuse
```

### S3 Retry Logic
Exponential backoff for transient S3 failures:
```
Attempt 1: Wait 1 second
Attempt 2: Wait 2 seconds
Attempt 3: Wait 4 seconds
Max 3 total attempts
```

### Comprehensive Logging
4 logging functions covering all operations:
- `log_login()` - Authentication tracking
- `log_user_action_detail()` - User action audit
- `log_file_operation()` - File operation tracking
- `log_s3_operation()` - AWS S3 interaction tracking

## Testing

### Bug Bash Results ✅
```
✅ User registration/login working
✅ File upload (40+ formats supported)
✅ File download/delete/recover
✅ Folder management
✅ Recycle bin functionality
✅ SQL injection protection verified
✅ Invalid login attempts blocked
✅ Proper HTTP status codes
```

### Manual Testing
Test a file upload:
```bash
curl -X POST http://localhost:5001/upload_file1 \
  -H "Cookie: session=your_session_id" \
  -F "files_name=@test.txt" \
  -F "folder_id=1"
```

Test login with SQL injection attempt (should fail gracefully):
```bash
curl -X POST http://localhost:5001/user_login \
  -d "email='; DROP TABLE users; --&password=test"
```

## Performance & Scaling

- **Connection Pooling**: Reuse connections, reduce overhead
- **Parameterized Queries**: Prepared statements improve performance
- **S3 Retry Logic**: Automatic recovery from transient failures
- **Storage Quotas**: Prevent disk space exhaustion
- **Audit Logging**: Rotating log files prevent unbounded growth

## Deployment

### Local Development
```bash
python main.py
# Visit http://localhost:5001
```

### Production Deployment (with gunicorn)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

### Environment Configuration
- Set `FLASK_ENV=production` in `.env`
- Use strong `SECRET_KEY`
- Configure proper MySQL backups
- Enable HTTPS/SSL
- Set up CloudWatch/monitoring for logs

## Troubleshooting

### MySQL Connection Issues
```bash
# Verify MySQL is running
mysql -u root -p

# Check database exists
mysql -u root -p -e "SHOW DATABASES;"

# Verify schema
mysql -u root -p MiniDropbox -e "SHOW TABLES;"
```

### Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Verify virtual environment activated
source .venv/bin/activate
```

### Port 5001 Already in Use
```bash
# Find process using port
lsof -i :5001

# Kill process (macOS/Linux)
kill -9 <PID>
```

## License

MIT License - See LICENSE file for details

## Author

**Sai Krishna Kandula** - [GitHub Profile](https://github.com/KrishReigns)

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Commit your changes (`git commit -am 'Add feature'`)
4. Push to branch (`git push origin feature/improvement`)
5. Submit a pull request

## Support

For issues, questions, or suggestions, please open an [issue](https://github.com/KrishReigns/MiniDropBox/issues) on GitHub.
