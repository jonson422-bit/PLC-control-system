"""
PLC 通信客户端 - 基于 snap7
只读模式：写入功能已移除，系统只能读取PLC数据，禁止任何写入操作
"""
import sys
sys.path.insert(0, '/home/pi/envs/plc_env/lib/python3.11/site-packages')

import snap7
import threading
import socket
from typing import Dict, Optional, Any, List, TypedDict
from datetime import datetime
from .logger import get_logger

# 获取日志器
logger = get_logger(__name__)


# ============ 类型定义 ============
class PointData(TypedDict):
    """单个点位数据"""
    point: str
    timestamp: str
    success: bool
    value: str | int
    raw_value: int
    type: str


class PointError(TypedDict):
    """点位读取错误"""
    point: str
    success: bool
    error: str


class ReadPointsResult(TypedDict):
    """读取点位列表结果"""
    cpu_state: str
    timestamp: str
    points: Dict[str, PointData | PointError]
# ==================================


class PLCClient:
    """S7-200 SMART PLC 通信客户端 - 只读模式"""

    def __init__(self, ip: str = '192.168.2.1', rack: int = 0, slot: int = 1):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.client: Optional[snap7.client.Client] = None
        self.lock = threading.Lock()
        self._connected = False
        self._last_connect_attempt = 0
        self._reconnect_interval = 5  # 重连间隔（秒）
        self._connect()

    def _connect(self):
        """建立连接"""
        import time
        current_time = time.time()

        # 限制重连频率
        if current_time - self._last_connect_attempt < self._reconnect_interval:
            return

        self._last_connect_attempt = current_time

        # 先清理旧连接（避免资源泄漏）
        if self.client is not None:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None

        try:
            # 先检查网络连通性
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((self.ip, 102))
            sock.close()

            if result != 0:
                logger.error(f"PLC 网络不可达: {self.ip}:102")
                self._connected = False
                return

            # 尝试连接
            self.client = snap7.client.Client()
            self.client.set_connection_type(3)
            self.client.connect(self.ip, self.rack, self.slot)
            self._connected = True
            logger.info(f"PLC 连接成功: {self.ip}")
        except Exception as e:
            logger.error(f"PLC 连接失败: {e}")
            # 清理失败时可能已创建的客户端对象
            if self.client is not None:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
            self.client = None
            self._connected = False

    def disconnect(self):
        """断开连接"""
        if self.client:
            try:
                self.client.disconnect()
            except Exception as e:
                logger.warning(f"PLC断开连接时出错: {e}")
            self.client = None
        self._connected = False

    def is_connected(self) -> bool:
        """检查连接状态 - 通过实际尝试读取来验证"""
        # 首先检查网络连通性
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((self.ip, 102))
            sock.close()
            if result != 0:
                self._connected = False
                return False
        except Exception as e:
            logger.warning(f"PLC网络检查失败: {e}")
            self._connected = False
            return False
        
        # 检查客户端对象
        if self.client is None:
            # 尝试自动重连
            self._connect()
            return self._connected
        
        # 真正验证连接是否有效 - 通过尝试获取CPU状态
        return self._check_connection()

    def _check_connection(self):
        """内部检查并更新连接状态"""
        try:
            # 尝试获取CPU状态来验证连接
            if self.client:
                self.client.get_cpu_state()
                self._connected = True
                return True
        except Exception as e:
            logger.warning(f"PLC连接检查失败: {e}")
        self._connected = False
        return False

    def _ensure_connection(self):
        """确保连接"""
        if not self.client or not self._connected:
            self._connect()  # 尝试重连
        if not self.client or not self._connected:
            raise ConnectionError("PLC 连接不可用")

    def get_cpu_state(self) -> str:
        """获取 CPU 状态"""
        try:
            self._ensure_connection()
            state = self.client.get_cpu_state()
            return str(state)
        except Exception as e:
            logger.warning(f"获取CPU状态失败: {e}")
            return "UNKNOWN"

    def read_bit(self, area: int, byte: int, bit: int) -> bool:
        """读取位数据"""
        self._ensure_connection()
        try:
            with self.lock:
                data = self.client.read_area(area, 0, byte, 1)
            self._connected = True
            return bool(data[0] & (1 << bit))
        except Exception as e:
            self._connected = False
            raise

    def read_word(self, area: int, address: int) -> int:
        """读取字数据"""
        self._ensure_connection()
        try:
            with self.lock:
                data = self.client.read_area(area, 0, address, 2)
            self._connected = True
            return int.from_bytes(data, byteorder='big')
        except Exception as e:
            self._connected = False
            raise

    def _parse_address(self, address: str) -> tuple:
        """
        解析各种格式的地址，返回 (area, byte, bit, is_bit) 元组
        
        支持的格式:
        - PLC 格式: I0.0, Q0.0, M1.0, AIW16, AQW32, VW0
        - Snap7 格式: PE:0:0, PA:0:0, MK:1:0
        """
        address = address.strip()
        is_bit = True
        area = None
        byte_addr = 0
        bit_addr = 0
        
        # Snap7 格式: PE:0:0, PA:0:0, MK:1:0, PE:16 (word)
        if ':' in address:
            parts = address.split(':')
            area_code = parts[0].upper()
            
            if area_code == 'PE':  # 外设输入
                area = snap7.Area.PE
            elif area_code == 'PA':  # 外设输出
                area = snap7.Area.PA
            elif area_code == 'MK':  # 内存区
                area = snap7.Area.MK
            elif area_code == 'DB':  # 数据块
                area = snap7.Area.DB
            
            if len(parts) >= 2:
                byte_addr = int(parts[1])
            if len(parts) >= 3:
                bit_addr = int(parts[2])
                is_bit = True
            else:
                is_bit = False  # 字地址（如 PE:16）
                
            return (area, byte_addr, bit_addr, is_bit)
        
        # PLC 格式解析
        # I0.0, I0 (数字量输入)
        if address.startswith('I'):
            area = snap7.Area.PE
            rest = address[1:]
            if '.' in rest:
                parts = rest.split('.')
                byte_addr = int(parts[0])
                bit_addr = int(parts[1])
                is_bit = True
            elif rest.startswith('W') or rest.startswith('IW'):
                # IW64 -> 字地址
                byte_addr = int(rest.replace('W', '').replace('IW', ''))
                is_bit = False
            else:
                byte_addr = int(rest) if rest else 0
                is_bit = True
            return (area, byte_addr, bit_addr, is_bit)
        
        # Q0.0, Q0 (数字量输出)
        if address.startswith('Q'):
            area = snap7.Area.PA
            rest = address[1:]
            if '.' in rest:
                parts = rest.split('.')
                byte_addr = int(parts[0])
                bit_addr = int(parts[1])
                is_bit = True
            elif rest.startswith('W') or rest.startswith('QW'):
                byte_addr = int(rest.replace('W', '').replace('QW', ''))
                is_bit = False
            else:
                byte_addr = int(rest) if rest else 0
                is_bit = True
            return (area, byte_addr, bit_addr, is_bit)
        
        # M1.0, M0 (内存区)
        if address.startswith('M'):
            area = snap7.Area.MK
            rest = address[1:]
            if '.' in rest:
                parts = rest.split('.')
                byte_addr = int(parts[0])
                bit_addr = int(parts[1])
                is_bit = True
            elif rest.startswith('W') or rest.startswith('MW'):
                byte_addr = int(rest.replace('W', '').replace('MW', ''))
                is_bit = False
            else:
                byte_addr = int(rest) if rest else 0
                is_bit = True
            return (area, byte_addr, bit_addr, is_bit)
        
        # AIW16, AIW (模拟量输入)
        if address.startswith('AIW'):
            area = snap7.Area.PE
            byte_addr = int(address[3:])
            is_bit = False
            return (area, byte_addr, 0, is_bit)
        
        # AQW32 (模拟量输出)
        if address.startswith('AQW'):
            area = snap7.Area.PA
            byte_addr = int(address[3:])
            is_bit = False
            return (area, byte_addr, 0, is_bit)
        
        # VW0 (变量存储区)
        if address.startswith('VW'):
            area = snap7.Area.DB
            byte_addr = int(address[2:])
            is_bit = False
            return (area, byte_addr, 0, is_bit)
        
        # V0.0 (变量存储区位)
        if address.startswith('V') and '.' in address:
            area = snap7.Area.DB
            rest = address[1:]
            parts = rest.split('.')
            byte_addr = int(parts[0])
            bit_addr = int(parts[1])
            is_bit = True
            return (area, byte_addr, bit_addr, is_bit)
        
        return (None, 0, 0, False)

    def read_point(self, point_name: str) -> Optional[bool | int]:
        """读取单个点位值 - 支持多种地址格式
        
        Returns:
            bool: 位数据 (True/False)
            int: 字数据 (模拟量值)
            None: 读取失败
        """
        self._ensure_connection()
        try:
            area, byte_addr, bit_addr, is_bit = self._parse_address(point_name)
            
            if area is None:
                logger.warning(f"无法解析地址: {point_name}")
                return None
            
            if is_bit:
                value = self.read_bit(area, byte_addr, bit_addr)
            else:
                value = self.read_word(area, byte_addr)
            
            self._connected = True
            return value
        except Exception as e:
            logger.error(f"读取 {point_name} 失败: {e}")
            self._connected = False
            return None

    def read_points(self, point_list: List[str]) -> ReadPointsResult:
        """读取指定的点位列表
        
        Args:
            point_list: 点位地址列表
            
        Returns:
            ReadPointsResult: 包含cpu_state、timestamp和points字典
        """
        result: ReadPointsResult = {
            'cpu_state': self.get_cpu_state(),
            'timestamp': datetime.now().isoformat(),
            'points': {}
        }

        for point in point_list:
            try:
                value = self.read_point(point)
                # 判断点位类型
                if '.' in point and (point.startswith('I') or point.startswith('Q') or point.startswith('M')):
                    # 位数据
                    result['points'][point] = {
                        'point': point,
                        'timestamp': datetime.now().isoformat(),
                        'success': True,
                        'value': 'ON' if value else 'OFF',
                        'raw_value': 1 if value else 0,
                        'type': 'bit'
                    }
                elif point.startswith('AIW') or point.startswith('AQW') or point.startswith('IW') or point.startswith('QW') or point.startswith('VW') or point.startswith('MW'):
                    # 字数据（模拟量）
                    result['points'][point] = {
                        'point': point,
                        'timestamp': datetime.now().isoformat(),
                        'success': True,
                        'value': value or 0,
                        'raw_value': value or 0,
                        'type': 'analog'
                    }
                else:
                    # 其他类型
                    result['points'][point] = {
                        'point': point,
                        'timestamp': datetime.now().isoformat(),
                        'success': True,
                        'value': value,
                        'raw_value': value,
                        'type': 'unknown'
                    }
            except Exception as e:
                result['points'][point] = {
                    'point': point,
                    'success': False,
                    'error': str(e)
                }

        return result

    def read_all_points(self) -> ReadPointsResult:
        """读取所有点位（使用统一的默认点位定义）"""
        from .database import DEFAULT_POINTS
        return self.read_points(DEFAULT_POINTS)
