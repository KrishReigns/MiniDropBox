"""
S3 Operations Wrapper with Retry Logic and Error Handling
Wraps all S3 operations with exponential backoff and timeout configuration
"""
import logging
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from config import (
    AWS_BUCKET_NAME, AWS_BUCKET_SUFFIX, AWS_REGION, AWS_BUCKET_REGION,
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_TIMEOUT,
    AWS_S3_MAX_RETRIES, S3_PRESIGNED_URL_EXPIRY_SECONDS
)

logger = logging.getLogger(__name__)

try:
    from tenacity import (
        retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
        before_log,
        after_log,
    )
    HAS_TENACITY = True
except ImportError:
    HAS_TENACITY = False
    logger.warning("tenacity not installed - S3 retry logic disabled")


# Determine actual bucket name
if AWS_BUCKET_SUFFIX:
    USER_BUCKET = f"{AWS_BUCKET_NAME}-{AWS_BUCKET_SUFFIX}".strip("-")
else:
    USER_BUCKET = AWS_BUCKET_NAME

# Configure S3 client with timeouts
s3_config = Config(
    signature_version='s3v4',
    s3={'addressing_style': 'virtual'},
    connect_timeout=AWS_S3_TIMEOUT,
    read_timeout=AWS_S3_TIMEOUT,
    retries={'max_attempts': AWS_S3_MAX_RETRIES, 'mode': 'standard'},
)

S3_ENDPOINT_URL = f"https://s3.{AWS_BUCKET_REGION}.amazonaws.com"


def get_s3_client():
    """Create and return S3 client"""
    try:
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            return boto3.client(
                's3',
                aws_access_key_id=AWS_ACCESS_KEY_ID,
                aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                region_name=AWS_BUCKET_REGION,
                endpoint_url=S3_ENDPOINT_URL,
                config=s3_config
            )
        else:
            return boto3.client('s3', region_name=AWS_BUCKET_REGION, endpoint_url=S3_ENDPOINT_URL, config=s3_config)
    except Exception as e:
        logger.error(f"Failed to create S3 client: {repr(e)}")
        raise


class S3OperationError(Exception):
    """Base exception for S3 operations"""
    def __init__(self, operation: str, key: str, message: str):
        self.operation = operation
        self.key = key
        self.message = message
        super().__init__(f"S3 {operation} failed for {key}: {message}")


class S3RetryableError(S3OperationError):
    """Exception for retryable S3 errors"""
    pass


class S3PermanentError(S3OperationError):
    """Exception for permanent S3 errors (don't retry)"""
    pass


def _classify_error(error: Exception, operation: str, key: str) -> S3OperationError:
    """Classify S3 errors as retryable or permanent"""
    error_msg = str(error)
    
    # Retryable errors
    retryable_codes = [
        'ServiceUnavailable', 'RequestTimeout', 'Throttling',
        'ProvisionedThroughputExceededException', 'RequestLimitExceeded',
        'SlowDown', 'PriorRequestNotComplete', 'InternalError',
    ]
    
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', '')
        if error_code in retryable_codes:
            return S3RetryableError(operation, key, error_msg)
        return S3PermanentError(operation, key, error_msg)
    
    if isinstance(error, (BotoCoreError, TimeoutError)):
        return S3RetryableError(operation, key, error_msg)
    
    return S3PermanentError(operation, key, error_msg)


# Decorator for S3 operations with retry logic
def s3_retry_decorator(f):
    """Apply retry decorator if tenacity available"""
    if HAS_TENACITY:
        return retry(
            stop=stop_after_attempt(AWS_S3_MAX_RETRIES),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type(S3RetryableError),
            before=before_log(logger, logging.DEBUG),
            after=after_log(logger, logging.DEBUG),
            reraise=True,
        )(f)
    return f


class S3Operations:
    """Wrapper for all S3 operations"""
    
    def __init__(self, bucket: str = USER_BUCKET):
        self.bucket = bucket
        self.s3_client = get_s3_client()
        logger.info(f"S3Operations initialized for bucket: {bucket}")
    
    @s3_retry_decorator
    def put_object(self, key: str, body: bytes = None) -> bool:
        """Create empty S3 object (usually for creating folders)"""
        try:
            if body is None:
                body = b''
            self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=body)
            logger.debug(f"S3 PUT succeeded: {key}")
            return True
        except Exception as e:
            error = _classify_error(e, 'put_object', key)
            logger.error(f"S3 put_object failed: {error}")
            if isinstance(error, S3RetryableError):
                raise error
            return False
    
    @s3_retry_decorator
    def upload_file(self, file_path: str, key: str) -> bool:
        """Upload file to S3"""
        try:
            self.s3_client.upload_file(file_path, self.bucket, key)
            logger.info(f"S3 upload succeeded: {key}")
            return True
        except Exception as e:
            error = _classify_error(e, 'upload_file', key)
            logger.error(f"S3 upload_file failed: {error}")
            if isinstance(error, S3RetryableError):
                raise error
            return False
    
    @s3_retry_decorator
    def delete_object(self, key: str) -> bool:
        """Delete object from S3 (idempotent - no error if not exists)"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=key)
            logger.debug(f"S3 DELETE succeeded: {key}")
            return True
        except Exception as e:
            error = _classify_error(e, 'delete_object', key)
            logger.error(f"S3 delete_object failed: {error}")
            if isinstance(error, S3RetryableError):
                raise error
            return False
    
    @s3_retry_decorator
    def generate_presigned_url(
        self,
        key: str,
        expiry_seconds: int = S3_PRESIGNED_URL_EXPIRY_SECONDS,
        response_content_disposition: str = None,
        response_content_type: str = None
    ) -> str:
        """Generate presigned URL for file access"""
        try:
            params = {
                'Bucket': self.bucket,
                'Key': key,
            }
            if response_content_disposition:
                params['ResponseContentDisposition'] = response_content_disposition
            if response_content_type:
                params['ResponseContentType'] = response_content_type
            
            url = self.s3_client.generate_presigned_url(
                ClientMethod='get_object',
                Params=params,
                ExpiresIn=expiry_seconds,
                HttpMethod='GET'
            )
            logger.debug(f"S3 presigned URL generated: {key}")
            return url
        except Exception as e:
            error = _classify_error(e, 'generate_presigned_url', key)
            logger.error(f"S3 presigned URL generation failed: {error}")
            if isinstance(error, S3RetryableError):
                raise error
            return None
    
    @s3_retry_decorator
    def head_object(self, key: str) -> dict:
        """Get object metadata"""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=key)
            logger.debug(f"S3 HEAD succeeded: {key}")
            return response
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.debug(f"S3 object not found: {key}")
                return None
            error = _classify_error(e, 'head_object', key)
            logger.error(f"S3 head_object failed: {error}")
            if isinstance(error, S3RetryableError):
                raise error
            return None
        except Exception as e:
            error = _classify_error(e, 'head_object', key)
            logger.error(f"S3 head_object failed: {error}")
            if isinstance(error, S3RetryableError):
                raise error
            return None


# Singleton instance
_s3_operations = None

def get_s3_operations() -> S3Operations:
    """Get or create S3Operations singleton"""
    global _s3_operations
    if _s3_operations is None:
        _s3_operations = S3Operations()
    return _s3_operations
