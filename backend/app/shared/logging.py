"""Logging configuration for the application."""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional
from app.config import settings

# Add custom SUCCESS log level (between INFO=20 and WARNING=30)
SUCCESS_LEVEL = 25
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_file: str = "app.log",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    enable_console: bool = True,
    enable_file: bool = True,
    json_format: bool = False
) -> None:
    """
    Configure application-wide logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory to store log files
        log_file: Name of the log file
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep
        enable_console: Enable console logging
        enable_file: Enable file logging
        json_format: Use JSON format for logs (useful for log aggregation)
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create formatters
    if json_format:
        # JSON formatter for structured logging
        import json
        from datetime import datetime
        
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }
                
                # Add exception info if present
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)
                
                # Add extra fields if present
                if hasattr(record, "extra"):
                    log_data.update(record.extra)
                
                return json.dumps(log_data)
        
        formatter = JSONFormatter()
    else:
        # Custom formatter with visual separators and error line highlighting
        class ErrorFormatter(logging.Formatter):
            """Custom formatter that adds visual separators and highlights error lines."""
            
            def format(self, record):
                # Format the base message (including exception if present)
                formatted = super().format(record)
                
                # Add visual separators and highlight error lines for ERROR and CRITICAL levels
                if record.levelno >= logging.ERROR:
                    # Highlight the actual error line in traceback
                    lines = formatted.split('\n')
                    highlighted_lines = []
                    error_line_indices = set()
                    
                    # First pass: find lines to highlight
                    for i, line in enumerate(lines):
                        # Check if this is the exception line (contains "Exception:" or "Error:")
                        if 'Exception:' in line or 'Error:' in line:
                            error_line_indices.add(i)
                            # Also highlight the previous line if it's the file/line reference
                            if i > 0:
                                error_line_indices.add(i - 1)
                        # Check if this is the file/line where error occurred (line with "raise")
                        elif 'raise ' in line:
                            error_line_indices.add(i)
                            # Also highlight the previous line if it's the file/line reference
                            if i > 0:
                                error_line_indices.add(i - 1)
                    
                    # Second pass: apply highlighting
                    for i, line in enumerate(lines):
                        if i in error_line_indices:
                            # Pad the line to make arrows align nicely
                            highlighted_lines.append(f">>> {line.ljust(95)} <<<")
                        else:
                            highlighted_lines.append(line)
                    
                    formatted = '\n'.join(highlighted_lines)
                    
                    # Add single separator before and after
                    separator = "=" * 100
                    formatted = f"{separator}\n{formatted}\n{separator}"
                
                return formatted
        
        # Console formatter with ANSI color codes and error line highlighting
        class ColoredConsoleFormatter(logging.Formatter):
            """Custom formatter with colors for console output and error line highlighting."""
            
            # ANSI color codes
            COLORS = {
                'DEBUG': '\033[36m',      # Cyan
                'INFO': '\033[32m',        # Green
                'SUCCESS': '\033[92m',     # Bright Green
                'WARNING': '\033[33m',    # Yellow
                'ERROR': '\033[31m',      # Red
                'CRITICAL': '\033[35m',   # Magenta
            }
            RESET = '\033[0m'
            BOLD = '\033[1m'
            BG_RED = '\033[41m'  # Red background
            BG_YELLOW = '\033[43m'  # Yellow background
            
            def format(self, record):
                # Get the base formatted message (including exception if present)
                formatted = super().format(record)
                
                # Highlight error lines and add colors for ERROR and CRITICAL levels
                if record.levelno >= logging.ERROR:
                    # Highlight the actual error line in traceback
                    lines = formatted.split('\n')
                    highlighted_lines = []
                    error_line_indices = set()
                    error_color = self.COLORS['ERROR']
                    
                    # First pass: find lines to highlight
                    for i, line in enumerate(lines):
                        # Check if this is the exception line (contains "Exception:" or "Error:")
                        if 'Exception:' in line or 'Error:' in line:
                            error_line_indices.add(i)
                            # Also highlight the previous line if it's the file/line reference
                            if i > 0:
                                error_line_indices.add(i - 1)
                        # Check if this is the file/line where error occurred (line with "raise")
                        elif 'raise ' in line:
                            error_line_indices.add(i)
                            # Also highlight the previous line if it's the file/line reference
                            if i > 0:
                                error_line_indices.add(i - 1)
                    
                    # Second pass: apply highlighting with colors
                    for i, line in enumerate(lines):
                        if i in error_line_indices:
                            # Use red background for exception line, yellow for raise/file lines
                            if 'Exception:' in line or 'Error:' in line:
                                highlighted_lines.append(
                                    f"{self.BOLD}{self.BG_RED}{error_color}>>> {line} <<<{self.RESET}"
                                )
                            else:
                                highlighted_lines.append(
                                    f"{self.BOLD}{self.BG_YELLOW}{error_color}>>> {line} <<<{self.RESET}"
                                )
                        else:
                            # Color the line based on log level
                            if record.levelname in self.COLORS:
                                color = self.COLORS[record.levelname]
                                highlighted_lines.append(f"{color}{line}{self.RESET}")
                            else:
                                highlighted_lines.append(line)
                    
                    formatted = '\n'.join(highlighted_lines)
                    
                    # Add single visual separator before and after
                    separator = "=" * 100
                    formatted = f"{self.BOLD}{error_color}{separator}{self.RESET}\n{formatted}\n{self.BOLD}{error_color}{separator}{self.RESET}"
                else:
                    # Add color for non-error levels
                    if record.levelname in self.COLORS:
                        color = self.COLORS[record.levelname]
                        formatted = f"{color}{formatted}{self.RESET}"
                
                return formatted
        
        # Standard formatter for console (without colors if not a TTY)
        detailed_formatter = ColoredConsoleFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # File formatter with visual separators for errors
        file_formatter = ErrorFormatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    # Console handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        if json_format:
            console_handler.setFormatter(formatter)
        else:
            console_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler with rotation
    if enable_file:
        # Main log file (all logs)
        log_file_path = log_path / log_file
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_file_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        if json_format:
            file_handler.setFormatter(formatter)
        else:
            file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
        
        # Separate error log file (ERROR and CRITICAL only)
        error_log_file = log_path / "error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            filename=str(error_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        if json_format:
            error_handler.setFormatter(formatter)
        else:
            error_handler.setFormatter(file_formatter)
        root_logger.addHandler(error_handler)
        
        # Separate warning log file (WARNING only)
        warning_log_file = log_path / "warning.log"
        warning_handler = logging.handlers.RotatingFileHandler(
            filename=str(warning_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        warning_handler.setLevel(logging.WARNING)
        # Only log WARNING level, not ERROR (to avoid duplicates)
        warning_handler.addFilter(lambda record: record.levelno == logging.WARNING)
        if json_format:
            warning_handler.setFormatter(formatter)
        else:
            warning_handler.setFormatter(file_formatter)
        root_logger.addHandler(warning_handler)
        
        # Separate info log file (INFO only)
        info_log_file = log_path / "info.log"
        info_handler = logging.handlers.RotatingFileHandler(
            filename=str(info_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        info_handler.setLevel(logging.INFO)
        # Only log INFO level, not WARNING or ERROR (to avoid duplicates)
        info_handler.addFilter(lambda record: record.levelno == logging.INFO)
        if json_format:
            info_handler.setFormatter(formatter)
        else:
            info_handler.setFormatter(file_formatter)
        root_logger.addHandler(info_handler)
        
        # Separate success log file (SUCCESS level only)
        success_log_file = log_path / "success.log"
        success_handler = logging.handlers.RotatingFileHandler(
            filename=str(success_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        success_handler.setLevel(SUCCESS_LEVEL)
        # Only log SUCCESS level
        success_handler.addFilter(lambda record: record.levelno == SUCCESS_LEVEL)
        if json_format:
            success_handler.setFormatter(formatter)
        else:
            success_handler.setFormatter(file_formatter)
        root_logger.addHandler(success_handler)
    
    # Set levels for third-party loggers to suppress verbose logs
    # Suppress SQLAlchemy query logs (we only want errors)
    logging.getLogger("sqlalchemy").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.ERROR)
    logging.getLogger("sqlalchemy.dialects").setLevel(logging.ERROR)
    
    # Suppress uvicorn access logs (we only want errors)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    
    # FastAPI logs
    logging.getLogger("fastapi").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance with success() method
    """
    logger = logging.getLogger(name)
    
    # Add success method to logger
    def success(message, *args, **kwargs):
        """Log a success message."""
        if logger.isEnabledFor(SUCCESS_LEVEL):
            logger._log(SUCCESS_LEVEL, message, args, **kwargs)
    
    logger.success = success
    return logger

