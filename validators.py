"""
Input Validation Module for MiniDropBox
Sanitizes and validates all user inputs before processing
"""
import re
import os
from config import VALIDATION_RULES, ALLOWED_FORMATS, MAX_FILE_SIZE_BYTES


class ValidationError(Exception):
    """Custom exception for validation failures"""
    pass


def validate_email(email: str) -> str:
    """Validate and return email address"""
    if not email:
        raise ValidationError("Email is required")
    
    rules = VALIDATION_RULES['email']
    email = email.strip()
    
    if len(email) < rules['min_length'] or len(email) > rules['max_length']:
        raise ValidationError(f"Email must be {rules['min_length']}-{rules['max_length']} characters")
    
    if not re.match(rules['pattern'], email):
        raise ValidationError("Invalid email format")
    
    return email.lower()


def validate_password(password: str) -> str:
    """Validate password strength"""
    if not password:
        raise ValidationError("Password is required")
    
    rules = VALIDATION_RULES['password']
    
    if len(password) < rules['min_length']:
        raise ValidationError(f"Password must be at least {rules['min_length']} characters")
    
    if rules['require_uppercase'] and not re.search(r'[A-Z]', password):
        raise ValidationError("Password must contain at least one uppercase letter")
    
    if rules['require_number'] and not re.search(r'\d', password):
        raise ValidationError("Password must contain at least one number")
    
    if rules['require_special'] and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError("Password must contain at least one special character")
    
    return password


def validate_phone(phone: str) -> str:
    """Validate phone number"""
    if not phone:
        raise ValidationError("Phone number is required")
    
    rules = VALIDATION_RULES['phone']
    phone = phone.strip()
    
    # Remove common separators
    phone_clean = re.sub(r'[\s\-\(\)\.]+', '', phone)
    
    if len(phone_clean) < rules['min_length'] or len(phone_clean) > rules['max_length']:
        raise ValidationError(f"Phone must be {rules['min_length']}-{rules['max_length']} digits")
    
    if not re.match(rules['pattern'], phone_clean):
        raise ValidationError("Invalid phone number format")
    
    return phone_clean


def validate_name(name: str) -> str:
    """Validate user name"""
    if not name:
        raise ValidationError("Name is required")
    
    rules = VALIDATION_RULES['name']
    name = name.strip()
    
    if len(name) < rules['min_length'] or len(name) > rules['max_length']:
        raise ValidationError(f"Name must be {rules['min_length']}-{rules['max_length']} characters")
    
    if not re.match(rules['pattern'], name):
        raise ValidationError("Name contains invalid characters")
    
    return name


def validate_filename(filename: str) -> str:
    """Validate and sanitize filename"""
    if not filename:
        raise ValidationError("Filename is required")
    
    rules = VALIDATION_RULES['filename']
    filename = filename.strip()
    
    # Check forbidden characters
    for forbidden in rules['forbidden_chars']:
        if forbidden in filename:
            raise ValidationError(f"Filename contains forbidden characters: {forbidden}")
    
    if len(filename) > rules['max_length']:
        raise ValidationError(f"Filename exceeds {rules['max_length']} characters")
    
    if not re.match(rules['pattern'], filename):
        raise ValidationError("Filename contains invalid characters")
    
    # Check file extension
    _, ext = os.path.splitext(filename)
    if ext and ext.lower() not in ALLOWED_FORMATS:
        raise ValidationError(f"File type '{ext}' not allowed")
    
    return filename


def validate_foldername(foldername: str) -> str:
    """Validate and sanitize folder name"""
    if not foldername:
        raise ValidationError("Folder name is required")
    
    rules = VALIDATION_RULES['foldername']
    foldername = foldername.strip()
    
    # Check forbidden characters
    for forbidden in rules['forbidden_chars']:
        if forbidden in foldername:
            raise ValidationError(f"Folder name contains forbidden characters: {forbidden}")
    
    if len(foldername) > rules['max_length']:
        raise ValidationError(f"Folder name exceeds {rules['max_length']} characters")
    
    if not re.match(rules['pattern'], foldername):
        raise ValidationError("Folder name contains invalid characters")
    
    return foldername


def validate_file_size(file_size: int) -> int:
    """Validate file size"""
    if not isinstance(file_size, int) or file_size <= 0:
        raise ValidationError("Invalid file size")
    
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File size exceeds maximum of {MAX_FILE_SIZE_BYTES / (1024**3):.1f}GB")
    
    return file_size


# Password hashing functions using werkzeug
from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(password: str) -> str:
    """Hash a password for storage"""
    return generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return check_password_hash(hashed_password, password)


def sanitize_input(value: str) -> str:
    """General input sanitization - remove XSS attempts"""
    if not isinstance(value, str):
        return value
    
    # Remove null bytes
    value = value.replace('\x00', '')
    
    # Remove dangerous HTML/JS patterns (basic)
    dangerous_patterns = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'on\w+\s*=',
        r'<iframe',
        r'<embed',
    ]
    
    for pattern in dangerous_patterns:
        value = re.sub(pattern, '', value, flags=re.IGNORECASE)
    
    return value.strip()


def validate_integer(value, min_val=None, max_val=None) -> int:
    """Validate integer input"""
    try:
        val = int(value)
    except (ValueError, TypeError):
        raise ValidationError("Invalid integer value")
    
    if min_val is not None and val < min_val:
        raise ValidationError(f"Value must be >= {min_val}")
    
    if max_val is not None and val > max_val:
        raise ValidationError(f"Value must be <= {max_val}")
    
    return val
