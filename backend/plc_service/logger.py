"""
PLC 智能管控系统 - 统一日志配置模块

特性:
- 支持多级别日志 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- 同时输出到控制台和文件
- 结构化日志格式 (时间戳 | 级别 | 模块:行号 | 消息)
- 日志文件按日期分割
- 支持 JSON 格式日志输出 (可选)
- 彩色控制台输出

使用方法:
    from logger import get_logger
    logger = get_logger(__name__)

    logger.info("服务启动")
    logger.warning("配置缺失")
    logger.error(f"连接失败: {e}")
    logger.debug(f"API响应: {response}")
"""

import logging
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import os

# 日志目录
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

# 默认日志级别 (可通过环境变量配置)
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# 日志格式
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# JSON 格式日志
class JsonFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""
    def format(self, record):
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage()
        }

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data["data"] = record.extra_data

        return json.dumps(log_data, ensure_ascii=False)


# 彩色控制台格式化器
class ColoredFormatter(logging.Formatter):
    """彩色控制台日志格式化器"""
    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def format(self, record):
        # 添加颜色
        color = self.COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:8s}{self.RESET}"
        return super().format(record)


# 全局日志管理器
_loggers = {}
_initialized = False


def setup_logging(
    level: str = DEFAULT_LOG_LEVEL,
    json_format: bool = False,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> None:
    """
    配置全局日志设置

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: 是否使用 JSON 格式输出
        log_to_file: 是否输出到文件
        log_to_console: 是否输出到控制台
    """
    global _initialized

    if _initialized:
        return

    log_level = LOG_LEVELS.get(level, logging.INFO)

    # 配置根日志器
    root_logger = logging.getLogger("plc_service")
    root_logger.setLevel(log_level)

    # 清除已有的处理器
    root_logger.handlers = []

    # 控制台处理器
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)

        if json_format:
            console_handler.setFormatter(JsonFormatter())
        else:
            console_handler.setFormatter(ColoredFormatter(LOG_FORMAT, DATE_FORMAT))

        root_logger.addHandler(console_handler)

    # 文件处理器
    if log_to_file:
        # 按日期命名日志文件
        log_file = LOG_DIR / f"plc_service_{datetime.now().strftime('%Y-%m-%d')}.log"

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)

        if json_format:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

        root_logger.addHandler(file_handler)

        # 错误日志单独文件
        error_log_file = LOG_DIR / f"error_{datetime.now().strftime('%Y-%m-%d')}.log"
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root_logger.addHandler(error_handler)

    # 清理过期日志文件（保留最近 30 天）
    try:
        cleanup_old_logs(max_days=30)
    except Exception as e:
        # 清理失败不影响日志功能
        print(f"日志清理警告: {e}")

    _initialized = True


def cleanup_old_logs(max_days: int = 30) -> int:
    """
    清理过期日志文件

    Args:
        max_days: 保留最近多少天的日志

    Returns:
        删除的文件数量
    """
    from datetime import timedelta
    import time

    cutoff = time.time() - max_days * 86400
    deleted = 0

    for log_file in LOG_DIR.glob("*.log"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                deleted += 1
        except OSError:
            pass

    if deleted > 0:
        print(f"已清理 {deleted} 个过期日志文件 (>{max_days}天)")

    return deleted


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    获取日志器实例

    Args:
        name: 日志器名称 (通常使用 __name__)
        level: 可选的日志级别覆盖

    Returns:
        配置好的日志器实例

    Example:
        logger = get_logger(__name__)
        logger.info("消息")
    """
    global _initialized

    # 确保日志系统已初始化
    if not _initialized:
        setup_logging()

    # 创建子日志器
    full_name = f"plc_service.{name}" if not name.startswith("plc_service") else name
    logger = logging.getLogger(full_name)

    if level:
        logger.setLevel(LOG_LEVELS.get(level, logging.INFO))

    return logger


# 便捷函数：记录带额外数据的日志
def log_with_data(logger: logging.Logger, level: int, message: str, **kwargs):
    """
    记录带额外数据的日志

    Args:
        logger: 日志器实例
        level: 日志级别
        message: 日志消息
        **kwargs: 额外数据字段
    """
    record = logger.makeRecord(
        logger.name, level, "", 0, message, (), None
    )
    record.extra_data = kwargs
    logger.handle(record)


# 模块级别的默认日志器
logger = get_logger("main")


if __name__ == "__main__":
    # 测试日志功能
    setup_logging(level="DEBUG")

    test_logger = get_logger("test")

    test_logger.debug("调试信息 - 详细的技术细节")
    test_logger.info("普通信息 - 正常的业务流程")
    test_logger.warning("警告信息 - 潜在问题")
    test_logger.error("错误信息 - 需要关注的错误")
    test_logger.critical("严重错误 - 系统级故障")

    # 测试带数据的日志
    log_with_data(test_logger, logging.INFO, "API请求",
                  method="GET", url="/api/health", status=200)

    print(f"\n日志文件目录: {LOG_DIR}")
