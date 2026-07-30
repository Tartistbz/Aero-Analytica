import pandas as pd
import numpy as np
from pymavlink import mavutil
from .parser_base import ParserBase

class ArduPilotParser(ParserBase):
    """
    [Aero-Analytica] ArduPilot 动态解析器
    专门针对 DFReader_binary 进行优化，支持全字段扫描。
    """

    def __init__(self, file_path):
        super().__init__(file_path)
        self.MODE_MAP = {
            0: 'Stabilize', 1: 'Acro', 2: 'AltHold', 3: 'Auto', 4: 'Guided',
            5: 'Loiter', 6: 'RTL', 7: 'Circle', 9: 'Land', 16: 'PosHold',
            17: 'Brake', 21: 'Smart_RTL', 23: 'Follow'
        }

    def list_all_fields(self) -> dict:
        """
        核心修复：通过 fmt.name 获取消息字符串，而不是使用字典的 Key。
        """
        print(f"[Debug] 正在深度扫描 {self.file_path} 的格式定义...")
        mlog = mavutil.mavlink_connection(self.file_path)
        
        fields_map = {}
        # 扫描前 3000 条消息以确保读到 FMT 定义
        for i in range(3000):
            msg = mlog.recv_msg()
            if msg is None: break
            
            # 获取格式字典 (针对 .bin 文件使用 formats 属性)
            formats = getattr(mlog, 'formats', getattr(mlog, 'fmt', {}))
            
            if formats:
                for msg_id, fmt in formats.items():
                    # --- 关键修复点：从 fmt 对象中提取真正的名字 ---
                    msg_name = getattr(fmt, 'name', None)
                    if not msg_name: continue
                    
                    msg_name = str(msg_name)
                    if msg_name not in fields_map:
                        # 过滤掉元数据消息
                        if msg_name.isupper() and msg_name not in ['FMT', 'UNIT', 'MULT', 'FORMAT', 'PARM', 'MSG']:
                            # 获取该消息的所有字段列名
                            fields_map[msg_name] = getattr(fmt, 'columns', [])
                
                # 如果已经扫描到足够多的数据类型，提前结束以节省时间
                if len(fields_map) > 40:
                    break

        print(f"[Debug] 扫描结束，发现 {len(fields_map)} 种有效格式。")
        return fields_map

    def get_custom_dataframe(self, field_mapping: dict) -> pd.DataFrame:
        """
        按需动态提取数据。
        """
        mlog = mavutil.mavlink_connection(self.file_path)
        data_rows = []
        target_types = list(field_mapping.keys())
        
        if 'MODE' not in target_types:
            target_types.append('MODE')

        while True:
            msg = mlog.recv_match(type=target_types, blocking=False)
            if msg is None: break
            
            m_type = msg.get_type()
            # 统一提取微秒级时间戳并转为秒
            t_us = getattr(msg, 'TimeUS', getattr(msg, 'GWkMS', 0))
            row = {'timestamp': t_us / 1e6}
            
            if m_type in field_mapping:
                for f in field_mapping[m_type]:
                    # 命名规范：消息名_字段名
                    row[f"{m_type}_{f}"] = getattr(msg, f, np.nan)
            
            if m_type == 'MODE':
                m_val = getattr(msg, 'ModeNum', getattr(msg, 'Mode', None))
                if isinstance(m_val, (int, float)):
                    row['mode'] = self.MODE_MAP.get(int(m_val), f"Mode {int(m_val)}").upper()
                else:
                    row['mode'] = str(m_val).upper()

            data_rows.append(row)
            
        df = pd.DataFrame(data_rows)
        if not df.empty:
            # 核心：按时间对齐并填充，确保跨消息分析的准确性
            df = df.sort_values('timestamp').ffill()
        return df
