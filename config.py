"""
MiniDropBox Configuration & Constants
Centralizes all magic numbers, configurations, and constants
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ==================== DATABASE CONFIG ====================
DB_HOST = os.getenv("RDS_HOST", "localhost")
DB_PORT = int(os.getenv("RDS_PORT", 3306))
DB_NAME = os.getenv("RDS_DBNAME", "MiniDropbox")
DB_USER = os.getenv("RDS_USERNAME", "root")
DB_PASSWORD = os.getenv("RDS_PASSWORD", "password")
DB_CONNECTION_TIMEOUT = 10  # seconds
DB_POOL_SIZE = 5  # Connection pool size
DB_MAX_OVERFLOW = 10  # Max overflow connections

# ==================== FILE OPERATIONS ====================
RECYCLE_BIN_RETENTION_DAYS = 30  # How long files stay in trash
S3_PRESIGNED_URL_EXPIRY_SECONDS = 3600  # 1 hour
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024 * 1024  # 5GB
CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks for uploads

# ==================== OTP / VERIFICATION ====================
OTP_MIN_VALUE = 1000
OTP_MAX_VALUE = 10000
OTP_VALIDITY_MINUTES = 10

# ==================== FILE TYPES ====================
FILE_TYPE_MAP = {
    # Video
    '.mp4': {'type': 'video', 'mime': 'video/mp4'},
    '.avi': {'type': 'video', 'mime': 'video/x-msvideo'},
    '.mov': {'type': 'video', 'mime': 'video/quicktime'},
    '.mkv': {'type': 'video', 'mime': 'video/x-matroska'},
    # Audio
    '.mp3': {'type': 'audio', 'mime': 'audio/mpeg'},
    '.wav': {'type': 'audio', 'mime': 'audio/wav'},
    '.aac': {'type': 'audio', 'mime': 'audio/aac'},
    '.flac': {'type': 'audio', 'mime': 'audio/flac'},
    # Image
    '.png': {'type': 'image', 'mime': 'image/png'},
    '.jpg': {'type': 'image', 'mime': 'image/jpeg'},
    '.jpeg': {'type': 'image', 'mime': 'image/jpeg'},
    '.gif': {'type': 'image', 'mime': 'image/gif'},
    '.bmp': {'type': 'image', 'mime': 'image/bmp'},
    '.webp': {'type': 'image', 'mime': 'image/webp'},
    # Document
    '.pdf': {'type': 'document', 'mime': 'application/pdf'},
    '.txt': {'type': 'document', 'mime': 'text/plain'},
    '.doc': {'type': 'document', 'mime': 'application/msword'},
    '.docx': {'type': 'document', 'mime': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'},
    '.xls': {'type': 'spreadsheet', 'mime': 'application/vnd.ms-excel'},
    '.xlsx': {'type': 'spreadsheet', 'mime': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},
    '.csv': {'type': 'spreadsheet', 'mime': 'text/csv'},
    '.ppt': {'type': 'presentation', 'mime': 'application/vnd.ms-powerpoint'},
    '.pptx': {'type': 'presentation', 'mime': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'},
    # Archive
    '.zip': {'type': 'archive', 'mime': 'application/zip'},
    '.rar': {'type': 'archive', 'mime': 'application/x-rar-compressed'},
    '.7z': {'type': 'archive', 'mime': 'application/x-7z-compressed'},
    '.tar': {'type': 'archive', 'mime': 'application/x-tar'},
    '.gz': {'type': 'archive', 'mime': 'application/gzip'},
    # Code
    '.py': {'type': 'code', 'mime': 'text/x-python'},
    '.js': {'type': 'code', 'mime': 'text/javascript'},
    '.html': {'type': 'code', 'mime': 'text/html'},
    '.css': {'type': 'code', 'mime': 'text/css'},
    '.json': {'type': 'code', 'mime': 'application/json'},
    '.xml': {'type': 'code', 'mime': 'application/xml'},
    '.sql': {'type': 'code', 'mime': 'text/x-sql'},
}

# For backwards compatibility
VIDEO_FORMATS = [".mp4", ".avi", ".mov", ".mkv"]
AUDIO_FORMATS = [".mp3", ".wav", ".aac", ".flac"]
IMAGE_FORMATS = [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]
PDF_FORMATS = [".pdf"]
DOCUMENT_FORMATS = [".txt", ".doc", ".docx"]
SPREADSHEET_FORMATS = [".xls", ".xlsx", ".csv"]
PRESENTATION_FORMATS = [".ppt", ".pptx"]
ARCHIVE_FORMATS = [".zip", ".rar", ".7z", ".tar", ".gz"]
CODE_FORMATS = [".py", ".js", ".html", ".css", ".json", ".xml", ".sql"]
ALLOWED_FORMATS = (VIDEO_FORMATS + AUDIO_FORMATS + IMAGE_FORMATS + PDF_FORMATS + 
                   DOCUMENT_FORMATS + SPREADSHEET_FORMATS + PRESENTATION_FORMATS + 
                   ARCHIVE_FORMATS + CODE_FORMATS)

# ==================== AWS CONFIG ====================
AWS_BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "userminidropbox")
AWS_BUCKET_SUFFIX = os.getenv("AWS_BUCKET_SUFFIX", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_BUCKET_REGION = os.getenv("AWS_BUCKET_REGION", AWS_REGION)
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_EMAIL_SOURCE = os.getenv("AWS_EMAIL_SOURCE", "krishna1996sai@gmail.com")
AWS_S3_TIMEOUT = 30  # seconds
AWS_S3_MAX_RETRIES = 3
AWS_SES_TIMEOUT = 10  # seconds

# ==================== VALIDATION RULES ====================
VALIDATION_RULES = {
    'email': {
        'min_length': 5,
        'max_length': 254,
        'pattern': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
    },
    'password': {
        'min_length': 6,  # Can be made stricter
        'require_uppercase': False,
        'require_number': False,
        'require_special': False,
    },
    'phone': {
        'min_length': 10,
        'max_length': 15,
        'pattern': r'^\d{10,15}$',
    },
    'name': {
        'min_length': 2,
        'max_length': 100,
        'pattern': r'^[a-zA-Z\s\-\']{2,100}$',
    },
    'filename': {
        'max_length': 255,
        'forbidden_chars': ['/', '\\', '..', '\x00', '|', '<', '>', '?', '*'],
        'pattern': r'^[^\x00/\\|<>?*]+$',  # Allow most chars except forbidden
    },
    'foldername': {
        'max_length': 100,
        'forbidden_chars': ['/', '\\', '..', '\x00', '|', '<', '>', '?', '*'],
        'pattern': r'^[^\x00/\\|<>?*]+$',  # Allow most chars except forbidden
    },
}

# ==================== STORAGE QUOTA ====================
DEFAULT_STORAGE_QUOTA_BYTES = 5 * 1024 * 1024 * 1024  # 5GB per user
STORAGE_QUOTA_TIERS = {
    'free': 5 * 1024 * 1024 * 1024,        # 5GB
    'pro': 100 * 1024 * 1024 * 1024,       # 100GB
    'business': 1 * 1024 * 1024 * 1024 * 1024,  # 1TB
}

# ==================== LOGGING ====================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "minidropbox.log")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Events to log (all important user actions)
AUDIT_EVENTS = [
    'login',
    'logout',
    'registration',
    'folder_create',
    'folder_delete',
    'file_upload',
    'file_download',
    'file_delete_trash',
    'file_delete_permanent',
    'file_recover',
    'file_share',
    'password_change',
]

# ==================== FLASK CONFIG ====================
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False") == "True"
FLASK_SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", 5001))

# ==================== ERROR MESSAGES ====================
ERROR_MESSAGES = {
    'invalid_email': 'Invalid email format',
    'invalid_password': 'Password must be at least 6 characters',
    'invalid_phone': 'Invalid phone number format',
    'invalid_name': 'Name must be 2-100 characters',
    'file_too_large': f'File size exceeds maximum of {MAX_FILE_SIZE_BYTES / (1024**3):.1f}GB',
    'quota_exceeded': 'Storage quota exceeded',
    'invalid_file_type': f'File type not allowed. Allowed types: {", ".join(ALLOWED_FORMATS)}',
    'db_error': 'Database operation failed',
    's3_error': 'Storage service error',
    'file_not_found': 'File not found',
    'folder_not_found': 'Folder not found',
    'user_not_found': 'User not found',
    'duplicate_email': 'Email already registered',
    'duplicate_phone': 'Phone number already registered',
    'duplicate_folder': 'Folder name already exists',
    'duplicate_file': 'File name already exists in this folder',
    'unauthorized': 'Unauthorized access',
    'login_failed': 'Invalid email or password',
}
