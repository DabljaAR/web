"""Custom middleware for exception, error, and success logging."""
import logging
import traceback
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings

logger = logging.getLogger(__name__)

# Get SUCCESS level from logging module
SUCCESS_LEVEL = 25
if not hasattr(logging, 'SUCCESS'):
    logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


class ExceptionLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to catch and log all exceptions and errors."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Catch exceptions, log errors, and log successful requests.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in the chain
            
        Returns:
            Response object
        """
        start_time = time.time()
        
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            client_ip = request.client.host if request.client else "unknown"
            
            # Log successful requests (2xx status codes) if enabled
            if settings.LOG_ENABLE_SUCCESS and 200 <= response.status_code < 300:
                # Use success level logging
                if logger.isEnabledFor(SUCCESS_LEVEL):
                    logger._log(
                        SUCCESS_LEVEL,
                        f"Request successful: {request.method} {request.url.path} - Status {response.status_code}",
                        (),  # args parameter (empty tuple for no formatting)
                        extra={
                            "client_ip": client_ip,
                            "method": request.method,
                            "path": request.url.path,
                            "status_code": response.status_code,
                            "process_time": round(process_time, 3),
                            "query_params": dict(request.query_params),
                        }
                    )
            
            # Log 5xx server errors
            elif response.status_code >= 500:
                logger.error(
                    f"Server error response: {request.method} {request.url.path} - Status {response.status_code}",
                    extra={
                        "client_ip": client_ip,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "process_time": round(process_time, 3),
                        "query_params": dict(request.query_params),
                    }
                )
            
            return response
            
        except Exception as e:
            # Get request details for error logging
            client_ip = request.client.host if request.client else "unknown"
            method = request.method
            path = request.url.path
            query_params = dict(request.query_params)
            
            # Log the exception with full details
            logger.error(
                f"Exception occurred: {method} {path}",
                exc_info=True,
                extra={
                    "client_ip": client_ip,
                    "method": method,
                    "path": path,
                    "query_params": query_params,
                    "url": str(request.url),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            
            # Re-raise the exception so FastAPI can handle it
            raise

