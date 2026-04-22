import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from .utils.text_cleaner import EncodingConverter


@dataclass
class LogEntry:
    timestamp: Optional[str]
    level: str
    source: str
    message: str
    raw_line: str
    line_number: int


class LogParser:
    COMMON_PATTERNS = [
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.:]\d{3})\s+\[?(\w+)\]?\s+\[?(\w+)\]?\s*[-:]?\s*(.*)',
        r'\[(\d{2}:\d{2}:\d{2})\]\s+\[?(\w+)\]?\s+\[?(\w+)\]?\s*[-:]?\s*(.*)',
        r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.*)',
        r'<(\w+)>\s*(\w+)\s*:\s*(.*)',
    ]

    PROTOCOL_KEYWORDS = [
        'send', 'recv', 'tx', 'rx', 'packet', 'frame', 'cmd', 'ack', 'nack',
        'connect', 'disconnect', 'publish', 'subscribe', 'BLE', 'CAN', 'MQTT',
        'dp_', 'data_point', 'payload', 'protocol', '0x', 'frame_id'
    ]

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.entries: List[LogEntry] = []
        self.detected_format = None

    def parse_file(self, file_path: str) -> List[LogEntry]:
        entries = []
        encoding, content = EncodingConverter.convert_file(file_path)
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            parsed = self._parse_line(line, i)
            entries.append(parsed)

        if entries:
            self.entries.extend(entries)
            self._detect_format(file_path)

        return entries

    def _parse_line(self, line: str, line_number: int) -> LogEntry:
        for pattern in self.COMMON_PATTERNS:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    return LogEntry(
                        timestamp=groups[0],
                        level=groups[1] if groups[1] else "INFO",
                        source=groups[2] if groups[2] else "unknown",
                        message=groups[3],
                        raw_line=line,
                        line_number=line_number
                    )

        return LogEntry(
            timestamp=None,
            level=self._detect_level(line),
            source="unknown",
            message=line,
            raw_line=line,
            line_number=line_number
        )

    def _detect_level(self, line: str) -> str:
        upper = line.upper()
        if any(k in upper for k in ['ERROR', 'ERR', 'FAIL']):
            return "ERROR"
        elif any(k in upper for k in ['WARN', 'WARNING']):
            return "WARN"
        elif any(k in upper for k in ['DEBUG', 'DBG']):
            return "DEBUG"
        return "INFO"

    def _detect_format(self, file_path: str):
        if self.entries:
            sample = self.entries[0]
            self.detected_format = f"{file_path}: format={sample.timestamp}~{sample.level}"

    def parse_directory(self) -> List[LogEntry]:
        all_entries = []
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.log', '.txt')) or 'log' in file.lower():
                    file_path = os.path.join(root, file)
                    try:
                        entries = self.parse_file(file_path)
                        all_entries.extend(entries)
                    except Exception as e:
                        print(f"Error parsing {file_path}: {e}")
        return all_entries

    def get_protocol_entries(self) -> List[LogEntry]:
        return [
            e for e in self.entries
            if any(k in e.message.upper() for k in [k.upper() for k in self.PROTOCOL_KEYWORDS])
            or any(k in e.raw_line.upper() for k in [k.upper() for k in self.PROTOCOL_KEYWORDS])
        ]

    def group_by_conversation(self, time_threshold_seconds: float = 5.0) -> List[List[LogEntry]]:
        if not self.entries:
            return []

        groups = []
        current_group = [self.entries[0]]

        for i in range(1, len(self.entries)):
            if self.entries[i].timestamp and current_group[-1].timestamp:
                try:
                    t1 = self._parse_timestamp(current_group[-1].timestamp)
                    t2 = self._parse_timestamp(self.entries[i].timestamp)
                    if t2 and t1 and (t2 - t1).total_seconds() <= time_threshold_seconds:
                        current_group.append(self.entries[i])
                    else:
                        groups.append(current_group)
                        current_group = [self.entries[i]]
                except:
                    groups.append(current_group)
                    current_group = [self.entries[i]]
            else:
                current_group.append(self.entries[i])

        if current_group:
            groups.append(current_group)

        return groups

    def _parse_timestamp(self, ts: str):
        formats = [
            '%Y-%m-%d %H:%M:%S,%f',
            '%Y-%m-%d %H:%M:%S.%f',
            '%H:%M:%S',
            '%Y/%m/%d %H:%M:%S'
        ]
        for fmt in formats:
            try:
                return datetime.strptime(ts, fmt)
            except:
                continue
        return None

    def export_to_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": f"log:{entry.line_number}",
                "type": "log_entry",
                "timestamp": entry.timestamp,
                "level": entry.level,
                "source": entry.source,
                "message": entry.message,
                "raw_line": entry.raw_line,
                "line_number": entry.line_number,
                "source_file": "log"
            }
            for entry in self.entries
        ]