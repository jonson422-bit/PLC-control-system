"""
PLC 通信客户端 - 基于 snap7
"""
import sys
sys.path.insert(0, '/home/pi/envs/plc_env/lib/python3.11/site-packages')

import snap7
import threading
from typing import Dict, Optional, Any
from datetime import datetime


class PLCClient:
    """S7-200 SMART PLC 通信客户端"""
    
    def __init__(self, ip: str = '192.168.2.1', rack: int = 0, slot: int = 1):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.client: Optional[snap7.client.Client] = None
        self.lock = threading.Lock()
        self._connect()
    
    def _connect(self):
        """建立连接"""
        try:
            self.client = snap7.client.Client()
            self.client.set_connection_type(3)
            self.client.connect(self.ip, self.rack, self.slot)
            print(f"✅ PLC 连接成功: {self.ip}")
        except Exception as e:
            print(f"❌ PLC 连接失败: {e}")
            self.client = None
    
    def disconnect(self):
        """断开连接"""
        if self.client:
            try:
                self.client.disconnect()
            except:
                pass
            self.client = None
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self.client is not None
    
    def _ensure_connection(self):
        """确保连接"""
        if not self.client:
            self._connect()  # 尝试重连
        if not self.client:
            self._connect()
        if not self.client:
            raise ConnectionError("PLC 连接不可用")
    
    def get_cpu_state(self) -> str:
        """获取 CPU 状态"""
        self._ensure_connection()
        try:
            with self.lock:
                state = self.client.get_cpu_state()
            # S7-200 SMART: RUN = 4, STOP = 8
            state_map = {4: 'RUN', 8: 'STOP', 0: 'UNKNOWN'}
            return state_map.get(state, f'UNKNOWN({state})')
        except Exception as e:
            return f'ERROR: {e}'
    
    def cpu_start(self) -> Dict[str, Any]:
        """启动 CPU"""
        self._ensure_connection()
        try:
            with self.lock:
                self.client.cpu_hot_start()
            return {'success': True, 'action': 'START', 'message': 'PLC 已启动'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def cpu_stop(self) -> Dict[str, Any]:
        """停止 CPU"""
        self._ensure_connection()
        try:
            with self.lock:
                self.client.cpu_stop()
            return {'success': True, 'action': 'STOP', 'message': 'PLC 已停止'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def read_bit(self, area: int, byte: int, bit: int) -> bool:
        """读取位数据"""
        self._ensure_connection()
        with self.lock:
            data = self.client.read_area(area, 0, byte, 1)
        return bool((data[0] >> bit) & 1)
    
    def write_bit(self, area: int, byte: int, bit: int, value: bool):
        """写入位数据"""
        self._ensure_connection()
        with self.lock:
            data = self.client.read_area(area, 0, byte, 1)
            if value:
                data[0] = data[0] | (1 << bit)
            else:
                data[0] = data[0] & ~(1 << bit)
            self.client.write_area(area, 0, byte, data)
        return True
    
    def read_word(self, area: int, address: int) -> int:
        """读取字数据"""
        self._ensure_connection()
        with self.lock:
            data = self.client.read_area(area, 0, address, 2)
        return int.from_bytes(data, byteorder='big')
    
    def write_word(self, area: int, address: int, value: int):
        """写入字数据"""
        self._ensure_connection()
        with self.lock:
            data = value.to_bytes(2, byteorder='big')
            self.client.write_area(area, 0, address, data)
        return True
    
    def read_point(self, point_name: str) -> Dict[str, Any]:
        """读取点位数据"""
        self._ensure_connection()
        
        result = {
            'point': point_name,
            'timestamp': datetime.now().isoformat(),
            'success': False
        }
        
        try:
            if point_name.startswith('I') and '.' in point_name:
                # 数字量输入 I0.0
                byte, bit = map(int, point_name[1:].split('.'))
                value = self.read_bit(snap7.Area.PE, byte, bit)
                result.update({
                    'value': 'ON' if value else 'OFF',
                    'raw_value': int(value),
                    'type': 'bit',
                    'success': True
                })
            
            elif point_name.startswith('Q') and '.' in point_name:
                # 数字量输出 Q0.0
                byte, bit = map(int, point_name[1:].split('.'))
                value = self.read_bit(snap7.Area.PA, byte, bit)
                result.update({
                    'value': 'ON' if value else 'OFF',
                    'raw_value': int(value),
                    'type': 'bit',
                    'success': True
                })
            
            elif point_name.startswith('AIW'):
                # 模拟量输入
                addr = int(point_name[3:])
                value = self.read_word(snap7.Area.PE, addr)
                result.update({
                    'value': value,
                    'raw_value': value,
                    'type': 'analog',
                    'success': True
                })
            
            elif point_name.startswith('AQW'):
                # 模拟量输出
                addr = int(point_name[3:])
                value = self.read_word(snap7.Area.PA, addr)
                result.update({
                    'value': value,
                    'raw_value': value,
                    'type': 'analog',
                    'success': True
                })
            
            else:
                result['error'] = f'未知的点位格式: {point_name}'
        
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def write_point(self, point_name: str, value: Any) -> Dict[str, Any]:
        """写入点位数据"""
        self._ensure_connection()
        
        result = {
            'point': point_name,
            'value': value,
            'timestamp': datetime.now().isoformat(),
            'success': False
        }
        
        try:
            if point_name.startswith('Q') and '.' in point_name:
                # 数字量输出
                byte, bit = map(int, point_name[1:].split('.'))
                if isinstance(value, str):
                    bool_value = value.upper() in ['ON', '1', 'TRUE']
                else:
                    bool_value = bool(value)
                self.write_bit(snap7.Area.PA, byte, bit, bool_value)
                result['success'] = True
                result['message'] = f'{point_name} 已设置为 {"ON" if bool_value else "OFF"}'
            
            elif point_name.startswith('AQW'):
                # 模拟量输出
                addr = int(point_name[3:])
                int_value = int(value)
                if 0 <= int_value <= 27648:
                    self.write_word(snap7.Area.PA, addr, int_value)
                    result['success'] = True
                    result['message'] = f'{point_name} 已设置为 {int_value}'
                else:
                    result['error'] = '值必须在 0-27648 范围内'
            
            else:
                result['error'] = f'只能写入输出点 (Q 或 AQW): {point_name}'
        
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def read_all_points(self, points: list) -> Dict[str, Any]:
        """读取所有点位"""
        result = {
            'cpu_state': self.get_cpu_state(),
            'timestamp': datetime.now().isoformat(),
            'points': {}
        }
        
        for point in points:
            try:
                data = self.read_point(point)
                result['points'][point] = data
            except Exception as e:
                result['points'][point] = {'error': str(e)}
        
        return result


# 全局实例
plc = PLCClient()
