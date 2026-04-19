"""
Error Handling and Logging System
Centralized logging and error response handling
"""
import logging
import logging.handlers
import json
import uuid
from functools import wraps
from flask import render_template, jsonify, request
from config import LOG_LEVEL, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, ERROR_MESSAGES


# ==================== LOGGING SETUP ====================
def setup_logging():
    """Initialize logging system"""
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT
    )
    file_handler.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logging()


# ==================== CUSTOM EXCEPTIONS ====================
class AppError(Exception):
    """Base application error"""
    def __init__(self, message: str, error_code: str = "APP_ERROR", status_code: int = 400):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.error_id = str(uuid.uuid4())
        super().__init__(self.message)


class AuthenticationError(AppError):
    """Authentication failed"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR", 401)


class AuthorizationError(AppError):
    """User not authorized for resource"""
    def __init__(self, message: str = "Unauthorized access"):
        super().__init__(message, "AUTHZ_ERROR", 403)


class ValidationError(AppError):
    """Input validation failed"""
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR", 400)


class DatabaseError(AppError):
    """Database operation failed"""
    def __init__(self, message: str = "Database operation failed"):
        super().__init__(message, "DB_ERROR", 500)


class S3Error(AppError):
    """S3 operation failed"""
    def __init__(self, message: str = "Storage service error"):
        super().__init__(message, "S3_ERROR", 503)


class ResourceNotFoundError(AppError):
    """Resource not found"""
    def __init__(self, resource_type: str):
        super().__init__(f"{resource_type} not found", "NOT_FOUND", 404)


# ==================== ERROR HANDLING DECORATORS ====================
def safe_route(render_on_error: str = None, redirect_on_error: str = None):
    """
    Decorator for Flask routes to handle all errors gracefully
    
    Args:
        render_on_error: Template to render on error (e.g., 'index.html')
        redirect_on_error: URL to redirect to on error
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except AppError as e:
                logger.warning(f"AppError [{e.error_id}]: {e.message}")
                
                if render_on_error:
                    return render_template(render_on_error, 
                                         message=e.message, 
                                         error_id=e.error_id), e.status_code
                
                return jsonify({
                    'error': e.error_code,
                    'message': e.message,
                    'error_id': e.error_id,
                }), e.status_code
            
            except Exception as e:
                error_id = str(uuid.uuid4())
                logger.exception(f"Unexpected error [{error_id}]: {repr(e)}")
                
                if render_on_error:
                    return render_template(render_on_error,
                                         message="An unexpected error occurred",
                                         error_id=error_id), 500
                
                return jsonify({
                    'error': 'INTERNAL_ERROR',
                    'message': 'An unexpected error occurred',
                    'error_id': error_id,
                }), 500
        
        return decorated_function
    return decorator


def log_user_action(action: str, resource_type: str = None, resource_id: int = None):
    """
    Decorator to log user actions for audit trail
    
    Args:
        action: Action being performed (login, upload, delete, etc.)
        resource_type: Type of resource affected (file, folder, user, etc.)
        resource_id: ID of the resource
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                result = f(*args, **kwargs)
                
                # Log successful action
                logger.info(f"Action '{action}' completed - "
                           f"Resource: {resource_type or 'N/A'}, "
                           f"ID: {resource_id or 'N/A'}, "
                           f"IP: {request.remote_addr}")
                
                return result
            except Exception as e:
                logger.warning(f"Action '{action}' failed - "
                              f"Error: {repr(e)}, "
                              f"IP: {request.remote_addr}")
                raise
        
        return decorated_function
    return decorator


def handle_db_errors(max_retries: int = 1):
    """Decorator for database error handling with retry logic"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            import time
            
            for attempt in range(max_retries + 1):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if "Operational" in str(type(e)) and attempt < max_retries:
                        wait_time = 2 ** attempt  # Exponential backoff
                        logger.warning(f"Database error on attempt {attempt + 1}, "
                                      f"retrying in {wait_time}s: {repr(e)}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Database error: {repr(e)}")
                        raise DatabaseError("Database operation failed") from e
        
        return decorated_function
    return decorator


# ==================== LOGGING FUNCTIONS ====================
def log_login(user_id: int, success: bool, email: str = None, error: str = None):
    """Log user login attempt"""
    if success:
        logger.info(f"User login successful - user_id={user_id}, email={email}, ip={request.remote_addr}")
    else:
        logger.warning(f"User login failed - email={email}, ip={request.remote_addr}, error={error}")


def log_user_action_detail(user_id: int, action: str, details: dict = None):
    """Log detailed user action"""
    detail_str = json.dumps(details) if details else ""
    logger.info(f"User action - user_id={user_id}, action={action}, ip={request.remote_addr}, details={detail_str}")


def log_file_operation(user_id: int, operation: str, file_id: int, filename: str, size: int = None):
    """Log file operations"""
    size_str = f", size={size}" if size else ""
    logger.info(f"File operation - user_id={user_id}, op={operation}, file_id={file_id}, "
                f"filename={filename}{size_str}, ip={request.remote_addr}")


def log_s3_operation(operation: str, key: str, success: bool, error: str = None):
    """Log S3 operations"""
    if success:
        logger.info(f"S3 operation successful - op={operation}, key={key}")
    else:
        logger.error(f"S3 operation failed - op={operation}, key={key}, error={error}")


def log_security_event(event_type: str, user_id: int = None, details: str = None):
    """Log security-relevant events"""
    logger.warning(f"Security event - type={event_type}, user_id={user_id}, "
                   f"ip={request.remote_addr}, details={details}")


# ==================== ERROR RESPONSE HELPERS ====================
def get_error_message(error_key: str, default: str = "An error occurred"):
    """Get user-friendly error message"""
    return ERROR_MESSAGES.get(error_key, default)


def create_error_response(error_key: str, template: str = None, status_code: int = 400):
    """Create error response"""
    message = get_error_message(error_key)
    
    if template:
        return render_template(template, message=message), status_code
    
    return jsonify({'error': message}), status_code
