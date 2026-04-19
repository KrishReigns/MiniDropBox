"""
Database Connection Management with Thread-Safe Connection Pool
Replaces global conn/cursor with DBUtils pooling
"""
import pymysql
import logging
from threading import Lock
from config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, DB_CONNECTION_TIMEOUT, DB_POOL_SIZE, DB_MAX_OVERFLOW

logger = logging.getLogger(__name__)

try:
    from DBUtils.PooledDB import PooledDB
    HAS_DBUTILS = True
except ImportError:
    HAS_DBUTILS = False
    logger.warning("DBUtils not installed - using fallback connection management")


class DatabasePool:
    """Thread-safe singleton database connection pool"""
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.pool = None
        self._init_pool()
    
    def _init_pool(self):
        """Initialize connection pool using DBUtils or fallback"""
        if HAS_DBUTILS:
            self.pool = PooledDB(
                creator=pymysql,
                maxconnections=DB_POOL_SIZE + DB_MAX_OVERFLOW,
                mincached=2,
                maxcached=5,
                maxshared=3,
                blocking=True,
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                connect_timeout=DB_CONNECTION_TIMEOUT,
                autocommit=True,
                read_timeout=30,
                write_timeout=30,
            )
            logger.info(f"DatabasePool initialized with DBUtils - {DB_POOL_SIZE} connections")
        else:
            self.pool = None
            logger.warning("DatabasePool initialized in fallback mode - NOT thread-safe for production")
    
    def get_connection(self):
        """Get a connection from the pool"""
        try:
            if self.pool:
                return self.pool.connection()
            else:
                # Fallback: create direct connection
                return pymysql.connect(
                    host=DB_HOST,
                    port=DB_PORT,
                    user=DB_USER,
                    password=DB_PASSWORD,
                    database=DB_NAME,
                    connect_timeout=DB_CONNECTION_TIMEOUT,
                    autocommit=True,
                    charset='utf8mb4',
                )
        except Exception as e:
            logger.error(f"Failed to get database connection: {repr(e)}")
            raise
    
    def get_cursor(self, conn=None):
        """Get a cursor from a connection"""
        if conn is None:
            conn = self.get_connection()
        return conn.cursor(), conn
    
    def close_connection(self, conn):
        """Return connection to pool (for non-DBUtils mode)"""
        if conn and not HAS_DBUTILS:
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Error closing connection: {repr(e)}")
    
    def ping_connection(self, conn):
        """Check if connection is alive"""
        try:
            conn.ping(reconnect=True)
            return True
        except Exception as e:
            logger.warning(f"Connection ping failed: {repr(e)}")
            return False


class DatabaseOperation:
    """Context manager for database operations with error handling"""
    
    def __init__(self, operation_name: str = "Unknown"):
        self.operation_name = operation_name
        self.pool = DatabasePool()
        self.conn = None
        self.cursor = None
    
    def __enter__(self):
        try:
            self.conn = self.pool.get_connection()
            self.cursor = self.conn.cursor()
            return self.cursor
        except Exception as e:
            logger.error(f"Failed to acquire database connection for {self.operation_name}: {repr(e)}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(f"Error in {self.operation_name}: {exc_type.__name__}: {exc_val}")
            if self.conn:
                try:
                    self.conn.rollback()
                except:
                    pass
        
        if self.cursor:
            try:
                self.cursor.close()
            except:
                pass
        
        if self.conn:
            self.pool.close_connection(self.conn)
        
        # Return False to propagate exceptions
        return False


# Module-level convenience function for backwards compatibility
_db_pool = DatabasePool()

def get_db_connection():
    """Get a database connection"""
    return _db_pool.get_connection()

def get_db_cursor():
    """Get a database cursor and connection"""
    return _db_pool.get_cursor()
