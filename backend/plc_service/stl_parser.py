#!/usr/bin/env python3
"""
STL 解析模块 - 支持西门子 S7-200 SMART PLC 的 STL 程序解析
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
import json


@dataclass
class Variable:
    """变量数据类"""
    name: str
    data_type: str
    address: Optional[str] = None
    block_name: Optional[str] = None
    block_type: Optional[str] = None
    description: Optional[str] = None
    initial_value: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class CodeBlock:
    """代码块数据类"""
    block_type: str  # OB, FB, FC, DB
    block_number: int
    block_name: str
    variables: List[Variable]
    code_lines: List[str]


class STLParser:
    """STL 程序解析器"""

    # S7-200 SMART 数据类型映射
    DATA_TYPES = {
        'BOOL': 'BOOL',
        'BYTE': 'BYTE',
        'WORD': 'WORD',
        'DWORD': 'DWORD',
        'INT': 'INT',
        'DINT': 'DINT',
        'REAL': 'REAL',
        'STRING': 'STRING',
        'TIMER': 'TIMER',
        'COUNTER': 'COUNTER',
        'TIME': 'TIME',
        'DATE': 'DATE',
        'TOD': 'TIME_OF_DAY',
        'S5TIME': 'S5TIME',
    }

    # 特殊功能块类型
    SPECIAL_BLOCKS = {
        'TON': 'TIMER',
        'TOF': 'TIMER',
        'TP': 'TIMER',
        'TONR': 'TIMER',
        'CTU': 'COUNTER',
        'CTD': 'COUNTER',
        'CTUD': 'COUNTER',
    }

    # 地址正则模式
    ADDRESS_PATTERNS = {
        'I': r'[IQM](\d+)\.(\d+)',      # I0.0, Q0.0, M0.0
        'IB': r'[IQM]B(\d+)',           # IB0, QB0, MB0
        'IW': r'[IQM]W(\d+)',           # IW0, QW0, MW0
        'ID': r'[IQM]D(\d+)',           # ID0, QD0, MD0
        'V': r'V(\d+)\.(\d+)',          # V0.0
        'VB': r'VB(\d+)',               # VB0
        'VW': r'VW(\d+)',               # VW0
        'VD': r'VD(\d+)',               # VD0
        'T': r'T(\d+)',                 # T0 (定时器)
        'C': r'C(\d+)',                 # C0 (计数器)
        'SM': r'SM(\d+)\.(\d+)',        # SM0.0 (特殊存储器)
        'SMB': r'SMB(\d+)',             # SMB0
        'SMW': r'SMW(\d+)',             # SMW0
        'SMD': r'SMD(\d+)',             # SMD0
        'AI': r'AIW(\d+)',              # AIW0 (模拟输入)
        'AQ': r'AQW(\d+)',              # AQW0 (模拟输出)
        'HC': r'HC(\d+)',               # HC0 (高速计数器)
        'AC': r'AC(\d+)',               # AC0 (累加器)
        'L': r'L(\d+)\.(\d+)',          # L0.0 (局部变量)
        'LB': r'LB(\d+)',               # LB0
        'LW': r'LW(\d+)',               # LW0
        'LD': r'LD(\d+)',               # LD0
    }

    def __init__(self):
        self.variables: List[Variable] = []
        self.blocks: List[CodeBlock] = []
        self.current_block: Optional[CodeBlock] = None

    # STL 指令及其操作数类型
    # 格式: 指令 -> [(操作数位置, 类型描述), ...]
    STL_INSTRUCTIONS = {
        # 位逻辑指令
        'LD': 'load',      # 装载
        'LDN': 'load',     # 装载取反
        'A': 'and',        # 与
        'AN': 'and',       # 与取反
        'O': 'or',         # 或
        'ON': 'or',        # 或取反
        'X': 'xor',        # 异或
        'XN': 'xor',       # 异或取反
        '=': 'output',     # 输出
        'S': 'set',        # 置位
        'R': 'reset',      # 复位
        'SI': 'set_immediate',
        'RI': 'reset_immediate',
        'ED': 'edge_down', # 下降沿
        'EU': 'edge_up',   # 上升沿
        
        # 定时器指令
        'TON': 'timer',    # 接通延时定时器
        'TOF': 'timer',    # 断开延时定时器
        'TP': 'timer',     # 脉冲定时器
        'TONR': 'timer',   # 保持型接通延时定时器
        'BITIM': 'timer',  # 块定时器开始
        'CITIM': 'timer',  # 计算定时器
        
        # 计数器指令
        'CTU': 'counter',  # 加计数器
        'CTD': 'counter',  # 减计数器
        'CTUD': 'counter', # 加减计数器
        
        # 比较指令
        'LDB': 'compare_byte',
        'LDW': 'compare_word',
        'LDD': 'compare_dword',
        'LDR': 'compare_real',
        'AB': 'compare_byte',
        'AW': 'compare_word',
        'AD': 'compare_dword',
        'AR': 'compare_real',
        'OB': 'compare_byte',
        'OW': 'compare_word',
        'OD': 'compare_dword',
        'OR': 'compare_real',
        
        # 数据移动指令
        'MOVB': 'move_byte',
        'MOVW': 'move_word',
        'MOVD': 'move_dword',
        'MOVR': 'move_real',
        'BMB': 'block_move_byte',
        'BMW': 'block_move_word',
        'BMD': 'block_move_dword',
        'SWAP': 'swap',
        
        # 算术运算指令
        'INC_B': 'inc_byte',
        'INC_W': 'inc_word',
        'INC_D': 'inc_dword',
        'DEC_B': 'dec_byte',
        'DEC_W': 'dec_word',
        'DEC_D': 'dec_dword',
        '+I': 'add_int',
        '+D': 'add_dint',
        '+R': 'add_real',
        '-I': 'sub_int',
        '-D': 'sub_dint',
        '-R': 'sub_real',
        '*I': 'mul_int',
        '*D': 'mul_dint',
        '*R': 'mul_real',
        '/I': 'div_int',
        '/D': 'div_dint',
        '/R': 'div_real',
        'SQRT': 'sqrt',
        'LN': 'ln',
        'EXP': 'exp',
        'SIN': 'sin',
        'COS': 'cos',
        'TAN': 'tan',
        
        # 逻辑运算指令
        'WAND_B': 'and_byte',
        'WAND_W': 'and_word',
        'WAND_D': 'and_dword',
        'WOR_B': 'or_byte',
        'WOR_W': 'or_word',
        'WOR_D': 'or_dword',
        'WXOR_B': 'xor_byte',
        'WXOR_W': 'xor_word',
        'WXOR_D': 'xor_dword',
        'INV_B': 'inv_byte',
        'INV_W': 'inv_word',
        'INV_D': 'inv_dword',
        
        # 移位/循环指令
        'SRB': 'shift_right_byte',
        'SRW': 'shift_right_word',
        'SRD': 'shift_right_dword',
        'SLB': 'shift_left_byte',
        'SLW': 'shift_left_word',
        'SLD': 'shift_left_dword',
        'RRB': 'rotate_right_byte',
        'RRW': 'rotate_right_word',
        'RRD': 'rotate_right_dword',
        'RLB': 'rotate_left_byte',
        'RLW': 'rotate_left_word',
        'RLD': 'rotate_left_dword',
        'SHRB': 'shift_register',
        
        # 转换指令
        'BTI': 'byte_to_int',
        'ITB': 'int_to_byte',
        'ITD': 'int_to_dint',
        'DTI': 'dint_to_int',
        'DTR': 'dint_to_real',
        'ROUND': 'round',
        'TRUNC': 'trunc',
        'SEG': 'segment',
        'BCDI': 'bcd_to_int',
        'IBCD': 'int_to_bcd',
        'ATH': 'ascii_to_hex',
        'HTA': 'hex_to_ascii',
        'ITA': 'int_to_ascii',
        'DTA': 'dint_to_ascii',
        'RTA': 'real_to_ascii',
        'DECO': 'decode',
        'ENCO': 'encode',
        
        # 程序控制指令
        'JMP': 'jump',
        'JMPN': 'jump_not',
        'LBL': 'label',
        'CALL': 'call',
        'CRET': 'return',
        'FOR': 'for_loop',
        'NEXT': 'next',
        'STOP': 'stop',
        'WDR': 'watchdog_reset',
        'END': 'end',
        
        # 高速计数器指令
        'HDEF': 'hsc_define',
        'HSC': 'hsc',
        'PLS': 'pulse',
        
        # PID 指令
        'PID': 'pid',
        
        # 通信指令
        'NETR': 'net_read',
        'NETW': 'net_write',
        'XMT': 'transmit',
        'RCV': 'receive',
        'ADDR': 'address',
    }

    def parse(self, content: str) -> Dict:
        """
        解析 STL 程序内容

        Args:
            content: STL 程序文本内容

        Returns:
            包含变量列表、代码块列表和统计信息的字典
        """
        self.variables = []
        self.blocks = []
        self.current_block = None

        lines = content.split('\n')

        # 解析主程序
        self._parse_program_header(lines)
        self._parse_variables(lines)
        self._parse_code_blocks(lines)
        self._extract_instructions_operands()  # 新增：从指令中提取操作数
        self._extract_implicit_addresses()

        return {
            'variables': [asdict(v) for v in self.variables],
            'blocks': [asdict(b) for b in self.blocks],
            'stats': {
                'total_variables': len(self.variables),
                'total_blocks': len(self.blocks),
                'variables_by_type': self._count_by_type(),
                'variables_by_block': self._count_by_block(),
            }
        }

    def _extract_instructions_operands(self):
        """从 STL 指令中提取操作数地址"""
        # 扫描所有代码行，提取指令操作数
        all_code_lines = []
        for block in self.blocks:
            all_code_lines.extend(block.code_lines)
        
        # 如果没有代码块，扫描所有行
        if not all_code_lines:
            all_code_lines = [line for block in self.blocks for line in block.code_lines]
        
        # 有效地址正则模式
        address_pattern = r'\b([IQMV][BWD]?\d+(?:\.\d+)?|AIW\d+|AQW\d+|T\d+|C\d+|SM[BWD]?\d+(?:\.\d+)?|HC\d+|AC\d+|L[BWD]?\d+(?:\.\d+)?)\b'
        
        for line in all_code_lines:
            # 移除注释
            code_line = line.split('//')[0].strip()
            if not code_line:
                continue
            
            # 检测指令格式: 指令 操作数1, 操作数2, ...
            # 匹配各种 STL 指令格式
            instruction_match = re.match(
                r'^\s*(\+?[A-Za-z_][\w]*|=)\s+(.+)$',
                code_line,
                re.IGNORECASE
            )
            
            if instruction_match:
                instruction = instruction_match.group(1).upper()
                operands_str = instruction_match.group(2).strip()
                
                # 检查是否是已知指令
                if instruction in self.STL_INSTRUCTIONS:
                    # 提取操作数中的地址
                    operands = re.split(r'[,\s]+', operands_str)
                    for operand in operands:
                        operand = operand.strip()
                        # 跳过立即数（纯数字、带符号数字、浮点数）
                        if re.match(r'^[+-]?\d+(\.\d+)?$', operand):
                            continue
                        # 跳过标签
                        if operand.isdigit():
                            continue
                        # 提取有效地址
                        addr_match = re.match(address_pattern, operand, re.IGNORECASE)
                        if addr_match:
                            addr = addr_match.group(1).upper()
                            # 确定数据类型
                            data_type = self._guess_type_from_address(addr)
                            if data_type == 'UNKNOWN':
                                continue
                            
                            # 检查是否已存在
                            existing = [v for v in self.variables if v.address and v.address.upper() == addr]
                            if not existing:
                                # 创建指令提取的变量
                                self.variables.append(Variable(
                                    name=f"_INST_{addr.replace('.', '_')}",
                                    data_type=data_type,
                                    address=addr,
                                    block_name='INSTRUCTION',
                                    block_type='CODE',
                                    description=f'从 {instruction} 指令提取',
                                    initial_value=None,
                                    line_number=None
                                ))

    def _parse_program_header(self, lines: List[str]):
        """解析程序头信息"""
        for line in lines[:20]:  # 通常前20行包含头信息
            line = line.strip()
            if line.startswith('TITLE=') or line.startswith('//'):
                continue

    def _parse_variables(self, lines: List[str]):
        """解析变量声明"""
        in_var_section = False
        current_block_type = None
        current_block_name = 'MAIN'

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 检测变量块开始
            var_block_match = re.match(
                r'^(VAR|VAR_INPUT|VAR_OUTPUT|VAR_GLOBAL|VAR_TEMP|VAR_EXTERNAL)\s*(?::\s*(\w+))?',
                line, re.IGNORECASE
            )
            if var_block_match:
                in_var_section = True
                current_block_type = var_block_match.group(1).upper()
                if var_block_match.group(2):
                    current_block_name = var_block_match.group(2)
                i += 1
                continue

            # 检测变量块结束
            if line.upper() == 'END_VAR':
                in_var_section = False
                current_block_type = None
                i += 1
                continue

            # 解析变量声明
            if in_var_section and line and not line.startswith('//'):
                var = self._parse_variable_line(line, current_block_type, current_block_name, i + 1)
                if var:
                    self.variables.append(var)

            # 检测程序块
            # 支持多种格式:
            # - ORGANIZATION_BLOCK MAIN:OB1
            # - ORGANIZATION_BLOCK OB1
            # - OB1
            # - FUNCTION_BLOCK FB1
            block_match = re.match(
                r'^(ORGANIZATION_BLOCK|FUNCTION_BLOCK|FUNCTION|DATA_BLOCK)\s+(\w+)?(?::\s*(\w+))?',
                line, re.IGNORECASE
            )
            if block_match:
                block_type_full = block_match.group(1).upper()
                # 确定块类型缩写
                if block_type_full == 'ORGANIZATION_BLOCK':
                    block_type = 'OB'
                elif block_type_full == 'FUNCTION_BLOCK':
                    block_type = 'FB'
                elif block_type_full == 'FUNCTION':
                    block_type = 'FC'
                elif block_type_full == 'DATA_BLOCK':
                    block_type = 'DB'
                else:
                    block_type = block_type_full[:2]
                
                # 确定块名和块号
                name_part = block_match.group(2) if block_match.group(2) else ''
                id_part = block_match.group(3) if block_match.group(3) else ''
                
                if id_part:
                    block_name = id_part  # 如 OB1
                    # 尝试从 id_part 提取数字
                    num_match = re.search(r'(\d+)', id_part)
                    block_num = int(num_match.group(1)) if num_match else 0
                elif name_part:
                    block_name = name_part
                    num_match = re.search(r'(\d+)', name_part)
                    block_num = int(num_match.group(1)) if num_match else 0
                else:
                    block_name = f"{block_type}0"
                    block_num = 0
                
                current_block_name = block_name

                self.blocks.append(CodeBlock(
                    block_type=block_type,
                    block_number=block_num,
                    block_name=block_name,
                    variables=[],
                    code_lines=[]
                ))
            else:
                # 尝试匹配简化格式如 OB1, FB1, FC1, DB1
                simple_block_match = re.match(r'^(OB|FB|FC|DB)(\d+)\s*$', line, re.IGNORECASE)
                if simple_block_match:
                    block_type = simple_block_match.group(1).upper()
                    block_num = int(simple_block_match.group(2))
                    block_name = f"{block_type}{block_num}"
                    current_block_name = block_name
                    
                    self.blocks.append(CodeBlock(
                        block_type=block_type,
                        block_number=block_num,
                        block_name=block_name,
                        variables=[],
                        code_lines=[]
                    ))

            i += 1

    def _parse_variable_line(self, line: str, block_type: str, block_name: str, line_num: int) -> Optional[Variable]:
        """解析单行变量声明"""
        # 跳过注释和空行
        if line.startswith('//') or not line:
            return None

        # 移除行尾注释
        code_part = line.split('//')[0].strip()
        if not code_part:
            return None

        # 解析格式: 变量名 AT 地址 : 类型 := 初始值 ; 注释
        # 或简化格式: 变量名 : 类型 ; 注释

        # 尝试匹配完整格式
        full_pattern = r'^(\w+)\s+(?:AT\s+(\S+)\s*)?:\s*(\w+)(?:\s*:=\s*([^;]+))?\s*;'
        match = re.match(full_pattern, code_part, re.IGNORECASE)

        if not match:
            # 尝试匹配简化格式（无分号）
            simple_pattern = r'^(\w+)\s+(?:AT\s+(\S+)\s*)?:\s*(\w+)(?:\s*:=\s*(.+))?$'
            match = re.match(simple_pattern, code_part, re.IGNORECASE)

        if not match:
            # 尝试匹配特殊功能块实例化
            fb_pattern = r'^(\w+)\s*:\s*(TON|TOF|TP|TONR|CTU|CTD|CTUD)(?:\s*:=\s*(.+))?$'
            fb_match = re.match(fb_pattern, code_part, re.IGNORECASE)
            if fb_match:
                var_name = fb_match.group(1)
                fb_type = fb_match.group(2).upper()
                initial = fb_match.group(3).strip() if fb_match.group(3) else None

                return Variable(
                    name=var_name,
                    data_type=fb_type,
                    address=None,  # 定时器/计数器地址由系统分配
                    block_name=block_name,
                    block_type=block_type,
                    description=f'{fb_type} 功能块实例',
                    initial_value=initial,
                    line_number=line_num
                )
            return None

        var_name = match.group(1)
        address = match.group(2)
        data_type = match.group(3).upper()
        initial_value = match.group(4).strip() if match.group(4) else None

        # 验证数据类型
        if data_type not in self.DATA_TYPES and data_type not in self.SPECIAL_BLOCKS:
            # 可能是自定义类型或功能块
            pass

        return Variable(
            name=var_name,
            data_type=data_type,
            address=address,
            block_name=block_name,
            block_type=block_type,
            description=None,
            initial_value=initial_value,
            line_number=line_num
        )

    def _parse_code_blocks(self, lines: List[str]):
        """解析代码块"""
        in_block = False
        in_code_section = False  # 是否在代码区域（BEGIN之后）
        current_block_lines = []
        current_block_idx = -1

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 检测块开始
            if re.match(r'^(ORGANIZATION_BLOCK|OB|FUNCTION_BLOCK|FB|FUNCTION|FC|DATA_BLOCK|DB)\s*\d*',
                       stripped, re.IGNORECASE):
                in_block = True
                in_code_section = False
                current_block_lines = [line]
                # 找到对应的块索引
                for idx, block in enumerate(self.blocks):
                    if stripped.upper().find(block.block_name.upper()) >= 0 or block.block_name in stripped:
                        current_block_idx = idx
                        break
                if current_block_idx < 0 and self.blocks:
                    current_block_idx = len(self.blocks) - 1

            # 检测 BEGIN 关键字，进入代码区
            elif stripped.upper() == 'BEGIN' and in_block:
                in_code_section = True
                current_block_lines.append(line)

            # 检测块结束（END_ORGANIZATION_BLOCK, END_FUNCTION_BLOCK 等）
            elif stripped.upper().startswith('END_ORGANIZATION') or \
                 stripped.upper().startswith('END_FUNCTION') or \
                 stripped.upper().startswith('END_DATA') or \
                 stripped.upper() in ['END_ORGANIZATION_BLOCK', 'END_FUNCTION_BLOCK', 'END_FUNCTION', 'END_DATA_BLOCK']:
                current_block_lines.append(line)
                if current_block_idx >= 0 and current_block_idx < len(self.blocks):
                    self.blocks[current_block_idx].code_lines = current_block_lines
                in_block = False
                in_code_section = False
                current_block_lines = []

            elif in_block:
                current_block_lines.append(line)

    def _extract_implicit_addresses(self):
        """从代码中提取隐式地址引用"""
        # 扫描所有代码行，查找地址引用
        all_code = ' '.join([line for block in self.blocks for line in block.code_lines])

        # 有效地址模式 - 只匹配标准 PLC 地址格式
        address_patterns = [
            (r'\b(I|Q|M)(\d+)\.(\d+)\b', 'BOOL', True),      # I0.0, Q0.0, M0.0 (有位地址)
            (r'\b(I|Q|M)B(\d+)\b', 'BYTE', False),           # IB0, QB0, MB0
            (r'\b(I|Q|M)W(\d+)\b', 'WORD', False),           # IW0, QW0, MW0
            (r'\b(I|Q|M)D(\d+)\b', 'DWORD', False),          # ID0, QD0, MD0
            (r'\bV(\d+)\.(\d+)\b', 'BOOL', True),            # V0.0
            (r'\bVB(\d+)\b', 'BYTE', False),                 # VB0
            (r'\bVW(\d+)\b', 'WORD', False),                 # VW0
            (r'\bVD(\d+)\b', 'DWORD', False),                # VD0
            (r'\bT(\d+)\b', 'TIMER', False),                 # T0 (定时器)
            (r'\bC(\d+)\b', 'COUNTER', False),               # C0 (计数器)
            (r'\bSM(\d+)\.(\d+)\b', 'BOOL', True),           # SM0.0 (特殊存储器)
            (r'\bSMB(\d+)\b', 'BYTE', False),                # SMB0
            (r'\bSMW(\d+)\b', 'WORD', False),                # SMW0
            (r'\bSMD(\d+)\b', 'DWORD', False),               # SMD0
            (r'\bAIW(\d+)\b', 'WORD', False),                # AIW0 (模拟输入)
            (r'\bAQW(\d+)\b', 'WORD', False),                # AQW0 (模拟输出)
            (r'\bHC(\d+)\b', 'DINT', False),                 # HC0 (高速计数器)
            (r'\bAC(\d+)\b', 'DWORD', False),                # AC0 (累加器)
            (r'\bL(\d+)\.(\d+)\b', 'BOOL', True),            # L0.0 (局部变量)
            (r'\bLB(\d+)\b', 'BYTE', False),                 # LB0
            (r'\bLW(\d+)\b', 'WORD', False),                 # LW0
            (r'\bLD(\d+)\b', 'DWORD', False),                # LD0
        ]

        for pattern, data_type, has_bit in address_patterns:
            matches = re.findall(pattern, all_code, re.IGNORECASE)
            for match in matches:
                # 构建地址字符串
                if isinstance(match, tuple):
                    if has_bit:
                        # 位地址格式: I0.0, Q0.0 等
                        addr_str = f"{match[0]}{match[1]}.{match[2]}"
                    else:
                        # 字节/字/双字地址格式: I0, Q0, VW0 等
                        addr_str = ''.join([str(p) for p in match if p])
                else:
                    addr_str = match

                # 验证地址格式有效性
                if not self._is_valid_address(addr_str):
                    continue

                # 检查是否已存在此地址的变量
                existing = [v for v in self.variables if v.address and v.address.upper() == addr_str.upper()]
                if not existing:
                    # 创建隐式变量
                    self.variables.append(Variable(
                        name=f"_IMPLICIT_{addr_str.replace('.', '_')}",
                        data_type=data_type,
                        address=addr_str.upper(),
                        block_name='IMPLICIT',
                        block_type='CODE',
                        description='从代码中自动提取',
                        initial_value=None,
                        line_number=None
                    ))

    def _is_valid_address(self, address: str) -> bool:
        """验证地址格式是否有效"""
        if not address:
            return False
        
        addr = address.upper().strip()
        
        # 有效地址格式: I/Q/M/V + 数字(位地址可带.数字), 或特殊寄存器
        valid_patterns = [
            r'^[IQM]\d+\.\d+$',      # I0.0, Q0.0, M0.0
            r'^[IQM]B?\d+$',          # I0, IB0, Q0, QB0, M0, MB0
            r'^[IQM][WD]\d+$',        # IW0, QW0, MW0, ID0, QD0, MD0
            r'^V\d+\.\d+$',           # V0.0
            r'^V[BWD]?\d+$',          # V0, VB0, VW0, VD0
            r'^T\d+$',                # T0 (定时器)
            r'^C\d+$',                # C0 (计数器)
            r'^SM\d+\.\d+$',          # SM0.0
            r'^SM[BWD]?\d+$',         # SM0, SMB0, SMW0, SMD0
            r'^AIW\d+$',              # AIW0
            r'^AQW\d+$',              # AQW0
            r'^HC\d+$',               # HC0
            r'^AC\d+$',               # AC0
            r'^L\d+\.\d+$',           # L0.0
            r'^L[BWD]?\d+$',          # L0, LB0, LW0, LD0
        ]
        
        for pattern in valid_patterns:
            if re.match(pattern, addr):
                return True
        
        return False

    def _guess_type_from_address(self, address: str) -> str:
        """根据地址猜测数据类型"""
        address = address.upper()

        if '.' in address and address[0] in 'IQMVS':
            return 'BOOL'
        elif address.startswith(('IB', 'QB', 'MB', 'VB', 'SMB', 'LB')):
            return 'BYTE'
        elif address.startswith(('IW', 'QW', 'MW', 'VW', 'SMW', 'LW', 'AIW', 'AQW')):
            return 'WORD'
        elif address.startswith(('ID', 'QD', 'MD', 'VD', 'SMD', 'LD')):
            return 'DWORD'
        elif address.startswith('T'):
            return 'TIMER'
        elif address.startswith('C'):
            return 'COUNTER'
        elif address.startswith('HC'):
            return 'DINT'
        elif address.startswith('AC'):
            return 'DWORD'
        else:
            return 'UNKNOWN'

    def _count_by_type(self) -> Dict[str, int]:
        """按类型统计变量"""
        counts = {}
        for var in self.variables:
            counts[var.data_type] = counts.get(var.data_type, 0) + 1
        return counts

    def _count_by_block(self) -> Dict[str, int]:
        """按代码块统计变量"""
        counts = {}
        for var in self.variables:
            counts[var.block_name] = counts.get(var.block_name, 0) + 1
        return counts


def parse_stl(content: str) -> List[Dict]:
    """
    解析 STL 内容并返回变量列表

    Args:
        content: STL 程序文本

    Returns:
        变量字典列表
    """
    parser = STLParser()
    result = parser.parse(content)
    return result['variables']


def parse_stl_file(file_path: str) -> Dict:
    """
    解析 STL 文件

    Args:
        file_path: STL 文件路径

    Returns:
        解析结果字典
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    parser = STLParser()
    return parser.parse(content)


# 测试代码
if __name__ == '__main__':
    # 示例 STL 代码
    sample_stl = """
    ORGANIZATION_BLOCK MAIN:OB1
    TITLE=主程序

    VAR
        StartButton AT I0.0 : BOOL;    // 启动按钮
        StopButton AT I0.1 : BOOL;     // 停止按钮
        MotorOutput AT Q0.0 : BOOL;    // 电机输出
        Temperature AT IW64 : INT;     // 温度值
        SetPoint : INT := 100;         // 设定值
        RunTimer : TON;                // 运行定时器
        Counter1 : CTU;                // 计数器
    END_VAR

    BEGIN
    NETWORK 1
    LD     StartButton
    O      MotorOutput
    AN     StopButton
    =      MotorOutput

    NETWORK 2
    LD     MotorOutput
    =      Q0.1

    END_ORGANIZATION_BLOCK
    """

    parser = STLParser()
    result = parser.parse(sample_stl)

    print("=== 解析结果 ===")
    print(f"总变量数: {result['stats']['total_variables']}")
    print(f"总代码块数: {result['stats']['total_blocks']}")
    print(f"\n按类型统计: {result['stats']['variables_by_type']}")
    print(f"\n变量列表:")
    for var in result['variables']:
        print(f"  - {var['name']}: {var['data_type']} @ {var['address']}")
